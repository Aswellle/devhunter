"""
scripts/eval_recommendation.py
推荐管线离线评测基准：用人工标注的 gold 集合衡量当前排序质量。

用法（在 backend/ 目录下运行）：

    # 1) 生成 gold：把推荐结果前 50 条逐条标注（relevant=1 该出现 / 0 不该出现）
    #    写入 .data/rec-gold.jsonl（每行一个 JSON，不入 Git）
    # 2) 跑评测（对当前管线的真实排序计算指标）：
    python scripts/eval_recommendation.py --gold .data/rec-gold.jsonl --label "基线"
    # 快速回归（零标注成本）：用「已收藏」条目当相关集
    # 注意：收藏行为本身是管线的输入信号，指标偏乐观，只用于版本间对比
    python scripts/eval_recommendation.py --from-stars --label "收藏回归"

参数：
    --gold PATH     gold 标注文件（JSONL：{"item_id": "...", "relevant": 0|1}）
    --from-stars    用已收藏条目构造相关集（与 --gold 二选一）
    --limit N       参与排序考察的推荐条数（默认 50）
    --label NAME    版本标签（输出用）
    --json PATH     结果存为 JSON（版本间对比）

只读运行：不写库、不调 LLM、不产生费用。
调参原则：先改评分标准/权重，再看指标；不要对着单次指标过拟合。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# 让 scripts/ 目录下可以直接 import app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(Path(__file__).resolve().parent.parent)

from app.core.database import get_db  # noqa: E402
from app.recommendation.eval_metrics import (  # noqa: E402
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from app.services.recommendation_service import recommendation_service  # noqa: E402


def load_gold(path: str) -> tuple[set[str], set[str]]:
    """读取 gold 标注，返回 (relevant_ids, not_relevant_ids)"""
    relevant: set[str] = set()
    not_relevant: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                raise SystemExit(f"gold 文件第 {line_no} 行不是合法 JSON: {e}")
            item_id = record.get("item_id")
            if not item_id:
                raise SystemExit(f"gold 文件第 {line_no} 行缺少 item_id")
            (relevant if record.get("relevant") else not_relevant).add(item_id)
    return relevant, not_relevant


def starred_ids() -> set[str]:
    """已收藏条目 ID（零标注成本的快速回归相关集）"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM items WHERE is_starred = 1"
        ).fetchall()
    return {r["id"] for r in rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="推荐管线离线评测基准")
    parser.add_argument("--gold", help="gold 标注文件（JSONL）")
    parser.add_argument("--from-stars", action="store_true", help="用已收藏条目当相关集")
    parser.add_argument("--limit", type=int, default=50, help="考察的推荐条数")
    parser.add_argument("--label", default="unlabeled", help="版本标签")
    parser.add_argument("--json", dest="json_out", help="结果存为 JSON 文件")
    args = parser.parse_args()

    if not args.gold and not args.from_stars:
        parser.error("需要 --gold 或 --from-stars 之一")

    if args.gold:
        relevant, not_relevant = load_gold(args.gold)
        source = "gold"
    else:
        relevant, not_relevant = starred_ids(), set()
        source = "stars"

    if not relevant:
        print("相关集为空：gold 里没有 relevant=1 的条目（或没有收藏）。无法评测。")
        sys.exit(1)

    ranked = recommendation_service.get_recommended_items(limit=args.limit, exclude_read=True)
    ranked_ids = [it["id"] for it in ranked]

    ks = [k for k in (5, 10, 20) if k <= args.limit] or [args.limit]
    report = {
        "label": args.label,
        "source": source,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": args.limit,
        "relevant_count": len(relevant),
        "ranked_count": len(ranked_ids),
        "metrics": {
            f"p@{k}": round(precision_at_k(ranked_ids, relevant, k), 4) for k in ks
        } | {
            f"r@{k}": round(recall_at_k(ranked_ids, relevant, k), 4) for k in ks
        } | {
            f"ndcg@{k}": round(ndcg_at_k(ranked_ids, relevant, k), 4) for k in ks
        },
        "not_relevant_in_top10": sum(
            1 for item_id in ranked_ids[:10] if item_id in not_relevant
        ) if not_relevant else None,
        "missed_relevant": len(relevant - set(ranked_ids)),
    }

    print(f"── 推荐评测（{args.label}）")
    print(f"相关集来源: {source} | 相关 {len(relevant)} 条 | 排序输出 {len(ranked_ids)} 条")
    for k in ks:
        print(
            f"  @{k:<3} P={report['metrics'][f'p@{k}']:.3f} "
            f"R={report['metrics'][f'r@{k}']:.3f} "
            f"NDCG={report['metrics'][f'ndcg@{k}']:.3f}"
        )
    if not_relevant:
        print(f"  前 10 位中的不相关条目: {report['not_relevant_in_top10']}")
    print(f"  未进入排序的相关条目: {report['missed_relevant']}（候选未覆盖或被过滤）")
    if source == "stars":
        print("  ⚠ 收藏是管线的输入信号，指标偏乐观——仅用于版本间横向对比")

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"结果已写入 {args.json_out}")


if __name__ == "__main__":
    main()

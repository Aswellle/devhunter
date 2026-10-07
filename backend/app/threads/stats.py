"""
app/threads/stats.py
Thread 聚合画像：把 Thread 的组成数据翻译成可解释的统计。

回答"为什么聚为一个 Thread"的三件事：
1. 规模 —— 多少条报道、覆盖多少个平台
2. 活跃度 —— 近 24h / 近 6h 新增条目数
3. 可信度 —— 非种子条目的平均匹配置信度（跨平台共识 vs 同源重复）

纯函数、无 I/O：输入 thread dict + items 列表，输出 stats dict。
种子条目（创建 Thread 的第一条，thread_items.similarity 恒为 1.0）是
定义性数据而非证据，计算置信度时必须剔除——否则单条目的 Thread
会永远显示 100% 置信度。
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from app.threads.hotness import compute_hotness

# 与 threads/scoring.py 的 CONFIDENCE_THRESHOLDS 保持一致
CONFIDENCE_HIGH = 0.70
CONFIDENCE_MEDIUM = 0.45

SEED_MATCH_REASON = "initial_item"


def parse_iso_utc(value: str | None) -> datetime | None:
    """解析 ISO 时间字符串（兼容尾缀 Z 与无时区两种形态），失败返回 None。"""
    if not value:
        return None
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def confidence_label(avg_similarity: float | None) -> str | None:
    """平均匹配置信度 → high/medium/low 标签，无数据返回 None。"""
    if avg_similarity is None:
        return None
    if avg_similarity >= CONFIDENCE_HIGH:
        return "high"
    if avg_similarity >= CONFIDENCE_MEDIUM:
        return "medium"
    return "low"


def _resolve_seed_ids(items: list[dict]) -> set[str]:
    """
    识别种子条目。

    017 迁移之后创建的 Thread 种子带 match_reason='initial_item'；
    更早的旧数据没有该标记，此时按"最早的条目即种子"兜底
    （Thread 由第一条条目创建，见 thread_repo.create）。
    """
    seeds = {it["id"] for it in items if it.get("match_reason") == SEED_MATCH_REASON}
    if not seeds and items:
        earliest = min(items, key=lambda it: parse_iso_utc(it.get("fetched_at")) or datetime.max.replace(tzinfo=timezone.utc))
        seeds.add(earliest["id"])
    return seeds


def build_thread_stats(
    thread: dict,
    items: list[dict],
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    构建 Thread 聚合画像。

    Args:
        thread: threads 表行 dict（使用 first_seen_at/last_seen_at）
        items: get_items_in_thread 返回的条目列表（含 similarity/match_reason/task_name）
        now: 当前时间（可注入以便测试），默认 UTC now

    Returns:
        stats dict，字段全部可选缺失安全（空 items 也能得到合法结构）。
    """
    now = now or datetime.now(timezone.utc)
    cutoff_6h = now - timedelta(hours=6)
    cutoff_24h = now - timedelta(hours=24)

    # 平台分布（task_name 即来源平台名，与 thread.platforms 的口径一致）
    platform_counts: Counter[str] = Counter()
    platform_latest: dict[str, str | None] = {}
    recent_6h = 0
    recent_24h = 0
    for it in items:
        platform_name = str(it.get("task_name") or "unknown")
        platform_counts[platform_name] += 1
        fetched_raw = it.get("fetched_at")
        fetched = parse_iso_utc(fetched_raw)
        # 各平台最新条目时间（热度口径：唯一来源计数 + 24h 半衰期）
        prev = parse_iso_utc(platform_latest.get(platform_name))
        if fetched and (prev is None or fetched > prev):
            platform_latest[platform_name] = fetched_raw
        if fetched and fetched >= cutoff_24h:
            recent_24h += 1
            if fetched >= cutoff_6h:
                recent_6h += 1

    # 匹配置信度：剔除种子条目
    seed_ids = _resolve_seed_ids(items)
    joined_similarities = [
        float(it["similarity"])
        for it in items
        if it["id"] not in seed_ids and it.get("similarity") is not None
    ]
    similarity_avg = (
        round(sum(joined_similarities) / len(joined_similarities), 4)
        if joined_similarities
        else None
    )
    similarity_max = (
        round(max(joined_similarities), 4) if joined_similarities else None
    )

    # 时间跨度
    first = parse_iso_utc(thread.get("first_seen_at"))
    last = parse_iso_utc(thread.get("last_seen_at"))
    span_hours: float | None = None
    if first and last and last >= first:
        span_hours = round((last - first).total_seconds() / 3600, 1)

    return {
        "item_count": len(items),
        "platform_count": len(platform_counts),
        "platform_breakdown": [
            {"platform": p, "count": c}
            for p, c in platform_counts.most_common()
        ],
        "recent_6h_count": recent_6h,
        "recent_24h_count": recent_24h,
        "span_hours": span_hours,
        "matched_item_count": len(joined_similarities),
        "similarity_avg": similarity_avg,
        "similarity_max": similarity_max,
        "confidence": confidence_label(similarity_avg),
        "is_cross_platform": len(platform_counts) > 1,
        "hotness": compute_hotness(platform_latest, now=now),
    }

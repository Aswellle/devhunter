"""
app/repositories/relevance_repo.py
relevance_labels 表的数据访问层：推荐质量金标。

每条 item 至多一条标注（UNIQUE 约束），重复提交视为改判（upsert 覆盖）。
sampled_score 是采样时的推荐得分快照，指标据此计算。
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.database import get_db

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RelevanceLabelRepository:

    def upsert(self, item_id: str, label: bool, sampled_score: float | None) -> dict[str, Any]:
        """记录/改判一条标注，返回落库后的完整行"""
        now = _now_iso()
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO relevance_labels (id, item_id, label, sampled_score, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (item_id) DO UPDATE SET
                    label = excluded.label,
                    sampled_score = excluded.sampled_score,
                    updated_at = excluded.updated_at
                """,
                (str(uuid.uuid4()), item_id, 1 if label else 0, sampled_score, now, now),
            )
            row = conn.execute(
                "SELECT * FROM relevance_labels WHERE item_id = ?",
                (item_id,),
            ).fetchone()
        result = dict(row)
        result["label"] = bool(result["label"])
        return result

    def get_labeled_item_ids(self) -> set[str]:
        """全部已打标的 item_id（采样时排除）"""
        with get_db() as conn:
            rows = conn.execute("SELECT item_id FROM relevance_labels").fetchall()
        return {r["item_id"] for r in rows}

    def summary(self) -> dict[str, int]:
        """标注计数汇总：{total, positive, negative}"""
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(label), 0) AS positive
                FROM relevance_labels
                """
            ).fetchone()
        positive = int(row["positive"] or 0)
        total = int(row["total"] or 0)
        return {"total": total, "positive": positive, "negative": total - positive}

    def list_scores(self) -> list[tuple[float, int]]:
        """
        全部 (sampled_score, label) 对（label: 1=感兴趣 0=不感兴趣）。

        供排序贴合度（win_rate）计算；快照得分为 NULL 的早期标注不参与。
        """
        with get_db() as conn:
            rows = conn.execute(
                "SELECT sampled_score, label FROM relevance_labels "
                "WHERE sampled_score IS NOT NULL"
            ).fetchall()
        return [(float(r["sampled_score"]), int(r["label"])) for r in rows]


# 全局单例
relevance_label_repo = RelevanceLabelRepository()

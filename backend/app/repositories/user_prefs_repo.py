"""
app/repositories/user_prefs_repo.py
用户偏好与行为追踪的数据访问层
"""
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.database import get_db

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


class UserTopicsRepository:

    def upsert(self, topic: str, category: str = "custom", weight: float = 1.0) -> dict:
        """创建或更新用户主题偏好"""
        topic_id = str(uuid.uuid4())
        now = _now_iso()
        with get_db() as conn:
            # 尝试查找已存在
            existing = conn.execute(
                "SELECT id FROM user_topics WHERE topic = ?",
                (topic,),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE user_topics SET weight = ?, category = ?, updated_at = ? WHERE topic = ?",
                    (weight, category, now, topic),
                )
                return self.get_by_topic(topic)
            conn.execute(
                """
                INSERT INTO user_topics (id, topic, category, weight, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (topic_id, topic, category, weight, now, now),
            )
        return self.get_by_topic(topic)

    def get_by_topic(self, topic: str) -> dict | None:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM user_topics WHERE topic = ?",
                (topic,),
            ).fetchone()
        return _row_to_dict(row) if row else None

    def list_all(self, category: str | None = None) -> list[dict]:
        """列出所有用户主题偏好"""
        with get_db() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM user_topics WHERE category = ? ORDER BY weight DESC, created_at DESC",
                    (category,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM user_topics ORDER BY weight DESC, created_at DESC",
                ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def delete(self, topic_id: str) -> bool:
        with get_db() as conn:
            cursor = conn.execute("DELETE FROM user_topics WHERE id = ?", (topic_id,))
        return cursor.rowcount > 0

    def delete_by_topic(self, topic: str) -> bool:
        with get_db() as conn:
            cursor = conn.execute("DELETE FROM user_topics WHERE topic = ?", (topic,))
        return cursor.rowcount > 0

    def get_all_topics_with_weights(self) -> list[tuple[str, float]]:
        """获取所有主题及其权重，返回 [(topic, weight)]"""
        rows = self.list_all()
        return [(r["topic"], r["weight"]) for r in rows]


class UserInteractionRepository:

    def record(
        self,
        item_id: str,
        interaction_type: str,
        dwell_seconds: int | None = None,
    ) -> dict:
        """记录一次用户交互，返回完整记录"""
        interaction_id = str(uuid.uuid4())
        now = _now_iso()
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO user_interactions (id, item_id, interaction_type, dwell_seconds, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (interaction_id, item_id, interaction_type, dwell_seconds, now),
            )
        return {
            "id": interaction_id,
            "item_id": item_id,
            "interaction_type": interaction_type,
            "dwell_seconds": dwell_seconds,
            "created_at": now,
        }

    def get_item_interactions(self, item_id: str) -> list[dict]:
        """获取某条目的所有交互"""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM user_interactions WHERE item_id = ? ORDER BY created_at DESC",
                (item_id,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_recent_interactions(
        self,
        interaction_type: str | None = None,
        hours: int = 24,
        limit: int = 100,
    ) -> list[dict]:
        """获取最近交互记录"""
        with get_db() as conn:
            if interaction_type:
                rows = conn.execute(
                    f"""
                    SELECT * FROM user_interactions
                    WHERE interaction_type = ?
                      AND created_at > datetime('now', '-{hours} hours')
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (interaction_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT * FROM user_interactions
                    WHERE created_at > datetime('now', '-{hours} hours')
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_user_engagement_stats(self, item_id: str) -> dict:
        """获取某条目的用户参与度统计"""
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total_interactions,
                    SUM(CASE WHEN interaction_type = 'view' THEN 1 ELSE 0 END) as view_count,
                    SUM(CASE WHEN interaction_type = 'dwell' THEN 1 ELSE 0 END) as dwell_count,
                    SUM(CASE WHEN interaction_type = 'star' THEN 1 ELSE 0 END) as star_count,
                    SUM(CASE WHEN interaction_type = 'click' THEN 1 ELSE 0 END) as click_count,
                    AVG(CASE WHEN dwell_seconds IS NOT NULL THEN dwell_seconds ELSE 0 END) as avg_dwell_seconds
                FROM user_interactions
                WHERE item_id = ?
                """,
                (item_id,),
            ).fetchone()
        return _row_to_dict(row) if row else {}


class UserAffinityRepository:

    def update_affinity(
        self,
        affinity_type: str,
        affinity_value: str,
        score_delta: float,
        interaction_increment: int = 1,
    ) -> None:
        """
        更新用户亲缘度得分。
        affinity_type: 'task' | 'platform' | 'keyword'
        score_delta: 本次交互增加的得分（会被衰减）
        """
        now = _now_iso()
        with get_db() as conn:
            existing = conn.execute(
                "SELECT * FROM user_topic_affinity WHERE affinity_type = ? AND affinity_value = ?",
                (affinity_type, affinity_value),
            ).fetchone()

            if existing:
                # 指数衰减更新：new_score = old_score * decay + delta
                decay = 0.9  # 每次交互衰减10%
                new_score = existing["affinity_score"] * decay + score_delta * (1 - decay)
                new_score = min(1.0, max(0.0, new_score))  # 限制在 0-1
                new_count = existing["interaction_count"] + interaction_increment
                conn.execute(
                    """
                    UPDATE user_topic_affinity
                    SET affinity_score = ?, interaction_count = ?, last_interacted_at = ?, updated_at = ?
                    WHERE affinity_type = ? AND affinity_value = ?
                    """,
                    (new_score, new_count, now, now, affinity_type, affinity_value),
                )
            else:
                affinity_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO user_topic_affinity (id, affinity_type, affinity_value, affinity_score, interaction_count, last_interacted_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (affinity_id, affinity_type, affinity_value, score_delta, interaction_increment, now, now),
                )

    def get_top_affinities(self, affinity_type: str | None = None, limit: int = 20) -> list[dict]:
        """获取最高亲缘度的主题/任务/平台"""
        with get_db() as conn:
            if affinity_type:
                rows = conn.execute(
                    """
                    SELECT * FROM user_topic_affinity
                    WHERE affinity_type = ?
                    ORDER BY affinity_score DESC
                    LIMIT ?
                    """,
                    (affinity_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM user_topic_affinity
                    ORDER BY affinity_score DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_affinity_score(self, affinity_type: str, affinity_value: str) -> float:
        """获取特定亲缘度得分"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT affinity_score FROM user_topic_affinity WHERE affinity_type = ? AND affinity_value = ?",
                (affinity_type, affinity_value),
            ).fetchone()
        return row["affinity_score"] if row else 0.0

    def get_all_affinities_map(self) -> dict[str, float]:
        """获取所有亲缘度得分，映射为 {type:value -> score}"""
        rows = self.get_top_affinities(limit=100)
        return {f"{r['affinity_type']}:{r['affinity_value']}": r["affinity_score"] for r in rows}


class RecommendationConfigRepository:

    def get(self, key: str, default: float) -> float:
        with get_db() as conn:
            row = conn.execute(
                "SELECT value FROM recommendation_config WHERE key = ?",
                (key,),
            ).fetchone()
        return row["value"] if row else default

    def get_all(self) -> dict[str, float]:
        with get_db() as conn:
            rows = conn.execute("SELECT key, value FROM recommendation_config").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def set(self, key: str, value: float) -> None:
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO recommendation_config (key, value) VALUES (?, ?)",
                (key, value),
            )


# 全局单例
user_topics_repo = UserTopicsRepository()
user_interaction_repo = UserInteractionRepository()
user_affinity_repo = UserAffinityRepository()
recommendation_config_repo = RecommendationConfigRepository()

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
        """
        创建或更新用户主题偏好。

        D3: 原来的 SELECT-then-branch 非原子，两个并发请求可能同时读到
        existing=None 并都执行 INSERT，在 007 迁移补上 UNIQUE(topic) 索引后
        会导致其中一个抛出未处理的 IntegrityError。改为单条原子语句。
        """
        topic_id = str(uuid.uuid4())
        now = _now_iso()
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO user_topics (id, topic, category, weight, created_at, updated_at)
                VALUES (:id, :topic, :category, :weight, :now, :now)
                ON CONFLICT (topic) DO UPDATE SET
                    weight = :weight,
                    category = :category,
                    updated_at = :now
                """,
                {
                    "id": topic_id, "topic": topic, "category": category,
                    "weight": weight, "now": now,
                },
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

    def update_weight(self, topic: str, weight: float) -> bool:
        """更新主题权重，返回是否有行被更新"""
        now = _now_iso()
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE user_topics SET weight = ?, updated_at = ? WHERE topic = ?",
                (weight, now, topic),
            )
        return cursor.rowcount > 0


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
        """
        获取最近交互记录。

        D6: hours 原来通过 f-string 直接拼进 SQL 文本
        (f"datetime('now', '-{hours} hours')")；调用方目前固定传 int，
        但下一次接口改动就可能让它变成用户可控字符串，成为 SQL 注入面。
        改为参数化：datetime('now', ? || ' hours') 让 SQLite 在拼接
        modifier 字符串前先完成参数绑定，语义与原来完全一致。
        """
        neg_hours_modifier = f"-{int(hours)}"
        with get_db() as conn:
            if interaction_type:
                rows = conn.execute(
                    """
                    SELECT * FROM user_interactions
                    WHERE interaction_type = ?
                      AND created_at > datetime('now', ? || ' hours')
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (interaction_type, neg_hours_modifier, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM user_interactions
                    WHERE created_at > datetime('now', ? || ' hours')
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (neg_hours_modifier, limit),
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

    def get_engagement_stats_bulk(self, item_ids: list[str]) -> dict[str, dict]:
        """
        批量获取多条目的用户参与度统计，一次查询替代 N 次单条查询。
        返回 {item_id: stats_dict}；未出现在结果中的 item_id 表示无交互记录。
        """
        if not item_ids:
            return {}
        placeholders = ",".join(["?"] * len(item_ids))
        with get_db() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    item_id,
                    COUNT(*) as total_interactions,
                    SUM(CASE WHEN interaction_type = 'view' THEN 1 ELSE 0 END) as view_count,
                    SUM(CASE WHEN interaction_type = 'dwell' THEN 1 ELSE 0 END) as dwell_count,
                    SUM(CASE WHEN interaction_type = 'star' THEN 1 ELSE 0 END) as star_count,
                    SUM(CASE WHEN interaction_type = 'click' THEN 1 ELSE 0 END) as click_count,
                    AVG(CASE WHEN dwell_seconds IS NOT NULL THEN dwell_seconds ELSE 0 END) as avg_dwell_seconds
                FROM user_interactions
                WHERE item_id IN ({placeholders})
                GROUP BY item_id
                """,
                item_ids,
            ).fetchall()
        return {r["item_id"]: _row_to_dict(r) for r in rows}


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
        decay = 0.9  # 每次交互衰减10%
        # D1: single atomic INSERT ... ON CONFLICT DO UPDATE replaces the
        # previous SELECT-then-branch (INSERT or UPDATE). The old code let
        # two threads (APScheduler worker + FastAPI request thread) both
        # read existing=None for the same (affinity_type, affinity_value)
        # and both attempt INSERT, with the loser crashing on the UNIQUE
        # constraint (idx_affinity_unique) with an unhandled IntegrityError.
        # The UPDATE branch here references the table's OWN current column
        # values (not excluded.*, which would be the just-inserted delta),
        # so the decay formula still reads the pre-conflict score/count.
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO user_topic_affinity
                    (id, affinity_type, affinity_value, affinity_score,
                     interaction_count, last_interacted_at, updated_at)
                VALUES (:id, :affinity_type, :affinity_value, :score_delta,
                        :interaction_increment, :now, :now)
                ON CONFLICT (affinity_type, affinity_value) DO UPDATE SET
                    affinity_score = MIN(1.0, MAX(0.0,
                        user_topic_affinity.affinity_score * :decay
                        + :score_delta * (1 - :decay))),
                    interaction_count = user_topic_affinity.interaction_count + :interaction_increment,
                    last_interacted_at = :now,
                    updated_at = :now
                """,
                {
                    "id": str(uuid.uuid4()),
                    "affinity_type": affinity_type,
                    "affinity_value": affinity_value,
                    "score_delta": score_delta,
                    "interaction_increment": interaction_increment,
                    "decay": decay,
                    "now": now,
                },
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
        """
        获取所有亲缘度得分，映射为 {type:value -> score}。

        D8: 名为 get_all_ 却隐式截断到 100 行（get_top_affinities 的默认
        limit）；用户使用越久，distinct affinity_value（task_id/platform/
        keyword）越可能超过 100，导致推荐评分静默丢失部分亲缘度数据。
        这里用一个足够大的上限（10000）近似"全部"——真正的无界只能等
        表规模失控时再引入分页，目前的量级下 10000 足够覆盖。
        """
        rows = self.get_top_affinities(limit=10000)
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

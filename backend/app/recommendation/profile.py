"""
app/recommendation/profile.py
User Profile：用户兴趣画像。

R2: 时间衰减 — 亲缘度按时间指数衰减，旧行为不再永久等权。
decay = exp(-age_hours / half_life_hours)
"""
import logging
import math
from datetime import datetime, timezone
from typing import Any

from app.repositories.user_prefs_repo import (
    user_topics_repo,
    user_affinity_repo,
    user_interaction_repo,
)

logger = logging.getLogger(__name__)


def _hours_since(iso_date: str) -> float:
    """计算距离 ISO 日期的小时数"""
    if not iso_date:
        return 999.0
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except (ValueError, TypeError):
        return 999.0


class UserProfileBuilder:
    """用户画像构建器"""

    def build(self, user_id: str | None = None) -> dict[str, Any]:
        """
        构建用户画像。
        R2: 亲缘度按时间衰减，旧行为权重降低。
        """
        half_life = 72.0  # 默认半衰期 72 小时（3 天）

        profile: dict[str, Any] = {
            "topics": {},
            "entities": {},
            "formats": {},
            "sources": {},
            "freshness_preference": 0.5,
            "interacted_tasks": set(),
            "engagement_stats": {},
            "negative_feedback": {},  # R3: 负反馈集合
        }

        # 1. 主题偏好
        topics = user_topics_repo.get_all_topics_with_weights()
        profile["topics"] = {t["topic"]: t["weight"] for t in topics}

        # 2. 亲缘度（R2: 应用时间衰减）
        affinities = user_affinity_repo.get_all_affinities_map()
        decayed_affinities: dict[str, float] = {}
        for key, score in affinities.items():
            # 获取该亲缘度的最后交互时间
            last_interacted = user_affinity_repo.get_last_interacted_at(key)
            if last_interacted:
                age_hours = _hours_since(last_interacted)
                decay = math.exp(-age_hours / half_life)
                decayed_score = score * decay
                if decayed_score > 0.01:  # 过滤衰减到接近 0 的
                    decayed_affinities[key] = decayed_score
            else:
                decayed_affinities[key] = score
        profile["affinities"] = decayed_affinities

        # 3. 互动过的任务
        interactions = user_interaction_repo.get_all_interactions(limit=100)
        profile["interacted_tasks"] = {
            i.get("task_id") for i in interactions if i.get("task_id")
        }

        # 4. 参与度统计
        profile["engagement_stats"] = user_interaction_repo.get_engagement_stats_bulk(
            [i.get("item_id") for i in interactions if i.get("item_id")]
        )

        # R3: 负反馈集合
        profile["negative_feedback"] = user_interaction_repo.get_negative_feedback_map()

        return profile


# 全局单例
user_profile_builder = UserProfileBuilder()

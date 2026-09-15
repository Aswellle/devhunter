"""
app/recommendation/profile.py
User Profile：用户兴趣画像。

构建统一用户兴趣画像：
{
  "topics": {"AI": 0.93, "Rust": 0.74},
  "entities": {"OpenAI": 0.91, "Anthropic": 0.65},
  "formats": {"tutorial": 0.72, "release": 0.84},
  "sources": {"GitHub": 0.88, "HackerNews": 0.72},
  "freshness_preference": 0.81,
  "interacted_tasks": {"task_1", "task_2"},
  "engagement_stats": {"item_1": {"score": 0.5}},
}
"""
import logging
from typing import Any

from app.repositories.user_prefs_repo import (
    user_topics_repo,
    user_affinity_repo,
    user_interaction_repo,
)

logger = logging.getLogger(__name__)


class UserProfileBuilder:
    """用户画像构建器"""

    def build(self, user_id: str | None = None) -> dict[str, Any]:
        """
        构建用户画像。

        Args:
            user_id: 用户 ID（可选）

        Returns:
            用户画像 dict
        """
        profile: dict[str, Any] = {
            "topics": {},
            "entities": {},
            "formats": {},
            "sources": {},
            "freshness_preference": 0.5,
            "interacted_tasks": set(),
            "engagement_stats": {},
        }

        # 1. 主题偏好
        topics = user_topics_repo.get_all_topics_with_weights()
        profile["topics"] = {t["topic"]: t["weight"] for t in topics}

        # 2. 亲缘度
        affinities = user_affinity_repo.get_all_affinities_map()
        profile["affinities"] = affinities

        # 3. 互动过的任务
        interactions = user_interaction_repo.get_all_interactions(limit=100)
        profile["interacted_tasks"] = {
            i.get("task_id") for i in interactions if i.get("task_id")
        }

        # 4. 参与度统计
        profile["engagement_stats"] = user_interaction_repo.get_engagement_stats_bulk(
            [i.get("item_id") for i in interactions if i.get("item_id")]
        )

        return profile


# 全局单例
user_profile_builder = UserProfileBuilder()

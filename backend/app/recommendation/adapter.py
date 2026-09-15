"""
app/recommendation/adapter.py
Adaptive Recommendation：自适应推荐策略。

根据用户活跃度和行为模式动态调整推荐参数：
- exploration_ratio: 新用户更多探索，老用户更多个性化
- diversity_limits: 根据用户互动频率调整
- freshness_weight: 根据用户阅读习惯调整
"""
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class UserActivityProfile:
    """用户活跃度画像"""
    total_interactions: int = 0
    recent_interactions_7d: int = 0
    avg_daily_interactions: float = 0.0
    unique_tasks: int = 0
    unique_topics: int = 0
    account_age_days: int = 0

    @property
    def activity_level(self) -> str:
        """
        计算用户活跃度级别。

        Returns:
            'new' | 'casual' | 'regular' | 'power'
        """
        if self.account_age_days < 3 or self.total_interactions < 5:
            return "new"
        if self.avg_daily_interactions < 1:
            return "casual"
        if self.avg_daily_interactions < 5:
            return "regular"
        return "power"


class AdaptiveConfig:
    """自适应推荐配置"""

    # 活跃度对应的 exploration ratio
    EXPLORATION_BY_ACTIVITY = {
        "new": 0.40,      # 新用户多探索
        "casual": 0.25,   # 偶尔使用
        "regular": 0.15,  # 常规用户
        "power": 0.10,    # 重度用户更个性化
    }

    # 活跃度对应的 freshness weight
    FRESHNESS_BY_ACTIVITY = {
        "new": 0.20,
        "casual": 0.15,
        "regular": 0.10,
        "power": 0.10,
    }

    # 活跃度对应的 diversity limits
    DIVERSITY_BY_ACTIVITY = {
        "new": {"max_per_thread": 1, "max_per_source": 3, "max_per_topic": 4},
        "casual": {"max_per_thread": 1, "max_per_source": 4, "max_per_topic": 5},
        "regular": {"max_per_thread": 1, "max_per_source": 5, "max_per_topic": 6},
        "power": {"max_per_thread": 1, "max_per_source": 6, "max_per_topic": 8},
    }

    @classmethod
    def get_exploration_ratio(cls, activity_level: str) -> float:
        """获取探索比例"""
        return cls.EXPLORATION_BY_ACTIVITY.get(activity_level, 0.20)

    @classmethod
    def get_freshness_weight(cls, activity_level: str) -> float:
        """获取新鲜度权重"""
        return cls.FRESHNESS_BY_ACTIVITY.get(activity_level, 0.15)

    @classmethod
    def get_diversity_limits(cls, activity_level: str) -> dict[str, int]:
        """获取多样性限制"""
        return cls.DIVERSITY_BY_ACTIVITY.get(
            activity_level,
            {"max_per_thread": 1, "max_per_source": 4, "max_per_topic": 6},
        )


class UserActivityAnalyzer:
    """用户活跃度分析器"""

    def analyze(self, user_profile: dict[str, Any]) -> UserActivityProfile:
        """
        分析用户活跃度。

        Args:
            user_profile: 用户画像

        Returns:
            UserActivityProfile
        """
        interactions = user_profile.get("recent_interactions", [])
        interacted_tasks = user_profile.get("interacted_tasks", set())
        topics = user_profile.get("topics", {})

        # 计算 7 天内的互动
        recent_count = len(interactions)

        # 计算日均互动
        account_age = max(1, user_profile.get("account_age_days", 1))
        avg_daily = recent_count / min(7, account_age)

        return UserActivityProfile(
            total_interactions=user_profile.get("total_interactions", 0),
            recent_interactions_7d=recent_count,
            avg_daily_interactions=avg_daily,
            unique_tasks=len(interacted_tasks),
            unique_topics=len(topics),
            account_age_days=account_age,
        )

    def get_adaptive_params(self, user_profile: dict[str, Any]) -> dict[str, Any]:
        """
        获取自适应推荐参数。

        Args:
            user_profile: 用户画像

        Returns:
            自适应参数字典
        """
        activity = self.analyze(user_profile)
        level = activity.activity_level

        return {
            "exploration_ratio": AdaptiveConfig.get_exploration_ratio(level),
            "freshness_weight": AdaptiveConfig.get_freshness_weight(level),
            "diversity_limits": AdaptiveConfig.get_diversity_limits(level),
            "activity_level": level,
        }


# 全局单例
user_activity_analyzer = UserActivityAnalyzer()

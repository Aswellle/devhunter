"""
tests/test_recommendation/test_adapter.py
Adaptive Recommendation 单元测试
"""
import pytest
from app.recommendation.adapter import (
    UserActivityProfile,
    AdaptiveConfig,
    UserActivityAnalyzer,
    user_activity_analyzer,
)


class TestUserActivityProfile:
    """用户活跃度画像测试"""

    def test_new_user(self):
        """新用户"""
        profile = UserActivityProfile(
            total_interactions=2,
            account_age_days=1,
        )
        assert profile.activity_level == "new"

    def test_casual_user(self):
        """偶尔使用用户"""
        profile = UserActivityProfile(
            total_interactions=20,
            avg_daily_interactions=0.5,
            account_age_days=30,
        )
        assert profile.activity_level == "casual"

    def test_regular_user(self):
        """常规用户"""
        profile = UserActivityProfile(
            total_interactions=100,
            avg_daily_interactions=2.0,
            account_age_days=60,
        )
        assert profile.activity_level == "regular"

    def test_power_user(self):
        """重度用户"""
        profile = UserActivityProfile(
            total_interactions=500,
            avg_daily_interactions=10.0,
            account_age_days=90,
        )
        assert profile.activity_level == "power"


class TestAdaptiveConfig:
    """自适应配置测试"""

    def test_exploration_ratio_new(self):
        """新用户探索比例"""
        ratio = AdaptiveConfig.get_exploration_ratio("new")
        assert ratio == 0.40

    def test_exploration_ratio_power(self):
        """重度用户探索比例"""
        ratio = AdaptiveConfig.get_exploration_ratio("power")
        assert ratio == 0.10

    def test_freshness_weight(self):
        """新鲜度权重"""
        weight = AdaptiveConfig.get_freshness_weight("new")
        assert weight == 0.20

    def test_diversity_limits(self):
        """多样性限制"""
        limits = AdaptiveConfig.get_diversity_limits("new")
        assert limits["max_per_thread"] == 1
        assert limits["max_per_source"] == 3

    def test_default_values(self):
        """默认值"""
        ratio = AdaptiveConfig.get_exploration_ratio("unknown")
        assert ratio == 0.20


class TestUserActivityAnalyzer:
    """用户活跃度分析器测试"""

    def test_analyze_new_user(self):
        """分析新用户"""
        user_profile = {
            "total_interactions": 2,
            "recent_interactions": [1, 2],
            "interacted_tasks": {"task_1"},
            "topics": {"ai": 0.5},
            "account_age_days": 1,
        }
        activity = user_activity_analyzer.analyze(user_profile)
        assert activity.activity_level == "new"

    def test_analyze_regular_user(self):
        """分析常规用户"""
        user_profile = {
            "total_interactions": 100,
            "recent_interactions": list(range(14)),
            "interacted_tasks": {"task_1", "task_2", "task_3"},
            "topics": {"ai": 0.8, "rust": 0.6},
            "account_age_days": 60,
        }
        activity = user_activity_analyzer.analyze(user_profile)
        assert activity.activity_level == "regular"

    def test_get_adaptive_params(self):
        """获取自适应参数"""
        user_profile = {
            "total_interactions": 500,
            "recent_interactions": list(range(50)),
            "interacted_tasks": {"task_1", "task_2"},
            "topics": {"ai": 0.8},
            "account_age_days": 90,
        }
        params = user_activity_analyzer.get_adaptive_params(user_profile)
        assert "exploration_ratio" in params
        assert "freshness_weight" in params
        assert "diversity_limits" in params
        assert "activity_level" in params

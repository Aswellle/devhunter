"""
tests/test_recommendation/test_explanations.py
Explanation Generation 单元测试
"""
import pytest
from app.recommendation.explanations import explanation_generator


class TestExplanationGenerator:
    """推荐解释生成器测试"""

    def test_generate_basic(self):
        """基本解释生成"""
        item = {
            "title": "OpenAI launches GPT-5",
            "task_name": "Hacker News",
        }
        score_details = {
            "preference_score": 0.5,
            "affinity_score": 0.4,
            "recency_score": 0.9,
            "engagement_score": 0.3,
            "thread_importance_score": 0.6,
            "exploration_score": 0.2,
        }
        user_profile = {}

        reasons = explanation_generator.generate(item, score_details, user_profile)
        assert isinstance(reasons, list)
        assert len(reasons) > 0

    def test_generate_topic_reason(self):
        """主题匹配解释"""
        item = {"title": "Test"}
        score_details = {"preference_score": 0.5}
        user_profile = {}

        reasons = explanation_generator.generate(item, score_details, user_profile)
        topic_reasons = [r for r in reasons if r["type"] == "topic"]
        assert len(topic_reasons) == 1

    def test_generate_recency_reason(self):
        """新鲜度解释"""
        item = {"title": "Test"}
        score_details = {"recency_score": 0.9}
        user_profile = {}

        reasons = explanation_generator.generate(item, score_details, user_profile)
        recency_reasons = [r for r in reasons if r["type"] == "recency"]
        assert len(recency_reasons) == 1

    def test_generate_empty_scores(self):
        """空得分 → 无解释"""
        item = {"title": "Test"}
        score_details = {}
        user_profile = {}

        reasons = explanation_generator.generate(item, score_details, user_profile)
        assert reasons == []

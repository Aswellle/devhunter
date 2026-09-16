"""
tests/test_recommendation/test_scoring.py
Recommendation Scoring 单元测试
"""
import pytest
from app.recommendation.scoring import recommendation_scorer


class TestRecommendationScorer:
    """推荐评分器测试"""

    def test_score_basic(self):
        """基本评分"""
        item = {
            "title": "OpenAI launches GPT-5",
            "summary": "OpenAI officially released GPT-5",
            "task_id": "task_1",
            "task_name": "Hacker News",
            "fetched_at": "2026-09-15T10:00:00Z",
        }
        user_profile = {
            "topics": {"ai": 0.8, "gpt": 0.6},
            "affinities": {"task_1": 0.7},
            "engagement_stats": {},
        }

        result = recommendation_scorer.score(item, user_profile)
        assert "total_score" in result
        assert 0 <= result["total_score"] <= 1.0

    def test_score_with_thread_info(self):
        """带 Thread 信息的评分"""
        item = {
            "title": "OpenAI launches GPT-5",
            "task_id": "task_1",
            "fetched_at": "2026-09-15T10:00:00Z",
        }
        user_profile = {
            "topics": {"ai": 0.8},
            "affinities": {},
            "engagement_stats": {},
        }
        thread_info = {
            "source_count": 4,
            "last_seen_at": "2026-09-15T10:00:00Z",
        }

        result = recommendation_scorer.score(item, user_profile, thread_info)
        assert result["thread_importance_score"] > 0

    def test_score_empty_profile(self):
        """空用户画像"""
        item = {
            "title": "Test Article",
            "task_id": "task_1",
            "fetched_at": "2026-09-15T10:00:00Z",
        }
        user_profile = {
            "topics": {},
            "affinities": {},
            "engagement_stats": {},
        }

        result = recommendation_scorer.score(item, user_profile)
        assert result["total_score"] >= 0

    def test_recency_score_recent(self):
        """最近内容 → 高分"""
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        item = {
            "title": "Test",
            "fetched_at": now_iso,
        }
        user_profile = {"topics": {}, "affinities": {}, "engagement_stats": {}}

        result = recommendation_scorer.score(item, user_profile)
        assert result["recency_score"] == 1.0

    def test_exploration_score_new_task(self):
        """新任务 → 高探索得分"""
        item = {
            "title": "Test",
            "task_id": "new_task",
            "fetched_at": "2026-09-15T10:00:00Z",
        }
        user_profile = {
            "topics": {},
            "affinities": {},
            "engagement_stats": {},
            "interacted_tasks": {"old_task"},
        }

        result = recommendation_scorer.score(item, user_profile)
        assert result["exploration_score"] > 0.5

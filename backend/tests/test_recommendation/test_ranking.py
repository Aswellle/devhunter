"""
tests/test_recommendation/test_ranking.py
Learning-to-Rank 单元测试
"""
import pytest
from app.recommendation.ranking import (
    LinearRanker,
    FeatureExtractor,
    RankFeatures,
    linear_ranker,
    feature_extractor,
)


class TestLinearRanker:
    """线性排序器测试"""

    def test_rank_basic(self):
        """基本排序"""
        ranker = LinearRanker()
        features = RankFeatures(
            preference_score=0.8,
            affinity_score=0.6,
            recency_score=0.9,
            engagement_score=0.5,
            thread_importance_score=0.7,
            exploration_score=0.3,
        )
        score = ranker.rank(features)
        assert 0 <= score <= 1.0

    def test_rank_zero_features(self):
        """全零特征"""
        ranker = LinearRanker()
        features = RankFeatures()
        score = ranker.rank(features)
        assert score == 0.0

    def test_rank_max_features(self):
        """满分特征"""
        ranker = LinearRanker()
        features = RankFeatures(
            preference_score=1.0,
            affinity_score=1.0,
            recency_score=1.0,
            engagement_score=1.0,
            thread_importance_score=1.0,
            exploration_score=1.0,
        )
        score = ranker.rank(features)
        assert score == 1.0

    def test_batch_rank(self):
        """批量排序"""
        ranker = LinearRanker()
        features_list = [
            RankFeatures(preference_score=0.8),
            RankFeatures(preference_score=0.5),
            RankFeatures(preference_score=0.9),
        ]
        scores = ranker.batch_rank(features_list)
        assert len(scores) == 3
        assert scores[0] < scores[2]  # 0.8 < 0.9

    def test_custom_weights(self):
        """自定义权重"""
        ranker = LinearRanker(weights=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        features = RankFeatures(preference_score=0.5)
        score = ranker.rank(features)
        assert score == 0.5

    def test_features_to_list(self):
        """特征转列表"""
        features = RankFeatures(
            preference_score=0.5,
            affinity_score=0.6,
            recency_score=0.7,
            engagement_score=0.8,
            thread_importance_score=0.9,
            exploration_score=1.0,
        )
        vec = features.to_list()
        assert len(vec) == 6
        assert vec == [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


class TestFeatureExtractor:
    """特征提取器测试"""

    def test_extract_basic(self):
        """基本特征提取"""
        item = {
            "title": "OpenAI launches GPT-5",
            "summary": "OpenAI released GPT-5",
            "task_id": "task_1",
            "task_name": "Hacker News",
            "fetched_at": "2026-09-15T10:00:00Z",
        }
        user_profile = {
            "topics": {"ai": 0.8, "gpt": 0.6},
            "affinities": {"task_1": 0.7},
            "engagement_stats": {},
            "interacted_tasks": {"task_1"},
        }

        features = feature_extractor.extract(item, user_profile)
        assert isinstance(features, RankFeatures)
        assert features.preference_score > 0

    def test_extract_empty_profile(self):
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
            "interacted_tasks": set(),
        }

        features = feature_extractor.extract(item, user_profile)
        assert isinstance(features, RankFeatures)

    def test_extract_with_thread_info(self):
        """带 Thread 信息的特征提取"""
        item = {
            "title": "Test",
            "task_id": "task_1",
            "fetched_at": "2026-09-15T10:00:00Z",
        }
        user_profile = {
            "topics": {},
            "affinities": {},
            "engagement_stats": {},
            "interacted_tasks": set(),
        }
        thread_info = {
            "source_count": 4,
            "last_seen_at": "2026-09-15T10:00:00Z",
        }

        features = feature_extractor.extract(item, user_profile, thread_info)
        assert features.thread_importance_score > 0


class TestRankFeatures:
    """排序特征测试"""

    def test_default_values(self):
        """默认值"""
        features = RankFeatures()
        assert features.preference_score == 0.0
        assert features.affinity_score == 0.0

    def test_custom_values(self):
        """自定义值"""
        features = RankFeatures(
            preference_score=0.5,
            affinity_score=0.6,
        )
        assert features.preference_score == 0.5
        assert features.affinity_score == 0.6

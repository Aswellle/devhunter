"""
tests/test_threads/test_scoring.py
Thread Scoring 单元测试
"""
import pytest
from app.threads.scoring import thread_scorer, ThreadScore


class TestThreadScorer:
    """Thread 评分器测试"""

    def test_score_identical_items(self):
        """完全相同的内容 → 高分"""
        item = {
            "title": "OpenAI launches GPT-5",
            "summary": "OpenAI officially released GPT-5",
            "source_id": "hackernews",
            "published_at": "2026-09-15T10:00:00Z",
        }
        thread = {
            "title": "OpenAI launches GPT-5",
            "last_seen_at": "2026-09-15T10:00:00Z",
            "platforms": ["hackernews"],
        }
        new_features = {
            "entities": {"company": ["openai"], "ai_model": ["gpt-5"]},
            "fingerprint": "abc123",
        }
        candidate_features = {
            "entities": {"company": ["openai"], "ai_model": ["gpt-5"]},
            "fingerprint": "abc123",
        }

        score = thread_scorer.score(item, thread, new_features, candidate_features)
        assert score.total_score > 0.5
        assert score.confidence in ("high", "medium")

    def test_score_different_items(self):
        """完全不同的内容 → 低分"""
        item = {
            "title": "React 19 performance",
            "summary": "React 19 benchmark results",
            "source_id": "hackernews",
            "published_at": "2026-09-15T10:00:00Z",
        }
        thread = {
            "title": "OpenAI launches GPT-5",
            "last_seen_at": "2026-09-15T10:00:00Z",
            "platforms": ["hackernews"],
        }
        new_features = {
            "entities": {"product": ["react"]},
            "fingerprint": "def456",
        }
        candidate_features = {
            "entities": {"company": ["openai"], "ai_model": ["gpt-5"]},
            "fingerprint": "abc123",
        }

        score = thread_scorer.score(item, thread, new_features, candidate_features)
        assert score.total_score < 0.5

    def test_entity_score_overlap(self):
        """实体重叠 → entity_score > 0"""
        entities_a = {"company": ["openai"], "ai_model": ["gpt-5"]}
        entities_b = {"company": ["openai"], "ai_model": ["gpt-5"]}
        score = thread_scorer._calc_entity_score(entities_a, entities_b)
        assert score > 0

    def test_entity_score_no_overlap(self):
        """实体不重叠 → entity_score = 0"""
        entities_a = {"company": ["openai"]}
        entities_b = {"company": ["google"]}
        score = thread_scorer._calc_entity_score(entities_a, entities_b)
        assert score == 0

    def test_semantic_score_identical(self):
        """相同指纹 → 1.0"""
        score = thread_scorer._calc_semantic_score("abc123", "abc123")
        assert score == 1.0

    def test_semantic_score_different(self):
        """不同指纹 → 0.0"""
        score = thread_scorer._calc_semantic_score("abc123", "def456")
        assert score == 0.0

    def test_source_score_cross_platform(self):
        """跨平台 → 1.0"""
        score = thread_scorer._calc_source_score("v2ex", ["hackernews", "github"])
        assert score == 1.0

    def test_source_score_same_source(self):
        """同源 → 0.3"""
        score = thread_scorer._calc_source_score("hackernews", ["hackernews", "github"])
        assert score == 0.3

    def test_confidence_high(self):
        """高分 → high confidence"""
        item = {
            "title": "OpenAI launches GPT-5",
            "source_id": "hackernews",
            "published_at": "2026-09-15T10:00:00Z",
        }
        thread = {
            "title": "OpenAI launches GPT-5",
            "last_seen_at": "2026-09-15T10:00:00Z",
            "platforms": ["v2ex"],
        }
        new_features = {
            "entities": {"company": ["openai"], "ai_model": ["gpt-5"]},
            "fingerprint": "abc123",
        }
        candidate_features = {
            "entities": {"company": ["openai"], "ai_model": ["gpt-5"]},
            "fingerprint": "abc123",
        }

        score = thread_scorer.score(item, thread, new_features, candidate_features)
        assert score.confidence == "high"

    def test_confidence_low(self):
        """低分 → low confidence"""
        item = {
            "title": "React 19 performance",
            "source_id": "hackernews",
            "published_at": "2026-09-15T10:00:00Z",
        }
        thread = {
            "title": "OpenAI launches GPT-5",
            "last_seen_at": "2026-09-15T10:00:00Z",
            "platforms": ["hackernews"],
        }
        new_features = {
            "entities": {"product": ["react"]},
            "fingerprint": "def456",
        }
        candidate_features = {
            "entities": {"company": ["openai"]},
            "fingerprint": "abc123",
        }

        score = thread_scorer.score(item, thread, new_features, candidate_features)
        assert score.confidence == "low"

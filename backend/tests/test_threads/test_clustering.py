"""
tests/test_threads/test_clustering.py
Thread Clustering 单元测试
"""
import pytest
from app.threads.clustering import thread_clusterer


class TestThreadClusterer:
    """Thread 聚类器测试"""

    def test_cluster_no_candidates(self):
        """无候选 → 创建新 Thread"""
        item = {"title": "Test Article", "source_id": "hackernews"}
        result = thread_clusterer.cluster(item, [])
        assert result.action == "create"

    def test_cluster_with_candidates(self):
        """有候选 → 可能加入或创建"""
        item = {
            "title": "OpenAI launches GPT-5",
            "source_id": "hackernews",
            "published_at": "2026-09-15T10:00:00Z",
        }
        candidates = [
            {
                "id": "thread_1",
                "title": "OpenAI launches GPT-5",
                "last_seen_at": "2026-09-15T10:00:00Z",
                "platforms": ["v2ex"],
            }
        ]
        result = thread_clusterer.cluster(item, candidates)
        assert result.action in ("join", "create")

    def test_cluster_result_to_dict(self):
        """结果序列化"""
        item = {"title": "Test", "source_id": "hackernews"}
        result = thread_clusterer.cluster(item, [])
        d = result.to_dict()
        assert d["action"] == "create"
        assert d["thread_id"] is None

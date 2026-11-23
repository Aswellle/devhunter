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

    def test_shared_entity_only_does_not_join(self):
        """只共用泛化实体（GPT-5）、标题内容完全不同 → 不合并。

        回归：跨来源来源分 1.0 + 实体分 0.22 + 时间分 1.0 可让总分
        刚好越过 0.35，把两篇不同故事硬并进一个 Thread。
        """
        item = {
            "title": "GPT-5 release notes 90a84ccb part 2",
            "summary": "GPT-5 release",
            "source_id": "compute task",
            "fetched_at": "2026-09-15T10:00:00Z",
        }
        candidates = [{
            "id": "thread_entity_only",
            "title": "OpenAI ships GPT-5 agent mode f4049b0a",
            "last_seen_at": "2026-09-15T10:00:00Z",
            "platforms": ["other source"],
        }]
        result = thread_clusterer.cluster(item, candidates, threshold=0.35)
        assert result.action == "create"

    def test_cluster_result_to_dict(self):
        """结果序列化"""
        item = {"title": "Test", "source_id": "hackernews"}
        result = thread_clusterer.cluster(item, [])
        d = result.to_dict()
        assert d["action"] == "create"
        assert d["thread_id"] is None

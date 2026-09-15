"""
tests/test_recommendation/test_diversification.py
Diversification 单元测试
"""
import pytest
from app.recommendation.diversification import diversifier


class TestDiversifier:
    """多样性处理器测试"""

    def test_apply_thread_limit(self):
        """相同 thread → 只保留 1 条（max_per_thread=1）"""
        items = [
            {"id": "1", "thread_id": "t1", "source_id": "s1"},
            {"id": "2", "thread_id": "t1", "source_id": "s1"},
        ]
        result = diversifier.apply(items)
        assert len(result) == 1  # max_per_thread=1

    def test_apply_thread_limit_three(self):
        """3 个相同 thread → 只保留 1 条"""
        items = [
            {"id": "1", "thread_id": "t1", "source_id": "s1"},
            {"id": "2", "thread_id": "t1", "source_id": "s1"},
            {"id": "3", "thread_id": "t1", "source_id": "s1"},
        ]
        result = diversifier.apply(items)
        assert len(result) == 1  # max_per_thread=1

    def test_apply_source_limit(self):
        """来源限制"""
        items = [
            {"id": "1", "thread_id": "t1", "source_id": "s1"},
            {"id": "2", "thread_id": "t2", "source_id": "s1"},
            {"id": "3", "thread_id": "t3", "source_id": "s1"},
            {"id": "4", "thread_id": "t4", "source_id": "s1"},
            {"id": "5", "thread_id": "t5", "source_id": "s1"},
        ]
        result = diversifier.apply(items)
        assert len(result) == 4  # max_per_source=4

    def test_apply_empty(self):
        """空列表"""
        result = diversifier.apply([])
        assert result == []

    def test_apply_different_threads(self):
        """不同 thread → 全部通过"""
        items = [
            {"id": "1", "thread_id": "t1", "source_id": "s1"},
            {"id": "2", "thread_id": "t2", "source_id": "s2"},
            {"id": "3", "thread_id": "t3", "source_id": "s3"},
        ]
        result = diversifier.apply(items)
        assert len(result) == 3

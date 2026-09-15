"""
tests/test_threads/test_merge_split.py
Thread Merge/Split 单元测试
"""
import pytest
from app.threads.merge import thread_merger
from app.threads.split import thread_splitter


class TestThreadMergeSplit:
    """Thread 合并/拆分测试"""

    def test_merge_same_thread_fails(self):
        """合并自身 → 失败"""
        result = thread_merger.merge("thread_1", "thread_1")
        assert result is None

    def test_merge_nonexistent_source(self):
        """不存在的源 Thread → 失败"""
        result = thread_merger.merge("nonexistent", "thread_1")
        assert result is None

    def test_split_empty_items(self):
        """空 items → 失败"""
        result = thread_splitter.split("thread_1", [])
        assert result is None

    def test_split_nonexistent_thread(self):
        """不存在的 Thread → 失败"""
        result = thread_splitter.split("nonexistent", ["item_1"])
        assert result is None

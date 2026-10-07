"""
tests/test_services/test_thread_service.py
Thread Service 单元测试
"""
import pytest
from unittest.mock import patch
from app.services.thread_service import thread_service
from app.repositories.thread_repo import thread_repo


class TestThreadService:
    """Thread Service 测试"""

    def test_compute_threads_empty_items(self):
        """空 items → 返回 0"""
        result = thread_service.compute_threads_for_items([])
        assert result == 0

    @patch("app.services.thread_service.thread_repo")
    @patch("app.services.thread_service.task_repo")
    def test_compute_threads_no_candidates(self, mock_task_repo, mock_thread_repo):
        """无候选 Thread → 全部创建新 Thread"""
        mock_task_repo.list_active.return_value = []
        mock_thread_repo.get_candidate_threads.return_value = []
        mock_thread_repo.create.return_value = "thread_1"

        new_items = [
            {"id": "item_1", "title": "Test Article", "task_id": "task_1"},
        ]
        result = thread_service.compute_threads_for_items(new_items)
        assert result == 1
        # 候选逐条目刷新
        assert mock_thread_repo.get_candidate_threads.call_count == 1
        mock_thread_repo.create.assert_called_once()

    @patch("app.services.thread_service.thread_repo")
    @patch("app.services.thread_service.task_repo")
    def test_compute_threads_forwards_threshold_and_window(self, mock_task_repo, mock_thread_repo):
        """threshold 与 window_hours 应传达到候选查询与聚类器"""
        mock_task_repo.list_active.return_value = []
        mock_thread_repo.get_candidate_threads.return_value = []
        mock_thread_repo.create.return_value = "thread_1"

        new_items = [{"id": "item_1", "title": "T", "task_id": "task_1"}]
        thread_service.compute_threads_for_items(new_items, threshold=0.6, window_hours=48)
        mock_thread_repo.get_candidate_threads.assert_called_with(hours=48)
        _, kwargs = mock_thread_repo.create.call_args
        assert kwargs["similarity_threshold"] == 0.6

    def test_list_threads_empty(self):
        """空数据库 → 返回空列表"""
        threads, total = thread_repo.list_all()
        assert isinstance(threads, list)
        assert total >= 0

    def test_get_thread_not_found(self):
        """不存在的 thread_id → 返回 None"""
        result = thread_service.get_thread("nonexistent_id")
        assert result is None

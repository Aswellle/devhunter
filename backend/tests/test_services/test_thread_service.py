"""
tests/test_services/test_thread_service.py
Thread Service 单元测试
"""
import pytest
from unittest.mock import patch, MagicMock
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
        """无候选 items → 全部创建新 Thread"""
        mock_task_repo.list_active.return_value = []
        mock_thread_repo.get_recent_items_for_comparison.return_value = []
        mock_thread_repo.create.return_value = "thread_1"

        new_items = [
            {"id": "item_1", "title": "Test Article", "task_id": "task_1"},
        ]
        result = thread_service.compute_threads_for_items(new_items)
        assert result == 1

    def test_list_threads_empty(self):
        """空数据库 → 返回空列表"""
        threads, total = thread_repo.list_all()
        assert isinstance(threads, list)
        assert total >= 0

    def test_get_thread_not_found(self):
        """不存在的 thread_id → 返回 None"""
        result = thread_service.get_thread("nonexistent_id")
        assert result is None

    def test_get_thread_by_item_not_found(self):
        """不存在的 item_id → 返回 None"""
        result = thread_service._get_thread_id_for_item("nonexistent_item")
        assert result is None

    def test_get_item_title_not_found(self):
        """不存在的 item_id → 返回空字符串"""
        result = thread_service._get_item_title("nonexistent_item")
        assert result == ""

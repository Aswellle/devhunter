"""
tests/test_services/test_thread_service.py
Thread Service 单元测试
"""
import uuid
from datetime import datetime, timezone

import pytest
from unittest.mock import patch
from app.core.exceptions import ConflictError
from app.services.thread_service import thread_service
from app.repositories.thread_repo import thread_repo
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo


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


class TestRecomputeAllThreads:
    """Thread 全量重建测试"""

    def _seed_items(self, titles: list[str]) -> list[dict]:
        task_id = task_repo.insert({
            "name": f"recompute 任务 {uuid.uuid4().hex[:6]}",
            "source_url": "https://example.com/",
            "selector_list": "div",
            "selector_title": "h2",
            "selector_link": "a",
            "cron_expression": "0 9 * * *",
        })["id"]
        token = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        item_repo.bulk_insert([
            {
                "task_id": task_id,
                "title": f"{t} {token}",
                "url": f"https://example.com/recompute/{token}/{i}",
                "url_hash": f"recompute-hash-{token}-{i}",
                "summary": "s",
                "fetched_at": now,
            }
            for i, t in enumerate(titles)
        ])
        return task_id

    def test_rebuild_reproduces_singleton_counts(self):
        """重建后条目全部重新归属（去重计数守恒）"""
        self._seed_items(["alpha topic", "beta topic", "gamma topic"])
        thread_service.compute_threads_for_items(
            item_repo.list_all_chronological()
        )
        items_all = item_repo.list_all_chronological()
        threads_before = thread_repo.count_all()

        result = thread_service.recompute_all_threads(window_hours=24)

        assert result["items"] == len(items_all)
        assert result["threads"] == threads_before, "互不相似的条目重建后 Thread 数不变"
        assert result["duration_ms"] >= 0
        # 全部条目重新挂上了 thread
        from app.core.database import get_db
        with get_db() as conn:
            linked = conn.execute("SELECT COUNT(*) FROM thread_items").fetchone()[0]
        assert linked == len(items_all)

    def test_rebuild_is_mutex(self):
        """已有重建进行中 → ConflictError"""
        with thread_service._recompute_lock:
            with pytest.raises(ConflictError):
                thread_service.recompute_all_threads()

    def test_rebuild_releases_lock_on_error(self):
        """重建中途异常也要释放互斥锁"""
        with patch.object(thread_service, "compute_threads_for_items", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                thread_service.recompute_all_threads()
        # 锁已释放：再次调用不再抛 ConflictError
        result = thread_service.recompute_all_threads()
        assert "threads" in result

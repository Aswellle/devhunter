"""
tests/test_services/test_thread_service.py
Thread Service 单元测试
"""
import uuid
from datetime import datetime, timedelta, timezone

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
        # 整批写入包在单事务里，候选查询走同一连接
        assert mock_thread_repo.get_candidate_threads.call_args.kwargs["hours"] == 48
        assert "conn" in mock_thread_repo.get_candidate_threads.call_args.kwargs
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

    def test_rebuild_relinks_every_item(self):
        """重建后每个条目都恰好重新归属一个 Thread（共享测试库，只验证结构性不变量）"""
        self._seed_items(["alpha topic", "beta topic", "gamma topic"])
        thread_service.compute_threads_for_items(
            item_repo.list_all_chronological()
        )

        from app.core.database import get_db
        with get_db() as conn:
            total_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

        result = thread_service.recompute_all_threads(window_hours=24)

        assert result["items"] == total_items
        assert result["threads"] >= 1
        with get_db() as conn:
            linked = conn.execute("SELECT COUNT(*) FROM thread_items").fetchone()[0]
            orphans = conn.execute(
                "SELECT COUNT(*) FROM items WHERE thread_id IS NULL"
            ).fetchone()[0]
        # 每个条目恰好挂载一个 Thread，无孤儿条目
        assert linked == total_items
        assert orphans == 0


class TestHotnessSort:
    """list_all 的热度排序与 hotness 字段附加"""

    def test_attaches_hotness_and_sorts_desc(self):
        """两条目新旧悬殊：两条路径都带 hotness；热度排序新鲜者在前"""
        task_id = task_repo.insert({
            "name": f"hotness 任务 {uuid.uuid4().hex[:6]}",
            "source_url": "https://example.com/",
            "selector_list": "div",
            "selector_title": "h2",
            "selector_link": "a",
            "cron_expression": "0 9 * * *",
        })["id"]
        token = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc)
        item_repo.bulk_insert([
            {
                "task_id": task_id,
                "title": f"fresh breaking news {token}",
                "url": f"https://example.com/hotness/{token}/fresh",
                "url_hash": f"hotness-hash-{token}-fresh",
                "summary": "s",
                "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            {
                "task_id": task_id,
                "title": "archived cold topic xyz",
                "url": f"https://example.com/hotness/{token}/cold",
                "url_hash": f"hotness-hash-{token}-cold",
                "summary": "s",
                # 72 小时前：超出 48h 窗口，热度归零
                "fetched_at": (now - timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        ])
        thread_service.compute_threads_for_items(item_repo.list_all_chronological())

        threads_default, _ = thread_repo.list_all(task_id=task_id, per_page=50)
        by_id_default = {t["title"]: t for t in threads_default}
        fresh_default = next(t for t in threads_default if "fresh" in t["title"])
        cold_default = next(t for t in threads_default if "cold" in t["title"])
        assert fresh_default["hotness"] > 0.9, "默认路径也应附加 hotness"
        assert cold_default["hotness"] == 0.0, "48h 窗口外的条目热度归零"
        # 趋势字段随两条路径一起附加：新鲜 Thread 24h 前尚无热度（delta=hotness 全为升），
        # 冷 Thread 无新报道、存量热量只会衰减（delta 非正）
        assert fresh_default["hotness_previous"] == 0.0
        assert fresh_default["hotness_delta"] == fresh_default["hotness"]
        assert 0.0 <= cold_default["hotness_previous"] <= 0.25
        assert cold_default["hotness_delta"] <= 0

        threads_hot, _ = thread_repo.list_all(task_id=task_id, per_page=50, sort="hotness")
        assert threads_hot[0]["title"] == fresh_default["title"], "热度排序新鲜者在前"
        assert threads_hot[-1]["hotness"] == 0.0
        assert threads_hot[0]["hotness_delta"] == threads_hot[0]["hotness"]

    def test_rebuild_is_mutex(self):
        """另一线程持有重建锁 → ConflictError（锁可重入，同线程的重建内部调用不冲突）"""
        import threading as _threading

        acquired = _threading.Event()
        release = _threading.Event()

        def _hold() -> None:
            thread_service._recompute_lock.acquire()
            acquired.set()
            release.wait(timeout=10)
            thread_service._recompute_lock.release()

        holder = _threading.Thread(target=_hold)
        holder.start()
        assert acquired.wait(timeout=5), "持锁线程未就绪"
        try:
            with pytest.raises(ConflictError):
                thread_service.recompute_all_threads()
        finally:
            release.set()
            holder.join(timeout=5)

    def test_rebuild_releases_lock_on_error(self):
        """重建中途异常也要释放互斥锁"""
        with patch.object(thread_service, "compute_threads_for_items", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                thread_service.recompute_all_threads()
        # 锁已释放：再次调用不再抛 ConflictError
        result = thread_service.recompute_all_threads()
        assert "threads" in result


class TestBackgroundRecompute:
    """后台重建生命周期：start_recompute + recompute_status"""

    def _reset_state(self):
        with thread_service._recompute_state_lock:
            thread_service._recompute_state.update(running=False, result=None, error=None)

    def test_start_completes_with_result(self):
        """启动后台重建后状态从 running → 完成并携带结果"""
        import time as _time

        self._reset_state()
        thread_service.start_recompute(window_hours=24)
        assert thread_service.recompute_status()["running"] is True

        deadline = _time.monotonic() + 60
        status = thread_service.recompute_status()
        while _time.monotonic() < deadline:
            status = thread_service.recompute_status()
            if not status["running"]:
                break
            _time.sleep(0.1)

        assert status["running"] is False
        assert status["error"] is None
        assert status["result"] is not None
        assert {"items", "threads", "duration_ms", "window_hours"} <= set(status["result"])

    def test_start_while_running_conflicts(self):
        """重建进行中再次启动 → ConflictError"""
        import threading as _threading
        import time as _time

        release = _threading.Event()
        self._reset_state()
        try:
            with patch.object(
                thread_service, "recompute_all_threads",
                side_effect=lambda **kw: (release.wait(timeout=10), {"items": 0})[1],
            ):
                thread_service.start_recompute()
                deadline = _time.monotonic() + 5
                while not thread_service.recompute_status()["running"] and _time.monotonic() < deadline:
                    _time.sleep(0.01)
                with pytest.raises(ConflictError):
                    thread_service.start_recompute()
        finally:
            release.set()
            deadline = _time.monotonic() + 10
            while thread_service.recompute_status()["running"] and _time.monotonic() < deadline:
                _time.sleep(0.05)

    def test_background_error_is_exposed(self):
        """后台线程的异常经 status 端点暴露，而不是静默吞掉"""
        import time as _time

        self._reset_state()
        try:
            with patch.object(
                thread_service, "recompute_all_threads",
                side_effect=RuntimeError("boom"),
            ):
                thread_service.start_recompute()
                deadline = _time.monotonic() + 10
                status = thread_service.recompute_status()
                while _time.monotonic() < deadline:
                    status = thread_service.recompute_status()
                    if not status["running"]:
                        break
                    _time.sleep(0.05)
            assert status["running"] is False
            assert "boom" in (status["error"] or "")
        finally:
            self._reset_state()

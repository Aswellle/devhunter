"""
tests/test_services/test_item_service.py
条目删除与 Thread 清理联动回归：删除最后一条成员时 Thread 回收
曾因 items.thread_id / thread_overrides.target_thread_id 悬空引用
触发 FOREIGN KEY constraint failed（500）。
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.repositories.thread_repo import thread_repo
from app.services.item_service import item_service

client = TestClient(app)


def _auth_headers():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}


def _task_with_items(count: int) -> tuple[str, list[str]]:
    task_id = task_repo.insert({
        "name": f"删除联动测试 {uuid.uuid4().hex[:6]}",
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
            "title": f"deletion item {token} #{i}",
            "url": f"https://example.com/del/{token}/{i}",
            "url_hash": f"del-hash-{token}-{i}",
            "summary": "s",
            "fetched_at": now,
        }
        for i in range(count)
    ])
    items, _ = item_repo.query(task_id=task_id)
    return task_id, [it["id"] for it in items]


class TestDeleteItemThreadCleanup:
    """删除条目时的空 Thread 回收"""

    def test_delete_last_member_of_thread(self):
        """单成员 Thread：删除条目不再 500，Thread 连带回收"""
        _, ids = _task_with_items(1)
        thread_id = thread_repo.create("单成员 Thread", ids[0], "hn")

        assert item_service.delete_item(ids[0]) is True
        assert thread_repo.get(thread_id) is None

        with get_db() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM thread_items WHERE thread_id = ?", (thread_id,)
            ).fetchone()[0] == 0

    def test_delete_one_member_keeps_thread(self):
        """多成员 Thread：删其一，Thread 保留且计数同步"""
        _, ids = _task_with_items(2)
        thread_id = thread_repo.create("多成员 Thread", ids[0], "hn")
        thread_repo.add_item(thread_id, ids[1], similarity=0.8, title="t2", platform="v2ex")

        assert item_service.delete_item(ids[1]) is True

        survivor = thread_repo.get(thread_id)
        assert survivor is not None
        assert survivor["item_count"] == 1

    def test_delete_survives_dangling_override_target(self):
        """thread_overrides.target_thread_id 无级联：回收时置空而非炸掉"""
        _, ids = _task_with_items(1)
        thread_id = thread_repo.create("带仲裁 Thread", ids[0], "hn")
        other = thread_repo.create("另一 Thread", _task_with_items(1)[1][0], "jd")
        thread_repo.record_override(other, "reject_merge", target_thread_id=thread_id, reason="unlink_relation")

        assert item_service.delete_item(ids[0]) is True
        assert thread_repo.get(thread_id) is None

        overrides = thread_repo.get_overrides_for_thread(other)
        assert overrides[0]["target_thread_id"] is None, "仲裁行保留、悬挂引用置空"

    def test_delete_via_api_returns_204(self):
        _, ids = _task_with_items(1)
        thread_repo.create("API 删除 Thread", ids[0], "hn")

        response = client.delete(f"/api/items/{ids[0]}", headers=_auth_headers())

        assert response.status_code == 204


# ── 批量删除原子性：所有清理必须在一个事务内 ─────────────────────

class TestBatchDeleteAtomicity:
    """批量删除曾跨多次连接逐条提交：membership 摘除、条目删除、
    Thread 统计、交互清理各自独立提交，中途异常留下半删除状态。"""

    def _threads_for(self, count: int) -> tuple[str, list[str], list[str]]:
        task_id, ids = _task_with_items(count)
        thread_ids = [
            thread_repo.create(f"批量删除 Thread {i}", ids[i], "hn")
            for i in range(count)
        ]
        return task_id, ids, thread_ids

    def test_batch_delete_recalculates_stats_across_threads(self):
        """跨多个 Thread 批量删除：统计正确重算，空 Thread 回收。"""
        _, ids, thread_ids = self._threads_for(3)
        # 每条目除自身 Thread 外互不重叠；删 2 条，两个 Thread 变空
        deleted = item_service.batch_delete(ids[:2])

        assert deleted == 2
        remaining = item_repo.get(ids[2])
        assert remaining is not None
        tid = thread_repo.get(thread_ids[0])
        assert tid is None, "空 Thread 必须被回收"

    def test_exception_in_membership_phase_rolls_everything_back(self, monkeypatch):
        """membership 清理阶段抛异常 → 条目/交互/统计全部回滚。"""
        _, ids, _ = self._threads_for(2)

        from app.repositories import thread_repo as tr_module
        real = tr_module.thread_repo.delete_item_from_thread
        calls = {"n": 0}

        def flaky(item_id, conn=None):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("injected mid-batch failure")
            return real(item_id, conn=conn)

        monkeypatch.setattr(tr_module.thread_repo, "delete_item_from_thread", flaky)
        with pytest.raises(RuntimeError):
            item_service.batch_delete(ids)

        assert item_repo.get(ids[0]) is not None, "事务回滚后条目必须完好"
        assert item_repo.get(ids[1]) is not None

    def test_exception_in_item_delete_phase_rolls_back_membership(self, monkeypatch):
        """条目删除阶段抛异常 → 已摘除的 membership 也要回滚。"""
        _, ids, thread_ids = self._threads_for(2)

        from app.repositories import item_repo as ir_module
        real_batch = ir_module.item_repo.batch_delete

        def flaky_batch(batch_ids, conn=None):
            raise RuntimeError("injected item delete failure")

        monkeypatch.setattr(ir_module.item_repo, "batch_delete", flaky_batch)
        with pytest.raises(RuntimeError):
            item_service.batch_delete(ids)

        # membership 完好（旧实现已逐条提交摘除，无法回滚）
        row = thread_repo.get(thread_ids[0])
        assert row is not None
        members = thread_repo.get_thread_item_map(thread_ids)
        member_ids = {m["id"] for m in members.get(thread_ids[0], [])}
        assert ids[0] in member_ids, "条目删除失败时 membership 必须回滚"

    def test_interactions_cleaned_in_same_transaction(self):
        """批量删除后 user_interactions 无孤儿（同一事务清理）。"""
        _, ids, _ = self._threads_for(1)
        from app.core.database import get_db
        with get_db() as conn:
            conn.execute(
                "INSERT INTO user_interactions (id, item_id, interaction_type, created_at)"
                " VALUES (?, ?, 'view', '2026-01-01T00:00:00Z')",
                (str(uuid.uuid4()), ids[0]),
            )

        item_service.batch_delete(ids)

        with get_db() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM user_interactions WHERE item_id = ?", (ids[0],)
            ).fetchone()[0]
        assert row == 0

    def test_repeat_delete_is_idempotent(self):
        """重复执行同一批删除安全：第二次返回 0 且不报错。"""
        _, ids, _ = self._threads_for(2)
        assert item_service.batch_delete(ids) == 2
        assert item_service.batch_delete(ids) == 0

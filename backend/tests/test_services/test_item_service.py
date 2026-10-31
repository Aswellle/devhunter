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

"""
tests/test_api/test_thread_relations_api.py
"同一故事线"关联 API：详情带关联层、解除关联、认证。
"""
import uuid

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.repositories.thread_repo import thread_repo

client = TestClient(app)


def _auth_headers():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}


def _two_related_threads() -> tuple[str, str]:
    task_id = task_repo.insert({
        "name": f"关联 API 测试任务 {uuid.uuid4().hex[:6]}",
        "source_url": "https://example.com/",
        "selector_list": "div",
        "selector_title": "h2",
        "selector_link": "a",
        "cron_expression": "0 9 * * *",
    })["id"]
    from datetime import datetime, timezone
    token = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    item_repo.bulk_insert([
        {
            "task_id": task_id,
            "title": f"relation api item {token} #{i}",
            "url": f"https://example.com/relation-api/{token}/{i}",
            "url_hash": f"relation-api-hash-{token}-{i}",
            "summary": "s",
            "fetched_at": now,
        }
        for i in range(2)
    ])
    items, _ = item_repo.query(task_id=task_id)
    ta = thread_repo.create("Thread 主线", items[0]["id"], "hn")
    tb = thread_repo.create("Thread 支线", items[1]["id"], "v2ex")
    thread_repo.record_relation(ta, tb, 0.38)
    return ta, tb


class TestThreadDetailRelations:
    """GET /api/items/threads/{id} 携带关联层"""

    def test_detail_includes_related_threads(self):
        ta, tb = _two_related_threads()

        response = client.get(f"/api/items/threads/{ta}", headers=_auth_headers())

        assert response.status_code == 200
        data = response.json()
        related = data["related_threads"]
        assert len(related) == 1
        assert related[0]["id"] == tb
        assert related[0]["title"] == "Thread 支线"
        assert related[0]["similarity"] == 0.38
        assert {"id", "title", "item_count", "platforms", "similarity", "source"} <= set(related[0])

    def test_detail_without_relations_returns_empty_list(self):
        task_id = task_repo.insert({
            "name": f"孤立线程 {uuid.uuid4().hex[:6]}",
            "source_url": "https://example.com/",
            "selector_list": "div",
            "selector_title": "h2",
            "selector_link": "a",
            "cron_expression": "0 9 * * *",
        })["id"]
        from datetime import datetime, timezone
        token = uuid.uuid4().hex[:8]
        item_repo.bulk_insert([{
            "task_id": task_id,
            "title": f"lonely thread item {token}",
            "url": f"https://example.com/lonely/{token}",
            "url_hash": f"lonely-hash-{token}",
            "summary": "s",
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }])
        items, _ = item_repo.query(task_id=task_id)
        ta = thread_repo.create("孤立 Thread", items[0]["id"], "hn")

        data = client.get(f"/api/items/threads/{ta}", headers=_auth_headers()).json()
        assert data["related_threads"] == []


class TestUnlinkRelationAPI:
    """DELETE /api/items/threads/{id}/relations/{related_id}"""

    def test_unlink_removes_relation(self):
        ta, tb = _two_related_threads()

        response = client.delete(
            f"/api/items/threads/{ta}/relations/{tb}",
            headers=_auth_headers(),
        )

        assert response.status_code == 204
        assert thread_repo.get_related_threads(ta) == []
        assert thread_repo.get_related_threads(tb) == []

    def test_unlink_nonexistent_relation_is_404(self):
        ta, tb = _two_related_threads()
        # 先拆掉，再拆一次 → 404
        client.delete(f"/api/items/threads/{ta}/relations/{tb}", headers=_auth_headers())

        response = client.delete(
            f"/api/items/threads/{ta}/relations/{tb}",
            headers=_auth_headers(),
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RELATION_NOT_FOUND"

    def test_requires_auth(self):
        ta, tb = _two_related_threads()
        response = client.delete(f"/api/items/threads/{ta}/relations/{tb}")
        assert response.status_code == 401

"""
tests/test_api/test_thread_merge_api.py
Thread 人工合并/拆分 API：POST /items/threads/{id}/merge 与 /split。
"""
import json
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.repositories.thread_repo import thread_repo

client = TestClient(app)


def _auth_headers():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}


def _make_task(name_hint: str) -> tuple[str, str]:
    name = f"{name_hint} {uuid.uuid4().hex[:6]}"
    task_id = task_repo.insert({
        "name": name,
        "source_url": "https://example.com/",
        "selector_list": "div",
        "selector_title": "h2",
        "selector_link": "a",
        "cron_expression": "0 9 * * *",
    })["id"]
    return task_id, name

def _insert_items(task_id: str, count: int) -> list[dict]:
    token = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    item_repo.bulk_insert([
        {
            "task_id": task_id,
            "title": f"merge api item {token} #{i}",
            "url": f"https://example.com/merge-api/{token}/{i}",
            "url_hash": f"merge-api-hash-{token}-{i}",
            "summary": "s",
            "fetched_at": now,
        }
        for i in range(count)
    ])
    items, _ = item_repo.query(task_id=task_id)
    return items


def _thread_with_items(task_id: str, items: list[dict], platform: str, title: str) -> str:
    tid = thread_repo.create(title, items[0]["id"], platform)
    for extra in items[1:]:
        thread_repo.add_item(tid, extra["id"], 0.9, extra["title"], platform)
    return tid


class TestThreadMergeAPI:
    """POST /api/items/threads/{id}/merge"""

    def test_merge_moves_items_and_rebuilds_platforms(self):
        """合并后条目并入目标、源被删除，platforms 来自任务名 JOIN
        （回归：旧实现查询不存在的 items.source_name 列）。"""
        task_a, name_a = _make_task("合并源任务")
        task_b, name_b = _make_task("合并目标任务")
        items_a = _insert_items(task_a, 1)
        items_b = _insert_items(task_b, 1)
        source = thread_repo.create("源 Thread", items_a[0]["id"], name_a)
        target = thread_repo.create("目标 Thread", items_b[0]["id"], name_b)

        response = client.post(
            f"/api/items/threads/{source}/merge",
            json={"target_thread_id": target, "reason": "同一事件"},
            headers=_auth_headers(),
        )

        assert response.status_code == 200
        merged = response.json()
        assert merged["id"] == target
        assert merged["item_count"] == 2
        platforms = json.loads(merged["platforms"])
        assert set(platforms) == {name_a, name_b}

        detail = client.get(f"/api/items/threads/{source}", headers=_auth_headers())
        assert detail.status_code == 404

    def test_merge_into_self_returns_400(self):
        task_id, _ = _make_task("自合并任务")
        items = _insert_items(task_id, 1)
        tid = thread_repo.create("自合并 Thread", items[0]["id"], "hn")

        response = client.post(
            f"/api/items/threads/{tid}/merge",
            json={"target_thread_id": tid},
            headers=_auth_headers(),
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_MERGE"

    def test_merge_unknown_thread_returns_404(self):
        response = client.post(
            f"/api/items/threads/{uuid.uuid4()}/merge",
            json={"target_thread_id": str(uuid.uuid4())},
            headers=_auth_headers(),
        )
        assert response.status_code == 404

    def test_merge_requires_auth(self):
        response = client.post(
            f"/api/items/threads/{uuid.uuid4()}/merge",
            json={"target_thread_id": str(uuid.uuid4())},
        )
        assert response.status_code == 401


class TestThreadSplitAPI:
    """POST /api/items/threads/{id}/split"""

    def test_split_creates_new_thread_with_relation(self):
        """拆分创建新 Thread，并与源 Thread 建立同故事线关联。"""
        task_id, task_name = _make_task("拆分任务")
        items = _insert_items(task_id, 2)
        source = _thread_with_items(task_id, items, task_name, "拆分源 Thread")

        response = client.post(
            f"/api/items/threads/{source}/split",
            json={"item_ids": [items[1]["id"]], "new_thread_title": "拆出 Thread"},
            headers=_auth_headers(),
        )

        assert response.status_code == 200
        new_thread = response.json()
        assert new_thread["id"] != source
        assert new_thread["item_count"] == 1
        # platforms 必须是合法 JSON（回归：旧实现 f-string 拼接任务名）
        assert json.loads(new_thread["platforms"]) == [task_name]

        detail = client.get(f"/api/items/threads/{source}", headers=_auth_headers())
        assert detail.status_code == 200
        data = detail.json()
        assert data["item_count"] == 1
        related = {r["id"]: r for r in data["related_threads"]}
        assert new_thread["id"] in related
        assert related[new_thread["id"]]["source"] == "split"

    def test_split_all_items_returns_400(self):
        """拆出全部条目被拒绝（否则源 Thread 被清空、关联写入撞外键）。"""
        task_id, _ = _make_task("全拆任务")
        items = _insert_items(task_id, 2)
        source = _thread_with_items(task_id, items, "hn", "全拆 Thread")

        response = client.post(
            f"/api/items/threads/{source}/split",
            json={"item_ids": [i["id"] for i in items]},
            headers=_auth_headers(),
        )

        assert response.status_code == 400

    def test_split_unknown_thread_returns_404(self):
        response = client.post(
            f"/api/items/threads/{uuid.uuid4()}/split",
            json={"item_ids": [str(uuid.uuid4())]},
            headers=_auth_headers(),
        )
        assert response.status_code == 404

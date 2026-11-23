"""
tests/test_api/test_star_folders_api.py
收藏分组（文件夹）API：创建 / 重命名 / 删除 / 批量归组 / 条目筛选。
"""
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo

client = TestClient(app)


def _auth_headers():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}


def _task_id() -> str:
    return task_repo.insert({
        "name": f"收藏分组任务 {uuid.uuid4().hex[:6]}",
        "source_url": "https://example.com/",
        "template_id": None,
        "selector_list": "div.item",
        "selector_title": "a",
        "selector_link": "a",
        "selector_summary": None,
        "selector_next_page": None,
        "keywords": [],
        "cron_expression": "0 9 * * *",
    })["id"]


def _insert_starred(task_id: str, count: int) -> list[str]:
    token = uuid.uuid4().hex[:10]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = [str(uuid.uuid4()) for _ in range(count)]
    item_repo.bulk_insert([
        {
            "id": item_id,
            "task_id": task_id,
            "title": f"folder item {token} #{i}",
            "url": f"https://example.com/folder/{token}/{i}",
            "url_hash": f"folder-hash-{token}-{i}",
            "summary": "s",
            "fetched_at": now,
        }
        for i, item_id in enumerate(ids)
    ])
    for item_id in ids:
        item_repo.patch(item_id, {"is_starred": True})
    return ids


def _create_folder(name: str) -> dict:
    response = client.post(
        "/api/star-folders", json={"name": name}, headers=_auth_headers(),
    )
    assert response.status_code == 201
    return response.json()


class TestStarFoldersAPI:
    def test_create_rename_delete_and_duplicate_name(self):
        name = f"阅读清单 {uuid.uuid4().hex[:6]}"
        folder = _create_folder(f"  {name}  ")
        assert folder["name"] == name

        duplicate = client.post(
            "/api/star-folders",
            json={"name": name.upper() if name.isascii() else name},
            headers=_auth_headers(),
        )
        assert duplicate.status_code == 409

        renamed = client.patch(
            f"/api/star-folders/{folder['id']}",
            json={"name": f"{name}（改）"},
            headers=_auth_headers(),
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == f"{name}（改）"

        deleted = client.delete(
            f"/api/star-folders/{folder['id']}", headers=_auth_headers(),
        )
        assert deleted.status_code == 204

    def test_assign_single_and_batch_then_filter(self):
        task_id = _task_id()
        item_ids = _insert_starred(task_id, 3)
        folder = _create_folder(f"批量归组 {uuid.uuid4().hex[:6]}")

        # 单条归组
        single = client.patch(
            "/api/star-folders/assign",
            json={"item_ids": [item_ids[0]], "folder_id": folder["id"]},
            headers=_auth_headers(),
        )
        assert single.status_code == 200
        assert single.json()["updated"] == 1

        # 批量归组
        batch = client.patch(
            "/api/star-folders/assign",
            json={"item_ids": item_ids[1:], "folder_id": folder["id"]},
            headers=_auth_headers(),
        )
        assert batch.status_code == 200
        assert batch.json()["updated"] == 2

        listed = client.get("/api/star-folders", headers=_auth_headers())
        assert listed.status_code == 200
        data = listed.json()
        target = next(f for f in data["folders"] if f["id"] == folder["id"])
        assert target["item_count"] == 3

        # 条目接口按文件夹过滤，返回文件夹名
        filtered = client.get(
            f"/api/items?starred=true&star_folder_id={folder['id']}",
            headers=_auth_headers(),
        )
        assert filtered.status_code == 200
        items = filtered.json()["items"]
        assert {i["id"] for i in items} == set(item_ids)
        assert all(i["star_folder_name"] == folder["name"] for i in items)

        # 移出到未分类
        unassign = client.patch(
            "/api/star-folders/assign",
            json={"item_ids": [item_ids[0]], "folder_id": None},
            headers=_auth_headers(),
        )
        assert unassign.json()["updated"] == 1
        item = client.get(f"/api/items/{item_ids[0]}", headers=_auth_headers()).json()
        assert item["star_folder_id"] is None
        assert item["star_folder_name"] is None

    def test_delete_folder_keeps_items_starred_in_uncategorized(self):
        task_id = _task_id()
        item_ids = _insert_starred(task_id, 1)
        folder = _create_folder(f"待删除 {uuid.uuid4().hex[:6]}")
        client.patch(
            "/api/star-folders/assign",
            json={"item_ids": item_ids, "folder_id": folder["id"]},
            headers=_auth_headers(),
        )

        response = client.delete(
            f"/api/star-folders/{folder['id']}", headers=_auth_headers(),
        )
        assert response.status_code == 204

        item = client.get(f"/api/items/{item_ids[0]}", headers=_auth_headers()).json()
        assert item["is_starred"] is True
        assert item["star_folder_id"] is None

        uncategorized = client.get(
            "/api/items?starred=true&star_folder_id=none", headers=_auth_headers(),
        )
        assert item_ids[0] in {i["id"] for i in uncategorized.json()["items"]}

    def test_assign_unknown_folder_returns_404(self):
        task_id = _task_id()
        item_ids = _insert_starred(task_id, 1)
        response = client.patch(
            "/api/star-folders/assign",
            json={"item_ids": item_ids, "folder_id": str(uuid.uuid4())},
            headers=_auth_headers(),
        )
        assert response.status_code == 404

    def test_requires_auth(self):
        assert client.get("/api/star-folders").status_code == 401

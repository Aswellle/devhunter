"""
tests/test_threads/test_consolidate.py
热点聚合的真实收敛路径：跨批次自动聚类、单条 Thread 增量合并、手动聚合。

背景：采集管线只让新条目去找候选 Thread，两个不同批次各自创建的单条
Thread 永远不会互相比较——即使标题完全相同。定时合并（consolidate）
与手动聚合（aggregate）是补齐这一环的两条入口。
"""
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.repositories.thread_repo import thread_repo
from app.services.thread_service import thread_service

client = TestClient(app)


def _auth_headers():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}


def _task(name: str) -> tuple[str, str]:
    actual = f"{name} {uuid.uuid4().hex[:6]}"
    task_id = task_repo.insert({
        "name": actual,
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
    return task_id, actual


def _insert_item(task_id: str, title: str) -> dict:
    token = uuid.uuid4().hex[:10]
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    item_repo.bulk_insert([{
        "id": item_id,
        "task_id": task_id,
        "title": title,
        "url": f"https://example.com/consolidate/{token}",
        "url_hash": f"consolidate-hash-{token}",
        "summary": "同一事件的报道",
        "fetched_at": now,
    }])
    return item_repo.get(item_id)


def _thread_id_of(item_id: str) -> str | None:
    item = item_repo.get(item_id)
    return item.get("thread_id") if item else None


class TestCrossBatchClustering:
    def test_same_story_from_two_sources_joins_one_thread(self):
        """两个任务的相同标题：后一批次应加入先创建的热点 Thread。"""
        token = uuid.uuid4().hex[:8]
        title = f"OpenAI ships GPT-5 agent mode {token}"
        task_a, name_a = _task("来源甲")
        task_b, name_b = _task("来源乙")
        item_a = _insert_item(task_a, title)
        item_b = _insert_item(task_b, title)

        thread_service.compute_threads_for_items([item_a])
        thread_service.compute_threads_for_items([item_b])

        assert _thread_id_of(item_a["id"]) == _thread_id_of(item_b["id"])
        thread = thread_repo.get(_thread_id_of(item_a["id"]))
        assert thread["item_count"] == 2
        assert set(thread["platforms"]) == {name_a, name_b}


class TestConsolidate:
    def test_merges_two_single_threads_for_same_story(self):
        """两条历史单条 Thread 在增量合并后应收敛为一个多来源热点。"""
        token = uuid.uuid4().hex[:8]
        title = f"Anthropic releases Claude 5 {token}"
        task_a, name_a = _task("合并来源甲")
        task_b, name_b = _task("合并来源乙")
        item_a = _insert_item(task_a, title)
        item_b = _insert_item(task_b, title)
        thread_repo.create(title, item_a["id"], name_a)
        thread_repo.create(title, item_b["id"], name_b)

        response = client.post(
            "/api/items/threads/consolidate",
            json={"window_hours": 72},
            headers=_auth_headers(),
        )
        assert response.status_code == 200
        result = response.json()
        assert result["merged_threads"] >= 1

        thread_id = _thread_id_of(item_a["id"])
        assert thread_id == _thread_id_of(item_b["id"])
        assert thread_repo.get(thread_id)["item_count"] == 2

    def test_min_items_filter_surfaces_multi_source_threads(self):
        token = uuid.uuid4().hex[:8]
        title = f"Multi source hotspot {token}"
        task_a, name_a = _task("筛选来源甲")
        task_b, name_b = _task("筛选来源乙")
        item_a = _insert_item(task_a, title)
        item_b = _insert_item(task_b, title)
        thread_repo.create(title, item_a["id"], name_a)
        thread_repo.create(title, item_b["id"], name_b)
        client.post(
            "/api/items/threads/consolidate",
            json={"window_hours": 72},
            headers=_auth_headers(),
        )

        response = client.get(
            "/api/items/threads?min_items=2&per_page=100", headers=_auth_headers(),
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert any(i["id"] == _thread_id_of(item_a["id"]) for i in items)
        assert all(i["item_count"] >= 2 for i in items)


class TestManualAggregate:
    def test_aggregate_creates_named_thread_and_moves_items(self):
        task_id, _ = _task("手动聚合来源")
        token = uuid.uuid4().hex[:8]
        # 三条标题互不相似，各自创建独立 Thread，再验证手动聚合一并搬走
        items = [
            _insert_item(
                task_id,
                f"Distinct subject {token} {uuid.uuid4().hex[:6]}",
            )
            for _ in range(3)
        ]
        old_thread_ids = set()
        for item in items:
            old_thread_ids.add(thread_repo.create(item["title"], item["id"], "手动聚合来源"))
        assert len(old_thread_ids) == 3

        response = client.post(
            "/api/items/threads/aggregate",
            json={
                "item_ids": [i["id"] for i in items],
                "title": "用户命名的热点",
            },
            headers=_auth_headers(),
        )
        assert response.status_code == 200
        thread = response.json()
        assert thread["title"] == "用户命名的热点"
        assert thread["algorithm_version"] == "manual"
        assert {i["id"] for i in thread["items"]} == {i["id"] for i in items}
        assert thread["item_count"] == 3

        # 旧的空 Thread 已回收
        for old_id in old_thread_ids - {thread["id"]}:
            assert thread_repo.get(old_id) is None

    def test_aggregate_requires_at_least_two_items(self):
        task_id, _ = _task("单条聚合来源")
        item = _insert_item(task_id, f"Single item {uuid.uuid4().hex[:8]}")
        response = client.post(
            "/api/items/threads/aggregate",
            json={"item_ids": [item["id"]]},
            headers=_auth_headers(),
        )
        assert response.status_code == 422


class TestOverview:
    def test_overview_reports_sources_and_counts(self):
        response = client.get(
            "/api/items/threads/overview?window_hours=72", headers=_auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        for key in (
            "threads_total", "threads_multi", "threads_single",
            "active_discussion_sources", "discussion_items_in_window",
            "orphan_items", "recompute", "last_consolidation",
        ):
            assert key in data
        assert data["threads_total"] >= data["threads_multi"]

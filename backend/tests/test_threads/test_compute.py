"""
tests/test_threads/test_compute.py
Thread 计算服务的回归测试。

compute_threads_for_items 曾在"候选池为空"时先预创建一轮 Thread，但没有 return，
继续走主循环又创建一轮 —— 一次执行 14 条会生成 28 个 Thread，同一标题在
"热点聚合"列表里出现两遍。
"""
import uuid
from datetime import datetime, timezone

from app.core.database import get_db
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.services.thread_service import thread_service


def _task_id() -> str:
    return task_repo.insert({
        "name": "compute 回归任务",
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


def _items(task_id: str, count: int) -> list[dict]:
    token = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    item_repo.bulk_insert([
        {
            "task_id": task_id,
            "title": f"compute item {token}-{i}",
            "url": f"https://example.com/compute/{token}/{i}",
            "url_hash": f"compute-hash-{token}-{i}",
            "summary": "s",
            "fetched_at": now,
        }
        for i in range(count)
    ])
    items, _ = item_repo.query(task_id=task_id)
    return items


class TestComputeThreadsForItems:
    def test_empty_candidate_pool_creates_one_thread_per_item(self, monkeypatch):
        # 强制走"候选池为空"的分支：测试库里其它用例的条目会混进候选池
        monkeypatch.setattr(
            "app.repositories.thread_repo.thread_repo.get_recent_items_for_comparison",
            lambda **kwargs: [],
        )
        task_id = _task_id()
        items = _items(task_id, 3)
        with get_db() as conn:
            threads_before = conn.execute("SELECT COUNT(*) FROM threads").fetchone()[0]

        processed = thread_service.compute_threads_for_items(items)

        assert processed == 3
        with get_db() as conn:
            for item in items:
                links = conn.execute(
                    "SELECT COUNT(*) FROM thread_items WHERE item_id = ?", (item["id"],)
                ).fetchone()[0]
                assert links == 1, "同一 item 只能归属一个 Thread"
            threads_after = conn.execute("SELECT COUNT(*) FROM threads").fetchone()[0]
        assert threads_after - threads_before == len(items)

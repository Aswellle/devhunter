"""
tests/test_repositories/test_thread_repo.py
Thread 列表与空 Thread 回收的回归测试。

条目被删除时 thread_items 会级联消失（item_id REFERENCES items ON DELETE CASCADE），
但 threads 行会留下来。历史上无过滤条件的列表会把这些空 Thread 一起列出来，
前端展开后就是"暂无内容"；清理任务也不回收，空 Thread 只能越积越多。
"""
import uuid
from datetime import datetime, timezone

from app.core.database import get_db
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.repositories.thread_repo import thread_repo
from app.scheduler.cleanup import cleanup_old_data


def _task_id() -> str:
    return task_repo.insert({
        "name": "thread 回归任务",
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


def _item_id(task_id: str) -> str:
    token = uuid.uuid4().hex[:10]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    item_repo.bulk_insert([{
        "task_id": task_id,
        "title": f"thread item {token}",
        "url": f"https://example.com/thread/{token}",
        "url_hash": f"thread-hash-{token}",
        "summary": "s",
        "fetched_at": now,
    }])
    items, _ = item_repo.query(task_id=task_id)
    return items[0]["id"]


def _thread_with_item(label: str) -> tuple[str, str]:
    task_id = _task_id()
    item_id = _item_id(task_id)
    thread_id = thread_repo.create(
        title=f"thread-{label}", item_id=item_id, platform="github",
    )
    return thread_id, item_id


def _delete_item(item_id: str) -> None:
    """删除条目：get_db() 打开外键约束，thread_items 会随之级联删除。"""
    with get_db() as conn:
        conn.execute("DELETE FROM items WHERE id = ?", (item_id,))


class TestThreadList:
    def test_thread_with_items_is_listed_and_expandable(self):
        thread_id, item_id = _thread_with_item("keep")

        listed, _ = thread_repo.list_all(per_page=100)
        assert thread_id in [t["id"] for t in listed]
        assert [i["id"] for i in thread_repo.get_items_in_thread(thread_id)] == [item_id]

    def test_thread_without_items_is_not_listed(self):
        thread_id, item_id = _thread_with_item("gone")
        _, before_total = thread_repo.list_all(per_page=1)

        _delete_item(item_id)

        listed, after_total = thread_repo.list_all(per_page=100)
        assert thread_id not in [t["id"] for t in listed], "空 Thread 不应再出现在聚合列表里"
        assert after_total == before_total - 1, "total 必须与过滤后的口径一致，否则分页会出现空页"

    def test_filtered_list_ignores_tasks_without_threads(self):
        _, item_id = _thread_with_item("filter")
        task_id = item_repo.get(item_id)["task_id"]

        listed, total = thread_repo.list_all(task_id=task_id, per_page=10)
        assert total == 1 and len(listed) == 1


class TestCleanupReclaimsEmptyThreads:
    def test_cleanup_deletes_empty_threads(self):
        thread_id, item_id = _thread_with_item("cleanup")
        _delete_item(item_id)

        assert thread_repo.get(thread_id) is not None, "条目删除后 threads 行仍在，这正是要回收的对象"

        cleanup_old_data()

        assert thread_repo.get(thread_id) is None

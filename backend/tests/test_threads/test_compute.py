"""
tests/test_threads/test_compute.py
Thread 计算服务的回归测试。

历史坑位：
1. compute_threads_for_items 曾在"候选池为空"时先预创建一轮 Thread，但没有
   return，继续走主循环又创建一轮 —— 一次执行 14 条会生成 28 个 Thread。
2. 候选池查询（get_recent_items_for_comparison）用 LEFT JOIN ... IS NULL 取
   "未入 Thread 的条目"再反查其 thread_id，而未入 Thread 的条目 thread_id
   必为 NULL —— 候选 Thread 恒为空，聚类 join 从未生效。现改为
   get_candidate_threads 直接返回近期活跃 Thread，并用真实数据验证
   同批次与跨批次的 join 都能发生。
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


def _items(task_id: str, count: int, title_prefix: str = "compute item") -> list[dict]:
    token = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    item_repo.bulk_insert([
        {
            "task_id": task_id,
            "title": f"{title_prefix} {token}-{i}",
            "url": f"https://example.com/compute/{token}/{i}",
            "url_hash": f"compute-hash-{token}-{i}",
            "summary": "s",
            "fetched_at": now,
        }
        for i in range(count)
    ])
    items, _ = item_repo.query(task_id=task_id)
    return items


def _thread_count() -> int:
    with get_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM threads").fetchone()[0]


class TestComputeThreadsForItems:
    def test_empty_candidate_pool_creates_one_thread_per_item(self, monkeypatch):
        # 强制走"候选池为空"的分支：测试库里其它用例的条目会混进候选池
        monkeypatch.setattr(
            "app.repositories.thread_repo.thread_repo.get_candidate_threads",
            lambda **kwargs: [],
        )
        task_id = _task_id()
        items = _items(task_id, 3)
        threads_before = _thread_count()

        processed = thread_service.compute_threads_for_items(items)

        assert processed == 3
        with get_db() as conn:
            for item in items:
                links = conn.execute(
                    "SELECT COUNT(*) FROM thread_items WHERE item_id = ?", (item["id"],)
                ).fetchone()[0]
                assert links == 1, "同一 item 只能归属一个 Thread"
        assert _thread_count() - threads_before == len(items)

    def test_same_batch_similar_items_join_one_thread(self):
        """同批次相似标题的条目应聚进同一个 Thread（候选逐条目刷新）"""
        task_id = _task_id()
        token = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        title = f"GPT-5 release notes {token}"
        items = [
            {
                "task_id": task_id,
                "title": f"{title} part {i}",
                "url": f"https://example.com/same/{token}/{i}",
                "url_hash": f"same-hash-{token}-{i}",
                "summary": "GPT-5 release",
                "fetched_at": now,
            }
            for i in range(3)
        ]
        item_repo.bulk_insert(items)
        items, _ = item_repo.query(task_id=task_id)
        # 只保留本批次的 3 条
        items = [i for i in items if i["title"].startswith(title)]

        thread_service.compute_threads_for_items(items)

        with get_db() as conn:
            links = conn.execute(
                """
                SELECT thread_id, COUNT(*) AS c FROM thread_items
                WHERE item_id IN (?, ?, ?)
                GROUP BY thread_id
                """,
                tuple(it["id"] for it in items),
            ).fetchall()
        # 三条同标题条目必须落在同一个 Thread
        assert len(links) == 1, f"期望聚进 1 个 Thread，实际 {len(links)} 个"
        assert links[0]["c"] == 3

    def test_cross_batch_similar_item_joins_existing_thread(self):
        """跨批次相似标题应加入已有 Thread，而非新建"""
        task_id = _task_id()
        token = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        title = f"Transformer architecture explained {token}"

        batch1 = [{
            "task_id": task_id,
            "title": f"{title} original",
            "url": f"https://example.com/cross/{token}/1",
            "url_hash": f"cross-hash-{token}-1",
            "summary": "transformer",
            "fetched_at": now,
        }]
        item_repo.bulk_insert(batch1)
        first_batch, _ = item_repo.query(task_id=task_id)
        first_batch = [i for i in first_batch if i["title"] == f"{title} original"]

        thread_service.compute_threads_for_items(first_batch)
        threads_after_first = _thread_count()

        # 第二批：相似标题（共享核心词）
        batch2 = [{
            "task_id": task_id,
            "title": f"{title} follow-up",
            "url": f"https://example.com/cross/{token}/2",
            "url_hash": f"cross-hash-{token}-2",
            "summary": "transformer",
            "fetched_at": now,
        }]
        item_repo.bulk_insert(batch2)
        second_batch, _ = item_repo.query(task_id=task_id)
        second_batch = [i for i in second_batch if i["title"] == f"{title} follow-up"]

        thread_service.compute_threads_for_items(second_batch)

        assert _thread_count() == threads_after_first, "相似条目不应新建 Thread"
        with get_db() as conn:
            row = conn.execute(
                "SELECT thread_id FROM items WHERE id = ?", (second_batch[0]["id"],)
            ).fetchone()
            first_row = conn.execute(
                "SELECT thread_id FROM items WHERE id = ?", (first_batch[0]["id"],)
            ).fetchone()
        assert row["thread_id"] == first_row["thread_id"], "跨批次条目应加入同一 Thread"


def _catalog_task_id() -> str:
    return task_repo.insert({
        "name": "条目型任务",
        "source_url": "https://github.com/trending",
        "template_id": None,
        "selector_list": "div.item",
        "selector_title": "h2",
        "selector_link": "a",
        "selector_summary": None,
        "selector_next_page": None,
        "keywords": [],
        "cron_expression": "0 9 * * *",
        "content_kind": "catalog",
    })["id"]


class TestCatalogKindGating:
    """条目型（catalog）任务的门控：不参与热点聚合"""

    def test_catalog_items_never_create_threads(self):
        """条目型任务的条目即使标题相似也不建 Thread"""
        threads_before = _thread_count()
        task_id = _catalog_task_id()
        token = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        item_repo.bulk_insert([
            {
                "task_id": task_id,
                "title": f"same repo title {token}",
                "url": f"https://example.com/catalog/{token}/{i}",
                "url_hash": f"catalog-hash-{token}-{i}",
                "summary": "s",
                "fetched_at": now,
            }
            for i in range(3)
        ])
        items, _ = item_repo.query(task_id=task_id)

        processed = thread_service.compute_threads_for_items(items)

        assert processed == 0, "条目型条目不应参与聚类"
        assert _thread_count() == threads_before, "不应产生任何 Thread"
        with get_db() as conn:
            for item in items:
                row = conn.execute(
                    "SELECT thread_id FROM items WHERE id = ?", (item["id"],)
                ).fetchone()
                assert row["thread_id"] is None, "条目型条目不应挂载 Thread"

    def test_recompute_drops_catalog_threads(self):
        """任务改为条目型后重建：其旧 Thread 被清除且不再重建"""
        # 先以讨论型建任务并生成 Thread
        task_id = _task_id()
        items = _items(task_id, 2)
        thread_service.compute_threads_for_items(items)
        with get_db() as conn:
            thread_ids_before = [
                r["id"] for r in conn.execute("SELECT id FROM threads").fetchall()
            ]
        assert thread_ids_before, "前置条件：讨论型时应有 Thread"

        # 任务改为条目型 → 重建
        task_repo.update(task_id, {"content_kind": "catalog"})
        result = thread_service.recompute_all_threads(window_hours=24)

        with get_db() as conn:
            remaining = conn.execute(
                "SELECT COUNT(*) FROM threads WHERE id IN (%s)"
                % ",".join("?" for _ in thread_ids_before),
                thread_ids_before,
            ).fetchone()[0]
            linked = conn.execute(
                "SELECT COUNT(*) FROM thread_items WHERE item_id IN (%s)"
                % ",".join("?" for _ in [i["id"] for i in items]),
                [i["id"] for i in items],
            ).fetchone()[0]
        assert remaining == 0, "条目型任务的旧 Thread 应回收"
        assert linked == 0, "条目型条目重建后不应再挂载 Thread"
        assert result["items"] >= 2

"""
tests/test_repositories/test_item_repo.py
items 写入与全文索引同步的回归测试。

两个历史缺陷都会让"抓取成功"变成"结果永远为空"：

1. bulk_insert 把插入逻辑放在内部函数 _do_insert 中却从未调用，函数恒返回 0，
   一条都不写库（外层调用方看到的是正常的返回，没有任何异常）。
2. 008_fk_cascade 通过 DROP TABLE items 重建表来补 FK CASCADE，连带删除了
   002_fts.sql 建立的 FTS 同步触发器；002 在同一轮启动里已经执行过，
   CREATE TRIGGER IF NOT EXISTS 不会再补一次 → 新条目永不进入 items_fts，
   而 items_fts MATCH 返回空集不抛异常，也不会触发 LIKE 回退，
   全文搜索静默返回 0 条。
"""
import uuid
from datetime import datetime, timezone

from app.core.database import get_db
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo


def _task_id() -> str:
    return task_repo.insert({
        "name": "items 回归任务",
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


def _record(task_id: str, n: int) -> tuple[dict, str]:
    """
    生成一条测试条目，返回 (record, token)。

    test_db_path 是 session 级临时库、跨测试共享，因此 url_hash 必须带唯一
    token —— 否则 url_hash UNIQUE 会让后一个测试的插入被静默跳过。
    """
    token = uuid.uuid4().hex[:10]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "task_id": task_id,
        "title": f"quokka {token} {n}",
        "url": f"https://example.com/quokka/{token}/{n}",
        "url_hash": f"quokka-hash-{token}-{n}",
        "summary": f"quokka summary {token} {n}",
        "fetched_at": now,
        "external_id": f"ext-{token}-{n}",
        "content_hash": f"content-{token}-{n}",
    }, token


class TestBulkInsert:
    """bulk_insert 必须真正落库"""

    def test_returns_inserted_count_and_persists_rows(self):
        task_id = _task_id()
        r1, _ = _record(task_id, 1)
        r2, _ = _record(task_id, 2)

        inserted = item_repo.bulk_insert([r1, r2])

        assert inserted == 2
        items, total = item_repo.query(task_id=task_id)
        assert total == 2
        assert {i["url_hash"] for i in items} == {r1["url_hash"], r2["url_hash"]}

    def test_persists_dedup_fields(self):
        """外部 ID / 内容指纹是去重第 1、3 层的依据，不能丢。"""
        task_id = _task_id()
        record, _ = _record(task_id, 1)
        item_repo.bulk_insert([record])

        assert item_repo.find_existing_external_ids(
            [record["external_id"]], task_id=task_id) == {record["external_id"]}
        assert item_repo.find_existing_content_hashes(
            [record["content_hash"]]) == {record["content_hash"]}

    def test_duplicate_url_hash_is_skipped_not_raised(self):
        task_id = _task_id()
        record, _ = _record(task_id, 1)
        item_repo.bulk_insert([record])

        assert item_repo.bulk_insert([record]) == 0
        _, total = item_repo.query(task_id=task_id)
        assert total == 1


class TestFtsSync:
    """全文索引与 items 表的同步"""

    def test_sync_triggers_exist_after_migrations(self):
        """008 会 DROP TABLE items，020 必须在其之后把触发器恢复回来。"""
        with get_db() as conn:
            names = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )}
        assert {"items_ai", "items_ad", "items_au"} <= names

    def test_inserted_item_is_searchable(self):
        task_id = _task_id()
        r1, token = _record(task_id, 1)
        r2, _ = _record(task_id, 2)
        r2["title"] = f"quokka {token} 2"
        item_repo.bulk_insert([r1, r2])

        _, total = item_repo.query(search=token)
        assert total == 2, "FTS 索引未同步时 MATCH 返回空集且不报错，搜索会静默失效"

    def test_deleted_item_leaves_index(self):
        task_id = _task_id()
        record, token = _record(task_id, 1)
        item_repo.bulk_insert([record])
        items, _ = item_repo.query(task_id=task_id)

        with get_db() as conn:
            conn.execute("DELETE FROM items WHERE id = ?", (items[0]["id"],))

        _, total = item_repo.query(search=token)
        assert total == 0

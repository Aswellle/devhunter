"""
tests/test_crawler/test_content_observation.py
内容实体与来源观测边界回归（ADR-002 / DATA-002）。

旧实现 content_hash 全局去重：三个站点转载同一篇内容只有第一条入库，
后续来源观测被静默丢弃——Thread 失去跨来源证据。改为按来源身份限定：
同来源重复同步仍被拦，跨来源同内容保留为独立观测行。
"""
import uuid

import pytest

from app.crawler.dedup import deduplicate
from app.crawler.engine import CrawlItem
from app.core.database import get_db
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo


def _task(source_url: str) -> str:
    return task_repo.insert({
        "name": f"观测 {uuid.uuid4().hex[:6]}",
        "source_url": source_url,
        "selector_list": "div",
        "selector_title": "h2",
        "selector_link": "a",
        "cron_expression": "0 9 * * *",
    })["id"]


def _item(task_id: str, url: str, title: str = "同一篇报道") -> CrawlItem:
    return CrawlItem(title=title, url=url, summary="相同摘要")


class TestMigration032:
    def test_items_has_source_key_column_and_index(self):
        with get_db() as conn:
            columns = {
                r["name"] for r in conn.execute("PRAGMA table_info(items)").fetchall()
            }
            indexes = {
                r[1] for r in conn.execute("PRAGMA index_list(items)").fetchall()
            }
        assert "source_key" in columns
        assert "idx_items_source_key" in indexes


class TestBackfillSourceKeys:
    def test_backfill_fills_host_identity_from_task(self):
        task_id = _task("https://www.juejin.cn/")
        item_id = str(uuid.uuid4())
        item_repo.bulk_insert([{
            "id": item_id, "task_id": task_id,
            "title": "旧条目", "url": "https://juejin.cn/post/1",
            "url_hash": f"obs-{item_id}", "summary": "s",
        }])
        # 模拟回填前的历史行
        with get_db() as conn:
            conn.execute("UPDATE items SET source_key = NULL WHERE id = ?", (item_id,))

        filled = item_repo.backfill_item_source_keys()

        row = item_repo.get(item_id)
        assert row["source_key"] == "juejin.cn"

    def test_backfill_is_idempotent(self):
        task_id = _task("https://news.ycombinator.com/")
        item_id = str(uuid.uuid4())
        item_repo.bulk_insert([{
            "id": item_id, "task_id": task_id,
            "title": "幂等", "url": "https://news.ycombinator.com/item?id=9",
            "url_hash": f"obs-{item_id}", "summary": "s",
        }])
        item_repo.backfill_item_source_keys()
        first = item_repo.get(item_id)["source_key"]

        item_repo.backfill_item_source_keys()
        assert item_repo.get(item_id)["source_key"] == first == "news.ycombinator.com"


class TestCrossProviderObservations:
    def test_same_content_from_other_provider_is_kept(self):
        """跨来源同内容（不同 URL）：必须保留为独立观测——旧实现按
        全局 content_hash 丢弃，Thread 失去跨来源证据。"""
        task_a = _task("https://news.a.com/")
        task_b = _task("https://news.b.com/")

        first = deduplicate([_item(task_a, "https://news.a.com/x")], task_a)
        assert len(first) == 1
        item_repo.bulk_insert([{
            "task_id": task_a,
            "title": first[0].title,
            "url": first[0].url,
            "url_hash": first[0].url_hash,
            "summary": first[0].summary,
            "content_hash": first[0].content_hash,
            "source_key": "news.a.com",
        }])

        second = deduplicate([_item(task_b, "https://news.b.com/y")], task_b)
        assert len(second) == 1, "B 站转载同内容必须保留为独立观测"

    def test_same_source_resync_is_still_deduped(self):
        """同一来源重复同步同内容（URL 微变）：仍被 content_hash 拦截，
        不增加来源计数。"""
        task_a = _task("https://news.a.com/")
        item_repo.bulk_insert([{
            "task_id": task_a,
            "title": "同一篇报道", "url": "https://news.a.com/x?utm=1",
            "url_hash": uuid.uuid4().hex, "summary": "相同摘要",
            "source_key": "news.a.com",
        }])

        resync = deduplicate([_item(task_a, "https://news.a.com/x?utm=2")], task_a)
        assert resync == [], "同来源重复观测必须被去重"

    def test_legacy_rows_without_source_key_keep_conservative_behavior(self):
        """回填前的历史行（source_key NULL）不参与内容指纹匹配：
        保守策略宁可多保留观测行，不丢跨来源证据。"""
        task_c = _task("https://news.c.com/")
        item_repo.bulk_insert([{
            "task_id": task_c,
            "title": "同一篇报道", "url": "https://news.c.com/old",
            "url_hash": uuid.uuid4().hex, "summary": "相同摘要",
            # source_key 未写（模拟 032 之前的行）
        }])

        candidate = deduplicate([_item(task_c, "https://news.c.com/new")], task_c)
        assert len(candidate) == 1, "身份未知的历史行不拦截新观测"


class TestSourceKeyPersistence:
    def test_bulk_insert_persists_source_key(self):
        task_id = _task("https://www.v2ex.com/")
        item_id = str(uuid.uuid4())
        item_repo.bulk_insert([{
            "id": item_id, "task_id": task_id,
            "title": "带身份", "url": "https://v2ex.com/t/1",
            "url_hash": f"obs-{item_id}", "summary": "s",
            "source_key": "v2ex.com",
        }])
        assert item_repo.get(item_id)["source_key"] == "v2ex.com"

"""
tests/test_crawler/test_dedup_inbatch.py
批内去重回归：同一批次内的重复候选不得同时保留。

旧实现把整批 external_id/url_hash/content_hash 一次性对 DB 查重后
逐条过滤，但保留一条后从不更新内存集合——同一批里相同 external_id
（不同 URL）或相同 content_hash（不同 URL）的候选会全部进入待插入
列表，触发批量插入约束冲突或产生重复条目。
"""
import uuid

import pytest

from app.crawler.dedup import deduplicate
from app.crawler.engine import CrawlItem
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo


@pytest.fixture
def task_id():
    return task_repo.insert({
        "name": f"批内去重 {uuid.uuid4().hex[:6]}",
        "source_url": "https://example.com/",
        "selector_list": "div",
        "selector_title": "h2",
        "selector_link": "a",
        "cron_expression": "0 9 * * *",
    })["id"]


class TestInBatchDedup:
    def test_same_batch_duplicate_external_id_kept_once(self, task_id):
        """同批两条相同 external_id（不同 URL）→ 只保留第一条。"""
        items = [
            CrawlItem(title="a", url="https://e.com/1", external_id="x1"),
            CrawlItem(title="b", url="https://e.com/2", external_id="x1"),
        ]
        kept = deduplicate(items, task_id)
        assert len(kept) == 1
        assert kept[0].url == "https://e.com/1"

    def test_same_batch_same_content_different_url_kept_once(self, task_id):
        """同批两条 title+summary 相同但 URL 不同（content_hash 相同）
        → 只保留第一条。"""
        items = [
            CrawlItem(title="same story", url="https://a.com/x", summary="s"),
            CrawlItem(title="same story", url="https://b.com/y", summary="s"),
        ]
        kept = deduplicate(items, task_id)
        assert len(kept) == 1

    def test_same_batch_duplicate_url_hash_kept_once(self, task_id):
        """同批两条相同 URL（url_hash 相同）→ 只保留一条。"""
        items = [
            CrawlItem(title="first", url="https://e.com/dup"),
            CrawlItem(title="second", url="https://e.com/dup"),
        ]
        kept = deduplicate(items, task_id)
        assert len(kept) == 1

    def test_db_existing_external_id_still_deduped(self, task_id):
        """既有行为回归：DB 已存在的 external_id 仍然被过滤。"""
        item_repo.bulk_insert([{
            "task_id": task_id,
            "title": "old",
            "url": "https://e.com/old",
            "url_hash": uuid.uuid4().hex,
            "external_id": "old-1",
        }])
        items = [
            CrawlItem(title="old again", url="https://e.com/old-2", external_id="old-1"),
        ]
        assert deduplicate(items, task_id) == []

    def test_distinct_items_all_kept(self, task_id):
        """互不重复的条目不受影响。"""
        items = [
            CrawlItem(title=f"t{i}", url=f"https://e.com/{i}", summary=f"s{i}")
            for i in range(5)
        ]
        kept = deduplicate(items, task_id)
        assert len(kept) == 5

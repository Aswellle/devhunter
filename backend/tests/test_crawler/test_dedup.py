"""
test_dedup.py — 三层去重的作用域测试。

覆盖：
- external_id 按任务去重（partial unique index (task_id, external_id) 语义）
- 回归：调用方漏传 task_id 时 external_id 层退化为全局匹配
- url_hash 保持跨任务全局去重
"""
import uuid
from datetime import datetime, timezone

from app.crawler.dedup import deduplicate
from app.crawler.engine import CrawlItem
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.utils.url import compute_url_hash


def _make_task(hint: str) -> str:
    return task_repo.insert({
        "name": f"{hint} {uuid.uuid4().hex[:6]}",
        "source_url": "https://example.com/",
        "selector_list": "div",
        "selector_title": "h2",
        "selector_link": "a",
        "cron_expression": "0 9 * * *",
    })["id"]


def _store_item(task_id: str, url: str, external_id: str) -> None:
    token = uuid.uuid4().hex[:8]
    item_repo.bulk_insert([{
        "task_id": task_id,
        "title": f"dedup item {token}",
        "url": url,
        "url_hash": compute_url_hash(url),
        "summary": "s",
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "external_id": external_id,
    }])


def _crawl_item(url: str, external_id: str, title: str) -> CrawlItem:
    return CrawlItem(title=title, url=url, external_id=external_id)


def test_external_id_dedups_within_same_task():
    """同任务同 external_id、不同 URL → external_id 层拦下。"""
    task_id = _make_task("去重同任务")
    _store_item(task_id, "https://example.com/a/1", "ext-1")

    new = deduplicate(
        [_crawl_item("https://example.com/a/1-renamed", "ext-1", "标题变化")],
        task_id=task_id,
    )
    assert new == []


def test_same_external_id_in_different_task_is_kept():
    """回归：external_id 只在任务内去重；不同任务的相同 external_id
    （如跨平台转载）必须保留——调用方漏传 task_id 会让该层退化成
    全局匹配，把合法条目误杀。"""
    task_a = _make_task("去重任务A")
    task_b = _make_task("去重任务B")
    _store_item(task_a, "https://a.example.com/1", "shared-ext")

    new = deduplicate(
        [_crawl_item("https://b.example.com/1", "shared-ext", "B 站同 ID 条目")],
        task_id=task_b,
    )
    assert len(new) == 1


def test_url_hash_still_global_across_tasks():
    """url_hash 层维持跨任务全局去重。"""
    task_a = _make_task("URL去重A")
    task_b = _make_task("URL去重B")
    _store_item(task_a, "https://same.example.com/post", "ext-a")

    new = deduplicate(
        [_crawl_item("https://same.example.com/post", "ext-b", "同 URL")],
        task_id=task_b,
    )
    assert new == []

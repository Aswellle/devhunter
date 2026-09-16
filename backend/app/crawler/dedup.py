"""
app/crawler/dedup.py
D1: 去重工具 — 三级优先级去重。

去重优先级（从高到低）：
1. external_id：来源平台原生 ID，最可靠
2. canonical_url (url_hash)：规范化 URL 的 hash
3. content_hash：title + summary 的内容指纹（防 URL 变更但内容相同的场景）
"""
import logging

from app.crawler.engine import CrawlItem
from app.repositories.item_repo import item_repo
from app.utils.hash import sha256_hex
from app.utils.url import compute_url_hash

logger = logging.getLogger(__name__)


def _compute_content_hash(item: CrawlItem) -> str:
    """计算内容指纹：title + summary 的 sha256。用于 URL 变更但内容相同的场景。"""
    content = f"{item.title.strip()}|{(item.summary or '').strip()}"
    return sha256_hex(content)


def deduplicate(items: list[CrawlItem], task_id: str = "") -> list[CrawlItem]:
    """
    给每个 CrawlItem 填充 url_hash / content_hash，然后按优先级去重：
    1. external_id 匹配（同一 task_id 内）
    2. url_hash 匹配（规范化 URL）
    3. content_hash 匹配（内容指纹）

    返回数据库中不存在的新条目列表。
    """
    if not items:
        return []

    # 计算所有 hash
    for item in items:
        item.url_hash = compute_url_hash(item.url)
        if not item.content_hash:
            item.content_hash = _compute_content_hash(item)

    # D1: 按优先级去重
    new_items = _filter_by_priority(items, task_id)

    logger.debug(
        "Dedup: %d total → %d new (%d duplicates skipped)",
        len(items), len(new_items), len(items) - len(new_items),
    )
    return new_items


def _filter_by_priority(items: list[CrawlItem], task_id: str) -> list[CrawlItem]:
    """
    三级去重过滤：
    1. external_id 存在时，查询 DB 中同 task_id 下已存在的 external_id
    2. url_hash 查询（跨任务全局去重）
    3. content_hash 查询（内容指纹，防 URL 变更）
    """
    # 第一优先级：external_id
    items_with_ext_id = [i for i in items if i.external_id]
    if items_with_ext_id:
        ext_ids = [i.external_id for i in items_with_ext_id]
        existing_ext = item_repo.find_existing_external_ids(ext_ids, task_id)
    else:
        existing_ext = set()

    # 过滤掉 external_id 已存在的
    after_ext = [i for i in items if not i.external_id or i.external_id not in existing_ext]

    # 第二优先级：url_hash（全局去重）
    hashes = [item.url_hash for item in after_ext]
    existing_hashes = item_repo.find_existing_hashes(hashes)
    after_url = [i for i in after_ext if i.url_hash not in existing_hashes]

    # 第三优先级：content_hash（内容指纹去重）
    content_hashes = [i.content_hash for i in after_url if i.content_hash]
    if content_hashes:
        existing_content = item_repo.find_existing_content_hashes(content_hashes)
    else:
        existing_content = set()

    new_items = [i for i in after_url if not i.content_hash or i.content_hash not in existing_content]

    return new_items

"""
app/crawler/dedup.py
去重工具：批量计算 url_hash 并查询数据库中已存在的 hash。
"""
import logging

from app.crawler.engine import CrawlItem
from app.repositories.item_repo import item_repo
from app.utils.url import compute_url_hash

logger = logging.getLogger(__name__)


def deduplicate(items: list[CrawlItem]) -> list[CrawlItem]:
    """
    给每个 CrawlItem 填充 url_hash，然后批量查询数据库，
    返回数据库中不存在的新条目列表。
    """
    if not items:
        return []

    # 计算所有 hash
    for item in items:
        item.url_hash = compute_url_hash(item.url)

    hashes = [item.url_hash for item in items]
    existing = item_repo.find_existing_hashes(hashes)

    new_items = [item for item in items if item.url_hash not in existing]
    logger.debug(
        "Dedup: %d total → %d new (%d duplicates skipped)",
        len(items), len(new_items), len(items) - len(new_items),
    )
    return new_items

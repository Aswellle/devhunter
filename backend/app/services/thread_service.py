"""
app/services/thread_service.py
Thread 业务层：计算新 Items 的 Thread 归属

V2: 使用多因素评分（lexical + entity + semantic + temporal + source）
"""
import logging

from app.repositories.thread_repo import thread_repo
from app.repositories.task_repo import task_repo
from app.utils.similarity import DEFAULT_THRESHOLD, find_similar_titles, jaccard_similarity
from app.features.extractor import feature_extractor
from app.threads.clustering import thread_clusterer
from app.threads.merge import thread_merger
from app.threads.split import thread_splitter

logger = logging.getLogger(__name__)


class ThreadService:

    def compute_threads_for_items(
        self,
        new_items: list[dict],
        threshold: float = DEFAULT_THRESHOLD,
    ) -> int:
        """
        为一批新采集的 Items 计算 Thread 归属。

        V2 流程：
        1. 获取最近 24h 内未分配 Thread 的 Items 作为候选池
        2. 对每个新 Item，使用多因素评分找到最佳匹配 Thread
        3. 若找到匹配 → 加入已有 Thread
          若未找到 → 创建新 Thread

        返回处理的新 Item 数量。
        """
        if not new_items:
            return 0

        # 获取各 task_id -> platform 名称的映射
        tasks = {t["id"]: t["name"] for t in task_repo.list_active()}
        item_id_to_platform = {
            item["id"]: tasks.get(item.get("task_id"), "unknown")
            for item in new_items
        }

        # 获取候选池：最近 24h 未分配 thread 的 items
        existing = thread_repo.get_recent_items_for_comparison(hours=24, limit=500)
        if not existing:
            # 无候选，全部创建新 Thread
            for item in new_items:
                platform = item_id_to_platform.get(item["id"], "unknown")
                thread_repo.create(
                    title=item["title"],
                    item_id=item["id"],
                    platform=platform,
                )
            logger.info("Thread compute: %d new items, all created as new threads", len(new_items))
            return len(new_items)

        # 构建候选 Thread 列表（从 existing items 中提取）
        candidate_threads = self._get_candidate_threads(existing)

        # 处理每个新 Item
        matched_count = 0
        for item in new_items:
            item_id = item["id"]
            title = item["title"]
            platform = item_id_to_platform.get(item_id, "unknown")

            # 使用多因素聚类
            result = thread_clusterer.cluster(item, candidate_threads)

            if result.action == "join" and result.thread_id:
                # 加入已有 Thread
                thread_repo.add_item(
                    thread_id=result.thread_id,
                    item_id=item_id,
                    similarity=result.score.total_score if result.score else 0.5,
                    title=title,
                    platform=platform,
                )
                matched_count += 1
                logger.debug(
                    "Thread match: %s -> %s (score=%.2f, confidence=%s)",
                    title[:40], result.thread_id[:8],
                    result.score.total_score if result.score else 0,
                    result.score.confidence if result.score else "unknown",
                )
            else:
                # 创建新 Thread
                thread_repo.create(title=title, item_id=item_id, platform=platform)

        logger.info(
            "Thread compute: %d new items, %d matched to existing threads, %d created new",
            len(new_items), matched_count, len(new_items) - matched_count,
        )
        return len(new_items)

    def _get_candidate_threads(self, existing_items: list[tuple]) -> list[dict]:
        """
        从 existing items 中提取候选 Thread 列表。

        Args:
            existing_items: [(item_id, title, fetched_at), ...]

        Returns:
            Thread dict 列表
        """
        # 获取所有相关的 thread_ids
        thread_ids = set()
        for item_id, _, _ in existing_items:
            thread_id = self._get_thread_id_for_item(item_id)
            if thread_id:
                thread_ids.add(thread_id)

        # 获取 Thread 详情
        threads = []
        for thread_id in thread_ids:
            thread = thread_repo.get(thread_id)
            if thread:
                threads.append(thread)

        return threads

    def merge_threads(
        self,
        source_thread_id: str,
        target_thread_id: str,
        reason: str = "",
    ) -> dict | None:
        """
        合并两个 Thread。

        Args:
            source_thread_id: 源 Thread ID（将被删除）
            target_thread_id: 目标 Thread ID
            reason: 合并原因

        Returns:
            合并后的 Thread dict
        """
        return thread_merger.merge(source_thread_id, target_thread_id, reason)

    def split_thread(
        self,
        thread_id: str,
        item_ids: list[str],
        new_thread_title: str | None = None,
    ) -> dict | None:
        """
        拆分 Thread。

        Args:
            thread_id: 源 Thread ID
            item_ids: 要移出的 item ID 列表
            new_thread_title: 新 Thread 标题

        Returns:
            新 Thread dict
        """
        return thread_splitter.split(thread_id, item_ids, new_thread_title)

    def list_threads(
        self,
        task_id: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict], int]:
        """列出 Threads"""
        return thread_repo.list_all(task_id=task_id, page=page, per_page=per_page)

    def get_thread(self, thread_id: str) -> dict | None:
        """获取 Thread 详情（包含 Items）"""
        thread = thread_repo.get(thread_id)
        if not thread:
            return None
        items = thread_repo.get_items_in_thread(thread_id)
        return {**thread, "items": items}

    def _get_thread_id_for_item(self, item_id: str) -> str | None:
        """获取 Item 所属的 Thread ID"""
        from app.repositories.item_repo import item_repo
        item = item_repo.get(item_id)
        return item.get("thread_id") if item else None

    def _get_item_title(self, item_id: str) -> str:
        """获取 Item 的标题"""
        from app.repositories.item_repo import item_repo
        item = item_repo.get(item_id)
        return item.get("title", "") if item else ""


# 全局单例
thread_service = ThreadService()

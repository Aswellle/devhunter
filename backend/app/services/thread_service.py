"""
app/services/thread_service.py
Thread 业务层：计算新 Items 的 Thread 归属
"""
import logging

from app.repositories.thread_repo import thread_repo
from app.repositories.task_repo import task_repo
from app.utils.similarity import DEFAULT_THRESHOLD, find_similar_titles, jaccard_similarity

logger = logging.getLogger(__name__)


class ThreadService:

    def compute_threads_for_items(
        self,
        new_items: list[dict],
        threshold: float = DEFAULT_THRESHOLD,
    ) -> int:
        """
        为一批新采集的 Items 计算 Thread 归属。

        流程：
        1. 获取最近 24h 内未分配 Thread 的 Items 作为候选池
        2. 对每个新 Item，在候选池中找到相似标题
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

        # 构建候选池：(title, item_id, fetched_at)
        candidate_items = [(ex_id, ex_title, ex_at) for ex_id, ex_title, ex_at in existing]

        # 新 Items 的标题列表
        new_titles = [item["title"] for item in new_items]
        new_ids = [item["id"] for item in new_items]

        # 批量查找相似项
        matches = find_similar_titles(
            new_titles=new_titles,
            existing_titles=candidate_items,
            threshold=threshold,
        )

        # 处理每个新 Item
        matched_count = 0
        for i, item in enumerate(new_items):
            item_id = item["id"]
            title = item["title"]
            platform = item_id_to_platform.get(item_id, "unknown")

            if i in matches:
                # 找到相似 → 加入已有 Thread
                existing_item_id = matches[i]
                # 找到该已有 item 所在的 thread
                existing_thread_id = self._get_thread_id_for_item(existing_item_id)
                if existing_thread_id:
                    sim = jaccard_similarity(title, self._get_item_title(existing_item_id))
                    thread_repo.add_item(
                        thread_id=existing_thread_id,
                        item_id=item_id,
                        similarity=sim,
                        title=title,
                        platform=platform,
                    )
                    matched_count += 1
                    logger.debug(
                        "Thread match: %s -> %s (sim=%.2f)",
                        title[:40], existing_thread_id[:8], sim,
                    )
            else:
                # 未找到 → 创建新 Thread
                thread_repo.create(title=title, item_id=item_id, platform=platform)

        logger.info(
            "Thread compute: %d new items, %d matched to existing threads, %d created new",
            len(new_items), matched_count, len(new_items) - matched_count,
        )
        return len(new_items)

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

"""
app/services/item_service.py
采集结果条目业务层
"""
import logging

from app.core.exceptions import ItemNotFoundError
from app.repositories.item_repo import item_repo

logger = logging.getLogger(__name__)


class ItemService:

    def get_counts_by_task(self) -> dict[str, dict[str, int]]:
        """Get counts per task_id for filter bar badges"""
        return item_repo.get_counts_by_task()

    def get_total_count(self) -> int:
        """Get total item count"""
        return item_repo.get_total_count()

    def list_items(
        self,
        task_id: str | None = None,
        search: str | None = None,
        starred: bool | None = None,
        is_read: bool | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict], int]:
        return item_repo.query(
            task_id=task_id,
            search=search,
            starred=starred,
            is_read=is_read,
            page=page,
            per_page=per_page,
        )

    def patch_item(self, item_id: str, data: dict) -> dict:
        item = item_repo.get(item_id)
        if not item:
            raise ItemNotFoundError(f"Item {item_id} not found")
        updated = item_repo.patch(item_id, data)
        return updated

    def batch_patch(self, ids: list[str], data: dict) -> int:
        return item_repo.batch_patch(ids, data)

    def get_item(self, item_id: str) -> dict:
        item = item_repo.get(item_id)
        if not item:
            raise ItemNotFoundError(f"Item {item_id} not found")
        return item

    def delete_item(self, item_id: str) -> bool:
        item = item_repo.get(item_id)
        if not item:
            raise ItemNotFoundError(f"Item {item_id} not found")
        from app.core.database import transaction
        from app.repositories.thread_repo import thread_repo
        # 三步必须原子：thread_items 摘除、空 Thread 回收（内含悬空镜像
        # 清理）、条目本体删除——任一步单独提交后崩溃都会留下不一致状态，
        # 且"先摘成员、后删条目"的中间态里条目的 thread_id 镜像还在，
        # 非 atomic 的回收会撞外键约束（历史上正是这里 500）
        with transaction() as conn:
            thread_repo.delete_item_from_thread(item_id, conn=conn)
            if item.get("thread_id"):
                thread_repo.rebuild_thread_stats(item["thread_id"], conn=conn)
            return item_repo.delete(item_id, conn=conn)

    def batch_delete(self, ids: list[str]) -> int:
        from app.repositories.thread_repo import thread_repo
        from app.core.database import get_db
        # collect thread_ids before deletion
        thread_ids: set[str] = set()
        for item_id in ids:
            item = item_repo.get(item_id)
            if item and item.get("thread_id"):
                thread_ids.add(item["thread_id"])
            thread_repo.delete_item_from_thread(item_id)
        count = item_repo.batch_delete(ids)
        for tid in thread_ids:
            thread_repo.rebuild_thread_stats(tid)
        # clean up orphan user_interactions
        with get_db() as conn:
            placeholders = ",".join(["?"] * len(ids))
            conn.execute(
                f"DELETE FROM user_interactions WHERE item_id IN ({placeholders})", ids
            )
        return count


# 全局单例
item_service = ItemService()

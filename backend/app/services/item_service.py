"""
app/services/item_service.py
采集结果条目业务层
"""
import logging

from app.core.exceptions import ItemNotFoundError
from app.repositories.item_repo import item_repo

logger = logging.getLogger(__name__)


class ItemService:

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
        from app.repositories.thread_repo import thread_repo
        thread_repo.delete_item_from_thread(item_id)
        if item.get("thread_id"):
            thread_repo.rebuild_thread_stats(item["thread_id"])
        return item_repo.delete(item_id)

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

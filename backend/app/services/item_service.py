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
        star_folder_id: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict], int]:
        return item_repo.query(
            task_id=task_id,
            search=search,
            starred=starred,
            is_read=is_read,
            star_folder_id=star_folder_id,
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
        """批量删除：membership 摘除、条目删除、受影响 Thread 统计重算
        （含空 Thread 回收）与交互清理在同一个事务内完成——旧实现跨多次
        连接逐条提交，中途异常会留下成员/统计/交互不一致的半删除状态。
        幂等：不存在的 id 直接跳过，重复执行安全。"""
        if not ids:
            return 0
        from app.core.database import transaction
        from app.repositories.thread_repo import thread_repo

        with transaction() as conn:
            placeholders = ",".join(["?"] * len(ids))
            rows = conn.execute(
                f"SELECT id, thread_id FROM items WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
            thread_ids = {r["thread_id"] for r in rows if r["thread_id"]}

            for item_id in ids:
                thread_repo.delete_item_from_thread(item_id, conn=conn)

            count = item_repo.batch_delete(ids, conn=conn)

            for tid in thread_ids:
                thread_repo.rebuild_thread_stats(tid, conn=conn)

            conn.execute(
                f"DELETE FROM user_interactions WHERE item_id IN ({placeholders})",
                ids,
            )
            return count


# 全局单例
item_service = ItemService()

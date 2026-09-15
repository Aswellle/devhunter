"""
app/threads/merge.py
Thread Merge：合并两个 Thread。

将 source_thread 的所有 items 移动到 target_thread，
并删除 source_thread。
"""
import logging
from typing import Any

from app.core.database import get_db

logger = logging.getLogger(__name__)


class ThreadMerger:
    """Thread 合并器"""

    def merge(
        self,
        source_thread_id: str,
        target_thread_id: str,
        reason: str = "",
    ) -> dict[str, Any] | None:
        """
        合并两个 Thread。

        Args:
            source_thread_id: 源 Thread ID（将被删除）
            target_thread_id: 目标 Thread ID
            reason: 合并原因

        Returns:
            合并后的 Thread dict，失败返回 None
        """
        if source_thread_id == target_thread_id:
            logger.warning("Cannot merge thread with itself")
            return None

        with get_db() as conn:
            # 1. 获取源 Thread 的所有 items
            source_items = conn.execute(
                "SELECT item_id FROM thread_items WHERE thread_id = ?",
                (source_thread_id,)
            ).fetchall()

            # 2. 将 items 移动到目标 Thread
            for row in source_items:
                item_id = row["item_id"]
                # 检查是否已在目标 Thread 中
                existing = conn.execute(
                    "SELECT 1 FROM thread_items WHERE thread_id = ? AND item_id = ?",
                    (target_thread_id, item_id)
                ).fetchone()
                if not existing:
                    conn.execute(
                        "INSERT OR IGNORE INTO thread_items (thread_id, item_id, similarity) VALUES (?, ?, 1.0)",
                        (target_thread_id, item_id)
                    )

            # 3. 删除源 Thread 的 items
            conn.execute(
                "DELETE FROM thread_items WHERE thread_id = ?",
                (source_thread_id,)
            )

            # 4. 删除源 Thread
            conn.execute(
                "DELETE FROM threads WHERE id = ?",
                (source_thread_id,)
            )

            # 5. 更新目标 Thread 统计
            self._rebuild_thread_stats(conn, target_thread_id)

        logger.info("Merged thread %s into %s (reason: %s)", source_thread_id, target_thread_id, reason)
        return self.get_thread(target_thread_id)

    def _rebuild_thread_stats(self, conn: Any, thread_id: str) -> None:
        """重新计算 Thread 统计"""
        # 更新 item_count
        conn.execute(
            "UPDATE threads SET item_count = (SELECT COUNT(*) FROM thread_items WHERE thread_id = ?) WHERE id = ?",
            (thread_id, thread_id)
        )

        # 更新 platforms（从 items 表的 source_name 获取）
        conn.execute(
            """
            UPDATE threads SET platforms = (
                SELECT json_group_array(DISTINCT source_name)
                FROM items
                WHERE id IN (SELECT item_id FROM thread_items WHERE thread_id = ?)
                  AND source_name IS NOT NULL
            ) WHERE id = ?
            """,
            (thread_id, thread_id)
        )

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        """获取 Thread"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM threads WHERE id = ?",
                (thread_id,)
            ).fetchone()
            return dict(row) if row else None


# 全局单例
thread_merger = ThreadMerger()

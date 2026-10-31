"""
app/threads/split.py
Thread Split：拆分 Thread。

将指定 items 从 Thread 中移出，创建新的 Thread。
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.database import get_db

logger = logging.getLogger(__name__)


class ThreadSplitter:
    """Thread 拆分器"""

    def split(
        self,
        thread_id: str,
        item_ids: list[str],
        new_thread_title: str | None = None,
    ) -> dict[str, Any] | None:
        """
        从 Thread 中拆分出指定 items，创建新 Thread。

        Args:
            thread_id: 源 Thread ID
            item_ids: 要移出的 item ID 列表
            new_thread_title: 新 Thread 标题（可选）

        Returns:
            新 Thread dict，失败返回 None
        """
        if not item_ids:
            logger.warning("No items to split")
            return None

        with get_db() as conn:
            # 1. 获取源 Thread 信息
            source_thread = conn.execute(
                "SELECT * FROM threads WHERE id = ?",
                (thread_id,)
            ).fetchone()

            if not source_thread:
                logger.warning("Source thread not found: %s", thread_id)
                return None

            # 2. 创建新 Thread
            new_thread_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            # 获取第一个 item 的信息
            first_row = conn.execute(
                "SELECT * FROM items WHERE id = ?",
                (item_ids[0],)
            ).fetchone()
            first_item = dict(first_row) if first_row else None

            title = new_thread_title or (first_item["title"] if first_item else "Split Thread")
            platform = first_item.get("source_name", "") if first_item else ""

            conn.execute(
                """
                INSERT INTO threads (id, title, first_seen_at, last_seen_at, item_count, platforms)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (new_thread_id, title, now, now, len(item_ids), f'["{platform}"]')
            )

            # 3. 移动 items 到新 Thread
            # 拆出条目对源 Thread 的平均匹配相似度 = 两条故事线的关联强度
            ph = ",".join("?" for _ in item_ids)
            avg_sim_row = conn.execute(
                f"SELECT AVG(similarity) AS avg_sim FROM thread_items "
                f"WHERE thread_id = ? AND item_id IN ({ph})",
                (thread_id, *item_ids)
            ).fetchone()
            avg_similarity = avg_sim_row["avg_sim"] if avg_sim_row and avg_sim_row["avg_sim"] is not None else 0.5

            for item_id in item_ids:
                # 从源 Thread 移除
                conn.execute(
                    "DELETE FROM thread_items WHERE thread_id = ? AND item_id = ?",
                    (thread_id, item_id)
                )
                # 添加到新 Thread
                conn.execute(
                    "INSERT OR IGNORE INTO thread_items (thread_id, item_id, similarity) VALUES (?, ?, 1.0)",
                    (new_thread_id, item_id)
                )

            # 3.5 同步 items.thread_id 到新 Thread——该列是 thread 成员关系
            # 的外键镜像（merge 已修复同类问题）；不同步的话，后续对
            # 新 Thread 的 merge 会把旧 Thread 的条目错误重指
            conn.execute(
                f"UPDATE items SET thread_id = ? WHERE id IN ({ph})",
                (new_thread_id, *item_ids)
            )

            # 4. 更新源 Thread 统计
            self._rebuild_thread_stats(conn, thread_id)

            # 5. 拆分出的新 Thread 与源 Thread 显式关联为同一故事线
            a, b = sorted((thread_id, new_thread_id))
            conn.execute(
                "INSERT OR IGNORE INTO thread_relations (thread_a, thread_b, similarity, source) "
                "VALUES (?, ?, ?, 'split')",
                (a, b, avg_similarity)
            )

        logger.info("Split thread %s: %d items moved to new thread %s", thread_id, len(item_ids), new_thread_id)
        return self.get_thread(new_thread_id)

    def _rebuild_thread_stats(self, conn: Any, thread_id: str) -> None:
        """重新计算 Thread 统计"""
        conn.execute(
            "UPDATE threads SET item_count = (SELECT COUNT(*) FROM thread_items WHERE thread_id = ?) WHERE id = ?",
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
thread_splitter = ThreadSplitter()

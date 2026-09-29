"""
app/scheduler/cleanup.py
自动清理任务：删除 30 天前软删除的任务及其关联数据。
由 APScheduler 每天凌晨 3:00 触发。
"""
import logging

logger = logging.getLogger(__name__)


def cleanup_old_data() -> None:
    """
    清理策略：
    1. 回收没有任何存活条目的空 Thread（条目删除后 thread_items 会级联消失，
       但 threads 行会留下来，列表里变成"点开暂无内容"的空卡片）
    2. 找出 deleted_at < now-30days 的任务
    3. 删除其关联 items 和 task_executions
    4. 永久删除 tasks 记录

    不修改数据库 Schema，只做 DELETE 操作。
    """
    from app.core.database import get_db

    try:
        with get_db() as conn:
            # 空 Thread 回收：无条件执行（不依赖是否存在过期任务）
            empty_cur = conn.execute(
                """
                DELETE FROM threads
                WHERE NOT EXISTS (
                    SELECT 1 FROM thread_items ti
                    JOIN items i ON i.id = ti.item_id
                    WHERE ti.thread_id = threads.id
                )
                """
            )

            # 找出过期的已删除任务
            old_tasks = conn.execute(
                "SELECT id, name FROM tasks WHERE deleted_at < datetime('now', '-30 days')"
            ).fetchall()

            if not old_tasks:
                logger.info("[Cleanup] No expired tasks (reclaimed %d empty threads)",
                            empty_cur.rowcount)
                return

            task_ids   = [r["id"] for r in old_tasks]
            task_names = [r["name"] for r in old_tasks]
            ph = ",".join(["?"] * len(task_ids))

            # 删除关联采集结果
            item_cur = conn.execute(
                f"DELETE FROM items WHERE task_id IN ({ph})", task_ids
            )

            # 删除执行记录
            exec_cur = conn.execute(
                f"DELETE FROM task_executions WHERE task_id IN ({ph})", task_ids
            )

            # 永久删除任务
            task_cur = conn.execute(
                f"DELETE FROM tasks WHERE id IN ({ph})", task_ids
            )

        logger.info(
            "[Cleanup] Removed %d expired tasks (%s), %d items, %d executions, %d empty threads",
            task_cur.rowcount,
            ", ".join(task_names[:5]) + ("..." if len(task_names) > 5 else ""),
            item_cur.rowcount,
            exec_cur.rowcount,
            empty_cur.rowcount,
        )

    except Exception as e:
        logger.error("[Cleanup] Cleanup job failed: %s", e)

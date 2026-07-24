"""
app/repositories/execution_repo.py
task_executions 表的数据访问层
"""
import logging
import sqlite3
import uuid
from typing import Any

from app.core.database import get_db

logger = logging.getLogger(__name__)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


class ExecutionRepository:

    def insert(self, data: dict) -> dict:
        """插入执行记录"""
        exec_id = data.get("id") or str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO task_executions
                    (id, task_id, status, items_fetched, items_new,
                     duration_ms, error_message, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exec_id,
                    data["task_id"],
                    data["status"],
                    data.get("items_fetched", 0),
                    data.get("items_new", 0),
                    data.get("duration_ms", 0),
                    data.get("error_message"),
                    data["executed_at"],
                ),
            )
        return self.get(exec_id)

    def get(self, exec_id: str) -> dict | None:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM task_executions WHERE id = ?", (exec_id,)
            ).fetchone()
        return _row_to_dict(row) if row else None

    def list_by_task(
        self,
        task_id: str,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[dict], int]:
        """获取某个任务的执行历史，按时间倒序"""
        offset = (page - 1) * per_page
        with get_db() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM task_executions WHERE task_id = ?",
                (task_id,),
            ).fetchone()[0]

            rows = conn.execute(
                """
                SELECT * FROM task_executions
                WHERE task_id = ?
                ORDER BY executed_at DESC
                LIMIT ? OFFSET ?
                """,
                (task_id, per_page, offset),
            ).fetchall()

        return [_row_to_dict(r) for r in rows], total

    def get_latest_by_task(self, task_id: str) -> dict | None:
        """获取任务最近一次执行记录"""
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT * FROM task_executions
                WHERE task_id = ?
                ORDER BY executed_at DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        return _row_to_dict(row) if row else None


# 全局单例
execution_repo = ExecutionRepository()

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
        """插入执行记录。R2: 支持新指标字段。"""
        exec_id = data.get("id") or str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO task_executions
                    (id, task_id, status, items_fetched, items_new,
                     duration_ms, error_message, executed_at,
                     pages_count, items_seen, items_created, items_deduped,
                     last_error_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exec_id,
                    data.get("task_id", ""),
                    data.get("status", "unknown"),
                    data.get("items_fetched", 0),
                    data.get("items_new", 0),
                    data.get("duration_ms", 0),
                    data.get("error_message"),
                    data.get("executed_at"),
                    data.get("pages_count", 0),
                    data.get("items_seen", 0),
                    data.get("items_created", 0),
                    data.get("items_deduped", 0),
                    data.get("last_error_code"),
                ),
            )
        return self.get(exec_id)

    def get(self, exec_id: str) -> dict | None:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM task_executions WHERE id = ?", (exec_id,)
            ).fetchone()
        return _row_to_dict(row) if row else None

    def create_running(self, exec_id: str, task_id: str, executed_at: str) -> dict:
        """
        R2: 手动触发时先同步创建一条 'running' 占位行，
        包含 heartbeat_at 用于后续 stale 检测。
        """
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO task_executions
                    (id, task_id, status, items_fetched, items_new,
                     duration_ms, error_message, executed_at, heartbeat_at,
                     attempt, last_error_code, pages_count, items_seen,
                     items_created, items_updated, items_deduped)
                VALUES (?, ?, 'running', 0, 0, 0, NULL, ?, ?, 1, NULL, 0, 0, 0, 0, 0)
                """,
                (exec_id, task_id, executed_at, now),
            )
        return self.get(exec_id)

    def finalize(self, exec_id: str, data: dict, conn: sqlite3.Connection | None = None) -> dict | None:
        """将 'running' 占位行更新为最终状态（success/failure/warning/interrupted）。
        R2: 支持写入 pages_count, items_seen, items_created, items_deduped, last_error_code。
        R3: 支持传入外部 connection 以参与事务。
        """
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        def _do_finalize(conn_: sqlite3.Connection) -> None:
            conn_.execute(
                """
                UPDATE task_executions
                SET status = ?,
                    items_fetched = ?,
                    items_new = ?,
                    duration_ms = ?,
                    error_message = ?,
                    heartbeat_at = ?,
                    pages_count = ?,
                    items_seen = ?,
                    items_created = ?,
                    items_deduped = ?,
                    last_error_code = COALESCE(?, last_error_code)
                WHERE id = ?
                """,
                (
                    data.get("status", "failure"),
                    data.get("items_fetched", 0),
                    data.get("items_new", 0),
                    data.get("duration_ms", 0),
                    data.get("error_message"),
                    now,
                    data.get("pages_count", 0),
                    data.get("items_seen", 0),
                    data.get("items_created", 0),
                    data.get("items_deduped", 0),
                    data.get("last_error_code"),
                    exec_id,
                ),
            )

        if conn is not None:
            _do_finalize(conn)
        else:
            with get_db() as db_conn:
                _do_finalize(db_conn)

        return self.get(exec_id)

    def transition_to(
        self,
        exec_id: str,
        new_status: str,
        items_fetched: int | None = None,
        items_new: int | None = None,
        error_message: str | None = None,
    ) -> dict | None:
        """
        状态机流转：更新执行状态。
        同时记录 execution_event。
        """
        from app.execution.state import ExecutionState, can_transition

        # 获取当前状态
        current = self.get(exec_id)
        if not current:
            return None

        current_status = current.get("status", "running")

        # 检查流转合法性
        try:
            from_state = ExecutionState(current_status)
            to_state = ExecutionState(new_status)
            if not can_transition(from_state, to_state):
                logger.warning(
                    f"Invalid state transition: {current_status} -> {new_status} for exec {exec_id}"
                )
                return None
        except ValueError:
            # 未知状态，允许流转（向后兼容）
            pass

        # 更新状态
        with get_db() as conn:
            conn.execute(
                """
                UPDATE task_executions
                SET status = ?, items_fetched = COALESCE(?, items_fetched),
                    items_new = COALESCE(?, items_new),
                    error_message = COALESCE(?, error_message)
                WHERE id = ?
                """,
                (new_status, items_fetched, items_new, error_message, exec_id),
            )

        # 记录执行事件
        from app.repositories.execution_event_repo import execution_event_repo
        execution_event_repo.record(
            execution_id=exec_id,
            task_id=current.get("task_id", ""),
            event_type=new_status,
            message=f"Transition: {current_status} -> {new_status}",
            data={"from_status": current_status, "to_status": new_status},
        )

        return self.get(exec_id)

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
    def list_stale_running(self) -> list[dict]:
        """
        R1: 查找所有 'running' 状态的执行记录。
        进程重启时调用，这些记录对应的执行已随进程死亡，需要标记为 interrupted。
        """
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT * FROM task_executions
                WHERE status = 'running'
                ORDER BY executed_at ASC
                """,
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def recover_stale_executions(self) -> int:
        """
        R1: 进程重启恢复 — 将所有 'running' 记录标记为 'interrupted'。
        返回被恢复的记录数。
        """
        from app.execution.state import ExecutionState, can_transition

        stale = self.list_stale_running()
        recovered = 0
        for row in stale:
            exec_id = row["id"]
            current_status = row.get("status", "running")
            try:
                from_state = ExecutionState(current_status)
                to_state = ExecutionState.INTERRUPTED
                if can_transition(from_state, to_status):
                    self.transition_to(
                        exec_id,
                        "interrupted",
                        error_message="Process restarted during execution",
                    )
                    recovered += 1
                else:
                    # 直接更新状态（绕过状态机检查，因为 interrupted 可能不在允许列表中）
                    with get_db() as conn:
                        conn.execute(
                            """
                            UPDATE task_executions
                            SET status = 'interrupted',
                                error_message = 'Process restarted during execution'
                            WHERE id = ?
                            """,
                            (exec_id,),
                        )
                    recovered += 1
            except ValueError:
                # 未知状态，直接更新
                with get_db() as conn:
                    conn.execute(
                        """
                        UPDATE task_executions
                        SET status = 'interrupted',
                            error_message = 'Process restarted during execution'
                        WHERE id = ?
                        """,
                        (exec_id,),
                    )
                recovered += 1

        if recovered:
            logger.info("Recovery: marked %d stale 'running' executions as interrupted", recovered)
        return recovered

# 全局单例
execution_repo = ExecutionRepository()

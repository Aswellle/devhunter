"""
app/repositories/execution_event_repo.py
execution_events 表的数据访问层 - 持久化执行事件流
"""
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.database import get_db

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    if d.get("data") and isinstance(d["data"], str):
        try:
            d["data"] = json.loads(d["data"])
        except (json.JSONDecodeError, TypeError):
            d["data"] = {}
    return d


class ExecutionEventRepository:
    """执行事件持久化"""

    def record(
        self,
        execution_id: str,
        task_id: str,
        event_type: str,
        message: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """记录一条执行事件"""
        event_id = str(uuid.uuid4())
        now = _now_iso()
        data_json = json.dumps(data or {}, ensure_ascii=False)

        with get_db() as conn:
            conn.execute(
                """INSERT INTO execution_events
                   (id, execution_id, task_id, event_type, message, data, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (event_id, execution_id, task_id, event_type, message, data_json, now)
            )
        return self.get(event_id) or {}

    def get(self, event_id: str) -> dict[str, Any] | None:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM execution_events WHERE id = ?",
                (event_id,)
            ).fetchone()
            return _row_to_dict(row) if row else None

    def list_by_execution(
        self,
        execution_id: str,
        after_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        获取执行的所有事件，按时间正序。
        after_id: 用于断线补发，只返回此 ID 之后的事件。
        """
        query = "SELECT * FROM execution_events WHERE execution_id = ?"
        params: list[str] = [execution_id]

        if after_id:
            query += " AND created_at > (SELECT created_at FROM execution_events WHERE id = ?)"
            params.append(after_id)

        query += " ORDER BY created_at ASC"

        with get_db() as conn:
            rows = conn.execute(query, params).fetchall()
            return [_row_to_dict(r) for r in rows]

    def list_by_task(
        self,
        task_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """获取任务最近的事件"""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM execution_events WHERE task_id = ? ORDER BY created_at DESC LIMIT ?",
                (task_id, limit)
            ).fetchall()
            return [_row_to_dict(r) for r in rows]

    def get_latest(self, execution_id: str) -> dict[str, Any] | None:
        """获取执行的最新事件"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM execution_events WHERE execution_id = ? ORDER BY created_at DESC LIMIT 1",
                (execution_id,)
            ).fetchone()
            return _row_to_dict(row) if row else None


# 全局单例
execution_event_repo = ExecutionEventRepository()

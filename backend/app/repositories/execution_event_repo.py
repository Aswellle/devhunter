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
        created_at: str | None = None,
    ) -> dict[str, Any]:
        """
        记录一条执行事件。

        created_at：事件的真实发生时间（毫秒精度，由 event_bus 传入）。
        实时流与断线重放共用同一份时间戳——重放路径若在入库时重新取
        now，重放出的时间线会比实时流整体后移，步骤耗时随之失真。
        """
        event_id = str(uuid.uuid4())
        now = created_at or _now_iso()
        data_json = json.dumps(data or {}, ensure_ascii=False)

        # seq 在同一条 BEGIN IMMEDIATE 事务里读取并写入：SQLite 单写者，
        # 立即事务拿写锁后再读 MAX(seq)，并发 record() 不会拿到重复序号
        # （029 的唯一索引兜底；游标语义要求 seq 严格递增且唯一）
        with get_db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                seq = conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM execution_events"
                ).fetchone()[0]
                conn.execute(
                    """INSERT INTO execution_events
                       (id, execution_id, task_id, event_type, message, data,
                        created_at, seq)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (event_id, execution_id, task_id, event_type, message,
                     data_json, now, seq)
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
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

        query += " ORDER BY seq ASC"

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

    def max_seq(self) -> int:
        """全表当前最大 seq（029 起全局唯一递增）——SSE 水位线。"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM execution_events"
            ).fetchone()
            return int(row[0])

    def list_by_task_after(
        self,
        task_id: str,
        after_id: str | None = None,
        after_seq: int | None = None,
        up_to_seq: int | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """
        断线补发：任务维度取游标之后的事件，按 seq 正序。

        游标优先用 after_seq（全局唯一递增序号，029 起由写入路径分配）；
        after_id（旧客户端的 Last-Event-ID，事件 uuid）解析出该事件的 seq
        后等价处理——同一毫秒内排在其后的事件不再被时间戳比较漏掉。
        无法解析的旧游标安静返回空——等价于无游标从头订阅，不补发历史。
        """
        query = "SELECT * FROM execution_events WHERE task_id = ?"
        params: list[Any] = [task_id]
        if after_seq is not None:
            query += " AND seq > ?"
            params.append(after_seq)
        elif after_id:
            # 旧游标：uuid → seq。查不到（占位 0 / 未知 id）时条件为
            # seq > NULL 恒假，安静返回空，与旧行为一致
            query += " AND seq > (SELECT seq FROM execution_events WHERE id = ?)"
            params.append(after_id)
        if up_to_seq is not None:
            # 补发窗口上界（水位线）：水位线之后的事件留给实时通道
            query += " AND seq <= ?"
            params.append(up_to_seq)
        query += " ORDER BY seq ASC LIMIT ?"
        params.append(limit)
        with get_db() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_latest(self, execution_id: str) -> dict[str, Any] | None:
        """获取执行的最新事件"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM execution_events WHERE execution_id = ? ORDER BY seq DESC LIMIT 1",
                (execution_id,)
            ).fetchone()
            return _row_to_dict(row) if row else None


# 全局单例
execution_event_repo = ExecutionEventRepository()

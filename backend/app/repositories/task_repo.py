"""
app/repositories/task_repo.py
tasks 表的数据访问层 - 所有 SQL 操作封装于此
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
    # keywords: JSON 字符串 → Python list
    if d.get("keywords"):
        try:
            d["keywords"] = json.loads(d["keywords"])
        except (json.JSONDecodeError, TypeError):
            d["keywords"] = []
    else:
        d["keywords"] = []
    # config_snapshot: JSON 字符串 → Python dict
    if d.get("config_snapshot"):
        try:
            d["config_snapshot"] = json.loads(d["config_snapshot"])
        except (json.JSONDecodeError, TypeError):
            d["config_snapshot"] = None
    else:
        d["config_snapshot"] = None
    return d


class TaskRepository:

    def insert(self, data: dict) -> dict:
        """插入新任务，返回插入后的完整记录"""
        task_id = data.get("id") or str(uuid.uuid4())
        now = _now_iso()
        keywords_json = json.dumps(data.get("keywords") or [], ensure_ascii=False)
        config_snapshot_json = json.dumps(data.get("config_snapshot") or {}, ensure_ascii=False) if data.get("config_snapshot") else None

        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    id, name, source_url, template_id,
                    selector_list, selector_title, selector_link, selector_summary,
                    selector_next_page,
                    keywords, cron_expression, status,
                    consecutive_failures, consecutive_empty,
                    config_snapshot,
                    created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?,
                    ?, ?, 'active',
                    0, 0,
                    ?,
                    ?, ?
                )
                """,
                (
                    task_id,
                    data["name"],
                    data["source_url"],
                    data.get("template_id"),
                    data["selector_list"],
                    data["selector_title"],
                    data["selector_link"],
                    data.get("selector_summary"),
                    data.get("selector_next_page"),
                    keywords_json,
                    data["cron_expression"],
                    config_snapshot_json,
                    now, now,
                ),
            )
        return self.get(task_id)

    def get(self, task_id: str) -> dict | None:
        """根据 ID 获取任务（未删除）"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ? AND deleted_at IS NULL",
                (task_id,),
            ).fetchone()
        return _row_to_dict(row) if row else None

    def list_all(
        self,
        status: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict], int]:
        """
        返回 (任务列表, 总数)，支持按 status 过滤和分页。
        """
        conditions = ["deleted_at IS NULL"]
        params: list[Any] = []

        if status:
            conditions.append("status = ?")
            params.append(status)

        where = " AND ".join(conditions)
        offset = (page - 1) * per_page

        with get_db() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM tasks WHERE {where}", params
            ).fetchone()[0]

            rows = conn.execute(
                f"""
                SELECT * FROM tasks
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [per_page, offset],
            ).fetchall()

        return [_row_to_dict(r) for r in rows], total

    def count_all(self) -> int:
        """获取任务总数（未删除）"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE deleted_at IS NULL"
            ).fetchone()
        return row[0] if row else 0

    def list_active(self) -> list[dict]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = 'active' AND deleted_at IS NULL"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def update(self, task_id: str, data: dict) -> dict | None:
        """部分更新任务字段，返回更新后的记录"""
        if not data:
            return self.get(task_id)

        # 构建动态 SET 子句
        allowed_fields = {
            "name", "source_url", "template_id",
            "selector_list", "selector_title", "selector_link", "selector_summary",
            "selector_next_page",
            "keywords", "cron_expression", "status",
        }
        set_parts: list[str] = []
        values: list[Any] = []

        for field, value in data.items():
            if field not in allowed_fields:
                continue
            if field == "keywords":
                value = json.dumps(value or [], ensure_ascii=False)
            set_parts.append(f"{field} = ?")
            values.append(value)

        if not set_parts:
            return self.get(task_id)

        set_parts.append("updated_at = ?")
        values.append(_now_iso())
        values.append(task_id)

        with get_db() as conn:
            conn.execute(
                f"UPDATE tasks SET {', '.join(set_parts)} WHERE id = ? AND deleted_at IS NULL",
                values,
            )
        return self.get(task_id)

    def update_status(self, task_id: str, status: str) -> None:
        # D2: guard against a crawl finishing after its task was soft-deleted
        # mid-flight — without this, status flips on an already-deleted row.
        with get_db() as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                (status, _now_iso(), task_id),
            )

    def update_execution_stats(
        self,
        task_id: str,
        success: bool,
        empty: bool,
        executed_at: str,
    ) -> None:
        """
        更新连续失败/空结果计数，并设置 last_executed_at。
        - 成功且非空 → 重置两个计数
        - 失败 → consecutive_failures +1（达到 3 次自动 error）
        - 成功但空 → consecutive_empty +1

        D2 (same root cause as update_status): 所有分支都加
        AND deleted_at IS NULL，避免爬取在任务被软删除后完成时，
        仍然修改已删除行的统计/状态字段。
        """
        with get_db() as conn:
            if success and not empty:
                conn.execute(
                    """
                    UPDATE tasks
                    SET consecutive_failures = 0,
                        consecutive_empty = 0,
                        last_executed_at = ?,
                        updated_at = ?
                    WHERE id = ? AND deleted_at IS NULL
                    """,
                    (executed_at, _now_iso(), task_id),
                )
            elif not success:
                conn.execute(
                    """
                    UPDATE tasks
                    SET consecutive_failures = consecutive_failures + 1,
                        last_executed_at = ?,
                        updated_at = ?,
                        status = CASE
                            WHEN consecutive_failures + 1 >= 3 THEN 'error'
                            ELSE status
                        END
                    WHERE id = ? AND deleted_at IS NULL
                    """,
                    (executed_at, _now_iso(), task_id),
                )
            else:  # success but empty
                conn.execute(
                    """
                    UPDATE tasks
                    SET consecutive_empty = consecutive_empty + 1,
                        consecutive_failures = 0,
                        last_executed_at = ?,
                        updated_at = ?
                    WHERE id = ? AND deleted_at IS NULL
                    """,
                    (executed_at, _now_iso(), task_id),
                )

    def soft_delete(self, task_id: str) -> bool:
        """软删除任务，返回是否成功"""
        now = _now_iso()
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                (now, now, task_id),
            )
        return cursor.rowcount > 0


# 全局单例
task_repo = TaskRepository()

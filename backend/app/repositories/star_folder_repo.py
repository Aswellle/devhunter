"""
app/repositories/star_folder_repo.py
收藏分组（文件夹）数据访问层。
"""
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.database import get_db


def _now_iso() -> str:
    """毫秒精度 ISO 时间（与执行事件/调用记录一致，便于稳定排序）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


class StarFolderRepository:

    def list_with_counts(self) -> list[dict[str, Any]]:
        """
        列出全部文件夹及其收藏数。

        只统计仍处于收藏状态的条目：取消收藏后条目从文件夹视图消失，
        但保留 folder_id，重新收藏时回到原文件夹。
        """
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT f.id, f.name, f.created_at, f.updated_at,
                       COUNT(i.id) AS item_count
                FROM star_folders f
                LEFT JOIN items i
                       ON i.star_folder_id = f.id AND i.is_starred = 1
                GROUP BY f.id
                ORDER BY f.created_at ASC, f.id ASC
                """
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def starred_counts(self) -> tuple[int, int]:
        """返回 (收藏总数, 未分类收藏数)。"""
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN star_folder_id IS NULL THEN 1 ELSE 0 END) AS uncategorized
                FROM items
                WHERE is_starred = 1
                """
            ).fetchone()
        return int(row["total"] or 0), int(row["uncategorized"] or 0)

    def get(self, folder_id: str) -> dict[str, Any] | None:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM star_folders WHERE id = ?", (folder_id,)
            ).fetchone()
        return _row_to_dict(row) if row else None

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM star_folders WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
        return _row_to_dict(row) if row else None

    def create(self, name: str) -> dict[str, Any]:
        folder_id = str(uuid.uuid4())
        now = _now_iso()
        with get_db() as conn:
            conn.execute(
                "INSERT INTO star_folders (id, name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (folder_id, name, now, now),
            )
        return self.get(folder_id) or {}

    def rename(self, folder_id: str, name: str) -> dict[str, Any] | None:
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE star_folders SET name = ?, updated_at = ? WHERE id = ?",
                (name, _now_iso(), folder_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get(folder_id)

    def delete(self, folder_id: str) -> bool:
        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM star_folders WHERE id = ?", (folder_id,)
            )
        return cursor.rowcount > 0

    def assign(self, item_ids: list[str], folder_id: str | None) -> int:
        """把一批条目移入文件夹（folder_id=None 表示移出到未分类），返回影响行数。"""
        if not item_ids:
            return 0
        placeholders = ",".join(["?"] * len(item_ids))
        with get_db() as conn:
            cursor = conn.execute(
                f"UPDATE items SET star_folder_id = ? WHERE id IN ({placeholders})",
                [folder_id, *item_ids],
            )
        return cursor.rowcount


# 全局单例
star_folder_repo = StarFolderRepository()

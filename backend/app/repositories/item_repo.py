"""
app/repositories/item_repo.py
items 表的数据访问层 - CRUD + FTS5 全文搜索
"""
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
    # SQLite 的 0/1 转为 Python bool
    d["is_read"] = bool(d.get("is_read", 0))
    d["is_starred"] = bool(d.get("is_starred", 0))
    return d


class ItemRepository:

    def bulk_insert(self, items: list[dict]) -> int:
        """
        批量插入新条目（已经过去重，直接插入）。
        返回成功插入数量。
        """
        if not items:
            return 0

        now = _now_iso()
        inserted = 0

        with get_db() as conn:
            for item in items:
                item_id = item.get("id") or str(uuid.uuid4())
                try:
                    conn.execute(
                        """
                        INSERT INTO items
                            (id, task_id, title, url, url_hash, summary, fetched_at, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item_id,
                            item["task_id"],
                            item["title"],
                            item["url"],
                            item["url_hash"],
                            item.get("summary") or "",
                            item.get("fetched_at") or now,
                            now,
                        ),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    # url_hash UNIQUE 冲突（极少数竞争情况）
                    logger.debug("Duplicate url_hash, skip: %s", item.get("url_hash", "")[:16])

        return inserted

    def find_existing_hashes(self, hashes: list[str]) -> set[str]:
        """批量查询哪些 url_hash 已存在，返回已存在的 hash 集合"""
        if not hashes:
            return set()
        placeholders = ",".join(["?"] * len(hashes))
        with get_db() as conn:
            rows = conn.execute(
                f"SELECT url_hash FROM items WHERE url_hash IN ({placeholders})",
                hashes,
            ).fetchall()
        return {row["url_hash"] for row in rows}

    def query(
        self,
        task_id: str | None = None,
        search: str | None = None,
        starred: bool | None = None,
        is_read: bool | None = None,
        page: int = 1,
        per_page: int = 20,
        created_after: str | None = None,
    ) -> tuple[list[dict], int]:
        """
        分页查询采集结果，支持多维度过滤。
        返回 (条目列表, 总数)，列表项包含 task_name（LEFT JOIN）。
        """
        # 基础 JOIN（获取 task_name）
        base_from = """
            FROM items i
            LEFT JOIN tasks t ON i.task_id = t.id
        """
        conditions: list[str] = []
        params: list[Any] = []

        if task_id:
            conditions.append("i.task_id = ?")
            params.append(task_id)

        if starred is not None:
            conditions.append("i.is_starred = ?")
            params.append(1 if starred else 0)

        if is_read is not None:
            conditions.append("i.is_read = ?")
            params.append(1 if is_read else 0)

        if created_after:
            conditions.append("i.created_at >= ?")
            params.append(created_after)

        # 全文搜索逻辑
        if search and search.strip():
            # 尝试 FTS5，回退到 LIKE
            fts_term = search.strip().replace('"', '""')
            conditions.append(
                "i.rowid IN (SELECT rowid FROM items_fts WHERE items_fts MATCH ?)"
            )
            params.append(f'"{fts_term}"')

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        offset = (page - 1) * per_page

        with get_db() as conn:
            try:
                total = conn.execute(
                    f"SELECT COUNT(*) {base_from} {where}", params
                ).fetchone()[0]

                rows = conn.execute(
                    f"""
                    SELECT i.*, t.name AS task_name
                    {base_from}
                    {where}
                    ORDER BY i.fetched_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    params + [per_page, offset],
                ).fetchall()
            except sqlite3.OperationalError:
                # FTS 查询语法错误时回退到 LIKE
                logger.warning("FTS query failed, falling back to LIKE for: %s", search)
                return self._query_with_like(
                    task_id, search, starred, is_read, page, per_page
                )

        return [_row_to_dict(r) for r in rows], total

    def _query_with_like(
        self,
        task_id: str | None,
        search: str | None,
        starred: bool | None,
        is_read: bool | None,
        page: int,
        per_page: int,
    ) -> tuple[list[dict], int]:
        """LIKE 回退查询（FTS 不可用时）"""
        base_from = "FROM items i LEFT JOIN tasks t ON i.task_id = t.id"
        conditions: list[str] = []
        params: list[Any] = []

        if task_id:
            conditions.append("i.task_id = ?")
            params.append(task_id)
        if starred is not None:
            conditions.append("i.is_starred = ?")
            params.append(1 if starred else 0)
        if is_read is not None:
            conditions.append("i.is_read = ?")
            params.append(1 if is_read else 0)
        if search:
            conditions.append("(i.title LIKE ? OR i.summary LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        offset = (page - 1) * per_page

        with get_db() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) {base_from} {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"""
                SELECT i.*, t.name AS task_name
                {base_from} {where}
                ORDER BY i.fetched_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [per_page, offset],
            ).fetchall()

        return [_row_to_dict(r) for r in rows], total

    def get(self, item_id: str) -> dict | None:
        with get_db() as conn:
            row = conn.execute(
                "SELECT i.*, t.name AS task_name FROM items i LEFT JOIN tasks t ON i.task_id = t.id WHERE i.id = ?",
                (item_id,),
            ).fetchone()
        return _row_to_dict(row) if row else None

    def patch(self, item_id: str, data: dict) -> dict | None:
        """更新 is_read / is_starred，返回更新后记录"""
        allowed = {"is_read", "is_starred"}
        set_parts = []
        values = []
        for k, v in data.items():
            if k in allowed and v is not None:
                set_parts.append(f"{k} = ?")
                values.append(1 if v else 0)

        if not set_parts:
            return self.get(item_id)

        values.append(item_id)
        with get_db() as conn:
            conn.execute(
                f"UPDATE items SET {', '.join(set_parts)} WHERE id = ?",
                values,
            )
        return self.get(item_id)

    def batch_patch(self, ids: list[str], data: dict) -> int:
        """批量更新，返回影响行数"""
        allowed = {"is_read", "is_starred"}
        set_parts = []
        values = []
        for k, v in data.items():
            if k in allowed and v is not None:
                set_parts.append(f"{k} = ?")
                values.append(1 if v else 0)

        if not set_parts or not ids:
            return 0

        placeholders = ",".join(["?"] * len(ids))
        with get_db() as conn:
            cursor = conn.execute(
                f"UPDATE items SET {', '.join(set_parts)} WHERE id IN ({placeholders})",
                values + ids,
            )
        return cursor.rowcount

    def delete(self, item_id: str) -> bool:
        """删除单条目，返回是否删除成功"""
        with get_db() as conn:
            cursor = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        return cursor.rowcount > 0

    def batch_delete(self, ids: list[str]) -> int:
        """批量删除，返回删除行数"""
        if not ids:
            return 0
        placeholders = ",".join(["?"] * len(ids))
        with get_db() as conn:
            cursor = conn.execute(
                f"DELETE FROM items WHERE id IN ({placeholders})",
                ids,
            )
        return cursor.rowcount


# 全局单例
item_repo = ItemRepository()

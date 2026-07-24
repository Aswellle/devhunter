"""
app/repositories/thread_repo.py
threads 表和 thread_items 表的数据访问层
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
    # 解析 platforms JSON 字段
    if d.get("platforms") and isinstance(d["platforms"], str):
        try:
            d["platforms"] = json.loads(d["platforms"])
        except Exception:
            d["platforms"] = []
    # SQLite 0/1 -> bool
    return d


class ThreadRepository:

    # ── Thread CRUD ─────────────────────────────────────────────

    def create(self, title: str, item_id: str, platform: str) -> str:
        """创建新 Thread，关联第一个 Item。返回 thread_id"""
        thread_id = str(uuid.uuid4())
        now = _now_iso()
        platforms = json.dumps([platform], ensure_ascii=False)

        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO threads (id, title, first_seen_at, last_seen_at, item_count, platforms)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (thread_id, title, now, now, platforms),
            )
            conn.execute(
                """
                INSERT INTO thread_items (thread_id, item_id, similarity)
                VALUES (?, ?, 1.0)
                """,
                (thread_id, item_id),
            )
            # 更新 items.thread_id
            conn.execute(
                "UPDATE items SET thread_id = ? WHERE id = ?",
                (thread_id, item_id),
            )

        logger.debug("Thread created: %s (%s)", thread_id, title[:40])
        return thread_id

    def get(self, thread_id: str) -> dict | None:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM threads WHERE id = ?",
                (thread_id,),
            ).fetchone()
        return _row_to_dict(row) if row else None

    def list_all(
        self,
        task_id: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict], int]:
        """
        分页列出 Threads，支持按 task_id 过滤。
        Threads 按 first_seen_at DESC 排序（最新事件优先）。
        """
        offset = (page - 1) * per_page

        if task_id:
            base_from = """
                FROM threads th
                JOIN thread_items ti ON th.id = ti.thread_id
                JOIN items i ON ti.item_id = i.id
                WHERE i.task_id = ?
            """
            params: list[Any] = [task_id]
            with get_db() as conn:
                total = conn.execute(
                    f"SELECT COUNT(DISTINCT th.id) {base_from}",
                    params,
                ).fetchone()[0]
                rows = conn.execute(
                    f"""
                    SELECT DISTINCT th.id, th.title, th.first_seen_at, th.last_seen_at,
                           th.item_count, th.platforms
                    {base_from}
                    ORDER BY th.first_seen_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    params + [per_page, offset],
                ).fetchall()
        else:
            base_from = "FROM threads"
            params = []
            with get_db() as conn:
                total = conn.execute(
                    f"SELECT COUNT(*) {base_from}",
                    params,
                ).fetchone()[0]
                rows = conn.execute(
                    f"""
                    SELECT id, title, first_seen_at, last_seen_at, item_count, platforms
                    {base_from}
                    ORDER BY first_seen_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    params + [per_page, offset],
                ).fetchall()

        return [_row_to_dict(r) for r in rows], total

    def add_item(
        self,
        thread_id: str,
        item_id: str,
        similarity: float,
        title: str,
        platform: str,
    ) -> None:
        """
        将已有 Item 加入现有 Thread。
        更新 Thread 元数据（item_count、last_seen_at、platforms、title 取最长的）。
        """
        now = _now_iso()

        with get_db() as conn:
            # 插入关联
            conn.execute(
                """
                INSERT OR IGNORE INTO thread_items (thread_id, item_id, similarity)
                VALUES (?, ?, ?)
                """,
                (thread_id, item_id, similarity),
            )
            # 更新 items.thread_id
            conn.execute(
                "UPDATE items SET thread_id = ? WHERE id = ?",
                (thread_id, item_id),
            )
            # 更新 Thread 元数据
            # platforms: 添加新 platform（去重）
            th = conn.execute(
                "SELECT platforms, item_count, title FROM threads WHERE id = ?",
                (thread_id,),
            ).fetchone()
            if th:
                current_platforms: list[str] = json.loads(th["platforms"]) if th["platforms"] else []
                if platform and platform not in current_platforms:
                    current_platforms.append(platform)
                new_count = th["item_count"] + 1
                # title 取最长的（更完整的描述）
                new_title = title if len(title) > len(th["title"]) else th["title"]
                conn.execute(
                    """
                    UPDATE threads
                    SET item_count = ?, last_seen_at = ?,
                        platforms = ?, title = ?
                    WHERE id = ?
                    """,
                    (new_count, now, json.dumps(current_platforms, ensure_ascii=False), new_title, thread_id),
                )

    def get_items_in_thread(self, thread_id: str) -> list[dict]:
        """获取 Thread 内所有 Items，按 fetched_at 倒序"""
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT i.*, t.name AS task_name, ti.similarity
                FROM thread_items ti
                JOIN items i ON ti.item_id = i.id
                LEFT JOIN tasks t ON i.task_id = t.id
                WHERE ti.thread_id = ?
                ORDER BY i.fetched_at DESC
                """,
                (thread_id,),
            ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            d["is_read"] = bool(d.get("is_read", 0))
            d["is_starred"] = bool(d.get("is_starred", 0))
            result.append(d)
        return result

    def get_recent_items_for_comparison(
        self,
        hours: int = 24,
        limit: int = 500,
        min_age_seconds: int = 600,
    ) -> list[tuple[str, str, str]]:
        """
        获取 N 小时内未加入 Thread 的 Items，用于与新 Items 比较。
        只取至少 min_age_seconds 秒前创建的 Items（避免新插入的 Items 自己匹配自己）。
        返回: list of (item_id, title, fetched_at)
        """
        # datetime('now', '-10 minutes') 排除刚刚插入的 Items（避免同批次自匹配）
        with get_db() as conn:
            rows = conn.execute(
                f"""
                SELECT i.id, i.title, i.fetched_at
                FROM items i
                LEFT JOIN thread_items ti ON i.id = ti.item_id
                WHERE ti.item_id IS NULL
                  AND i.created_at < datetime('now', '-{min_age_seconds} seconds')
                ORDER BY i.fetched_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [(r["id"], r["title"], r["fetched_at"]) for r in rows]

    def delete_item_from_thread(self, item_id: str) -> None:
        """将 Item 从 Thread 中移除（用于 Item 删除时级联清理）"""
        with get_db() as conn:
            conn.execute(
                "DELETE FROM thread_items WHERE item_id = ?",
                (item_id,),
            )

    def rebuild_thread_stats(self, thread_id: str) -> None:
        """重新计算 Thread 的 item_count、platforms、title（Item 被删除后调用）"""
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT i.title, t.name AS task_name
                FROM thread_items ti
                JOIN items i ON ti.item_id = i.id
                LEFT JOIN tasks t ON i.task_id = t.id
                WHERE ti.thread_id = ?
                """,
                (thread_id,),
            ).fetchall()

            if not rows:
                # Thread 已空，删除
                conn.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
                return

            platforms = list({r["task_name"] for r in rows if r["task_name"]})
            titles = [r["title"] for r in rows]
            longest_title = max(titles, key=len) if titles else ""
            now = _now_iso()

            conn.execute(
                """
                UPDATE threads
                SET item_count = ?, platforms = ?, title = ?
                WHERE id = ?
                """,
                (len(rows), json.dumps(platforms, ensure_ascii=False), longest_title, thread_id),
            )


# 全局单例
thread_repo = ThreadRepository()
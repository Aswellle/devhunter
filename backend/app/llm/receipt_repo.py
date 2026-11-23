"""
app/llm/receipt_repo.py
model_receipts 表的数据访问层：LLM 付费回执的落账与复用查询。
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.database import get_db


def _now_iso() -> str:
    """
    毫秒精度 UTC 时间戳。

    秒级精度下同一秒的多条回执只能靠 id 决定先后（UUID 随机），
    游标分页的"上一页末条"锚点因此不稳定（新记录可能落到锚点之后）。
    毫秒精度让 created_at 本身单调，翻页锚点才有意义。
    """
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class ModelReceiptRepository:

    def find_done_result(self, model: str, prompt_hash: str) -> str | None:
        """相同 (model, prompt_hash) 的已完成调用正文——命中则复用，不重复付费"""
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT result_text FROM model_receipts
                WHERE model = ? AND prompt_hash = ? AND status = 'done'
                ORDER BY created_at DESC LIMIT 1
                """,
                (model, prompt_hash),
            ).fetchone()
        return row["result_text"] if row else None

    def create_pending(self, purpose: str, model: str, prompt_hash: str) -> str:
        """回执先行：调用前落一条 pending 记账"""
        receipt_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO model_receipts (id, purpose, model, prompt_hash, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (receipt_id, purpose, model, prompt_hash, _now_iso()),
            )
        return receipt_id

    def complete(
        self,
        receipt_id: str,
        result_text: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int,
    ) -> None:
        with get_db() as conn:
            conn.execute(
                """
                UPDATE model_receipts
                SET status = 'done', result_text = ?, input_tokens = ?,
                    output_tokens = ?, duration_ms = ?
                WHERE id = ?
                """,
                (result_text, input_tokens, output_tokens, duration_ms, receipt_id),
            )

    def fail(self, receipt_id: str, error: str) -> None:
        with get_db() as conn:
            conn.execute(
                "UPDATE model_receipts SET status = 'failed', error = ? WHERE id = ?",
                (error[:500], receipt_id),
            )

    def tokens_since(self, since_iso: str) -> int:
        """自某时刻起（含）已完成调用的 token 总消耗（输入+输出）"""
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)), 0) AS total
                FROM model_receipts
                WHERE status = 'done' AND created_at >= ?
                """,
                (since_iso,),
            ).fetchone()
        return int(row["total"])

    def usage_summary(self, since_iso: str) -> dict[str, int]:
        """自某时刻起（含）的调用次数与消耗汇总（含失败，供用量页展示）"""
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS calls,
                    COALESCE(SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END), 0) AS done_calls,
                    COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_calls,
                    COALESCE(SUM(CASE WHEN status = 'done'
                        THEN COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0) END), 0) AS tokens
                FROM model_receipts
                WHERE created_at >= ?
                """,
                (since_iso,),
            ).fetchone()
        return {
            "calls": int(row["calls"]),
            "done": int(row["done_calls"]),
            "failed": int(row["failed_calls"]),
            "tokens": int(row["tokens"]),
        }

    def stats(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """
        最近回执（offset 分页，兼容旧调用方）。

        排序与游标分页保持一致（created_at DESC, id DESC）：同一秒内的多条
        回执按 id 稳定排序，否则 offset 路径取到的"页末条"在游标路径下
        可能不是真正的前一锚点，切换分页方式时会漏项。
        """
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT id, purpose, model, status, input_tokens, output_tokens,
                       duration_ms, error, created_at
                FROM model_receipts ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def stats_page(
        self, limit: int = 20, before: tuple[str, str] | None = None,
    ) -> tuple[list[dict[str, Any]], tuple[str, str] | None]:
        """
        游标（keyset）分页：按 (created_at, id) 倒序，返回 (本页, 下一页游标)。

        offset 分页在"边翻页边有新调用"时会整体错位（新记录插到队首，
        offset 4 变成原来的第 3 条，翻页会重复或漏项）。keyset 以
        「上一页最后一条的 (created_at, id)」为锚点，翻页期间新增记录
        只会出现在第一页之前，不会扰动后续页。

        游标为 (created_at, id) 二元组；None 表示已到末页。
        """
        with get_db() as conn:
            if before is None:
                rows = conn.execute(
                    """
                    SELECT id, purpose, model, status, input_tokens, output_tokens,
                           duration_ms, error, created_at
                    FROM model_receipts
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                before_created, before_id = before
                rows = conn.execute(
                    """
                    SELECT id, purpose, model, status, input_tokens, output_tokens,
                           duration_ms, error, created_at
                    FROM model_receipts
                    WHERE created_at < ? OR (created_at = ? AND id < ?)
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                    """,
                    (before_created, before_created, before_id, limit),
                ).fetchall()

        items = [dict(r) for r in rows]
        next_cursor = None
        if len(items) == limit:
            last = items[-1]
            next_cursor = (last["created_at"], last["id"])
        return items, next_cursor

    def count_all(self) -> int:
        """回执总数（分页用）"""
        with get_db() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM model_receipts").fetchone()
        return int(row["n"])


# 全局单例
model_receipt_repo = ModelReceiptRepository()

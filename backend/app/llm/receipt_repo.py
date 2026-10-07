"""
app/llm/receipt_repo.py
model_receipts 表的数据访问层：LLM 付费回执的落账与复用查询。
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.database import get_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
        """最近回执（分页，created_at 倒序）"""
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT id, purpose, model, status, input_tokens, output_tokens,
                       duration_ms, error, created_at
                FROM model_receipts ORDER BY created_at DESC LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_all(self) -> int:
        """回执总数（分页用）"""
        with get_db() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM model_receipts").fetchone()
        return int(row["n"])


# 全局单例
model_receipt_repo = ModelReceiptRepository()

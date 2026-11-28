"""
app/repositories/opportunity_repo.py
机会板数据访问（PROD-005，migration 035）。
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.database import get_db

logger = logging.getLogger(__name__)

_STATUSES = ("inbox", "investigating", "planned", "building", "shipped", "dismissed")
_TYPES = (
    "user_problem", "product_launch", "open_source_project",
    "hiring", "collaboration", "trend", "technical_risk", "idea",
)
_PRIORITIES = ("low", "normal", "high")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    if isinstance(d.get("tags_json"), str):
        try:
            d["tags"] = json.loads(d["tags_json"])
        except Exception:
            d["tags"] = []
    return d


class OpportunityRepository:
    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        opp_id = str(uuid.uuid4())
        now = _now_iso()
        status = data.get("status") if data.get("status") in _STATUSES else "inbox"
        opp_type = data.get("opportunity_type") if data.get("opportunity_type") in _TYPES else "idea"
        priority = data.get("priority") if data.get("priority") in _PRIORITIES else "normal"
        with get_db() as conn:
            conn.execute(
                """INSERT INTO opportunities
                   (id, origin_type, origin_id, title, opportunity_type, status,
                    priority, value_score, notes, tags_json, remind_at,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (opp_id, data["origin_type"], data["origin_id"], data["title"][:300],
                 opp_type, status, priority, data.get("value_score"),
                 data.get("notes") or "",
                 json.dumps(data.get("tags") or [], ensure_ascii=False),
                 data.get("remind_at"), now, now),
            )
            conn.execute(
                """INSERT INTO opportunity_events
                   (id, opportunity_id, event_type, to_value, created_at)
                   VALUES (?, ?, 'created', ?, ?)""",
                (str(uuid.uuid4()), opp_id, status, now),
            )
        return self.get(opp_id) or {}

    def get(self, opp_id: str) -> dict[str, Any] | None:
        with get_db() as conn:
            return _row(conn.execute(
                "SELECT * FROM opportunities WHERE id = ?", (opp_id,)
            ).fetchone())

    def list(
        self,
        status: str | None = None,
        origin_type: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM opportunities"
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if origin_type:
            clauses.append("origin_type = ?")
            params.append(origin_type)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with get_db() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row(r) for r in rows]

    def update(
        self,
        opp_id: str,
        data: dict[str, Any],
        event_type: str | None = None,
        from_value: str | None = None,
        to_value: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any] | None:
        current = self.get(opp_id)
        if not current:
            return None
        fields, params = [], []
        if data.get("title") is not None:
            fields.append("title = ?")
            params.append(data["title"][:300])
        if data.get("opportunity_type") in _TYPES:
            fields.append("opportunity_type = ?")
            params.append(data["opportunity_type"])
        if data.get("status") in _STATUSES:
            fields.append("status = ?")
            params.append(data["status"])
        if data.get("priority") in _PRIORITIES:
            fields.append("priority = ?")
            params.append(data["priority"])
        if "value_score" in data:
            fields.append("value_score = ?")
            params.append(data["value_score"])
        if data.get("notes") is not None:
            fields.append("notes = ?")
            params.append(data["notes"])
        if data.get("tags") is not None:
            fields.append("tags_json = ?")
            params.append(json.dumps(data["tags"], ensure_ascii=False))
        if "remind_at" in data:
            fields.append("remind_at = ?")
            params.append(data["remind_at"])
        # 事件-only 更新（状态/优先级/笔记/标签/提醒变更的审计记录）：
        # 没有字段变更时也必须写事件，不能提前返回丢掉审计
        if fields:
            fields.append("updated_at = ?")
            params.append(_now_iso())
            params.append(opp_id)
        with get_db() as conn:
            if fields:
                conn.execute(
                    f"UPDATE opportunities SET {', '.join(fields)} WHERE id = ?", params
                )
            if event_type:
                conn.execute(
                    """INSERT INTO opportunity_events
                       (id, opportunity_id, event_type, from_value, to_value, note, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (str(uuid.uuid4()), opp_id, event_type, from_value, to_value,
                     note, _now_iso()),
                )
        return self.get(opp_id)

    def get_events(self, opp_id: str) -> list[dict[str, Any]]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM opportunity_events WHERE opportunity_id = ?"
                " ORDER BY created_at ASC",
                (opp_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, opp_id: str) -> bool:
        with get_db() as conn:
            cursor = conn.execute("DELETE FROM opportunities WHERE id = ?", (opp_id,))
        return cursor.rowcount > 0


opportunity_repo = OpportunityRepository()

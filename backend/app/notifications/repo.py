"""
app/notifications/repo.py
通知渠道 / 规则 / 投递记录的数据访问（PROD-003，migration 034）。
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


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    if d.get("config_json"):
        try:
            d["config"] = json.loads(d["config_json"])
        except Exception:
            d["config"] = {}
    if d.get("payload_json"):
        try:
            d["payload"] = json.loads(d["payload_json"])
        except Exception:
            d["payload"] = {}
    return d


class NotificationRepository:
    # ── 渠道 ────────────────────────────────────────────────
    def create_channel(self, name: str, url: str, enabled: bool = True) -> dict[str, Any]:
        channel_id = str(uuid.uuid4())
        now = _now_iso()
        with get_db() as conn:
            conn.execute(
                "INSERT INTO notification_channels (id, name, url, enabled, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (channel_id, name, url, 1 if enabled else 0, now, now),
            )
        return self.get_channel(channel_id) or {}

    def get_channel(self, channel_id: str) -> dict[str, Any] | None:
        with get_db() as conn:
            return _row(conn.execute(
                "SELECT * FROM notification_channels WHERE id = ?", (channel_id,)
            ).fetchone())

    def list_channels(self) -> list[dict[str, Any]]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM notification_channels ORDER BY created_at DESC"
            ).fetchall()
        return [_row(r) for r in rows]

    def update_channel(self, channel_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        fields, params = [], []
        for key in ("name", "url"):
            if key in data and data[key] is not None:
                fields.append(f"{key} = ?")
                params.append(data[key])
        if "enabled" in data and data["enabled"] is not None:
            fields.append("enabled = ?")
            params.append(1 if data["enabled"] else 0)
        if not fields:
            return self.get_channel(channel_id)
        fields.append("updated_at = ?")
        params.append(_now_iso())
        params.append(channel_id)
        with get_db() as conn:
            conn.execute(
                f"UPDATE notification_channels SET {', '.join(fields)} WHERE id = ?",
                params,
            )
        return self.get_channel(channel_id)

    def delete_channel(self, channel_id: str) -> bool:
        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM notification_channels WHERE id = ?", (channel_id,)
            )
        return cursor.rowcount > 0

    # ── 规则 ────────────────────────────────────────────────
    def create_rule(
        self,
        name: str,
        trigger_type: str,
        config: dict[str, Any],
        channel_id: str,
        enabled: bool = True,
    ) -> dict[str, Any]:
        rule_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                "INSERT INTO notification_rules"
                " (id, name, trigger_type, config_json, channel_id, enabled, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rule_id, name, trigger_type,
                 json.dumps(config, ensure_ascii=False), channel_id,
                 1 if enabled else 0, _now_iso()),
            )
        return self.get_rule(rule_id) or {}

    def get_rule(self, rule_id: str) -> dict[str, Any] | None:
        with get_db() as conn:
            return _row(conn.execute(
                "SELECT * FROM notification_rules WHERE id = ?", (rule_id,)
            ).fetchone())

    def list_rules(self, trigger_type: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM notification_rules"
        params: list[Any] = []
        if trigger_type:
            query += " WHERE trigger_type = ?"
            params.append(trigger_type)
        query += " ORDER BY created_at DESC"
        with get_db() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row(r) for r in rows]

    def list_enabled_rules(self, trigger_type: str) -> list[dict[str, Any]]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM notification_rules WHERE trigger_type = ? AND enabled = 1",
                (trigger_type,),
            ).fetchall()
        return [_row(r) for r in rows]

    def update_rule(self, rule_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        fields, params = [], []
        if data.get("name") is not None:
            fields.append("name = ?")
            params.append(data["name"])
        if data.get("config") is not None:
            fields.append("config_json = ?")
            params.append(json.dumps(data["config"], ensure_ascii=False))
        if data.get("channel_id") is not None:
            fields.append("channel_id = ?")
            params.append(data["channel_id"])
        if data.get("enabled") is not None:
            fields.append("enabled = ?")
            params.append(1 if data["enabled"] else 0)
        if not fields:
            return self.get_rule(rule_id)
        params.append(rule_id)
        with get_db() as conn:
            conn.execute(
                f"UPDATE notification_rules SET {', '.join(fields)} WHERE id = ?",
                params,
            )
        return self.get_rule(rule_id)

    def delete_rule(self, rule_id: str) -> bool:
        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM notification_rules WHERE id = ?", (rule_id,)
            )
        return cursor.rowcount > 0

    def mark_rule_fired(self, rule_id: str) -> None:
        with get_db() as conn:
            conn.execute(
                "UPDATE notification_rules SET last_fired_at = ? WHERE id = ?",
                (_now_iso(), rule_id),
            )

    # ── 投递 ────────────────────────────────────────────────
    def enqueue(
        self,
        rule_id: str,
        channel_id: str,
        event_key: str,
        payload: dict[str, Any],
    ) -> bool:
        """入队一条投递；(rule_id, event_key) 唯一 → 同事件幂等。

        返回是否真的新建（重复事件返回 False）。"""
        with get_db() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO notification_deliveries"
                " (id, rule_id, channel_id, event_key, payload_json, status,"
                "  attempts, next_attempt_at)"
                " VALUES (?, ?, ?, ?, ?, 'pending', 0, ?)",
                (str(uuid.uuid4()), rule_id, channel_id, event_key,
                 json.dumps(payload, ensure_ascii=False), _now_iso()),
            )
        return cursor.rowcount > 0

    def list_pending_deliveries(self, limit: int = 50) -> list[dict[str, Any]]:
        """到期待投递（pending/failed 且 next_attempt_at 已到或为空）。"""
        now = _now_iso()
        with get_db() as conn:
            rows = conn.execute(
                """SELECT * FROM notification_deliveries
                   WHERE status IN ('pending', 'failed')
                     AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                   ORDER BY created_at ASC LIMIT ?""",
                (now, limit),
            ).fetchall()
        return [_row(r) for r in rows]

    def list_deliveries_for_rule(self, rule_id: str) -> list[dict[str, Any]]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM notification_deliveries WHERE rule_id = ?"
                " ORDER BY created_at DESC",
                (rule_id,),
            ).fetchall()
        return [_row(r) for r in rows]

    def list_recent_deliveries(self, limit: int = 100) -> list[dict[str, Any]]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM notification_deliveries ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row(r) for r in rows]

    def mark_sent(self, delivery_id: str) -> None:
        with get_db() as conn:
            conn.execute(
                "UPDATE notification_deliveries SET status = 'sent', sent_at = ?,"
                " attempts = attempts + 1, last_error = NULL, next_attempt_at = NULL"
                " WHERE id = ?",
                (_now_iso(), delivery_id),
            )

    def mark_failed(
        self,
        delivery_id: str,
        error: str,
        next_attempt_at: str | None,
        dead: bool,
    ) -> None:
        with get_db() as conn:
            conn.execute(
                "UPDATE notification_deliveries SET status = ?, attempts = attempts + 1,"
                " last_error = ?, next_attempt_at = ? WHERE id = ?",
                ("dead" if dead else "failed", error[:500], next_attempt_at, delivery_id),
            )

    def reset_for_retry(self, delivery_id: str) -> bool:
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE notification_deliveries SET status = 'pending', attempts = 0,"
                " next_attempt_at = ?, last_error = NULL WHERE id = ?",
                (_now_iso(), delivery_id),
            )
        return cursor.rowcount > 0


notification_repo = NotificationRepository()


# ── 模块级便捷函数（服务层与测试的稳定入口）──────────────────────
def create_channel(name: str, url: str, enabled: bool = True) -> dict[str, Any]:
    return notification_repo.create_channel(name, url, enabled)


def get_channel(channel_id: str) -> dict[str, Any] | None:
    return notification_repo.get_channel(channel_id)


def list_channels() -> list[dict[str, Any]]:
    return notification_repo.list_channels()


def update_channel(channel_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    return notification_repo.update_channel(channel_id, data)


def delete_channel(channel_id: str) -> bool:
    return notification_repo.delete_channel(channel_id)


def create_rule(
    name: str,
    trigger_type: str,
    config: dict[str, Any],
    channel_id: str,
    enabled: bool = True,
) -> dict[str, Any]:
    return notification_repo.create_rule(name, trigger_type, config, channel_id, enabled)


def update_rule(rule_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    return notification_repo.update_rule(rule_id, data)


def delete_rule(rule_id: str) -> bool:
    return notification_repo.delete_rule(rule_id)


def list_rules(trigger_type: str | None = None) -> list[dict[str, Any]]:
    return notification_repo.list_rules(trigger_type)


def list_pending_deliveries(limit: int = 50) -> list[dict[str, Any]]:
    return notification_repo.list_pending_deliveries(limit)


def list_deliveries_for_rule(rule_id: str) -> list[dict[str, Any]]:
    return notification_repo.list_deliveries_for_rule(rule_id)


def list_recent_deliveries(limit: int = 100) -> list[dict[str, Any]]:
    return notification_repo.list_recent_deliveries(limit)

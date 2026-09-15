"""
app/sources/registry.py
Template Registry：预设 + 自定义模板的单一数据源。

所有模板（preset / custom / imported）统一存储在 source_templates 表中。
向后兼容：保留 PRESET_TEMPLATES 常量作为 fallback。
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
    if d.get("config_json") and isinstance(d["config_json"], str):
        try:
            d["config"] = json.loads(d["config_json"])
        except (json.JSONDecodeError, TypeError):
            d["config"] = {}
    else:
        d["config"] = {}
    return d


class SourceTemplateRegistry:
    """模板注册表：CRUD + 查询"""

    def get(self, template_id: str) -> dict[str, Any] | None:
        """根据 ID 获取模板"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM source_templates WHERE id = ?",
                (template_id,)
            ).fetchone()
            return _row_to_dict(row) if row else None

    def list_all(
        self,
        kind: str | None = None,
        status: str | None = None,
        owner_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """列出模板，支持筛选"""
        query = "SELECT * FROM source_templates WHERE 1=1"
        params: list[str] = []
        if kind:
            query += " AND kind = ?"
            params.append(kind)
        if status:
            query += " AND status = ?"
            params.append(status)
        if owner_type:
            query += " AND owner_type = ?"
            params.append(owner_type)
        query += " ORDER BY name"

        with get_db() as conn:
            rows = conn.execute(query, params).fetchall()
            return [_row_to_dict(r) for r in rows]

    def exists(self, template_id: str) -> bool:
        """检查模板是否存在"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT 1 FROM source_templates WHERE id = ?",
                (template_id,)
            ).fetchone()
            return row is not None

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """创建模板"""
        template_id = data.get("id") or str(uuid.uuid4())
        now = _now_iso()
        config_json = json.dumps(data.get("config", {}), ensure_ascii=False)

        with get_db() as conn:
            conn.execute(
                """INSERT INTO source_templates
                   (id, owner_type, owner_id, kind, schema_version, version,
                    name, config_json, status, health_score, last_validated_at,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    template_id,
                    data.get("owner_type", "system"),
                    data.get("owner_id"),
                    data.get("kind", "preset"),
                    data.get("schema_version", 2),
                    data.get("version", 1),
                    data.get("name", ""),
                    config_json,
                    data.get("status", "draft"),
                    data.get("health_score", 0.0),
                    data.get("last_validated_at"),
                    now,
                    now,
                )
            )
        return self.get(template_id) or {}

    def update(self, template_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """更新模板"""
        now = _now_iso()
        config_json = json.dumps(data.get("config", {}), ensure_ascii=False) if "config" in data else None

        with get_db() as conn:
            conn.execute(
                """UPDATE source_templates SET
                    name = ?, config_json = ?, status = ?,
                    health_score = ?, last_validated_at = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    data.get("name", ""),
                    config_json or "{}",
                    data.get("status", "draft"),
                    data.get("health_score", 0.0),
                    data.get("last_validated_at"),
                    now,
                    template_id,
                )
            )
        return self.get(template_id)

    def update_health(self, template_id: str, health_score: float, status: str) -> None:
        """更新健康状态"""
        now = _now_iso()
        with get_db() as conn:
            conn.execute(
                """UPDATE source_templates SET
                    health_score = ?, status = ?, last_validated_at = ?, updated_at = ?
                   WHERE id = ?""",
                (health_score, status, now, now, template_id)
            )

    def delete(self, template_id: str) -> bool:
        """删除模板"""
        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM source_templates WHERE id = ?",
                (template_id,)
            )
            return cursor.rowcount > 0

    def apply_to_task(self, template_id: str, task_data: dict[str, Any]) -> dict[str, Any]:
        """
        将模板配置合并到 task_data（用户数据优先）。
        若字段为空则从模板填充。
        """
        tpl = self.get(template_id)
        if not tpl:
            return task_data

        config = tpl.get("config", {})
        result = dict(task_data)

        # 从 config 中提取字段（仅在字段为空时填充）
        if not result.get("source_url"):
            result["source_url"] = config.get("source", {}).get("url", "")
        if not result.get("selector_list"):
            result["selector_list"] = config.get("fields", {}).get("list", "")
        if not result.get("selector_title"):
            result["selector_title"] = config.get("fields", {}).get("title", "")
        if not result.get("selector_link"):
            result["selector_link"] = config.get("fields", {}).get("link", "")
        if result.get("selector_summary") is None:
            result["selector_summary"] = config.get("fields", {}).get("summary")

        # 保存模板版本快照
        result["template_id"] = template_id
        result["template_version"] = tpl.get("version", 1)

        return result


# 全局单例
template_registry = SourceTemplateRegistry()

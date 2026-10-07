"""
app/repositories/settings_repo.py
app_settings 表的数据访问层：应用运行时设置的 KV 存取。

用于存放用户经界面配置的运行参数（当前为 LLM 接入配置），
与 .env 的分工：.env 是部署期默认值，这里是运行期覆盖值。
"""
from app.core.database import get_db


class AppSettingsRepository:

    def get(self, key: str) -> str | None:
        """读取设置值；未设置返回 None"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()
        return row["value"] if row else None

    def set(self, key: str, value: str) -> None:
        """写入/覆盖设置值（upsert）"""
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value),
            )

    def delete(self, key: str) -> None:
        """删除设置；不存在时静默（幂等）"""
        with get_db() as conn:
            conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))


# 全局单例
app_settings_repo = AppSettingsRepository()

-- ===========================================
-- migrations/024_app_settings.sql
-- 应用运行时设置（KV）：存放用户经界面配置的运行参数。
-- 当前用于 LLM 接入配置（llm_api_key / llm_base_url / llm_model），
-- 界面保存的值优先于 .env 环境变量；清除后回落环境变量。
-- ===========================================
CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

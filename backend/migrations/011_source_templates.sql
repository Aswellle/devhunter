-- ===========================================
-- migrations/011_source_templates.sql
-- Template Registry: 单一数据源
-- ===========================================

-- source_templates 表：预设 + 自定义模板的统一注册表
CREATE TABLE IF NOT EXISTS source_templates (
    id                TEXT PRIMARY KEY,
    owner_type        TEXT NOT NULL DEFAULT 'system',  -- system | user
    owner_id          TEXT,                            -- user_id (自定义模板时)
    kind              TEXT NOT NULL,                   -- preset | custom | imported
    schema_version    INTEGER NOT NULL DEFAULT 2,
    version           INTEGER NOT NULL DEFAULT 1,
    name              TEXT NOT NULL,
    config_json       TEXT NOT NULL,                   -- 完整配置 JSON
    status            TEXT NOT NULL DEFAULT 'draft',    -- draft | healthy | degraded | broken
    health_score      REAL DEFAULT 0,                  -- 0-100
    last_validated_at TEXT,
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_source_templates_kind ON source_templates(kind);
CREATE INDEX IF NOT EXISTS idx_source_templates_status ON source_templates(status);
CREATE INDEX IF NOT EXISTS idx_source_templates_owner ON source_templates(owner_type, owner_id);

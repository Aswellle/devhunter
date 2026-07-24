-- ===========================================
-- migrations/001_init.sql
-- DevHunter 核心表建表语句（SQLite 兼容）
-- ===========================================

-- SQLite WAL 模式在连接层配置，非 SQL 语句
-- PRAGMA journal_mode=WAL;
-- PRAGMA busy_timeout=5000;
-- PRAGMA foreign_keys=ON;

-- -------------------------------------------
-- tasks 表：采集任务
-- -------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id                   TEXT PRIMARY KEY,          -- UUID v4 字符串
    name                 TEXT NOT NULL,             -- 任务名称（应用层限制 100 字符）
    source_url           TEXT NOT NULL,             -- 目标页面 URL
    template_id          TEXT,                      -- 预设模板标识，NULL = 自定义
    selector_list        TEXT NOT NULL,             -- 列表项 CSS Selector
    selector_title       TEXT NOT NULL,             -- 标题 Selector（相对于列表项）
    selector_link        TEXT NOT NULL,             -- 链接 Selector（相对于列表项）
    selector_summary     TEXT,                      -- 摘要 Selector（可选）
    keywords             TEXT,                      -- JSON 数组格式，如 '["React","Python"]'
    cron_expression      TEXT NOT NULL,             -- Cron 表达式（5 段）
    status               TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'paused', 'error')),
    consecutive_failures INTEGER NOT NULL DEFAULT 0, -- 连续失败次数
    consecutive_empty    INTEGER NOT NULL DEFAULT 0, -- 连续空结果次数
    last_executed_at     TEXT,                      -- 最近执行时间
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at           TEXT                       -- 软删除时间戳，NULL = 未删除
);

-- 按状态筛选活跃任务（调度启动时批量加载，WHERE 部分索引 SQLite 3.8+）
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

-- -------------------------------------------
-- items 表：采集结果条目
-- -------------------------------------------
CREATE TABLE IF NOT EXISTS items (
    id          TEXT PRIMARY KEY,                   -- UUID v4 字符串
    task_id     TEXT NOT NULL REFERENCES tasks(id),
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    url_hash    TEXT NOT NULL,                      -- sha256(normalized_url)，64 字符 hex
    summary     TEXT,
    is_read     INTEGER NOT NULL DEFAULT 0,         -- 0=未读, 1=已读
    is_starred  INTEGER NOT NULL DEFAULT 0,         -- 0=未收藏, 1=已收藏
    fetched_at  TEXT NOT NULL,                      -- 采集时间（ISO 8601）
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- 全局去重（UNIQUE 索引，跨任务）
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_url_hash ON items(url_hash);

-- 按任务 + 时间倒序（任务结果列表主查询）
CREATE INDEX IF NOT EXISTS idx_items_task_fetched ON items(task_id, fetched_at DESC);

-- 全局时间倒序（首页全局结果列表）
CREATE INDEX IF NOT EXISTS idx_items_fetched_desc ON items(fetched_at DESC);

-- 收藏筛选（仅索引 is_starred=1 的行）
CREATE INDEX IF NOT EXISTS idx_items_starred ON items(is_starred);

-- -------------------------------------------
-- task_executions 表：任务执行记录
-- -------------------------------------------
CREATE TABLE IF NOT EXISTS task_executions (
    id             TEXT PRIMARY KEY,                -- UUID v4 字符串
    task_id        TEXT NOT NULL REFERENCES tasks(id),
    status         TEXT NOT NULL CHECK (status IN ('success', 'failure', 'warning')),
    items_fetched  INTEGER NOT NULL DEFAULT 0,      -- 本次抓取条目数
    items_new      INTEGER NOT NULL DEFAULT 0,      -- 去重后新增条目数
    duration_ms    INTEGER NOT NULL DEFAULT 0,      -- 执行耗时（毫秒）
    error_message  TEXT,                            -- 错误信息（失败时）
    executed_at    TEXT NOT NULL                    -- 执行开始时间
);

-- 按任务 + 执行时间倒序（执行历史列表）
CREATE INDEX IF NOT EXISTS idx_executions_task_time
    ON task_executions(task_id, executed_at DESC);

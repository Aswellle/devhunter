-- ===========================================
-- migrations/015_execution_recovery_and_metrics.sql
-- R1: 进程重启恢复 + R2: 执行指标字段
-- ===========================================

-- 1. 扩展 task_executions 表：添加恢复与指标字段
-- SQLite 不支持 ALTER TABLE ADD COLUMN with CHECK，且不能修改已有 CHECK 约束，
-- 因此使用重建表策略（与 006 迁移相同模式）。

CREATE TABLE IF NOT EXISTS task_executions_new (
    id              TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL REFERENCES tasks(id),
    status          TEXT NOT NULL CHECK (status IN ('running', 'success', 'failure', 'warning', 'interrupted')),
    items_fetched   INTEGER NOT NULL DEFAULT 0,
    items_new       INTEGER NOT NULL DEFAULT 0,
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT,
    executed_at     TEXT NOT NULL,
    -- R2: 执行指标字段
    heartbeat_at    TEXT,                       -- 最后心跳时间（用于 stale 检测）
    attempt         INTEGER NOT NULL DEFAULT 1, -- 执行尝试次数
    last_error_code TEXT,                       -- 错误分类码（NETWORK/TIMEOUT/SSRF_BLOCKED/...）
    pages_count     INTEGER NOT NULL DEFAULT 0, -- 抓取页数
    items_seen      INTEGER NOT NULL DEFAULT 0, -- 原始解析条数（去重前）
    items_created   INTEGER NOT NULL DEFAULT 0, -- 新增入库条数
    items_updated   INTEGER NOT NULL DEFAULT 0, -- 更新条数
    items_deduped   INTEGER NOT NULL DEFAULT 0  -- 去重跳过的条数
);

-- 迁移旧数据
INSERT INTO task_executions_new
    (id, task_id, status, items_fetched, items_new, duration_ms, error_message, executed_at)
SELECT id, task_id, status, items_fetched, items_new, duration_ms, error_message, executed_at
FROM task_executions;

DROP TABLE task_executions;
ALTER TABLE task_executions_new RENAME TO task_executions;

-- 重建索引
CREATE INDEX IF NOT EXISTS idx_executions_task_time
    ON task_executions(task_id, executed_at DESC);

-- 加速 stale 查询
CREATE INDEX IF NOT EXISTS idx_executions_status
    ON task_executions(status);

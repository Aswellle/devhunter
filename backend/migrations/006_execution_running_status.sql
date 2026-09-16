-- 006_execution_running_status.sql
-- F14 修复：trigger_execute 需要在返回 exec_id 前同步创建 task_executions 行，
-- 供客户端立即轮询；执行线程随后将其更新为 success/failure/warning。
-- 因此 status 枚举需新增 'running' 作为该行的初始状态。
-- SQLite 不支持直接修改 CHECK 约束，需重建表。

CREATE TABLE IF NOT EXISTS task_executions_new (
    id             TEXT PRIMARY KEY,
    task_id        TEXT NOT NULL REFERENCES tasks(id),
    status         TEXT NOT NULL CHECK (status IN ('running', 'success', 'failure', 'warning')),
    items_fetched  INTEGER NOT NULL DEFAULT 0,
    items_new      INTEGER NOT NULL DEFAULT 0,
    duration_ms    INTEGER NOT NULL DEFAULT 0,
    error_message  TEXT,
    executed_at    TEXT NOT NULL
);

INSERT INTO task_executions_new
    SELECT id, task_id, status, items_fetched, items_new, duration_ms, error_message, executed_at
    FROM task_executions;

DROP TABLE task_executions;
ALTER TABLE task_executions_new RENAME TO task_executions;

CREATE INDEX IF NOT EXISTS idx_executions_task_time
    ON task_executions(task_id, executed_at DESC);

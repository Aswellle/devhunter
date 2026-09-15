-- ===========================================
-- migrations/010_execution_events.sql
-- Durable execution events for state machine
-- ===========================================

-- execution_events 表：持久化执行事件流
-- 与 EventBus 配合：EventBus 用于实时 SSE，此表用于审计和断线补发
CREATE TABLE IF NOT EXISTS execution_events (
    id           TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    event_type   TEXT NOT NULL,           -- queued|start|fetch|parse|normalize|dedup|persist|cluster|complete|fail|warning
    message      TEXT,
    data         TEXT NOT NULL DEFAULT '{}',  -- JSON 扩展数据
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_execution_events_exec ON execution_events(execution_id);
CREATE INDEX IF NOT EXISTS idx_execution_events_task ON execution_events(task_id, created_at DESC);

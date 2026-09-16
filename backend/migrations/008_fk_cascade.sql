-- 008_fk_cascade.sql
-- D7 修复：items.task_id 与 task_executions.task_id 引用 tasks(id) 时未声明
-- ON DELETE CASCADE。当前唯一的硬删除路径（scheduler/cleanup.py）已经手动
-- 先删 items/task_executions 再删 tasks，所以现状不会产生孤儿行；但这依赖
-- 调用方"记得按正确顺序删"，任何新增的硬删除路径都可能漏做而留下孤儿行。
-- 加上 CASCADE 作为数据库层兜底。
--
-- SQLite 的外键约束在建表时固定，只能通过重建表来修改。

PRAGMA foreign_keys = OFF;

CREATE TABLE items_new (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    url_hash    TEXT NOT NULL,
    summary     TEXT,
    is_read     INTEGER NOT NULL DEFAULT 0,
    is_starred  INTEGER NOT NULL DEFAULT 0,
    fetched_at  TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    thread_id   TEXT REFERENCES threads(id)
);

INSERT INTO items_new
    SELECT id, task_id, title, url, url_hash, summary, is_read, is_starred,
           fetched_at, created_at, thread_id
    FROM items;

DROP TABLE items;
ALTER TABLE items_new RENAME TO items;

CREATE UNIQUE INDEX IF NOT EXISTS idx_items_url_hash ON items(url_hash);
CREATE INDEX IF NOT EXISTS idx_items_task_fetched ON items(task_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_fetched_desc ON items(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_starred ON items(is_starred);
CREATE INDEX IF NOT EXISTS idx_items_thread ON items(thread_id);

CREATE TABLE task_executions_cascade (
    id             TEXT PRIMARY KEY,
    task_id        TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    status         TEXT NOT NULL CHECK (status IN ('running', 'success', 'failure', 'warning')),
    items_fetched  INTEGER NOT NULL DEFAULT 0,
    items_new      INTEGER NOT NULL DEFAULT 0,
    duration_ms    INTEGER NOT NULL DEFAULT 0,
    error_message  TEXT,
    executed_at    TEXT NOT NULL
);

INSERT INTO task_executions_cascade
    SELECT id, task_id, status, items_fetched, items_new, duration_ms, error_message, executed_at
    FROM task_executions;

DROP TABLE task_executions;
ALTER TABLE task_executions_cascade RENAME TO task_executions;

CREATE INDEX IF NOT EXISTS idx_executions_task_time
    ON task_executions(task_id, executed_at DESC);

PRAGMA foreign_keys = ON;

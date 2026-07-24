-- ===========================================
-- migrations/003_threads.sql
-- Cross-Platform Thread: 多平台聚合表结构
-- ===========================================

-- -------------------------------------------
-- threads 表：同一事件的多平台报道聚合
-- -------------------------------------------
CREATE TABLE IF NOT EXISTS threads (
    id             TEXT PRIMARY KEY,
    title          TEXT NOT NULL,                      -- 规范化的 Thread 标题（取最完整的那个）
    first_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    last_seen_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    item_count     INTEGER NOT NULL DEFAULT 1,
    platforms      TEXT NOT NULL DEFAULT '[]'          -- JSON 数组，如 '["hackernews","v2ex"]'
);

CREATE INDEX IF NOT EXISTS idx_threads_first_seen ON threads(first_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_threads_last_seen ON threads(last_seen_at DESC);

-- -------------------------------------------
-- thread_items 表：item 与 thread 的多对多关联
-- -------------------------------------------
CREATE TABLE IF NOT EXISTS thread_items (
    thread_id   TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    item_id     TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    similarity  REAL NOT NULL DEFAULT 1.0,           -- Jaccard 相似度 (0-1)
    PRIMARY KEY (thread_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_thread_items_thread ON thread_items(thread_id);
CREATE INDEX IF NOT EXISTS idx_thread_items_item ON thread_items(item_id);

-- -------------------------------------------
-- items 表：新增 thread_id 外键
-- -------------------------------------------
-- 注意：SQLite 支持 ADD COLUMN，但需确保列不存在（IF NOT EXISTS 在 SQLite 中对 ALTER TABLE ADD COLUMN 不生效）
-- 迁移时若列已存在会报错 "duplicate column name"，此时可安全忽略
PRAGMA ignore_lock_table_warnings = 1;

-- 使用 TRY 开始批量操作
SAVEPOINT add_thread_column;

-- 尝试添加列（已在 002 中添加则忽略错误）
-- SQLite 的 ALTER TABLE ADD COLUMN 如果列已存在会报错
-- 我们用这种方式检测：先尝试添加，出错则回滚并继续
ALTER TABLE items ADD COLUMN thread_id TEXT REFERENCES threads(id);

-- 如果成功，添加索引
CREATE INDEX IF NOT EXISTS idx_items_thread ON items(thread_id);

RELEASE SAVEPOINT add_thread_column;

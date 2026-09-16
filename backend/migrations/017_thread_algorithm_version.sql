-- ===========================================
-- migrations/017_thread_algorithm_version.sql
-- T2: Thread 聚合版本化 + T3: 人工纠错模型
-- ===========================================

-- T2: 添加算法版本和阈值字段到 threads 表
ALTER TABLE threads ADD COLUMN algorithm_version TEXT NOT NULL DEFAULT 'v2';
ALTER TABLE threads ADD COLUMN similarity_threshold REAL NOT NULL DEFAULT 0.45;
ALTER TABLE threads ADD COLUMN clustered_at TEXT;

-- T2: 添加 match_reason 到 thread_items（解释为什么聚合）
ALTER TABLE thread_items ADD COLUMN match_reason TEXT;

-- T3: 人工纠错记录表
-- 记录用户的 split/merge override，用于后续算法改进和避免重复错误
CREATE TABLE IF NOT EXISTS thread_overrides (
    id          TEXT PRIMARY KEY,
    thread_id   TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    override_type TEXT NOT NULL CHECK (override_type IN ('split', 'merge', 'reject_merge', 'force_join')),
    item_id     TEXT REFERENCES items(id),
    target_thread_id TEXT REFERENCES threads(id),
    reason      TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_overrides_thread ON thread_overrides(thread_id);
CREATE INDEX IF NOT EXISTS idx_overrides_type ON thread_overrides(override_type);

-- T2: 添加复合索引支持版本化查询
CREATE INDEX IF NOT EXISTS idx_threads_algorithm ON threads(algorithm_version, last_seen_at DESC);

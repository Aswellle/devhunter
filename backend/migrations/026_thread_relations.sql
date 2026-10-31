-- ===========================================
-- migrations/026_thread_relations.sql
-- 同一故事线关联：相似但未被聚合为同一事件的 Thread 之间的显式关联。
--
-- 典型来源：
-- - auto：聚类评分落在 [storyline_threshold, join_threshold) 区间
--   （同一故事线、不同子事件），建新 Thread 时记录与最佳候选的关联
-- - split：人工拆分后，源 Thread 与拆分出的新 Thread 天然同属一条故事线
--
-- 关联只做展示层（"同一故事线"分层），不影响聚类归属与热度。
-- (thread_a, thread_b) 以字典序规范存储，CHECK 保证无方向歧义、无自关联。
-- ===========================================
CREATE TABLE IF NOT EXISTS thread_relations (
    thread_a   TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    thread_b   TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    similarity REAL NOT NULL DEFAULT 0.0,
    source     TEXT NOT NULL DEFAULT 'auto',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (thread_a, thread_b),
    CHECK (thread_a < thread_b)
);

CREATE INDEX IF NOT EXISTS idx_thread_relations_b ON thread_relations(thread_b);

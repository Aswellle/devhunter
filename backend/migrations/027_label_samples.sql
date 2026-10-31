-- ===========================================
-- migrations/027_label_samples.sql
-- 打标采样快照：GET /labels/sample 返回候选时，把该条目当时的
-- 推荐得分落在服务端。POST /labels 落标时以此为准，
-- 客户端回传值一律不采信——金标指标的输入不再依赖客户端。
-- 条目标注完成后快照行即被取走删除；改判（无新采样）沿用
-- relevance_labels 中已存的分数，不随后续权重调整漂移。
-- ===========================================
CREATE TABLE IF NOT EXISTS label_samples (
    item_id       TEXT PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    sampled_score REAL NOT NULL,
    sampled_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ===========================================
-- migrations/025_relevance_labels.sql
-- 推荐质量金标：用户对采样条目的相关性判断（感兴趣 / 不感兴趣）。
-- 采样条目在落标时快照当时的推荐得分（sampled_score），
-- 排序贴合度指标基于该快照计算，不随后续权重调整漂移。
-- 打标仅用于评估，不参与推荐打分与画像。
-- ===========================================
CREATE TABLE IF NOT EXISTS relevance_labels (
    id            TEXT PRIMARY KEY,
    item_id       TEXT NOT NULL UNIQUE,
    label         INTEGER NOT NULL CHECK (label IN (0, 1)),
    sampled_score REAL,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_relevance_labels_updated ON relevance_labels(updated_at);

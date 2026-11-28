-- Migration 031: 人工纠错决策按成员条目 ID（稳定身份）存储（ADR-001）
-- 旧的 thread_overrides 以一次性 Thread UUID 为键，全量重建生成新 ID 后
-- 人工 merge/split/reject 全部失效。决策表记录锚定的成员条目 ID，
-- 重建后重放；replayed_at 追踪重放进度，崩溃后下次重建自动补放。

CREATE TABLE IF NOT EXISTS thread_manual_decisions (
    id            TEXT PRIMARY KEY,
    decision_type TEXT NOT NULL CHECK (decision_type IN ('merge', 'split', 'reject_merge')),
    item_ids      TEXT NOT NULL,                     -- JSON 数组：锚定的成员条目 ID
    payload_json  TEXT NOT NULL DEFAULT '{}',        -- 附加信息（如 split 的保留侧锚点）
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    replayed_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_manual_decisions_pending
    ON thread_manual_decisions(replayed_at)
    WHERE replayed_at IS NULL;

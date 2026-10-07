-- ===========================================
-- migrations/022_model_receipts.sql
-- LLM 付费回执：
-- 调用前先落 pending 回执，成功后补全结果与 token 用量——
-- 崩溃/重启不会丢失"已付费"记录；相同 (model, prompt_hash)
-- 的已完成调用可复用，不重复付费。
-- ===========================================
CREATE TABLE IF NOT EXISTS model_receipts (
    id            TEXT PRIMARY KEY,
    purpose       TEXT NOT NULL,              -- 调用目的（thread_digest / eval_* / ...）
    model         TEXT NOT NULL,
    prompt_hash   TEXT NOT NULL,              -- sha256(model + system + user prompt)
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'done', 'failed')),
    result_text   TEXT,                       -- done 时存正文（复用用）
    error         TEXT,                       -- failed 时存错误摘要
    input_tokens  INTEGER,
    output_tokens INTEGER,
    duration_ms   INTEGER,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_model_receipts_lookup ON model_receipts(model, prompt_hash, status);
CREATE INDEX IF NOT EXISTS idx_model_receipts_created ON model_receipts(created_at);

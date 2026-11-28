-- Migration 036: 独立命名机器令牌（SEC-002）
-- 旧机器令牌由 SECRET_KEY 确定性派生：无法单独撤销、无过期/最后使用时间、
-- 无法区分用途。命名令牌以哈希存储（不存明文），scope 当前仅 read
-- （RSS/MCP 只读出口），可单独撤销与过期；撤销立即失效。

CREATE TABLE IF NOT EXISTS api_tokens (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    token_hash   TEXT NOT NULL UNIQUE,
    scope        TEXT NOT NULL DEFAULT 'read' CHECK (scope IN ('read')),
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at   TEXT,
    last_used_at TEXT,
    revoked_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_api_tokens_active
    ON api_tokens(revoked_at)
    WHERE revoked_at IS NULL;

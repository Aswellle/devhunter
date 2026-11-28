-- Migration 033: HTTP 条件请求缓存（ETag）
-- GitHub Connector（PROD-002）用 If-None-Match 减少重复请求：响应 etag
-- 按 URL 持久化，304 视为来源未变化。表结构通用，后续其他 Connector
-- 可复用（last_modified 预留 Last-Modified 条件请求）。

CREATE TABLE IF NOT EXISTS http_cache (
    url           TEXT PRIMARY KEY,
    etag          TEXT,
    last_modified TEXT,
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Migration 034: 通知渠道、规则与投递记录（PROD-003）
-- 规则按 saved search（关键词）/ Thread / 来源健康触发；投递记录以
-- event_key 唯一约束保证幂等，重试有次数上限，超限进入 dead-letter 状态
-- 可手动重试。webhook URL 受 SSRF 限制（每跳每次投递前预检）。

CREATE TABLE IF NOT EXISTS notification_channels (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'webhook' CHECK (kind IN ('webhook')),
    url         TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS notification_rules (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    trigger_type  TEXT NOT NULL CHECK (trigger_type IN ('keyword', 'thread', 'health')),
    config_json   TEXT NOT NULL DEFAULT '{}',
    channel_id    TEXT NOT NULL REFERENCES notification_channels(id) ON DELETE CASCADE,
    enabled       INTEGER NOT NULL DEFAULT 1,
    last_fired_at TEXT,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_notification_rules_trigger
    ON notification_rules(trigger_type)
    WHERE enabled = 1;

CREATE TABLE IF NOT EXISTS notification_deliveries (
    id              TEXT PRIMARY KEY,
    rule_id         TEXT NOT NULL REFERENCES notification_rules(id) ON DELETE CASCADE,
    channel_id      TEXT NOT NULL REFERENCES notification_channels(id) ON DELETE CASCADE,
    event_key       TEXT NOT NULL,
    payload_json    TEXT NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'sent', 'failed', 'dead')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    last_error      TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    sent_at         TEXT,
    UNIQUE (rule_id, event_key)
);

CREATE INDEX IF NOT EXISTS idx_notification_deliveries_pending
    ON notification_deliveries(status, next_attempt_at);

-- Migration 035: 机会板（PROD-005）
-- 机会可关联一条 Item 或一个 Thread；状态流转全部写入 opportunity_events
-- 审计表（含 from/to 与时间），笔记/标签/提醒同样留痕，任何操作都能回溯
-- 到原始证据（origin_type + origin_id）。

CREATE TABLE IF NOT EXISTS opportunities (
    id              TEXT PRIMARY KEY,
    origin_type     TEXT NOT NULL CHECK (origin_type IN ('item', 'thread')),
    origin_id       TEXT NOT NULL,
    title           TEXT NOT NULL,
    opportunity_type TEXT NOT NULL DEFAULT 'idea'
                    CHECK (opportunity_type IN (
                        'user_problem', 'product_launch', 'open_source_project',
                        'hiring', 'collaboration', 'trend', 'technical_risk', 'idea')),
    status          TEXT NOT NULL DEFAULT 'inbox'
                    CHECK (status IN ('inbox', 'investigating', 'planned',
                                      'building', 'shipped', 'dismissed')),
    priority        TEXT NOT NULL DEFAULT 'normal'
                    CHECK (priority IN ('low', 'normal', 'high')),
    value_score     REAL,
    notes           TEXT NOT NULL DEFAULT '',
    tags_json       TEXT NOT NULL DEFAULT '[]',
    remind_at       TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_opportunities_status
    ON opportunities(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_origin
    ON opportunities(origin_type, origin_id);

CREATE TABLE IF NOT EXISTS opportunity_events (
    id              TEXT PRIMARY KEY,
    opportunity_id  TEXT NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL CHECK (event_type IN (
                        'created', 'status_change', 'priority_change',
                        'note', 'tags', 'remind')),
    from_value      TEXT,
    to_value        TEXT,
    note            TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_opportunity_events_opp
    ON opportunity_events(opportunity_id, created_at DESC);

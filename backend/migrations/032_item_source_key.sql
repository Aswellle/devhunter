-- Migration 032: 条目级来源身份（ADR-002，内容实体 vs 来源观测）
-- content_hash 此前全局去重：跨来源同内容的观测被静默丢弃，Thread
-- 失去跨来源证据。source_key（来源 URL 主机名，与 threads.source_keys
-- 同一身份体系）把内容指纹匹配限定在同一来源内——同来源重复同步仍被
-- 拦，跨来源同内容保留为独立观测行。历史行回填在启动时执行
-- （item_repo.backfill_item_source_keys，幂等），NULL 身份保守地
-- 不参与内容匹配。

ALTER TABLE items ADD COLUMN source_key TEXT;

CREATE INDEX IF NOT EXISTS idx_items_source_key
    ON items(source_key);

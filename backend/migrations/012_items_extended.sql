-- ===========================================
-- migrations/012_items_extended.sql
-- Items 表扩展：支持 Thread V2 和推荐 V2
-- ============================================

-- 新增字段用于更好的跨平台聚类、推荐、去重
-- SQLite ALTER TABLE ADD COLUMN 不支持 IF NOT EXISTS，
-- 但重复执行会报错 "duplicate column name"，可安全忽略

ALTER TABLE items ADD COLUMN source_id TEXT;
ALTER TABLE items ADD COLUMN source_name TEXT;
ALTER TABLE items ADD COLUMN canonical_url TEXT;
ALTER TABLE items ADD COLUMN published_at TEXT;
ALTER TABLE items ADD COLUMN author TEXT;
ALTER TABLE items ADD COLUMN language TEXT;
ALTER TABLE items ADD COLUMN content_type TEXT;
ALTER TABLE items ADD COLUMN entities TEXT;       -- JSON 数组
ALTER TABLE items ADD COLUMN fingerprint TEXT;    -- 内容指纹（用于语义去重）

-- 索引
CREATE INDEX IF NOT EXISTS idx_items_source ON items(source_id);
CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_fingerprint ON items(fingerprint);

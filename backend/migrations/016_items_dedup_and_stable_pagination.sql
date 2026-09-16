-- ===========================================
-- migrations/016_items_dedup_and_stable_pagination.sql
-- D1: 去重优先级 (external_id > canonical_url > content_hash)
-- D2: 分页稳定排序
-- ===========================================

-- 1. 扩展 items 表：添加去重字段
-- 使用 ALTER TABLE ADD COLUMN（SQLite 支持，且这些字段有 DEFAULT NULL，安全）
ALTER TABLE items ADD COLUMN external_id TEXT;
ALTER TABLE items ADD COLUMN content_hash TEXT;

-- 2. 创建 partial unique index：external_id 去重（仅当 external_id IS NOT NULL 时生效）
-- 这允许不同任务的相同 external_id（如跨平台转载），但同一 source 内唯一
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_external_id
    ON items(task_id, external_id)
    WHERE external_id IS NOT NULL;

-- 3. 创建 content_hash 索引（用于内容指纹去重）
CREATE INDEX IF NOT EXISTS idx_items_content_hash
    ON items(content_hash)
    WHERE content_hash IS NOT NULL;

-- 4. D2: 分页稳定排序索引
-- 将 fetched_at 排序改为 created_at + id 稳定排序
-- 删除旧的全局 fetched_at 索引，替换为 created_at + id
DROP INDEX IF EXISTS idx_items_fetched_desc;
CREATE INDEX IF NOT EXISTS idx_items_created_id_desc
    ON items(created_at DESC, id DESC);

-- 任务维度也改为稳定排序
DROP INDEX IF EXISTS idx_items_task_fetched;
CREATE INDEX IF NOT EXISTS idx_items_task_created
    ON items(task_id, created_at DESC, id DESC);

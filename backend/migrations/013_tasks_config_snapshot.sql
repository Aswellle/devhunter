-- ===========================================
-- migrations/013_tasks_config_snapshot.sql
-- Tasks 表增加 config_snapshot 列
-- ===========================================

-- config_snapshot: 创建时的模板配置快照（JSON）
-- 用于 Task 与模板解耦：Task 保存 effective config，不依赖未来模板版本
ALTER TABLE tasks ADD COLUMN config_snapshot TEXT;

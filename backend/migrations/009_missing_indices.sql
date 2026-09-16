-- 009_missing_indices.sql
-- D9 修复：补充两个查询路径实际用到但缺失的索引。
--
-- tasks.created_at: task_repo.list_all() 的 ORDER BY created_at DESC
-- 之前没有索引支持，任务数一多就会全表扫描 + 排序。
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC);

-- items.is_read: item_repo.query() 支持 is_read 过滤，但只有 is_starred
-- 建了索引，is_read 一直缺失（对称性缺口）。
CREATE INDEX IF NOT EXISTS idx_items_is_read ON items(is_read);

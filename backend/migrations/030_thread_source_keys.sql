-- Migration 030: Thread 稳定来源身份
-- 来源独立性评分此前依赖可修改的任务名（threads.platforms）：
-- 任务改名会改变聚类结果，同平台多任务被当成跨平台共识。
-- source_keys 存来源 URL 主机名（稳定身份），rebuild_thread_stats
-- 自愈回填；旧线程未回填时评分回退任务名比较，行为不变。

ALTER TABLE threads ADD COLUMN source_keys TEXT NOT NULL DEFAULT '[]';

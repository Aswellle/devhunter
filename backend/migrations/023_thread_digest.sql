-- ===========================================
-- migrations/023_thread_digest.sql
-- Thread AI 综述：多来源事件由 LLM 生成的中文摘要。
-- 只存正文与生成时间；LLM 未配置/熔断时保持 NULL，前端隐藏。
-- 重建 Thread 会随旧行一并删除，之后的采集会重新生成。
-- ===========================================
ALTER TABLE threads ADD COLUMN digest TEXT;
ALTER TABLE threads ADD COLUMN digest_at TEXT;

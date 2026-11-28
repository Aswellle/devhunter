-- Migration 029: 全局唯一递增 seq，作为 SSE 断线补发游标
--
-- 019 的 seq 按 execution_id 分组编号（每个执行内 1..n），跨执行重复，
-- 不能充当全局游标；旧重放查询用毫秒级 created_at > 比较，同一毫秒内
-- 的后续事件会被漏掉。事件表从不清理，rowid 即真实插入顺序——直接以
-- rowid 重排全部历史行，再用唯一索引约束未来的写入。

UPDATE execution_events SET seq = rowid;

-- 全局唯一：并发写入路径（repo 层 BEGIN IMMEDIATE 内 MAX(seq)+1）依赖它兜底
CREATE UNIQUE INDEX IF NOT EXISTS uq_execution_events_seq
    ON execution_events(seq);

-- 断线补发主查询走 (task_id, seq) keyset 扫描
CREATE INDEX IF NOT EXISTS idx_execution_events_task_seq
    ON execution_events(task_id, seq);

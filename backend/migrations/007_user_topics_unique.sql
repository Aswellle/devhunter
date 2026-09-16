-- 007_user_topics_unique.sql
-- D3 修复：user_topics.topic 缺少 UNIQUE 约束，upsert() 原来的
-- SELECT-then-INSERT 非原子，允许并发请求插入重复 topic 行。
--
-- 先去重（保留每个 topic 最早创建的一行，按 rowid 最小），
-- 再建唯一索引，否则若已有重复数据，CREATE UNIQUE INDEX 会直接失败。
DELETE FROM user_topics
WHERE rowid NOT IN (
    SELECT MIN(rowid) FROM user_topics GROUP BY topic
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_topics_topic_unique ON user_topics(topic);

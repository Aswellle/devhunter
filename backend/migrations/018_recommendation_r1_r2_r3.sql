-- ===========================================
-- migrations/018_recommendation_r1_r2_r3.sql
-- R1: Interaction taxonomy extension
-- R2: Time-based affinity decay
-- R3: Negative feedback (not_interested / hide_source / mute_topic)
-- ===========================================

-- R1: 扩展 user_interactions 的 interaction_type 枚举
-- SQLite 不支持 ALTER TABLE MODIFY CHECK，需重建表
-- 使用 rename-then-drop 模式：先重命名旧表再删除，确保迁移失败时数据不丢失

-- Step 1: 将旧表重命名为备份（如果存在）
ALTER TABLE user_interactions RENAME TO user_interactions_old;

-- Step 2: 创建新表
-- 注意：CHECK 取「旧词表 ∪ R1 词表」的并集。API 层 / 前端 / 参与度统计用的是
-- view/click/dwell/star/share，R1 引擎用的是 impression/open/click_source/...；
-- 只保留 R1 词表会让最高频的 view / click 直接撞 CHECK 约束（IntegrityError → 500），
-- 亲缘度因此永远累积不起来。
CREATE TABLE user_interactions (
    id              TEXT PRIMARY KEY,
    item_id         TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    interaction_type TEXT NOT NULL CHECK (interaction_type IN (
        'view', 'click', 'dwell', 'star', 'share',
        'impression', 'open', 'click_source', 'unstar',
        'read', 'hide', 'thread_expand', 'search', 'not_interested'
    )),
    dwell_seconds   INTEGER,
    weight          REAL NOT NULL DEFAULT 1.0,  -- R1: 事件权重（star > view）
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Step 3: 从旧表迁移数据（原样拷贝）
-- 这里刻意不再做 view→impression / click→click_source 改写：迁移文件在每次启动
-- 都会重跑，改写会让已经写入的 view/click 在每次重启后被改掉，而统计口径
-- （get_user_engagement_stats 按 'view'/'click' 计数）随之失效。
INSERT INTO user_interactions (id, item_id, interaction_type, dwell_seconds, weight, created_at)
SELECT id, item_id, interaction_type, dwell_seconds, 1.0, created_at
FROM user_interactions_old;

-- Step 4: 安全删除备份表
DROP TABLE IF EXISTS user_interactions_old;

-- Step 5: 创建索引
CREATE INDEX IF NOT EXISTS idx_interactions_item ON user_interactions(item_id);
CREATE INDEX IF NOT EXISTS idx_interactions_type ON user_interactions(interaction_type);
CREATE INDEX IF NOT EXISTS idx_interactions_created ON user_interactions(created_at DESC);

-- R2: 为 user_topic_affinity 添加半衰期配置字段
ALTER TABLE user_topic_affinity ADD COLUMN half_life_hours REAL NOT NULL DEFAULT 72.0;

-- R3: 用户负反馈表（不感兴趣 / 隐藏来源 / 屏蔽主题）
CREATE TABLE IF NOT EXISTS user_negative_feedback (
    id              TEXT PRIMARY KEY,
    feedback_type   TEXT NOT NULL CHECK (feedback_type IN ('not_interested', 'hide_source', 'mute_topic')),
    target_value    TEXT NOT NULL,  -- item_id / source_id / topic_keyword
    reason          TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_negative_type ON user_negative_feedback(feedback_type, target_value);
CREATE INDEX IF NOT EXISTS idx_negative_created ON user_negative_feedback(created_at DESC);

-- R2: 推荐配置 — 时间衰减半衰期
INSERT OR IGNORE INTO recommendation_config (key, value) VALUES
    ('affinity_half_life_hours', 72.0),     -- 亲缘度时间衰减半衰期（小时）
    ('recency_half_life_hours', 6.0),       -- 新鲜度衰减半衰期（小时）
    ('negative_feedback_weight', -0.5);     -- 负反馈对得分的影响权重

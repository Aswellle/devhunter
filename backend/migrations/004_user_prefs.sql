-- ===========================================
-- migrations/004_user_prefs.sql
-- 用户偏好与行为追踪：个性化推荐表结构
-- ===========================================

-- -------------------------------------------
-- user_topics 表：用户主动设置的关注主题/关键词
-- -------------------------------------------
CREATE TABLE IF NOT EXISTS user_topics (
    id          TEXT PRIMARY KEY,
    topic       TEXT NOT NULL,                      -- 主题关键词，如 "GPT-5", "React", "AI创业"
    category    TEXT NOT NULL DEFAULT 'custom',     -- 分类：custom=自定义, ai=AI, web=Web开发, mobile=移动端, devops=DevOps, other=其他
    weight      REAL NOT NULL DEFAULT 1.0,          -- 权重系数 (0.5-2.0)，用户可调整
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_user_topics_category ON user_topics(category);

-- -------------------------------------------
-- user_interactions 表：用户隐式行为信号（用于强化推荐）
-- -------------------------------------------
CREATE TABLE IF NOT EXISTS user_interactions (
    id              TEXT PRIMARY KEY,
    item_id         TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    interaction_type TEXT NOT NULL CHECK (interaction_type IN ('view', 'click', 'dwell', 'star', 'share')),
    dwell_seconds   INTEGER,                         -- 阅读停留时长（秒），仅 interaction_type='dwell' 时记录
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_interactions_item ON user_interactions(item_id);
CREATE INDEX IF NOT EXISTS idx_interactions_type ON user_interactions(interaction_type);
CREATE INDEX IF NOT EXISTS idx_interactions_created ON user_interactions(created_at DESC);

-- -------------------------------------------
-- user_topic_affinity 表：用户与任务/平台的主题亲缘度
-- 根据用户阅读历史自动计算，用于推荐同类主题的新内容
-- -------------------------------------------
CREATE TABLE IF NOT EXISTS user_topic_affinity (
    id              TEXT PRIMARY KEY,
    affinity_type   TEXT NOT NULL CHECK (affinity_type IN ('task', 'platform', 'keyword')),
    affinity_value  TEXT NOT NULL,                  -- task_id 或 platform 名称 或 关键词
    affinity_score  REAL NOT NULL DEFAULT 0.0,      -- 亲缘度得分 (0.0-1.0)，随交互累积
    interaction_count INTEGER NOT NULL DEFAULT 0,    -- 累计交互次数
    last_interacted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_affinity_unique ON user_topic_affinity(affinity_type, affinity_value);
CREATE INDEX IF NOT EXISTS idx_affinity_score ON user_topic_affinity(affinity_score DESC);

-- -------------------------------------------
-- 推荐算法参数（可调配置）
-- -------------------------------------------
CREATE TABLE IF NOT EXISTS recommendation_config (
    key   TEXT PRIMARY KEY,
    value REAL NOT NULL
);

-- 默认参数
INSERT OR IGNORE INTO recommendation_config (key, value) VALUES
    ('topic_match_weight', 0.4),      -- 主题关键词匹配权重
    ('affinity_weight', 0.3),        -- 亲缘度权重
    ('recency_weight', 0.2),         -- 新鲜度权重
    ('engagement_weight', 0.1),      -- 总体参与度权重
    ('min_score_threshold', 0.1),     -- 最低推荐阈值
    ('max_items', 20),               -- 最多返回推荐数量
    ('dwell_time_decay', 0.95),      -- 停留时间衰减系数（每小时）
    ('view_decay', 0.9),             -- 阅读衰减系数（每天）
    ('affinity_boost', 0.1);         -- 高亲缘度加分

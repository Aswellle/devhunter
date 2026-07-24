-- ===========================================
-- migrations/002_fts.sql
-- SQLite FTS5 全文搜索虚拟表
-- ===========================================

-- content-table 模式：FTS 表不存储原始数据，仅存储倒排索引
-- 通过触发器与 items 表保持同步
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    title,
    summary,
    content='items',
    content_rowid='rowid'
);

-- -------------------------------------------
-- 触发器：保持 FTS 索引与 items 表同步
-- -------------------------------------------

-- 插入后：将新条目加入 FTS 索引
CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
    INSERT INTO items_fts(rowid, title, summary)
    VALUES (new.rowid, new.title, COALESCE(new.summary, ''));
END;

-- 删除后：从 FTS 索引移除条目
CREATE TRIGGER IF NOT EXISTS items_ad AFTER DELETE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, summary)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.summary, ''));
END;

-- 更新后：先删除旧索引，再插入新索引（MVP 阶段 title/summary 理论上不更新）
CREATE TRIGGER IF NOT EXISTS items_au AFTER UPDATE OF title, summary ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, summary)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.summary, ''));
    INSERT INTO items_fts(rowid, title, summary)
    VALUES (new.rowid, new.title, COALESCE(new.summary, ''));
END;

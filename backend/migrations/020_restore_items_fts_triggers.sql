-- 020_restore_items_fts_triggers.sql
-- 008_fk_cascade 用 "CREATE items_new → INSERT SELECT → DROP TABLE items → RENAME"
-- 的方式重建 items 表以补 FK CASCADE。"DROP TABLE items" 会连带删除
-- 002_fts.sql 建立的 items_ai/items_ad/items_au 三个索引同步触发器。
--
-- 由于迁移按文件名排序在同一轮启动内依次执行，002 排在 008 之前、本轮已经跑过，
-- "CREATE TRIGGER IF NOT EXISTS" 不会再补一次 —— 结果是每次启动结束后
-- 全文索引触发器都处于缺失状态：新入库的条目永不进入 items_fts，
-- item_repo.query 的 MATCH 分支（items_fts MATCH ?）恒定返回空，
-- 且因为不抛异常，不会触发 LIKE 回退，全文搜索"静默失效"。
--
-- 该文件排在 008 之后，负责幂等恢复触发器，并把已有条目的倒排索引重建一次。

CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
    INSERT INTO items_fts(rowid, title, summary)
    VALUES (new.rowid, new.title, COALESCE(new.summary, ''));
END;

CREATE TRIGGER IF NOT EXISTS items_ad AFTER DELETE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, summary)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.summary, ''));
END;

CREATE TRIGGER IF NOT EXISTS items_au AFTER UPDATE OF title, summary ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, summary)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.summary, ''));
    INSERT INTO items_fts(rowid, title, summary)
    VALUES (new.rowid, new.title, COALESCE(new.summary, ''));
END;

-- external content 模式：触发器只覆盖写入路径，历史行需要显式重建索引
INSERT INTO items_fts(items_fts) VALUES('rebuild');

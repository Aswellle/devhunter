-- 收藏分组：用户自定义命名的收藏文件夹。
-- 条目通过 items.star_folder_id 归入文件夹；删除文件夹时回落到"未分类"，
-- 不取消收藏本身（ON DELETE SET NULL）。
CREATE TABLE IF NOT EXISTS star_folders (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 文件夹名称不区分大小写唯一，避免出现仅大小写不同的两个分组
CREATE UNIQUE INDEX IF NOT EXISTS idx_star_folders_name
    ON star_folders(name COLLATE NOCASE);

ALTER TABLE items ADD COLUMN star_folder_id TEXT
    REFERENCES star_folders(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_items_star_folder
    ON items(star_folder_id)
    WHERE star_folder_id IS NOT NULL;

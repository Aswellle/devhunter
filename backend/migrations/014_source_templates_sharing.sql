-- ===========================================
-- migrations/014_source_templates_sharing.sql
-- Template sharing support
-- ===========================================

-- Add sharing columns to source_templates
ALTER TABLE source_templates ADD COLUMN shared INTEGER NOT NULL DEFAULT 0;  -- 0=private, 1=shared
ALTER TABLE source_templates ADD COLUMN share_count INTEGER NOT NULL DEFAULT 0;  -- import count
ALTER TABLE source_templates ADD COLUMN category TEXT;  -- template category
ALTER TABLE source_templates ADD COLUMN tags TEXT;  -- JSON array of tags

-- Index for shared templates
CREATE INDEX IF NOT EXISTS idx_source_templates_shared ON source_templates(shared);
CREATE INDEX IF NOT EXISTS idx_source_templates_category ON source_templates(category);

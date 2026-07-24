-- ===========================================
-- migrations/005_pagination.sql
-- Add optional next-page selector for paginated crawls.
-- ===========================================

-- selector_next_page: nullable. Absent/NULL = single-page crawl (backward compatible).
-- Supports CSS selector (HTML mode) or json:/json-post: prefixed path (JSON modes).
-- RSS mode ignores this field.
ALTER TABLE tasks ADD COLUMN selector_next_page TEXT;

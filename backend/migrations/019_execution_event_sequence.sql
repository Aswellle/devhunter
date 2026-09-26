-- Migration 019: Add monotonic sequence column to execution_events
-- Fixes non-monotonic UUID-based event IDs for SSE cursor replay

ALTER TABLE execution_events ADD COLUMN seq INTEGER;

-- Backfill with rowid-based sequence numbers
UPDATE execution_events SET seq = (
    SELECT COUNT(*) FROM execution_events e2
    WHERE e2.execution_id = execution_events.execution_id
    AND e2.rowid <= execution_events.rowid
);

-- Create index for efficient cursor-based queries
CREATE INDEX IF NOT EXISTS idx_execution_events_seq ON execution_events(execution_id, seq);

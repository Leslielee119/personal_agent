CREATE TABLE IF NOT EXISTS canonical_events (
    event_id TEXT PRIMARY KEY,
    timestamp_ns INTEGER NOT NULL,
    monotonic_seq INTEGER NOT NULL UNIQUE CHECK (monotonic_seq > 0),
    data_json TEXT NOT NULL CHECK (json_valid(data_json))
);

CREATE INDEX IF NOT EXISTS idx_canonical_events_order
ON canonical_events(timestamp_ns, monotonic_seq);

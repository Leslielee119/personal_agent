CREATE TABLE IF NOT EXISTS memory_runs (
    run_id TEXT PRIMARY KEY,
    source_b1_run_id TEXT NOT NULL,
    source_high_water INTEGER NOT NULL CHECK (source_high_water >= 0),
    extractor_version TEXT NOT NULL,
    config_version TEXT NOT NULL,
    schema_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_records (
    run_id TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    created_seq INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (run_id, memory_id),
    FOREIGN KEY (run_id) REFERENCES memory_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_evidence_links (
    run_id TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    role TEXT NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (run_id, memory_id, evidence_type, evidence_id, role),
    FOREIGN KEY (run_id) REFERENCES memory_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_dependencies (
    run_id TEXT NOT NULL,
    dependency_id TEXT NOT NULL,
    created_seq INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (run_id, dependency_id),
    FOREIGN KEY (run_id) REFERENCES memory_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_supersessions (
    run_id TEXT NOT NULL,
    supersession_id TEXT NOT NULL,
    created_seq INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (run_id, supersession_id),
    FOREIGN KEY (run_id) REFERENCES memory_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_audit_events (
    run_id TEXT NOT NULL,
    audit_id TEXT NOT NULL,
    source_seq INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (run_id, audit_id),
    FOREIGN KEY (run_id) REFERENCES memory_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memory_records_run_seq
ON memory_records(run_id, created_seq, memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_evidence_run_memory
ON memory_evidence_links(run_id, memory_id, evidence_type, evidence_id, role);
CREATE INDEX IF NOT EXISTS idx_memory_dependencies_run_seq
ON memory_dependencies(run_id, created_seq, dependency_id);
CREATE INDEX IF NOT EXISTS idx_memory_supersessions_run_seq
ON memory_supersessions(run_id, created_seq, supersession_id);
CREATE INDEX IF NOT EXISTS idx_memory_audit_run_seq
ON memory_audit_events(run_id, source_seq, audit_id);

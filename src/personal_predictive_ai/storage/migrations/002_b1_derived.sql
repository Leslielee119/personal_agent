CREATE TABLE IF NOT EXISTS derived_runs (
    run_id TEXT PRIMARY KEY,
    source_high_water INTEGER NOT NULL CHECK (source_high_water >= 0),
    schema_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS b1_state_snapshots (
    run_id TEXT NOT NULL,
    state_id TEXT NOT NULL,
    monotonic_seq INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (run_id, state_id),
    FOREIGN KEY (run_id) REFERENCES derived_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS b1_actions (
    run_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    monotonic_seq INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (run_id, action_id),
    FOREIGN KEY (run_id) REFERENCES derived_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS b1_sessions (
    run_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    start_ns INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (run_id, session_id),
    FOREIGN KEY (run_id) REFERENCES derived_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS b1_transitions (
    run_id TEXT NOT NULL,
    transition_id TEXT NOT NULL,
    start_seq INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (run_id, transition_id),
    FOREIGN KEY (run_id) REFERENCES derived_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_b1_states_run_seq
ON b1_state_snapshots(run_id, monotonic_seq);
CREATE INDEX IF NOT EXISTS idx_b1_actions_run_seq
ON b1_actions(run_id, monotonic_seq);
CREATE INDEX IF NOT EXISTS idx_b1_sessions_run_start
ON b1_sessions(run_id, start_ns);
CREATE INDEX IF NOT EXISTS idx_b1_transitions_run_seq
ON b1_transitions(run_id, start_seq);

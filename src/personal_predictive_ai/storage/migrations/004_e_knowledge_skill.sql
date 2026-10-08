CREATE TABLE IF NOT EXISTS knowledge_records (
    knowledge_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_records (
    skill_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    status TEXT NOT NULL,
    risk_class TEXT NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (skill_id, version)
);

CREATE TABLE IF NOT EXISTS skill_mutation_proposals (
    proposal_id TEXT PRIMARY KEY,
    target_skill_id TEXT NOT NULL,
    base_version INTEGER,
    approval_status TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_package_manifests (
    package_id TEXT PRIMARY KEY,
    trust_state TEXT NOT NULL,
    source_type TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_audit_events (
    audit_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_projection_manifests (
    projection_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    data_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_skill_records_latest
ON skill_records(skill_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_skill_records_status
ON skill_records(status, skill_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_skill_proposals_target
ON skill_mutation_proposals(target_skill_id, approval_status, proposal_id);
CREATE INDEX IF NOT EXISTS idx_skill_packages_state
ON skill_package_manifests(trust_state, package_id);
CREATE INDEX IF NOT EXISTS idx_skill_audit_skill_time
ON skill_audit_events(skill_id, occurred_at, audit_id);

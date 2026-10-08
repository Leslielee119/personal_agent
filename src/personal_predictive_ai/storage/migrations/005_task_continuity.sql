CREATE TABLE IF NOT EXISTS continuity_projects (
    project_id TEXT PRIMARY KEY,
    created_at_ns INTEGER NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS continuity_workcopies (
    workcopy_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES continuity_projects(project_id) ON DELETE CASCADE,
    created_at_ns INTEGER NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS continuity_tasks (
    task_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES continuity_projects(project_id) ON DELETE CASCADE,
    workcopy_id TEXT REFERENCES continuity_workcopies(workcopy_id) ON DELETE CASCADE,
    created_at_ns INTEGER NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS continuity_evidence (
    evidence_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES continuity_projects(project_id) ON DELETE CASCADE,
    workcopy_id TEXT REFERENCES continuity_workcopies(workcopy_id) ON DELETE CASCADE,
    task_id TEXT REFERENCES continuity_tasks(task_id) ON DELETE CASCADE,
    available_at_ns INTEGER NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS continuity_field_versions (
    field_version_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES continuity_tasks(task_id) ON DELETE CASCADE,
    field_name TEXT NOT NULL,
    created_at_ns INTEGER NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS continuity_verified_results (
    result_id TEXT PRIMARY KEY,
    workcopy_id TEXT NOT NULL REFERENCES continuity_workcopies(workcopy_id) ON DELETE CASCADE,
    task_id TEXT REFERENCES continuity_tasks(task_id) ON DELETE CASCADE,
    observed_at_ns INTEGER NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS continuity_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES continuity_tasks(task_id) ON DELETE CASCADE,
    captured_at_ns INTEGER NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS continuity_briefs (
    brief_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES continuity_tasks(task_id) ON DELETE CASCADE,
    created_at_ns INTEGER NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS continuity_deletions (
    deletion_id TEXT PRIMARY KEY,
    deleted_at_ns INTEGER NOT NULL,
    data_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_continuity_evidence_scope
ON continuity_evidence(project_id, workcopy_id, task_id, available_at_ns, evidence_id);
CREATE INDEX IF NOT EXISTS idx_continuity_fields_task
ON continuity_field_versions(task_id, field_name, created_at_ns, field_version_id);

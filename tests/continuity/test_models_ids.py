from __future__ import annotations

import pytest
from pydantic import ValidationError

from personal_predictive_ai.continuity.ids import (
    project_id_for,
    task_id_for,
    workcopy_id_for,
)
from personal_predictive_ai.continuity.models import (
    ApplicabilityStatus,
    ContinuityRecordStatus,
    DeletionTombstoneRecord,
    EvidenceAvailability,
    EvidenceRecord,
    FieldProvenance,
    ProjectRecord,
    ResumeBriefRecord,
    TaskRecord,
    TaskSnapshot,
    TaskStateFieldVersion,
    VerifiedResultRecord,
    WorkCopyRecord,
)


def test_continuity_enums_have_frozen_json_values() -> None:
    assert FieldProvenance.USER_DECLARED.value == "user_declared"
    assert ApplicabilityStatus.NEEDS_REVALIDATION.value == "needs_revalidation"
    assert EvidenceAvailability.INTEGRITY_INVALID.value == "integrity_invalid"
    assert ContinuityRecordStatus.SUPERSEDED.value == "superseded"


def test_project_record_is_frozen_and_forbids_extra_fields() -> None:
    record = ProjectRecord(
        project_id="project:1", project_key="personal_agent", created_at_ns=1, last_seen_at_ns=1
    )
    with pytest.raises(ValidationError):
        ProjectRecord(
            project_id="project:1",
            project_key="personal_agent",
            created_at_ns=1,
            last_seen_at_ns=1,
            unexpected=True,
        )
    with pytest.raises(ValidationError):
        record.project_key = "other"


def test_ids_are_stable_and_workcopies_are_root_specific() -> None:
    project_id = project_id_for("personal_agent")
    assert project_id == project_id_for("personal_agent")
    assert workcopy_id_for(project_id, "C:/repo") != workcopy_id_for(project_id, "C:/repo-wt")


def test_task_id_depends_on_identity_not_git_branch() -> None:
    project_id = project_id_for("personal_agent")
    workcopy_id = workcopy_id_for(project_id, "C:/repo")
    first = task_id_for(project_id, workcopy_id, 123, "Task Continuity")
    second = task_id_for(project_id, workcopy_id, 123, "Task Continuity")
    assert first == second
    assert "branch" not in first


def test_ids_reject_empty_identity_inputs() -> None:
    with pytest.raises(ValueError):
        project_id_for("")
    with pytest.raises(ValueError):
        workcopy_id_for("project:1", "")


def test_all_v1_records_are_constructible_and_json_safe() -> None:
    project = ProjectRecord(
        project_id="project:1", project_key="p", created_at_ns=1, last_seen_at_ns=1
    )
    workcopy = WorkCopyRecord(
        workcopy_id="workcopy:1",
        project_id=project.project_id,
        canonical_root="C:/r",
        created_at_ns=1,
        last_seen_at_ns=1,
    )
    task = TaskRecord(
        task_id="task:1",
        project_id=project.project_id,
        workcopy_id=workcopy.workcopy_id,
        title="t",
        created_at_ns=1,
    )
    evidence = EvidenceRecord(
        evidence_id="e:1",
        kind="user_note",
        source_ref="manual",
        observed_at_ns=1,
        available_at_ns=1,
        project_id=project.project_id,
        workcopy_id=workcopy.workcopy_id,
        task_id=task.task_id,
        scope="task",
        provenance=FieldProvenance.USER_DECLARED,
        content={"text": "x"},
    )
    field = TaskStateFieldVersion(
        field_version_id="f:1",
        project_id=project.project_id,
        workcopy_id=workcopy.workcopy_id,
        task_id=task.task_id,
        field_name="current_goal",
        value="x",
        provenance=FieldProvenance.USER_DECLARED,
        applicability=ApplicabilityStatus.CURRENT,
        evidence_ids=[evidence.evidence_id],
        created_at_ns=1,
    )
    verified = VerifiedResultRecord(
        result_id="v:1",
        project_id=project.project_id,
        workcopy_id=workcopy.workcopy_id,
        check_kind="pytest",
        command_or_adapter_scope="user_report",
        environment_fingerprint="env",
        code_state_fingerprint="code",
        observed_at_ns=1,
        outcome="pass",
        evidence_ids=[evidence.evidence_id],
    )
    snapshot = TaskSnapshot(
        snapshot_id="s:1",
        project_id=project.project_id,
        workcopy_id=workcopy.workcopy_id,
        task_id=task.task_id,
        captured_at_ns=1,
        field_version_ids=[field.field_version_id],
        evidence_ids=[evidence.evidence_id],
    )
    brief = ResumeBriefRecord(
        brief_id="b:1",
        snapshot_id=snapshot.snapshot_id,
        project_id=project.project_id,
        workcopy_id=workcopy.workcopy_id,
        task_id=task.task_id,
        created_at_ns=1,
        sections={"current_task": "t"},
        evidence_ids=[evidence.evidence_id],
    )
    tombstone = DeletionTombstoneRecord(
        deletion_id="d:1", scope_type="evidence", scope_hash="abc", deleted_at_ns=2
    )
    for model in (project, workcopy, task, evidence, field, verified, snapshot, brief, tombstone):
        assert isinstance(model.model_dump(mode="json"), dict)

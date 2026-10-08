from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from personal_predictive_ai.continuity.models import (
    EvidenceRecord,
    FieldProvenance,
    ProjectRecord,
    TaskRecord,
    WorkCopyRecord,
)
from personal_predictive_ai.storage.continuity_store import ContinuityStore


def _identity_records(root: Path) -> tuple[ProjectRecord, WorkCopyRecord, TaskRecord]:
    project = ProjectRecord(
        project_id="project:one", project_key="p", created_at_ns=1, last_seen_at_ns=1
    )
    workcopy = WorkCopyRecord(
        workcopy_id="workcopy:one",
        project_id=project.project_id,
        canonical_root=str(root),
        created_at_ns=2,
        last_seen_at_ns=2,
    )
    task = TaskRecord(
        task_id="task:one",
        project_id=project.project_id,
        workcopy_id=workcopy.workcopy_id,
        title="task",
        created_at_ns=3,
    )
    return project, workcopy, task


def test_continuity_store_round_trip_and_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "continuity.db"
    project, workcopy, task = _identity_records(tmp_path)
    store = ContinuityStore(db_path)
    store.add_project(project)
    store.add_workcopy(workcopy)
    store.add_task(task)
    assert store.get_project(project.project_id) == project
    assert store.get_workcopy(workcopy.workcopy_id) == workcopy
    assert store.get_task(task.task_id) == task
    assert store.integrity_check() == "ok"
    store.close()

    reopened = ContinuityStore(db_path)
    try:
        assert reopened.get_task(task.task_id) == task
        assert reopened.integrity_check() == "ok"
    finally:
        reopened.close()


def test_store_rejects_unknown_identity_foreign_keys(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            store.add_task(
                TaskRecord(
                    task_id="task:bad",
                    project_id="project:missing",
                    workcopy_id="workcopy:missing",
                    title="bad",
                    created_at_ns=1,
                )
            )
    finally:
        store.close()


def test_evidence_iteration_is_scope_ordered_and_as_of_safe(tmp_path: Path) -> None:
    project, workcopy, task = _identity_records(tmp_path)
    store = ContinuityStore(tmp_path / "continuity.db")
    store.add_project(project)
    store.add_workcopy(workcopy)
    store.add_task(task)
    early = EvidenceRecord(
        evidence_id="e:early",
        kind="note",
        source_ref="manual",
        observed_at_ns=4,
        available_at_ns=5,
        project_id=project.project_id,
        workcopy_id=workcopy.workcopy_id,
        task_id=task.task_id,
        scope="task",
        provenance=FieldProvenance.USER_DECLARED,
        content={"text": "early"},
    )
    late = early.model_copy(
        update={
            "evidence_id": "e:late",
            "observed_at_ns": 6,
            "available_at_ns": 10,
            "content": {"text": "late"},
        }
    )
    store.add_evidence(late)
    store.add_evidence(early)
    try:
        visible = list(
            store.iter_evidence(
                project.project_id,
                workcopy_id=workcopy.workcopy_id,
                task_id=task.task_id,
                as_of_ns=7,
            )
        )
        assert visible == [early]
        assert list(store.iter_evidence(project.project_id)) == [early, late]
    finally:
        store.close()

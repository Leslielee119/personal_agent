from __future__ import annotations

from pathlib import Path

from personal_predictive_ai.continuity.git_observer import GitObserver
from personal_predictive_ai.continuity.ids import evidence_id_for, field_version_id_for
from personal_predictive_ai.continuity.models import (
    ApplicabilityStatus,
    EvidenceRecord,
    FieldProvenance,
    TaskStateFieldVersion,
)
from personal_predictive_ai.continuity.registry import ContinuityRegistry
from personal_predictive_ai.continuity.state import TaskStateService
from personal_predictive_ai.continuity.verification import VerificationService
from personal_predictive_ai.storage.continuity_store import ContinuityStore


def _git_repo(tmp_path: Path):
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    commands = (
        ("init",),
        ("config", "user.email", "t@example.com"),
        ("config", "user.name", "T"),
    )
    for args in commands:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    (root / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "a.txt"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    return root


def test_verification_applicability_tracks_complete_git_state(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    store = ContinuityStore(tmp_path / "continuity.db")
    try:
        binding = ContinuityRegistry(store).bind("p", root, "task", now_ns=1)
        observer = GitObserver()
        clean = observer.observe(binding.workcopy, now_ns=10)
        service = VerificationService(store)
        result = service.record_user_declared(
            binding.task.task_id,
            check_kind="pytest",
            outcome="pass",
            command_or_adapter_scope="pytest -q",
            git_state=clean,
            now_ns=11,
        )
        assert service.evaluate(result, clean) == ApplicabilityStatus.CURRENT

        (root / "a.txt").write_text("two\n", encoding="utf-8")
        dirty = observer.observe(binding.workcopy, now_ns=20)
        assert service.evaluate(result, dirty) == ApplicabilityStatus.NEEDS_REVALIDATION

        (root / "a.txt").write_text("one\n", encoding="utf-8")
        restored = observer.observe(binding.workcopy, now_ns=30)
        assert service.evaluate(result, restored) == ApplicabilityStatus.CURRENT
    finally:
        store.close()


def test_conflicting_active_field_versions_are_preserved_as_conflict(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    store = ContinuityStore(tmp_path / "continuity.db")
    try:
        binding = ContinuityRegistry(store).bind("p", root, "task", now_ns=1)
        task = binding.task
        for index, (value, provenance) in enumerate((
            ("user goal", FieldProvenance.USER_DECLARED),
            ("observed goal", FieldProvenance.OBSERVED),
        ), start=10):
            evidence_id = evidence_id_for(
                task.project_id, task.workcopy_id, task.task_id,
                "goal", f"source:{index}", index, {"value": value},
            )
            store.add_evidence(EvidenceRecord(
                evidence_id=evidence_id, kind="goal", source_ref=f"source:{index}",
                observed_at_ns=index, available_at_ns=index,
                project_id=task.project_id, workcopy_id=task.workcopy_id,
                task_id=task.task_id, scope="task", provenance=provenance,
                content={"value": value},
            ))
            store.add_field_version(TaskStateFieldVersion(
                field_version_id=field_version_id_for(
                    task.task_id, "current_goal", value, index, [evidence_id]
                ),
                project_id=task.project_id, workcopy_id=task.workcopy_id,
                task_id=task.task_id, field_name="current_goal", value=value,
                provenance=provenance, evidence_ids=[evidence_id], created_at_ns=index,
            ))
        snapshot = TaskStateService(store).build(task.task_id, as_of_ns=20)
        assert snapshot.current_goal is None
        assert len(snapshot.conflicts) == 1
        conflict = snapshot.conflicts[0]
        assert conflict.field_name == "current_goal"
        assert set(conflict.values) == {"user goal", "observed goal"}
        assert len(conflict.evidence_ids) == 2
    finally:
        store.close()


def test_snapshot_records_current_git_observation_evidence(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    store = ContinuityStore(tmp_path / "continuity.db")
    try:
        binding = ContinuityRegistry(store).bind("p", root, "task", now_ns=1)
        TaskStateService(store).initialize(
            binding.task.task_id,
            current_goal="goal",
            last_position="position",
            next_step="next",
            now_ns=5,
        )
        git_state = GitObserver().observe(binding.workcopy, now_ns=10)
        snapshot = TaskStateService(store).build(
            binding.task.task_id, as_of_ns=10, git_state=git_state
        )
        repeated = TaskStateService(store).build(
            binding.task.task_id, as_of_ns=10, git_state=git_state
        )
        assert repeated.snapshot_id == snapshot.snapshot_id
        evidence = list(
            store.iter_evidence(
                binding.project.project_id,
                workcopy_id=binding.workcopy.workcopy_id,
                task_id=binding.task.task_id,
                as_of_ns=10,
            )
        )
        git_evidence = [item for item in evidence if item.kind == "git_state"]
        assert len(git_evidence) == 1
        assert git_evidence[0].evidence_id in snapshot.evidence_ids
    finally:
        store.close()


def test_verification_environment_drift_requires_revalidation(
    tmp_path: Path, monkeypatch
) -> None:
    root = _git_repo(tmp_path)
    store = ContinuityStore(tmp_path / "continuity.db")
    try:
        binding = ContinuityRegistry(store).bind("p", root, "task", now_ns=1)
        git_state = GitObserver().observe(binding.workcopy, now_ns=10)
        service = VerificationService(store)
        result = service.record_user_declared(
            binding.task.task_id,
            check_kind="pytest",
            outcome="pass",
            command_or_adapter_scope="pytest -q",
            git_state=git_state,
            now_ns=11,
        )
        monkeypatch.setattr(
            VerificationService,
            "_environment_fingerprint",
            staticmethod(lambda: "changed-environment"),
        )
        assert service.evaluate(result, git_state) == ApplicabilityStatus.NEEDS_REVALIDATION
    finally:
        store.close()

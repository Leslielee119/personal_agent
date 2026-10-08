from __future__ import annotations

from pathlib import Path

from personal_predictive_ai.continuity.brief import ResumeBriefService
from personal_predictive_ai.continuity.corrections import CorrectionService, EvidenceViewService
from personal_predictive_ai.continuity.registry import ContinuityRegistry
from personal_predictive_ai.continuity.state import TaskStateService
from personal_predictive_ai.storage.continuity_store import ContinuityStore

_SENTINEL = "DELETE-ME-UNIQUE-7f3c91"


def _create_task(store: ContinuityStore, root: Path, project: str, title: str, now_ns: int):
    binding = ContinuityRegistry(store).bind(project, root, title, now_ns=now_ns)
    snapshot = TaskStateService(store).initialize(
        binding.task.task_id,
        current_goal=_SENTINEL,
        last_position="safe position",
        next_step="safe next",
        now_ns=now_ns + 1,
    )
    ResumeBriefService(store).render(snapshot, generated_at_ns=now_ns + 2)
    return binding


def test_forget_evidence_removes_derived_and_physical_content(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    db_path = tmp_path / "continuity.db"
    store = ContinuityStore(db_path)
    try:
        binding = _create_task(store, root, "p", "task", 10)
        goal_evidence = EvidenceViewService(store).list_for_task(
            binding.task.task_id, field_name="current_goal"
        )
        assert len(goal_evidence) == 1
        tombstone = CorrectionService(store).forget(
            "evidence", goal_evidence[0].evidence_id, now_ns=30
        )
        assert tombstone.scope_type == "evidence"
        assert _SENTINEL not in str(tombstone.model_dump(mode="json"))
        assert EvidenceViewService(store).list_for_task(
            binding.task.task_id, field_name="current_goal"
        ) == []
        rebuilt = TaskStateService(store).build(binding.task.task_id, as_of_ns=31)
        assert rebuilt.current_goal is None
        assert all(
            _SENTINEL not in str(item.model_dump(mode="json"))
            for item in store.iter_snapshots(binding.task.task_id)
        )
        assert all(
            _SENTINEL not in str(item.model_dump(mode="json"))
            for item in store.iter_briefs(binding.task.task_id)
        )
    finally:
        store.close()

    sentinel = _SENTINEL.encode("utf-8")
    for candidate in (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
        if candidate.exists():
            assert sentinel not in candidate.read_bytes()


def test_task_workcopy_and_project_deletion_are_scope_isolated(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_c = tmp_path / "c"
    for root in (root_a, root_b, root_c):
        root.mkdir()
    store = ContinuityStore(tmp_path / "continuity.db")
    try:
        a = ContinuityRegistry(store).bind("p", root_a, "a", now_ns=1)
        b = ContinuityRegistry(store).bind("p", root_b, "b", now_ns=2)
        c = ContinuityRegistry(store).bind("q", root_c, "c", now_ns=3)

        CorrectionService(store).forget("task", a.task.task_id, now_ns=10)
        assert store.get_task(a.task.task_id) is None
        assert store.get_task(b.task.task_id) is not None

        CorrectionService(store).forget("workcopy", b.workcopy.workcopy_id, now_ns=20)
        assert store.get_workcopy(b.workcopy.workcopy_id) is None
        assert store.get_project(b.project.project_id) is not None

        CorrectionService(store).forget("project", b.project.project_id, now_ns=30)
        assert store.get_project(b.project.project_id) is None
        assert store.get_project(c.project.project_id) is not None
    finally:
        store.close()

from __future__ import annotations

from pathlib import Path

from personal_predictive_ai.continuity.brief import ResumeBriefService
from personal_predictive_ai.continuity.corrections import CorrectionService, EvidenceViewService
from personal_predictive_ai.continuity.models import ContinuityRecordStatus
from personal_predictive_ai.continuity.registry import ContinuityRegistry
from personal_predictive_ai.continuity.state import TaskStateService
from personal_predictive_ai.storage.continuity_store import ContinuityStore


def _task(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    store = ContinuityStore(tmp_path / "continuity.db")
    binding = ContinuityRegistry(store).bind("p", root, "task", now_ns=1)
    TaskStateService(store).initialize(
        binding.task.task_id,
        current_goal="old goal",
        last_position="position",
        next_step="next",
        now_ns=10,
    )
    return store, binding


def test_scalar_correction_supersedes_old_version_and_updates_brief(tmp_path: Path) -> None:
    store, binding = _task(tmp_path)
    try:
        snapshot = CorrectionService(store).correct_scalar(
            binding.task.task_id, "current_goal", "new goal", now_ns=20
        )
        versions = list(
            store.iter_field_versions(binding.task.task_id, field_name="current_goal")
        )
        assert len(versions) == 2
        assert versions[0].status == ContinuityRecordStatus.SUPERSEDED
        assert versions[1].status == ContinuityRecordStatus.ACTIVE
        assert versions[1].supersedes == versions[0].field_version_id
        assert snapshot.current_goal == "new goal"
        brief = ResumeBriefService(store).render(snapshot, generated_at_ns=21)
        text = ResumeBriefService(store).render_text(brief)
        assert "new goal" in text
        assert "old goal" not in text
    finally:
        store.close()


def test_add_and_resolve_blocker_updates_compact_attention_but_keeps_evidence(
    tmp_path: Path,
) -> None:
    store, binding = _task(tmp_path)
    try:
        service = CorrectionService(store)
        blocked = service.add_item(
            binding.task.task_id, "blockers", "fix parser", now_ns=20
        )
        assert blocked.blockers == ["fix parser"]
        text = ResumeBriefService(store).render_text(
            ResumeBriefService(store).render(blocked, generated_at_ns=21)
        )
        assert "需要注意" in text and "fix parser" in text
        resolved = service.resolve_item(
            binding.task.task_id, "blockers", "fix parser", now_ns=30
        )
        assert resolved.blockers == []
        text = ResumeBriefService(store).render_text(
            ResumeBriefService(store).render(resolved, generated_at_ns=31)
        )
        assert "需要注意" not in text
        evidence = EvidenceViewService(store).list_for_task(binding.task.task_id)
        assert any(item.content.get("action") == "resolve" for item in evidence)
        assert any(item.content.get("value") == "fix parser" for item in evidence)
    finally:
        store.close()


def test_evidence_view_is_task_scoped_and_as_of_safe(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    store = ContinuityStore(tmp_path / "continuity.db")
    try:
        registry = ContinuityRegistry(store)
        first = registry.bind("p", root, "first", now_ns=1)
        second = registry.bind("p", root, "second", now_ns=2)
        TaskStateService(store).initialize(
            first.task.task_id, current_goal="first-old", last_position="", next_step="",
            now_ns=10,
        )
        TaskStateService(store).initialize(
            second.task.task_id, current_goal="second", last_position="", next_step="",
            now_ns=15,
        )
        CorrectionService(store).correct_scalar(
            first.task.task_id, "current_goal", "first-new", now_ns=20
        )
        view = EvidenceViewService(store)
        at_t10 = view.list_for_task(first.task.task_id, as_of_ns=10)
        assert any(item.content.get("value") == "first-old" for item in at_t10)
        assert not any(item.content.get("value") == "first-new" for item in at_t10)
        current = view.list_for_task(first.task.task_id)
        assert not any(item.task_id == second.task.task_id for item in current)
    finally:
        store.close()

from __future__ import annotations

from pathlib import Path

from personal_predictive_ai.continuity.brief import ResumeBriefService
from personal_predictive_ai.continuity.registry import ContinuityRegistry
from personal_predictive_ai.continuity.state import TaskStateService
from personal_predictive_ai.storage.continuity_store import ContinuityStore


def _bound_task(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    store = ContinuityStore(tmp_path / "continuity.db")
    binding = ContinuityRegistry(store).bind("personal_agent", root, "Task Continuity", now_ns=1)
    return store, binding


def test_first_use_note_renders_compact_resume_brief(tmp_path: Path) -> None:
    store, binding = _bound_task(tmp_path)
    try:
        state = TaskStateService(store)
        snapshot = state.initialize(
            binding.task.task_id,
            current_goal="实现 Task Continuity",
            last_position="完成 registry",
            next_step="实现 Resume Brief",
            now_ns=10,
        )
        brief = ResumeBriefService(store).render(snapshot, generated_at_ns=11)
        text = ResumeBriefService(store).render_text(brief)
        assert "当前任务" in text
        assert "上次停在哪里" in text
        assert "建议继续" in text
        assert "需要注意" not in text
        assert "实现 Task Continuity" in text
        assert len(brief.evidence_ids) == 3
    finally:
        store.close()


def test_build_as_of_never_uses_future_task_state(tmp_path: Path) -> None:
    store, binding = _bound_task(tmp_path)
    try:
        state = TaskStateService(store)
        state.initialize(
            binding.task.task_id,
            current_goal="旧目标",
            last_position="旧位置",
            next_step="旧下一步",
            now_ns=10,
        )
        state.initialize(
            binding.task.task_id,
            current_goal="未来目标",
            last_position="未来位置",
            next_step="未来下一步",
            now_ns=20,
        )
        snapshot = state.build(binding.task.task_id, as_of_ns=10)
        assert snapshot.current_goal == "旧目标"
        assert snapshot.last_position == "旧位置"
        assert snapshot.candidate_next_step == "旧下一步"
        assert "未来目标" not in ResumeBriefService(store).render_text(
            ResumeBriefService(store).render(snapshot, generated_at_ns=21)
        )
    finally:
        store.close()

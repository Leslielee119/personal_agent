from __future__ import annotations

from pathlib import Path

import pytest

from personal_predictive_ai.continuity.registry import (
    ContinuityRegistry,
    UnknownTaskError,
    WorkCopyMismatchError,
)
from personal_predictive_ai.storage.continuity_store import ContinuityStore


def test_same_project_two_roots_are_isolated_workcopies(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    store = ContinuityStore(tmp_path / "continuity.db")
    registry = ContinuityRegistry(store)
    try:
        a = registry.bind("personal_agent", root_a, "task-a", now_ns=1)
        b = registry.bind("personal_agent", root_b, "task-b", now_ns=2)
        assert a.project.project_id == b.project.project_id
        assert a.workcopy.workcopy_id != b.workcopy.workcopy_id
        assert a.task.task_id != b.task.task_id
    finally:
        store.close()


def test_same_workcopy_can_hold_multiple_tasks_without_branch_identity(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    store = ContinuityStore(tmp_path / "continuity.db")
    registry = ContinuityRegistry(store)
    try:
        one = registry.bind("p", root, "feat/foo", now_ns=1)
        two = registry.bind("p", root, "feat/bar", now_ns=2)
        assert one.workcopy.workcopy_id == two.workcopy.workcopy_id
        assert one.task.task_id != two.task.task_id
        assert "feat" not in one.task.task_id
    finally:
        store.close()


def test_resolve_task_fails_closed_on_wrong_workcopy(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    store = ContinuityStore(tmp_path / "continuity.db")
    registry = ContinuityRegistry(store)
    try:
        binding = registry.bind("p", root_a, "task", now_ns=1)
        with pytest.raises(WorkCopyMismatchError):
            registry.resolve_task(binding.task.task_id, expected_workcopy_root=root_b)
        with pytest.raises(UnknownTaskError):
            registry.resolve_task("task:missing")
    finally:
        store.close()

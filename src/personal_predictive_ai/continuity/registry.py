from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from personal_predictive_ai.continuity.ids import project_id_for, task_id_for, workcopy_id_for
from personal_predictive_ai.continuity.models import ProjectRecord, TaskRecord, WorkCopyRecord
from personal_predictive_ai.storage.continuity_store import ContinuityStore


class UnknownTaskError(LookupError):
    pass


class WorkCopyMismatchError(ValueError):
    pass


@dataclass(frozen=True)
class TaskBinding:
    project: ProjectRecord
    workcopy: WorkCopyRecord
    task: TaskRecord


def _canonical_root(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=True)))


class ContinuityRegistry:
    def __init__(self, store: ContinuityStore) -> None:
        self.store = store

    def bind(
        self,
        project_key: str,
        workcopy_root: Path,
        task_title: str,
        *,
        now_ns: int,
    ) -> TaskBinding:
        canonical_root = _canonical_root(workcopy_root)
        project_id = project_id_for(project_key)
        project = self.store.get_project(project_id)
        if project is None:
            project = ProjectRecord(
                project_id=project_id,
                project_key=project_key,
                created_at_ns=now_ns,
                last_seen_at_ns=now_ns,
            )
            self.store.add_project(project)

        workcopy_id = workcopy_id_for(project_id, canonical_root)
        workcopy = self.store.get_workcopy(workcopy_id)
        if workcopy is None:
            workcopy = WorkCopyRecord(
                workcopy_id=workcopy_id,
                project_id=project_id,
                canonical_root=canonical_root,
                created_at_ns=now_ns,
                last_seen_at_ns=now_ns,
            )
            self.store.add_workcopy(workcopy)

        task = TaskRecord(
            task_id=task_id_for(project_id, workcopy_id, now_ns, task_title),
            project_id=project_id,
            workcopy_id=workcopy_id,
            title=task_title,
            created_at_ns=now_ns,
        )
        self.store.add_task(task)
        return TaskBinding(project=project, workcopy=workcopy, task=task)

    def resolve_task(
        self,
        task_id: str,
        *,
        expected_workcopy_root: Path | None = None,
    ) -> TaskBinding:
        task = self.store.get_task(task_id)
        if task is None or task.workcopy_id is None:
            raise UnknownTaskError(task_id)
        project = self.store.get_project(task.project_id)
        workcopy = self.store.get_workcopy(task.workcopy_id)
        if project is None or workcopy is None:
            raise UnknownTaskError(task_id)
        if expected_workcopy_root is not None:
            expected = _canonical_root(expected_workcopy_root)
            if expected != workcopy.canonical_root:
                raise WorkCopyMismatchError(task_id)
        return TaskBinding(project=project, workcopy=workcopy, task=task)

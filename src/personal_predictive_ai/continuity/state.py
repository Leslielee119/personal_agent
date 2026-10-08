from __future__ import annotations

from personal_predictive_ai.continuity.ids import (
    evidence_id_for,
    field_version_id_for,
    snapshot_id_for,
)
from personal_predictive_ai.continuity.models import (
    EvidenceRecord,
    FieldProvenance,
    TaskSnapshot,
    TaskStateFieldVersion,
)
from personal_predictive_ai.storage.continuity_store import ContinuityStore

_SCALAR_FIELDS = ("current_goal", "last_position", "candidate_next_step")


class TaskStateService:
    def __init__(self, store: ContinuityStore) -> None:
        self.store = store

    def initialize(
        self,
        task_id: str,
        *,
        current_goal: str,
        last_position: str,
        next_step: str,
        now_ns: int,
    ) -> TaskSnapshot:
        values = {
            "current_goal": current_goal,
            "last_position": last_position,
            "candidate_next_step": next_step,
        }
        task = self.store.get_task(task_id)
        if task is None or task.workcopy_id is None:
            raise KeyError(task_id)
        for field_name, value in values.items():
            if not value:
                continue
            evidence_id = evidence_id_for(
                task.project_id,
                task.workcopy_id,
                task.task_id,
                "user_note",
                f"manual:{field_name}",
                now_ns,
                {"field": field_name, "value": value},
            )
            evidence = EvidenceRecord(
                evidence_id=evidence_id,
                kind="user_note",
                source_ref=f"manual:{field_name}",
                observed_at_ns=now_ns,
                available_at_ns=now_ns,
                project_id=task.project_id,
                workcopy_id=task.workcopy_id,
                task_id=task.task_id,
                scope="task",
                provenance=FieldProvenance.USER_DECLARED,
                content={"field": field_name, "value": value},
            )
            self.store.add_evidence(evidence)
            field_id = field_version_id_for(task_id, field_name, value, now_ns, [evidence_id])
            self.store.add_field_version(
                TaskStateFieldVersion(
                    field_version_id=field_id,
                    project_id=task.project_id,
                    workcopy_id=task.workcopy_id,
                    task_id=task.task_id,
                    field_name=field_name,
                    value=value,
                    provenance=FieldProvenance.USER_DECLARED,
                    evidence_ids=[evidence_id],
                    created_at_ns=now_ns,
                )
            )
        return self.build(task_id, as_of_ns=now_ns)

    def build(self, task_id: str, *, as_of_ns: int) -> TaskSnapshot:
        task = self.store.get_task(task_id)
        if task is None or task.workcopy_id is None:
            raise KeyError(task_id)
        latest: dict[str, TaskStateFieldVersion] = {}
        for item in self.store.iter_field_versions(task_id, as_of_ns=as_of_ns):
            if item.status.value == "active":
                latest[item.field_name] = item
        field_ids = [item.field_version_id for item in latest.values()]
        evidence_ids = [eid for item in latest.values() for eid in item.evidence_ids]
        snapshot_id = snapshot_id_for(task_id, as_of_ns, sorted(field_ids))
        existing = self.store.get_snapshot(snapshot_id)
        if existing is not None:
            return existing
        snapshot = TaskSnapshot(
            snapshot_id=snapshot_id,
            project_id=task.project_id,
            workcopy_id=task.workcopy_id,
            task_id=task.task_id,
            captured_at_ns=as_of_ns,
            current_goal=_text(latest.get("current_goal")),
            last_position=_text(latest.get("last_position")),
            candidate_next_step=_text(latest.get("candidate_next_step")),
            blockers=_items(latest.get("blockers")),
            pending_items=_items(latest.get("pending_items")),
            constraints=_items(latest.get("constraints")),
            field_version_ids=sorted(field_ids),
            evidence_ids=sorted(set(evidence_ids)),
        )
        self.store.add_snapshot(snapshot)
        return snapshot


def _text(item: TaskStateFieldVersion | None) -> str | None:
    return None if item is None else str(item.value)


def _items(item: TaskStateFieldVersion | None) -> list[str]:
    if item is None:
        return []
    return (
        [str(value) for value in item.value] if isinstance(item.value, list) else [str(item.value)]
    )

from __future__ import annotations

from personal_predictive_ai.continuity.ids import evidence_id_for, field_version_id_for
from personal_predictive_ai.continuity.models import (
    ContinuityRecordStatus,
    EvidenceRecord,
    FieldProvenance,
    TaskSnapshot,
    TaskStateFieldVersion,
)
from personal_predictive_ai.continuity.state import TaskStateService
from personal_predictive_ai.storage.continuity_store import ContinuityStore

_SCALAR_FIELDS = {"current_goal", "last_position", "candidate_next_step"}
_LIST_FIELDS = {"blockers", "pending_items", "constraints"}


class CorrectionService:
    def __init__(self, store: ContinuityStore) -> None:
        self.store = store
        self.state = TaskStateService(store)

    def correct_scalar(
        self,
        task_id: str,
        field_name: str,
        value: str,
        *,
        now_ns: int,
    ) -> TaskSnapshot:
        if field_name not in _SCALAR_FIELDS:
            raise ValueError("set action requires a scalar task field")
        active = self._active_versions(task_id, field_name)
        evidence = self._write_evidence(
            task_id, field_name, value, action="set", now_ns=now_ns
        )
        for old in active:
            self.store.replace_field_version(
                old.model_copy(update={"status": ContinuityRecordStatus.SUPERSEDED})
            )
        supersedes = active[-1].field_version_id if active else None
        self._add_field_version(
            task_id,
            field_name,
            value,
            evidence.evidence_id,
            now_ns=now_ns,
            supersedes=supersedes,
        )
        return self.state.build(task_id, as_of_ns=now_ns)

    def add_item(
        self,
        task_id: str,
        field_name: str,
        value: str,
        *,
        now_ns: int,
    ) -> TaskSnapshot:
        if field_name not in _LIST_FIELDS:
            raise ValueError("add action requires a list task field")
        evidence = self._write_evidence(
            task_id, field_name, value, action="add", now_ns=now_ns
        )
        self._add_field_version(
            task_id, field_name, value, evidence.evidence_id, now_ns=now_ns
        )
        return self.state.build(task_id, as_of_ns=now_ns)

    def resolve_item(
        self,
        task_id: str,
        field_name: str,
        value: str,
        *,
        now_ns: int,
    ) -> TaskSnapshot:
        if field_name not in _LIST_FIELDS:
            raise ValueError("resolve action requires a list task field")
        matching = [
            item for item in self._active_versions(task_id, field_name) if str(item.value) == value
        ]
        if not matching:
            raise KeyError(f"active item not found: {field_name}={value}")
        self._write_evidence(task_id, field_name, value, action="resolve", now_ns=now_ns)
        for old in matching:
            self.store.replace_field_version(
                old.model_copy(update={"status": ContinuityRecordStatus.SUPERSEDED})
            )
        return self.state.build(task_id, as_of_ns=now_ns)

    def _active_versions(self, task_id: str, field_name: str) -> list[TaskStateFieldVersion]:
        return [
            item
            for item in self.store.iter_field_versions(task_id, field_name=field_name)
            if item.status == ContinuityRecordStatus.ACTIVE
        ]

    def _write_evidence(
        self,
        task_id: str,
        field_name: str,
        value: str,
        *,
        action: str,
        now_ns: int,
    ) -> EvidenceRecord:
        task = self.store.get_task(task_id)
        if task is None or task.workcopy_id is None:
            raise KeyError(task_id)
        content = {"action": action, "field": field_name, "value": value}
        evidence_id = evidence_id_for(
            task.project_id,
            task.workcopy_id,
            task.task_id,
            "correction",
            f"user_correction:{field_name}:{action}",
            now_ns,
            content,
        )
        evidence = EvidenceRecord(
            evidence_id=evidence_id,
            kind="correction",
            source_ref=f"user_correction:{field_name}:{action}",
            observed_at_ns=now_ns,
            available_at_ns=now_ns,
            project_id=task.project_id,
            workcopy_id=task.workcopy_id,
            task_id=task.task_id,
            scope="task",
            provenance=FieldProvenance.USER_DECLARED,
            content=content,
        )
        self.store.add_evidence(evidence)
        return evidence

    def _add_field_version(
        self,
        task_id: str,
        field_name: str,
        value: str,
        evidence_id: str,
        *,
        now_ns: int,
        supersedes: str | None = None,
    ) -> TaskStateFieldVersion:
        task = self.store.get_task(task_id)
        if task is None or task.workcopy_id is None:
            raise KeyError(task_id)
        record = TaskStateFieldVersion(
            field_version_id=field_version_id_for(
                task_id, field_name, value, now_ns, [evidence_id]
            ),
            project_id=task.project_id,
            workcopy_id=task.workcopy_id,
            task_id=task.task_id,
            field_name=field_name,
            value=value,
            provenance=FieldProvenance.USER_DECLARED,
            evidence_ids=[evidence_id],
            created_at_ns=now_ns,
            supersedes=supersedes,
        )
        self.store.add_field_version(record)
        return record


class EvidenceViewService:
    def __init__(self, store: ContinuityStore) -> None:
        self.store = store

    def list_for_task(
        self,
        task_id: str,
        *,
        field_name: str | None = None,
        as_of_ns: int | None = None,
    ) -> list[EvidenceRecord]:
        task = self.store.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        items = list(
            self.store.iter_evidence(
                task.project_id,
                workcopy_id=task.workcopy_id,
                task_id=task.task_id,
                as_of_ns=as_of_ns,
            )
        )
        if field_name is None:
            return items
        return [item for item in items if item.content.get("field") == field_name]

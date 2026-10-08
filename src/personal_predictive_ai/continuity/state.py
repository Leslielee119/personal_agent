from __future__ import annotations

import json

from personal_predictive_ai.continuity.ids import (
    evidence_id_for,
    field_version_id_for,
    snapshot_id_for,
)
from personal_predictive_ai.continuity.models import (
    EvidenceRecord,
    FieldConflict,
    FieldProvenance,
    GitWorkCopyState,
    TaskSnapshot,
    TaskStateFieldVersion,
)
from personal_predictive_ai.continuity.verification import VerificationService
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

    def build(
        self,
        task_id: str,
        *,
        as_of_ns: int,
        git_state: GitWorkCopyState | None = None,
    ) -> TaskSnapshot:
        task = self.store.get_task(task_id)
        if task is None or task.workcopy_id is None:
            raise KeyError(task_id)

        git_evidence_id: str | None = None
        if git_state is not None:
            if git_state.workcopy_id != task.workcopy_id:
                raise ValueError("git state workcopy does not match task workcopy")
            if git_state.observed_at_ns > as_of_ns:
                raise ValueError("git state cannot be observed after snapshot as_of")
            git_content = git_state.model_dump(mode="json")
            git_evidence_id = evidence_id_for(
                task.project_id,
                task.workcopy_id,
                task.task_id,
                "git_state",
                "git_observer",
                git_state.observed_at_ns,
                git_content,
            )
            self.store.add_evidence(
                EvidenceRecord(
                    evidence_id=git_evidence_id,
                    kind="git_state",
                    source_ref="git_observer",
                    observed_at_ns=git_state.observed_at_ns,
                    available_at_ns=git_state.observed_at_ns,
                    project_id=task.project_id,
                    workcopy_id=task.workcopy_id,
                    task_id=task.task_id,
                    scope="workcopy",
                    provenance=FieldProvenance.OBSERVED,
                    content=git_content,
                )
            )

        active_by_field: dict[str, list[TaskStateFieldVersion]] = {}
        for item in self.store.iter_field_versions(task_id, as_of_ns=as_of_ns):
            if item.status.value == "active":
                active_by_field.setdefault(item.field_name, []).append(item)

        latest: dict[str, TaskStateFieldVersion] = {}
        conflicts: list[FieldConflict] = []
        all_active: list[TaskStateFieldVersion] = []
        for field_name, candidates in active_by_field.items():
            all_active.extend(candidates)
            distinct = {
                json.dumps(item.value, ensure_ascii=False, sort_keys=True): item.value
                for item in candidates
            }
            if field_name in _SCALAR_FIELDS and len(distinct) > 1:
                conflicts.append(
                    FieldConflict(
                        field_name=field_name,
                        field_version_ids=[item.field_version_id for item in candidates],
                        evidence_ids=sorted(
                            {eid for item in candidates for eid in item.evidence_ids}
                        ),
                        values=list(distinct.values()),
                    )
                )
                continue
            latest[field_name] = candidates[-1]

        verification_results = list(
            self.store.iter_verified_results(task_id, as_of_ns=as_of_ns)
        )
        verified_result_ids: list[str] = []
        verification_applicability = {}
        if verification_results:
            current_result = verification_results[-1]
            verified_result_ids = [current_result.result_id]
            applicability = current_result.applicability
            if git_state is not None:
                applicability = VerificationService.evaluate(current_result, git_state)
            verification_applicability[current_result.result_id] = applicability

        field_ids = sorted(item.field_version_id for item in all_active)
        evidence_ids = sorted({eid for item in all_active for eid in item.evidence_ids})
        evidence_ids.extend(
            eid for item in verification_results[-1:] for eid in item.evidence_ids
        )
        if git_evidence_id is not None:
            evidence_ids.append(git_evidence_id)
        code_state_fingerprint = None if git_state is None else git_state.code_state_fingerprint
        snapshot_id = snapshot_id_for(
            task_id,
            as_of_ns,
            field_ids,
            verified_result_ids,
            code_state_fingerprint,
        )
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
            field_version_ids=field_ids,
            evidence_ids=sorted(set(evidence_ids)),
            verified_result_ids=verified_result_ids,
            verification_applicability=verification_applicability,
            conflicts=conflicts,
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

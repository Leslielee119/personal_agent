from __future__ import annotations

import hashlib
import json
import platform

from personal_predictive_ai.continuity.ids import evidence_id_for, verified_result_id_for
from personal_predictive_ai.continuity.models import (
    ApplicabilityStatus,
    EvidenceRecord,
    FieldProvenance,
    GitWorkCopyState,
    VerifiedResultRecord,
)
from personal_predictive_ai.storage.continuity_store import ContinuityStore


class VerificationService:
    def __init__(self, store: ContinuityStore) -> None:
        self.store = store

    def record_user_declared(
        self,
        task_id: str,
        *,
        check_kind: str,
        outcome: str,
        command_or_adapter_scope: str,
        git_state: GitWorkCopyState,
        now_ns: int,
    ) -> VerifiedResultRecord:
        task = self.store.get_task(task_id)
        if task is None or task.workcopy_id is None:
            raise KeyError(task_id)
        if git_state.workcopy_id != task.workcopy_id:
            raise ValueError("verification workcopy does not match task workcopy")
        content = {
            "check_kind": check_kind,
            "outcome": outcome,
            "command_or_adapter_scope": command_or_adapter_scope,
            "code_state_fingerprint": git_state.code_state_fingerprint,
        }
        evidence_id = evidence_id_for(
            task.project_id,
            task.workcopy_id,
            task.task_id,
            "verification",
            f"user_verification:{check_kind}",
            now_ns,
            content,
        )
        self.store.add_evidence(
            EvidenceRecord(
                evidence_id=evidence_id,
                kind="verification",
                source_ref=f"user_verification:{check_kind}",
                observed_at_ns=now_ns,
                available_at_ns=now_ns,
                project_id=task.project_id,
                workcopy_id=task.workcopy_id,
                task_id=task.task_id,
                scope="task",
                provenance=FieldProvenance.USER_DECLARED,
                content=content,
            )
        )
        environment_fingerprint = self._environment_fingerprint()
        result = VerifiedResultRecord(
            result_id=verified_result_id_for(
                task.workcopy_id,
                check_kind,
                git_state.code_state_fingerprint,
                now_ns,
            ),
            project_id=task.project_id,
            workcopy_id=task.workcopy_id,
            task_id=task.task_id,
            check_kind=check_kind,
            command_or_adapter_scope=command_or_adapter_scope,
            environment_fingerprint=environment_fingerprint,
            code_state_fingerprint=git_state.code_state_fingerprint,
            observed_at_ns=now_ns,
            outcome=outcome,
            evidence_ids=[evidence_id],
        )
        self.store.add_verified_result(result)
        return result

    @staticmethod
    def evaluate(
        result: VerifiedResultRecord,
        current_git_state: GitWorkCopyState,
    ) -> ApplicabilityStatus:
        if result.workcopy_id != current_git_state.workcopy_id:
            return ApplicabilityStatus.UNSUPPORTED
        if result.environment_fingerprint != VerificationService._environment_fingerprint():
            return ApplicabilityStatus.NEEDS_REVALIDATION
        if result.code_state_fingerprint != current_git_state.code_state_fingerprint:
            return ApplicabilityStatus.NEEDS_REVALIDATION
        return ApplicabilityStatus.CURRENT

    @staticmethod
    def _environment_fingerprint() -> str:
        payload = {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

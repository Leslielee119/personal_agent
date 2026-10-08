from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from personal_predictive_ai.knowledge.models import KnowledgeRecord, KnowledgeSourceClass
from personal_predictive_ai.skills.ids import proposal_id_for, skill_id_for
from personal_predictive_ai.skills.models import (
    MutationKind,
    PackageTrustState,
    ProposalStatus,
    SkillAuditEvent,
    SkillDraft,
    SkillMutationProposal,
    SkillRecord,
    SkillStatus,
)
from personal_predictive_ai.skills.safety import risk_rank
from personal_predictive_ai.storage.knowledge_skill_store import KnowledgeSkillStore


class StaleSkillVersionError(RuntimeError):
    pass


class RiskDowngradeApprovalRequired(RuntimeError):
    pass


class UnsupportedE1TransitionError(RuntimeError):
    pass


class UntrustedSkillPackageError(RuntimeError):
    pass

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit_id(skill_id: str, event_type: str, proposal_id: str, actor: str) -> str:
    payload = json.dumps(
        {
            "skill_id": skill_id,
            "event_type": event_type,
            "proposal_id": proposal_id,
            "actor": actor,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"audit:{hashlib.sha256(payload).hexdigest()}"


def _draft_payload(draft: SkillDraft) -> dict[str, Any]:
    return draft.model_dump(mode="json")


class TrustedRegistryService:
    def __init__(self, store: KnowledgeSkillStore) -> None:
        self.store = store

    def import_human_knowledge(self, record: KnowledgeRecord) -> KnowledgeRecord:
        human_sources = {
            KnowledgeSourceClass.HUMAN_DECLARED,
            KnowledgeSourceClass.HUMAN_APPROVED_IMPORT,
        }
        if record.source_class not in human_sources:
            raise ValueError("human-origin knowledge source required")
        self.store.put_knowledge(record)
        return record

    def _validate_package(self, draft: SkillDraft) -> None:
        if draft.source_package_id is None:
            return
        manifest = self.store.get_package_manifest(draft.source_package_id)
        if manifest is None or manifest.trust_state is not PackageTrustState.APPROVED:
            raise UntrustedSkillPackageError(draft.source_package_id)

    def stage_skill_create(
        self,
        draft: SkillDraft,
        *,
        proposed_by: str,
    ) -> SkillMutationProposal:
        self._validate_package(draft)
        skill_id = skill_id_for(draft.kind, draft.canonical_name, draft.scope)
        patch = _draft_payload(draft)
        proposal = SkillMutationProposal(
            proposal_id=proposal_id_for(
                skill_id,
                None,
                MutationKind.CREATE,
                patch,
                proposed_by,
            ),
            target_skill_id=skill_id,
            base_version=None,
            mutation_kind=MutationKind.CREATE,
            proposed_patch=patch,
            proposed_by=proposed_by,
            created_at=_utc_now(),
            validation_result={"valid": True},
        )
        self.store.stage_proposal(proposal)
        self._stage_audit(proposal)
        return proposal

    def stage_skill_update(
        self,
        skill_id: str,
        patch: dict[str, object],
        *,
        proposed_by: str,
    ) -> SkillMutationProposal:
        current = self.store.get_skill(skill_id)
        if current is None:
            raise KeyError(skill_id)
        if "status" in patch:
            requested = SkillStatus(str(patch["status"]))
            if requested in {SkillStatus.VERIFIED, SkillStatus.ACTIVE}:
                raise UnsupportedE1TransitionError(requested.value)
        proposal = SkillMutationProposal(
            proposal_id=proposal_id_for(
                skill_id,
                current.version,
                MutationKind.UPDATE,
                patch,
                proposed_by,
            ),
            target_skill_id=skill_id,
            base_version=current.version,
            mutation_kind=MutationKind.UPDATE,
            proposed_patch=patch,
            proposed_by=proposed_by,
            created_at=_utc_now(),
            validation_result={"valid": True},
        )
        self.store.stage_proposal(proposal)
        self._stage_audit(proposal)
        return proposal

    def reject_proposal(
        self,
        proposal_id: str,
        *,
        approver: str,
        reason: str,
    ) -> SkillMutationProposal:
        proposal = self.store.get_proposal(proposal_id)
        if proposal is None:
            raise KeyError(proposal_id)
        rejected = proposal.model_copy(
            update={
                "approval_status": ProposalStatus.REJECTED,
                "approved_by": approver,
                "approved_at": _utc_now(),
                "validation_result": {"valid": False, "reason": reason},
            }
        )
        self.store.replace_proposal(rejected)
        self.store.append_audit_event(
            SkillAuditEvent(
                audit_id=_audit_id(
                    proposal.target_skill_id,
                    "skill.proposal.rejected",
                    proposal.proposal_id,
                    approver,
                ),
                skill_id=proposal.target_skill_id,
                event_type="skill.proposal.rejected",
                actor=approver,
                occurred_at=rejected.approved_at or _utc_now(),
                details={"proposal_id": proposal.proposal_id, "reason": reason},
            )
        )
        return rejected

    def _stage_audit(self, proposal: SkillMutationProposal) -> None:
        self.store.append_audit_event(
            SkillAuditEvent(
                audit_id=_audit_id(
                    proposal.target_skill_id,
                    "skill.proposal.staged",
                    proposal.proposal_id,
                    proposal.proposed_by,
                ),
                skill_id=proposal.target_skill_id,
                event_type="skill.proposal.staged",
                actor=proposal.proposed_by,
                occurred_at=proposal.created_at,
                details={
                    "proposal_id": proposal.proposal_id,
                    "mutation_kind": proposal.mutation_kind.value,
                },
            )
        )

    def _record_from_create(
        self,
        proposal: SkillMutationProposal,
        *,
        created_at: str,
    ) -> SkillRecord:
        draft = SkillDraft.model_validate(proposal.proposed_patch)
        self._validate_package(draft)
        return SkillRecord(
            **draft.model_dump(exclude={"schema_version"}),
            skill_id=proposal.target_skill_id,
            version=1,
            status=SkillStatus.DRAFT,
            valid_from=0,
            created_by=proposal.proposed_by,
            created_at=created_at,
        )

    def _record_from_update(
        self,
        proposal: SkillMutationProposal,
        current: SkillRecord,
        *,
        created_at: str,
    ) -> SkillRecord:
        editable = current.model_dump(
            mode="json",
            exclude={
                "schema_version",
                "skill_id",
                "version",
                "status",
                "valid_from",
                "valid_to",
                "supersedes",
                "created_by",
                "created_at",
            },
        )
        editable.update(proposal.proposed_patch)
        draft = SkillDraft.model_validate(editable)
        self._validate_package(draft)
        return SkillRecord(
            **draft.model_dump(exclude={"schema_version"}),
            skill_id=current.skill_id,
            version=current.version + 1,
            status=SkillStatus.DRAFT,
            valid_from=current.valid_from,
            created_by=proposal.proposed_by,
            created_at=created_at,
        )

    def approve_proposal(
        self,
        proposal_id: str,
        *,
        approver: str,
        allow_risk_downgrade: bool = False,
    ) -> SkillRecord:
        proposal = self.store.get_proposal(proposal_id)
        if proposal is None:
            raise KeyError(proposal_id)
        if proposal.approval_status is not ProposalStatus.PENDING:
            raise ValueError("proposal is not pending")
        approved_at = _utc_now()
        if proposal.mutation_kind is MutationKind.CREATE:
            current = None
            record = self._record_from_create(proposal, created_at=approved_at)
        elif proposal.mutation_kind is MutationKind.UPDATE:
            current = self.store.get_skill(proposal.target_skill_id)
            if current is None:
                raise StaleSkillVersionError(proposal.target_skill_id)
            if current.version != proposal.base_version:
                raise StaleSkillVersionError(proposal.target_skill_id)
            record = self._record_from_update(proposal, current, created_at=approved_at)
        else:
            raise UnsupportedE1TransitionError(proposal.mutation_kind.value)

        if current is not None and risk_rank(record.risk_class) < risk_rank(current.risk_class):
            if not allow_risk_downgrade:
                raise RiskDowngradeApprovalRequired(
                    f"{current.risk_class.value}->{record.risk_class.value}"
                )

        approved = proposal.model_copy(
            update={
                "approval_status": ProposalStatus.APPROVED,
                "approved_by": approver,
                "approved_at": approved_at,
                "resulting_version": record.version,
            }
        )
        audit = SkillAuditEvent(
            audit_id=_audit_id(
                record.skill_id,
                "skill.proposal.approved",
                proposal.proposal_id,
                approver,
            ),
            skill_id=record.skill_id,
            event_type="skill.proposal.approved",
            actor=approver,
            occurred_at=approved_at,
            details={
                "proposal_id": proposal.proposal_id,
                "resulting_version": record.version,
            },
        )
        try:
            self.store.commit_approved_skill(
                approved,
                record,
                audit,
                expected_base_version=proposal.base_version,
            )
        except ValueError as exc:
            if "base version mismatch" in str(exc):
                raise StaleSkillVersionError(proposal.target_skill_id) from exc
            raise
        return record

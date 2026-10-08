from pathlib import Path

import pytest

from personal_predictive_ai.knowledge.models import (
    KnowledgeRecord,
    KnowledgeScope,
    KnowledgeSourceClass,
    KnowledgeStatus,
)
from personal_predictive_ai.skills.models import (
    PackageSourceType,
    PackageTrustState,
    RiskClass,
    SkillDraft,
    SkillKind,
    SkillPackageManifest,
    SkillScope,
    SkillStatus,
    VerificationMethod,
    VerificationSpec,
)
from personal_predictive_ai.skills.registry import (
    RiskDowngradeApprovalRequired,
    StaleSkillVersionError,
    TrustedRegistryService,
    UnsupportedE1TransitionError,
    UntrustedSkillPackageError,
)
from personal_predictive_ai.storage.knowledge_skill_store import KnowledgeSkillStore


def _verification() -> VerificationSpec:
    return VerificationSpec(
        verification_id="verify:tests",
        method=VerificationMethod.STATIC,
        expected_observation="tests pass",
        allowed_risk_class=RiskClass.ACT_LOCAL,
        independence_requirement="independent command result",
    )

def _draft(**overrides) -> SkillDraft:
    data = {
        "canonical_name": "run-project-tests",
        "name": "Run project tests",
        "kind": SkillKind.EXECUTOR,
        "purpose": "Run the project test suite",
        "procedure_steps": ["run pytest"],
        "verification_spec": _verification(),
        "scope": SkillScope(scope_type="project", scope_id="alpha"),
        "risk_class": RiskClass.ACT_LOCAL,
    }
    data.update(overrides)
    return SkillDraft(**data)


def _service(tmp_path: Path) -> tuple[TrustedRegistryService, KnowledgeSkillStore]:
    store = KnowledgeSkillStore(tmp_path / "events.db")
    return TrustedRegistryService(store), store


def _approved_manifest() -> SkillPackageManifest:
    return SkillPackageManifest(
        package_id="pkg:approved",
        source_type=PackageSourceType.PROJECT,
        source_uri="file:///approved",
        source_revision="abc123",
        content_hash="sha256:approved",
        imported_at="2026-10-08T00:00:00Z",
        importer="human",
        trust_state=PackageTrustState.APPROVED,
        approved_by="reviewer",
        approved_at="2026-10-08T00:01:00Z",
    )

def test_create_requires_approval_and_materializes_draft_only(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    proposal = service.stage_skill_create(_draft(), proposed_by="human")
    assert store.get_skill(proposal.target_skill_id) is None

    record = service.approve_proposal(proposal.proposal_id, approver="reviewer")
    assert record.status is SkillStatus.DRAFT
    assert record.version == 1
    assert store.get_skill(record.skill_id) == record

    with pytest.raises(UnsupportedE1TransitionError):
        service.stage_skill_update(
            record.skill_id,
            {"status": SkillStatus.VERIFIED.value},
            proposed_by="human",
        )
    store.close()


def test_rejected_proposal_never_creates_skill(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    proposal = service.stage_skill_create(_draft(), proposed_by="human")
    rejected = service.reject_proposal(proposal.proposal_id, approver="reviewer", reason="no")
    assert rejected.approval_status.value == "rejected"
    assert store.get_skill(proposal.target_skill_id) is None
    store.close()

def test_stale_update_fails_closed_without_new_version(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    created = service.approve_proposal(
        service.stage_skill_create(_draft(), proposed_by="human").proposal_id,
        approver="reviewer",
    )
    stale = service.stage_skill_update(
        created.skill_id,
        {"purpose": "stale purpose"},
        proposed_by="human-a",
    )
    fresh = service.stage_skill_update(
        created.skill_id,
        {"purpose": "fresh purpose"},
        proposed_by="human-b",
    )
    version2 = service.approve_proposal(fresh.proposal_id, approver="reviewer")
    assert version2.version == 2

    with pytest.raises(StaleSkillVersionError):
        service.approve_proposal(stale.proposal_id, approver="reviewer")
    assert [item.version for item in store.iter_skill_versions(created.skill_id)] == [1, 2]
    store.close()


def test_risk_downgrade_requires_explicit_override(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    created = service.approve_proposal(
        service.stage_skill_create(_draft(), proposed_by="human").proposal_id,
        approver="reviewer",
    )
    proposal = service.stage_skill_update(
        created.skill_id,
        {"risk_class": RiskClass.READ_ONLY.value},
        proposed_by="human",
    )
    with pytest.raises(RiskDowngradeApprovalRequired):
        service.approve_proposal(proposal.proposal_id, approver="reviewer")
    downgraded = service.approve_proposal(
        proposal.proposal_id,
        approver="reviewer",
        allow_risk_downgrade=True,
    )
    assert downgraded.risk_class is RiskClass.READ_ONLY
    store.close()

def test_package_must_be_approved_before_skill_staging(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    untrusted = _approved_manifest().model_copy(
        update={
            "package_id": "pkg:quarantined",
            "trust_state": PackageTrustState.QUARANTINED,
            "approved_by": None,
            "approved_at": None,
        }
    )
    store.put_package_manifest(untrusted)
    with pytest.raises(UntrustedSkillPackageError):
        service.stage_skill_create(
            _draft(source_package_id=untrusted.package_id),
            proposed_by="human",
        )

    approved = _approved_manifest()
    store.put_package_manifest(approved)
    proposal = service.stage_skill_create(
        _draft(source_package_id=approved.package_id),
        proposed_by="human",
    )
    record = service.approve_proposal(proposal.proposal_id, approver="reviewer")
    assert record.source_package_id == approved.package_id
    store.close()


def test_duplicate_create_for_same_skill_id_fails_after_first_approval(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    first = service.stage_skill_create(_draft(), proposed_by="human-a")
    second = service.stage_skill_create(_draft(), proposed_by="human-b")
    created = service.approve_proposal(first.proposal_id, approver="reviewer")
    assert created.version == 1
    with pytest.raises(StaleSkillVersionError):
        service.approve_proposal(second.proposal_id, approver="reviewer")
    assert [item.version for item in store.iter_skill_versions(created.skill_id)] == [1]
    store.close()


def test_human_knowledge_import_rejects_non_human_source(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    record = KnowledgeRecord(
        knowledge_id="kn:ai-proposed",
        kind="preference",
        key="editor.theme",
        value="dark",
        scope=KnowledgeScope(scope_type="global", scope_id="user"),
        source_class=KnowledgeSourceClass.AI_PROPOSED,
        created_at="2026-10-08T00:00:00+00:00",
        created_seq=1,
        valid_from=0,
        confidence=0.5,
        status=KnowledgeStatus.DRAFT,
    )

    with pytest.raises(ValueError, match="human-origin"):
        service.import_human_knowledge(record)
    assert store.get_knowledge(record.knowledge_id) is None
    store.close()

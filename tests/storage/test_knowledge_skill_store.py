import sqlite3
from pathlib import Path

import pytest

from personal_predictive_ai.events.models import CanonicalEvent, EventOrigin
from personal_predictive_ai.knowledge.models import (
    KnowledgeRecord,
    KnowledgeScope,
    KnowledgeSourceClass,
    KnowledgeStatus,
)
from personal_predictive_ai.skills.models import (
    MutationKind,
    PackageSourceType,
    PackageTrustState,
    ProposalStatus,
    RiskClass,
    SkillAuditEvent,
    SkillDraft,
    SkillKind,
    SkillMutationProposal,
    SkillPackageManifest,
    SkillProjectionManifest,
    SkillRecord,
    SkillScope,
    SkillStatus,
    VerificationMethod,
    VerificationSpec,
)
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.storage.derived_store import DerivedStore
from personal_predictive_ai.storage.knowledge_skill_store import KnowledgeSkillStore
from personal_predictive_ai.storage.sqlite_store import EventStore


def _verification() -> VerificationSpec:
    return VerificationSpec(
        verification_id="verify:1",
        method=VerificationMethod.STATIC,
        expected_observation="schema valid",
        evidence_requirements=["schema"],
        allowed_risk_class=RiskClass.READ_ONLY,
        failure_conditions=["invalid"],
        independence_requirement="none",
    )


def _draft() -> SkillDraft:
    return SkillDraft(
        canonical_name="run_tests",
        name="Run tests",
        kind=SkillKind.EXECUTOR,
        purpose="Validate project",
        initiation_conditions=["project_open"],
        preconditions=["tests_available"],
        procedure_steps=["run pytest"],
        required_capabilities=["shell.read_only"],
        termination_conditions=["pytest exits"],
        success_conditions=["exit code 0"],
        verification_spec=_verification(),
        scope=SkillScope(scope_type="project", scope_id="alpha"),
        risk_class=RiskClass.READ_ONLY,
        confidence=1.0,
    )


def _skill(version: int = 1) -> SkillRecord:
    draft = _draft()
    return SkillRecord(
        **draft.model_dump(exclude={"schema_version"}),
        skill_id="skill:alpha",
        version=version,
        status=SkillStatus.DRAFT,
        valid_from=1,
        created_by="human",
        created_at="2026-10-08T09:00:00+08:00",
    )


def _knowledge() -> KnowledgeRecord:
    return KnowledgeRecord(
        knowledge_id="kn:alpha",
        kind="preference",
        key="editor.theme",
        value="dark",
        scope=KnowledgeScope(scope_type="global", scope_id="user"),
        source_class=KnowledgeSourceClass.HUMAN_DECLARED,
        provenance={"author": "human"},
        created_at="2026-10-08T09:00:00+08:00",
        created_seq=1,
        valid_from=1,
        confidence=1.0,
        status=KnowledgeStatus.ACTIVE,
    )


def _proposal(status: ProposalStatus = ProposalStatus.PENDING) -> SkillMutationProposal:
    return SkillMutationProposal(
        proposal_id="proposal:alpha",
        target_skill_id="skill:alpha",
        base_version=None,
        mutation_kind=MutationKind.CREATE,
        proposed_patch={"name": "Run tests"},
        rationale="human-authored",
        proposed_by="human",
        created_at="2026-10-08T09:00:00+08:00",
        approval_status=status,
    )


def _package() -> SkillPackageManifest:
    return SkillPackageManifest(
        package_id="pkg:alpha",
        source_type=PackageSourceType.GITHUB,
        source_uri="https://example.invalid/repo",
        source_revision="abc123",
        content_hash="deadbeef",
        imported_at="2026-10-08T09:00:00+08:00",
        importer="human",
        trust_state=PackageTrustState.QUARANTINED,
    )


def _audit() -> SkillAuditEvent:
    return SkillAuditEvent(
        audit_id="audit:alpha",
        skill_id="skill:alpha",
        event_type="skill.approved",
        actor="human",
        occurred_at="2026-10-08T09:00:00+08:00",
        details={"version": 1},
    )


def _projection() -> SkillProjectionManifest:
    return SkillProjectionManifest(
        projection_id="projection:alpha",
        skill_id="skill:alpha",
        version=1,
        output_path="skills/run_tests.md",
        content_hash="cafebabe",
        created_at="2026-10-08T09:00:00+08:00",
    )


def test_store_round_trip_restart_and_immutable_skill_versions(tmp_path: Path) -> None:
    db = tmp_path / "events.db"
    store = KnowledgeSkillStore(db)
    store.put_knowledge(_knowledge())
    store.stage_proposal(_proposal())
    store.append_skill_version(_skill())
    store.put_package_manifest(_package())
    store.append_audit_event(_audit())
    store.put_projection_manifest(_projection())
    assert store.get_knowledge("kn:alpha") == _knowledge()
    assert list(store.iter_knowledge()) == [_knowledge()]
    assert store.get_proposal("proposal:alpha") == _proposal()
    assert store.get_skill("skill:alpha") == _skill()
    assert list(store.iter_skill_versions("skill:alpha")) == [_skill()]
    assert store.get_package_manifest("pkg:alpha") == _package()
    assert list(store.iter_audit_events("skill:alpha")) == [_audit()]
    assert store.get_projection_manifest("projection:alpha") == _projection()
    assert store.integrity_check() == "ok"

    with pytest.raises(sqlite3.IntegrityError):
        store.append_skill_version(_skill())
    store.close()

    reopened = KnowledgeSkillStore(db)
    assert reopened.get_skill("skill:alpha", 1) == _skill()
    assert reopened.get_proposal("proposal:alpha") == _proposal()
    reopened.close()


def test_commit_approved_skill_is_atomic_and_checks_expected_base(tmp_path: Path) -> None:
    db = tmp_path / "events.db"
    store = KnowledgeSkillStore(db)
    pending = _proposal()
    store.stage_proposal(pending)
    approved = pending.model_copy(
        update={
            "approval_status": ProposalStatus.APPROVED,
            "approved_by": "reviewer",
            "approved_at": "2026-10-08T09:05:00+08:00",
            "resulting_version": 1,
        }
    )

    with pytest.raises(ValueError, match="base version"):
        store.commit_approved_skill(approved, _skill(), _audit(), expected_base_version=1)
    assert store.get_skill("skill:alpha") is None
    assert store.get_proposal("proposal:alpha") == pending
    assert list(store.iter_audit_events()) == []

    store.commit_approved_skill(approved, _skill(), _audit(), expected_base_version=None)
    assert store.get_skill("skill:alpha") == _skill()
    assert store.get_proposal("proposal:alpha") == approved
    assert list(store.iter_audit_events()) == [_audit()]
    store.close()


def test_e_store_never_modifies_canonical_or_b1_rows(tmp_path: Path) -> None:
    db = tmp_path / "events.db"
    canonical = EventStore(db)
    canonical.append(
        CanonicalEvent(
            event_id="evt-1",
            timestamp_ns=10,
            monotonic_seq=1,
            source="unit",
            modality="window",
            origin=EventOrigin.EXOGENOUS,
            event_type="window.foreground.changed",
        )
    )
    canonical.close()

    b1 = DerivedStore(db)
    b1.replace_run(
        "run-b1",
        1,
        [
            StateSnapshot(
                state_id="state-1",
                source_event_id="evt-1",
                timestamp_ns=10,
                monotonic_seq=1,
            )
        ],
        [],
        [],
        [],
    )
    b1.close()

    conn = sqlite3.connect(db)
    before_event = conn.execute(
        "SELECT data_json FROM canonical_events WHERE event_id='evt-1'"
    ).fetchone()[0]
    before_state = conn.execute(
        "SELECT data_json FROM b1_state_snapshots WHERE state_id='state-1'"
    ).fetchone()[0]
    conn.close()

    store = KnowledgeSkillStore(db)
    store.put_knowledge(_knowledge())
    store.stage_proposal(_proposal())
    store.close()

    conn = sqlite3.connect(db)
    after_event = conn.execute(
        "SELECT data_json FROM canonical_events WHERE event_id='evt-1'"
    ).fetchone()[0]
    after_state = conn.execute(
        "SELECT data_json FROM b1_state_snapshots WHERE state_id='state-1'"
    ).fetchone()[0]
    conn.close()

    assert after_event == before_event
    assert after_state == before_state

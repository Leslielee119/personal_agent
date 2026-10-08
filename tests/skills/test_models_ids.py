import pytest
from pydantic import ValidationError

from personal_predictive_ai.skills.ids import package_id_for, proposal_id_for, skill_id_for
from personal_predictive_ai.skills.models import (
    MutationKind,
    PackageTrustState,
    ProposalStatus,
    RiskClass,
    SkillDraft,
    SkillKind,
    SkillScope,
    SkillStatus,
    VerificationMethod,
    VerificationSpec,
)
from personal_predictive_ai.skills.safety import risk_rank, validate_safe_structured_text


def _verification() -> VerificationSpec:
    return VerificationSpec(
        verification_id="verify:1",
        method=VerificationMethod.STATIC,
        expected_observation="schema valid",
        evidence_requirements=["schema"],
        allowed_risk_class=RiskClass.READ_ONLY,
        failure_conditions=["schema invalid"],
        independence_requirement="none",
    )


def _draft(**overrides) -> SkillDraft:
    data = {
        "canonical_name": "run_project_tests",
        "name": "Run project tests",
        "kind": SkillKind.EXECUTOR,
        "purpose": "Validate the current project",
        "initiation_conditions": ["project_open"],
        "preconditions": ["tests_available"],
        "parameters": {},
        "procedure_steps": ["run pytest"],
        "required_capabilities": ["shell.read_only"],
        "termination_conditions": ["pytest exits"],
        "success_conditions": ["exit code 0"],
        "verification_spec": _verification(),
        "scope": SkillScope(scope_type="project", scope_id="alpha"),
        "risk_class": RiskClass.READ_ONLY,
        "evidence_refs": [],
        "contradiction_refs": [],
        "provenance_summary": {"source": "human"},
        "support_sessions": [],
        "confidence": 1.0,
        "source_package_id": None,
    }
    data.update(overrides)
    return SkillDraft(**data)


def test_skill_enums_and_risk_order_are_exact() -> None:
    assert [item.value for item in SkillKind] == ["planner", "executor"]
    assert [item.value for item in RiskClass] == [
        "read_only",
        "write_local",
        "act_local",
        "external_effect",
        "unknown",
    ]
    assert SkillStatus.DRAFT.value == "draft"
    assert MutationKind.CREATE.value == "create"
    assert ProposalStatus.PENDING.value == "pending"
    assert PackageTrustState.QUARANTINED.value == "quarantined"
    assert risk_rank(RiskClass.READ_ONLY) < risk_rank(RiskClass.ACT_LOCAL)
    assert risk_rank(RiskClass.UNKNOWN) > risk_rank(RiskClass.EXTERNAL_EFFECT)


def test_skill_ids_are_semantic_and_deterministic() -> None:
    draft = _draft()
    first = skill_id_for(draft.kind, draft.canonical_name, draft.scope)
    second = skill_id_for(draft.kind, draft.canonical_name, draft.scope)
    assert first == second
    assert first.startswith("skill:")
    assert first != skill_id_for(draft.kind, "other", draft.scope)

    proposal_a = proposal_id_for(first, 1, MutationKind.UPDATE, {"purpose": "new"}, "human")
    proposal_b = proposal_id_for(first, 1, MutationKind.UPDATE, {"purpose": "new"}, "human")
    assert proposal_a == proposal_b
    assert proposal_a.startswith("proposal:")

    package_a = package_id_for("github", "https://example.invalid/repo", "abc123", "deadbeef")
    package_b = package_id_for("github", "https://example.invalid/repo", "abc123", "deadbeef")
    assert package_a == package_b
    assert package_a.startswith("pkg:")


def test_skill_draft_is_frozen_strict_and_json_safe() -> None:
    draft = _draft()
    assert draft.schema_version == "ppa.skill-draft/v1"
    with pytest.raises(ValidationError):
        SkillDraft(**{**draft.model_dump(), "unexpected": True})
    with pytest.raises(ValidationError):
        _draft(parameters={"bad": {1, 2}})
    with pytest.raises(ValidationError):
        _draft(confidence=1.1)


def test_structured_text_rejects_secret_sentinels() -> None:
    validate_safe_structured_text({"note": "ordinary text"})
    with pytest.raises(ValueError, match="sensitive"):
        validate_safe_structured_text({"note": "api_key=SUPER_SECRET_VALUE"})

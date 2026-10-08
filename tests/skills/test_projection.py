import sqlite3
from pathlib import Path

import pytest

from personal_predictive_ai.skills.models import (
    RiskClass,
    SkillDraft,
    SkillKind,
    SkillScope,
    VerificationMethod,
    VerificationSpec,
)
from personal_predictive_ai.skills.projection import (
    ProjectionValidationError,
    parse_skill_markdown,
    projection_manifest_for,
    proposal_from_projection_edit,
    render_skill_markdown,
)
from personal_predictive_ai.skills.registry import TrustedRegistryService
from personal_predictive_ai.storage.knowledge_skill_store import KnowledgeSkillStore


def _verification() -> VerificationSpec:
    return VerificationSpec(
        verification_id="verify:projection",
        method=VerificationMethod.STATIC,
        expected_observation="tests pass",
        evidence_requirements=["pytest output"],
        allowed_risk_class=RiskClass.READ_ONLY,
        failure_conditions=["pytest fails"],
        independence_requirement="independent command result",
    )

def _draft() -> SkillDraft:
    return SkillDraft(
        canonical_name="run-tests",
        name="Run tests",
        kind=SkillKind.EXECUTOR,
        purpose="Run project tests",
        initiation_conditions=["project open"],
        preconditions=["pytest configured"],
        parameters={"target": "tests"},
        procedure_steps=["pytest -q"],
        required_capabilities=["process.read"],
        termination_conditions=["pytest exits"],
        success_conditions=["exit code 0"],
        verification_spec=_verification(),
        scope=SkillScope(scope_type="project", scope_id="alpha"),
        risk_class=RiskClass.READ_ONLY,
        evidence_refs=["evt-1"],
        contradiction_refs=["evt-2"],
        provenance_summary={"human": 2},
        support_sessions=["s1", "s2"],
        confidence=0.8,
    )


def _record(tmp_path: Path):
    store = KnowledgeSkillStore(tmp_path / "events.db")
    service = TrustedRegistryService(store)
    record = service.approve_proposal(
        service.stage_skill_create(_draft(), proposed_by="human").proposal_id,
        approver="reviewer",
    )
    return store, service, record


def _editable_dump(record) -> dict:
    return SkillDraft(
        **record.model_dump(
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
            }
        )
    ).model_dump(mode="json")

def test_unedited_projection_round_trip_is_semantically_equivalent(tmp_path: Path) -> None:
    store, _, record = _record(tmp_path)
    markdown = render_skill_markdown(record)
    parsed = parse_skill_markdown(markdown)
    assert parsed.model_dump(mode="json") == _editable_dump(record)

    manifest = projection_manifest_for(
        record,
        output_path=tmp_path / "skill.md",
        content=markdown,
    )
    manifest2 = projection_manifest_for(
        record,
        output_path=tmp_path / "skill.md",
        content=markdown,
    )
    assert manifest.projection_id == manifest2.projection_id
    assert manifest.content_hash == manifest2.content_hash
    store.close()


def test_projection_edit_stages_proposal_but_identical_projection_does_not(tmp_path: Path) -> None:
    store, service, record = _record(tmp_path)
    markdown = render_skill_markdown(record)
    assert proposal_from_projection_edit(
        service,
        record,
        markdown,
        proposed_by="human",
    ) is None

    edited = markdown.replace("Run project tests", "Run focused project tests", 1)
    proposal = proposal_from_projection_edit(
        service,
        record,
        edited,
        proposed_by="human",
    )
    assert proposal is not None
    assert proposal.base_version == record.version
    assert store.get_proposal(proposal.proposal_id) == proposal
    store.close()

def _proposal_count(db: Path) -> int:
    conn = sqlite3.connect(db)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM skill_mutation_proposals").fetchone()[0])
    finally:
        conn.close()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda text: text.replace(
            "schema_version: ppa.skill-projection-md/v1",
            "schema_version: bad/v9",
            1,
        ),
        lambda text: text.replace("status: draft", "status: active", 1),
        lambda text: text.replace("version: 1", "version: 99", 1),
        lambda text: text.replace("skill_id:", "evil: 1\nskill_id:", 1),
        lambda text: "---\n[broken yaml\n---\n" + text.split("---\n", 2)[-1],
        lambda text: text.replace("Run project tests", "api_key = secret-value", 1),
    ],
)
def test_projection_corruption_fails_closed_without_store_mutation(
    tmp_path: Path,
    mutation,
) -> None:
    store, service, record = _record(tmp_path)
    db = tmp_path / "events.db"
    before = _proposal_count(db)
    markdown = mutation(render_skill_markdown(record))
    with pytest.raises(ProjectionValidationError):
        proposal_from_projection_edit(
            service,
            record,
            markdown,
            proposed_by="human",
        )
    assert _proposal_count(db) == before
    store.close()

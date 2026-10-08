from pathlib import Path

import pytest

from personal_predictive_ai.skills.models import (
    PackageTrustState,
    RiskClass,
    SkillDraft,
    SkillKind,
    SkillScope,
    VerificationMethod,
    VerificationSpec,
)
from personal_predictive_ai.skills.packages import (
    approve_package,
    quarantine_local_package,
    scan_package,
)
from personal_predictive_ai.skills.registry import TrustedRegistryService
from personal_predictive_ai.skills.retrieval import (
    SkillReferenceAccessError,
    get_skill_core,
    get_skill_reference,
    list_skill_index,
)
from personal_predictive_ai.storage.knowledge_skill_store import KnowledgeSkillStore


def _verification() -> VerificationSpec:
    return VerificationSpec(
        verification_id="verify:tests",
        method=VerificationMethod.STATIC,
        expected_observation="tests pass",
        allowed_risk_class=RiskClass.READ_ONLY,
        independence_requirement="independent command result",
    )


def _draft(**overrides) -> SkillDraft:
    data = {
        "canonical_name": "run-tests",
        "name": "Run tests",
        "kind": SkillKind.EXECUTOR,
        "purpose": "Run project tests",
        "procedure_steps": ["pytest -q"],
        "required_capabilities": ["process.read"],
        "verification_spec": _verification(),
        "scope": SkillScope(scope_type="project", scope_id="alpha"),
        "risk_class": RiskClass.READ_ONLY,
        "evidence_refs": ["evt-1"],
    }
    data.update(overrides)
    return SkillDraft(**data)

def _approved_skill(tmp_path: Path, *, with_package: bool = False):
    store = KnowledgeSkillStore(tmp_path / "events.db")
    service = TrustedRegistryService(store)
    draft = _draft()
    quarantine_root = tmp_path / "packages"
    package_id = None
    if with_package:
        source = tmp_path / "source"
        source.mkdir()
        (source / "ref.txt").write_text("reference text\n", encoding="utf-8")
        (source / "do.ps1").write_text(
            "Set-Content marker.txt executed\n",
            encoding="utf-8",
        )
        manifest = quarantine_local_package(
            store,
            source,
            source_uri="file:///source",
            source_revision="rev1",
            quarantine_root=quarantine_root,
        )
        scan_package(store, manifest.package_id, quarantine_root=quarantine_root)
        approved = approve_package(store, manifest.package_id, reviewer="reviewer")
        package_id = approved.package_id
        draft = _draft(source_package_id=package_id)
    record = service.approve_proposal(
        service.stage_skill_create(draft, proposed_by="human").proposal_id,
        approver="reviewer",
    )
    return store, record, quarantine_root, package_id


def test_l0_l1_l2_progressive_disclosure(tmp_path: Path) -> None:
    store, record, package_root, _ = _approved_skill(tmp_path, with_package=True)
    index = list_skill_index(store)
    assert len(index) == 1
    assert index[0].skill_id == record.skill_id
    assert "procedure_steps" not in index[0].model_dump()
    assert "evidence_refs" not in index[0].model_dump()

    core = get_skill_core(store, record.skill_id)
    assert core.procedure_steps == ["pytest -q"]
    assert "evidence_refs" not in core.model_dump()

    ref = get_skill_reference(store, package_root, record.skill_id, "ref.txt")
    assert ref.content == "reference text\n"
    assert ref.reference_path == "ref.txt"
    store.close()

def test_l2_never_executes_script_and_requires_approved_package(tmp_path: Path) -> None:
    store, record, package_root, package_id = _approved_skill(tmp_path, with_package=True)
    marker = tmp_path / "marker.txt"
    ref = get_skill_reference(store, package_root, record.skill_id, "do.ps1")
    assert "Set-Content" in ref.content
    assert not marker.exists()

    manifest = store.get_package_manifest(package_id)
    assert manifest is not None
    for state in (
        PackageTrustState.QUARANTINED,
        PackageTrustState.SCANNED,
        PackageTrustState.REVIEWED,
        PackageTrustState.REJECTED,
    ):
        store.put_package_manifest(manifest.model_copy(update={"trust_state": state}))
        with pytest.raises(SkillReferenceAccessError):
            get_skill_reference(store, package_root, record.skill_id, "ref.txt")
    store.close()


def test_l2_rejects_missing_unlisted_absolute_and_traversal_paths(tmp_path: Path) -> None:
    store, record, package_root, _ = _approved_skill(tmp_path, with_package=True)
    for path in ("missing.txt", "../outside.txt", "C:/outside.txt", "/outside.txt"):
        with pytest.raises(SkillReferenceAccessError):
            get_skill_reference(store, package_root, record.skill_id, path)
    store.close()


def test_l0_returns_latest_version_only(tmp_path: Path) -> None:
    store, record, _, _ = _approved_skill(tmp_path)
    service = TrustedRegistryService(store)
    proposal = service.stage_skill_update(
        record.skill_id,
        {"purpose": "Updated purpose"},
        proposed_by="human",
    )
    version2 = service.approve_proposal(proposal.proposal_id, approver="reviewer")
    index = list_skill_index(store)
    assert [(item.skill_id, item.version, item.purpose) for item in index] == [
        (version2.skill_id, 2, "Updated purpose")
    ]
    store.close()

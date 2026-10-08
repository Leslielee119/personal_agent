import json
from pathlib import Path

from personal_predictive_ai.cli import main
from personal_predictive_ai.knowledge.models import (
    KnowledgeRecord,
    KnowledgeScope,
    KnowledgeSourceClass,
    KnowledgeStatus,
)
from personal_predictive_ai.skills.models import (
    RiskClass,
    SkillDraft,
    SkillKind,
    SkillScope,
    VerificationMethod,
    VerificationSpec,
)
from personal_predictive_ai.skills.packages import package_directory
from personal_predictive_ai.storage.knowledge_skill_store import KnowledgeSkillStore


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _verification() -> VerificationSpec:
    return VerificationSpec(
        verification_id="verify:cli",
        method=VerificationMethod.STATIC,
        expected_observation="tests pass",
        allowed_risk_class=RiskClass.READ_ONLY,
        independence_requirement="independent command result",
    )


def _knowledge() -> KnowledgeRecord:
    return KnowledgeRecord(
        knowledge_id="kn:cli",
        kind="preference",
        key="editor.theme",
        value="dark",
        scope=KnowledgeScope(scope_type="global", scope_id="user"),
        source_class=KnowledgeSourceClass.HUMAN_DECLARED,
        created_at="2026-10-08T00:00:00+00:00",
        created_seq=1,
        valid_from=0,
        confidence=1.0,
        status=KnowledgeStatus.ACTIVE,
    )


def _draft() -> SkillDraft:
    return SkillDraft(
        canonical_name="run-tests",
        name="Run tests",
        kind=SkillKind.EXECUTOR,
        purpose="Run project tests",
        procedure_steps=["pytest -q"],
        required_capabilities=["process.read"],
        verification_spec=_verification(),
        scope=SkillScope(scope_type="project", scope_id="alpha"),
        risk_class=RiskClass.READ_ONLY,
    )


def _run_json(capsys, argv: list[str]) -> tuple[int, object]:
    code = main(argv)
    output = capsys.readouterr().out.strip()
    return code, json.loads(output) if output else None


def test_cli_human_knowledge_skill_approval_and_read_only_views(tmp_path: Path, capsys) -> None:
    data_dir = tmp_path / "data"
    knowledge_file = tmp_path / "knowledge.json"
    draft_file = tmp_path / "skill.json"
    _write_json(knowledge_file, _knowledge().model_dump(mode="json"))
    _write_json(draft_file, _draft().model_dump(mode="json"))

    code, payload = _run_json(
        capsys,
        ["--data-dir", str(data_dir), "knowledge-import", "--file", str(knowledge_file)],
    )
    assert code == 0
    assert payload["knowledge_id"] == "kn:cli"

    code, proposal = _run_json(
        capsys,
        [
            "--data-dir", str(data_dir), "skill-stage", "--file", str(draft_file),
            "--proposed-by", "human",
        ],
    )
    assert code == 0

    code, items = _run_json(capsys, ["--data-dir", str(data_dir), "skill-list"])
    assert code == 0
    assert items == []

    code, record = _run_json(
        capsys,
        [
            "--data-dir", str(data_dir), "skill-approve",
            "--proposal-id", proposal["proposal_id"], "--approver", "reviewer",
        ],
    )
    assert code == 0
    assert record["status"] == "draft"
    assert record["version"] == 1

    code, items = _run_json(capsys, ["--data-dir", str(data_dir), "skill-list"])
    assert code == 0
    assert [item["skill_id"] for item in items] == [record["skill_id"]]
    assert "procedure_steps" not in items[0]

    code, core = _run_json(
        capsys,
        [
            "--data-dir", str(data_dir), "skill-show", "--skill-id", record["skill_id"],
            "--level", "core",
        ],
    )
    assert code == 0
    assert core["procedure_steps"] == ["pytest -q"]

    store = KnowledgeSkillStore(data_dir / "events.db")
    assert [item.version for item in store.iter_skill_versions(record["skill_id"])] == [1]
    assert store.get_knowledge("kn:cli") is not None
    store.close()


def test_cli_package_flow_preserves_provenance_and_blocks_unapproved_use(
    tmp_path: Path,
    capsys,
) -> None:
    data_dir = tmp_path / "data"
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    (package_dir / "SKILL.md").write_text("# Safe skill\n", encoding="utf-8")
    draft_file = tmp_path / "skill.json"
    _write_json(draft_file, _draft().model_dump(mode="json"))

    code, manifest = _run_json(
        capsys,
        [
            "--data-dir", str(data_dir), "skill-package-import", "--path", str(package_dir),
            "--source-uri", "local://safe", "--source-revision", "rev1",
        ],
    )
    assert code == 0
    assert manifest["trust_state"] == "quarantined"

    code, error = _run_json(
        capsys,
        [
            "--data-dir", str(data_dir), "skill-stage", "--file", str(draft_file),
            "--proposed-by", "human", "--package-id", manifest["package_id"],
        ],
    )
    assert code != 0
    assert error["error"] == "untrusted_skill_package"

    code, scanned = _run_json(
        capsys,
        [
            "--data-dir", str(data_dir), "skill-package-scan",
            "--package-id", manifest["package_id"],
        ],
    )
    assert code == 0
    assert scanned["trust_state"] == "scanned"

    code, approved_package = _run_json(
        capsys,
        [
            "--data-dir", str(data_dir), "skill-package-approve",
            "--package-id", manifest["package_id"], "--reviewer", "reviewer",
        ],
    )
    assert code == 0
    assert approved_package["trust_state"] == "approved"

    code, proposal = _run_json(
        capsys,
        [
            "--data-dir", str(data_dir), "skill-stage", "--file", str(draft_file),
            "--proposed-by", "human", "--package-id", manifest["package_id"],
        ],
    )
    assert code == 0

    code, record = _run_json(
        capsys,
        [
            "--data-dir", str(data_dir), "skill-approve",
            "--proposal-id", proposal["proposal_id"], "--approver", "reviewer",
        ],
    )
    assert code == 0
    assert record["source_package_id"] == manifest["package_id"]


def test_cli_export_is_deterministic_and_projection_only(tmp_path: Path, capsys) -> None:
    data_dir = tmp_path / "data"
    draft_file = tmp_path / "skill.json"
    output = tmp_path / "skill.md"
    _write_json(draft_file, _draft().model_dump(mode="json"))

    _, proposal = _run_json(
        capsys,
        [
            "--data-dir", str(data_dir), "skill-stage", "--file", str(draft_file),
            "--proposed-by", "human",
        ],
    )
    _, record = _run_json(
        capsys,
        [
            "--data-dir", str(data_dir), "skill-approve",
            "--proposal-id", proposal["proposal_id"], "--approver", "reviewer",
        ],
    )

    store = KnowledgeSkillStore(data_dir / "events.db")
    before = store.get_skill(record["skill_id"])
    store.close()

    code, manifest = _run_json(
        capsys,
        [
            "--data-dir", str(data_dir), "skill-export", "--skill-id", record["skill_id"],
            "--output", str(output),
        ],
    )
    assert code == 0
    first_text = output.read_text(encoding="utf-8")
    assert manifest["content_hash"]

    code, manifest2 = _run_json(
        capsys,
        [
            "--data-dir", str(data_dir), "skill-export", "--skill-id", record["skill_id"],
            "--output", str(output),
        ],
    )
    assert code == 0
    assert output.read_text(encoding="utf-8") == first_text
    assert manifest2["projection_id"] == manifest["projection_id"]

    store = KnowledgeSkillStore(data_dir / "events.db")
    after = store.get_skill(record["skill_id"])
    stored_manifest = store.get_projection_manifest(manifest["projection_id"])
    assert after == before
    assert stored_manifest is not None
    assert stored_manifest.content_hash == manifest["content_hash"]
    store.close()



def test_cli_scan_reports_tampered_quarantine_as_structured_error(tmp_path: Path, capsys) -> None:
    data_dir = tmp_path / "data"
    package_dir = tmp_path / "package-tamper"
    package_dir.mkdir()
    (package_dir / "SKILL.md").write_text("# Safe skill\n", encoding="utf-8")

    code, manifest = _run_json(
        capsys,
        [
            "--data-dir", str(data_dir), "skill-package-import", "--path", str(package_dir),
            "--source-uri", "local://tamper", "--source-revision", "rev1",
        ],
    )
    assert code == 0

    quarantine_root = data_dir / "skill-packages" / "quarantine"
    quarantined = package_directory(quarantine_root, manifest["package_id"]) / "SKILL.md"
    quarantined.write_text("# Modified after quarantine\n", encoding="utf-8")

    code, error = _run_json(
        capsys,
        ["--data-dir", str(data_dir), "skill-package-scan", "--package-id", manifest["package_id"]],
    )
    assert code == 2
    assert error["error"] == "package_tampered"

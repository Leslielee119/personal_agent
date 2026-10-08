from pathlib import Path

import pytest

from personal_predictive_ai.skills.models import PackageTrustState
from personal_predictive_ai.skills.packages import (
    PackageScanBlockedError,
    PackageTamperedError,
    UnsafePackagePathError,
    approve_package,
    package_directory,
    quarantine_local_package,
    scan_package,
    validate_package_reference_path,
)
from personal_predictive_ai.storage.knowledge_skill_store import KnowledgeSkillStore


def _store(tmp_path: Path, name: str = "events.db") -> KnowledgeSkillStore:
    return KnowledgeSkillStore(tmp_path / name)


def test_quarantine_hash_and_provenance_are_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("# Safe skill\n", encoding="utf-8")
    (source / "notes.txt").write_text("notes\n", encoding="utf-8")

    first_store = _store(tmp_path, "first.db")
    second_store = _store(tmp_path, "second.db")
    first = quarantine_local_package(
        first_store,
        source,
        source_uri="file:///source",
        source_revision="rev1",
        quarantine_root=tmp_path / "q1",
    )
    second = quarantine_local_package(
        second_store,
        source,
        source_uri="file:///source",
        source_revision="rev1",
        quarantine_root=tmp_path / "q2",
    )
    assert first.package_id == second.package_id
    assert first.content_hash == second.content_hash
    assert first.source_revision == "rev1"
    assert first.trust_state is PackageTrustState.QUARANTINED
    assert sorted(first.referenced_files) == ["SKILL.md", "notes.txt"]
    first_store.close()
    second_store.close()


def test_scan_and_approve_safe_package(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("# Safe skill\nRun tests.\n", encoding="utf-8")
    store = _store(tmp_path)
    manifest = quarantine_local_package(
        store,
        source,
        source_uri="file:///source",
        source_revision="rev1",
        quarantine_root=tmp_path / "q",
    )
    scanned = scan_package(store, manifest.package_id, quarantine_root=tmp_path / "q")
    assert scanned.trust_state is PackageTrustState.SCANNED
    assert scanned.scanner_version == "ppa.skill-package-scan/v1"
    assert scanned.scanner_findings == []
    approved = approve_package(
        store,
        manifest.package_id,
        reviewer="reviewer",
        quarantine_root=tmp_path / "q",
    )
    assert approved.trust_state is PackageTrustState.APPROVED
    assert approved.approved_by == "reviewer"
    store.close()

def test_blocking_findings_prevent_approval(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "api_key = secret-value\nHidden\u200btext\n",
        encoding="utf-8",
    )
    store = _store(tmp_path)
    manifest = quarantine_local_package(
        store,
        source,
        source_uri="file:///source",
        source_revision="rev1",
        quarantine_root=tmp_path / "q",
    )
    scanned = scan_package(store, manifest.package_id, quarantine_root=tmp_path / "q")
    codes = {item["code"] for item in scanned.scanner_findings}
    assert "sensitive_text" in codes
    assert "invisible_unicode" in codes
    with pytest.raises(PackageScanBlockedError):
        approve_package(
            store,
            manifest.package_id,
            reviewer="reviewer",
            quarantine_root=tmp_path / "q",
        )
    store.close()


def test_reference_path_validation_rejects_absolute_and_traversal() -> None:
    assert validate_package_reference_path("docs/readme.md") == Path("docs/readme.md")
    with pytest.raises(UnsafePackagePathError):
        validate_package_reference_path("../outside.txt")
    with pytest.raises(UnsafePackagePathError):
        validate_package_reference_path("C:/outside.txt")
    with pytest.raises(UnsafePackagePathError):
        validate_package_reference_path("/outside.txt")

def test_quarantine_rejects_symlink_or_junction_escape(tmp_path: Path) -> None:
    source = tmp_path / "source"
    outside = tmp_path / "outside.txt"
    source.mkdir()
    outside.write_text("outside", encoding="utf-8")
    link = source / "escape.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable on this Windows host")

    store = _store(tmp_path)
    with pytest.raises(UnsafePackagePathError):
        quarantine_local_package(
            store,
            source,
            source_uri="file:///source",
            source_revision="rev1",
            quarantine_root=tmp_path / "q",
        )
    store.close()


def test_scan_rejects_package_modified_after_quarantine(tmp_path: Path) -> None:
    source = tmp_path / "source-tamper"
    source.mkdir()
    (source / "SKILL.md").write_text("# Safe skill\n", encoding="utf-8")
    store = _store(tmp_path, "tamper.db")
    quarantine_root = tmp_path / "qt"
    manifest = quarantine_local_package(
        store,
        source,
        source_uri="file:///source-tamper",
        source_revision="rev1",
        quarantine_root=quarantine_root,
    )
    copied = package_directory(quarantine_root, manifest.package_id) / "SKILL.md"
    copied.write_text("# Modified after quarantine\n", encoding="utf-8")

    with pytest.raises(PackageTamperedError):
        scan_package(store, manifest.package_id, quarantine_root=quarantine_root)
    assert store.get_package_manifest(manifest.package_id) == manifest
    store.close()


def test_approval_rechecks_content_after_scan(tmp_path: Path) -> None:
    source = tmp_path / "source-approval-tamper"
    source.mkdir()
    (source / "SKILL.md").write_text("# Safe skill\n", encoding="utf-8")
    store = _store(tmp_path, "approval-tamper.db")
    quarantine_root = tmp_path / "qa"
    manifest = quarantine_local_package(
        store,
        source,
        source_uri="file:///source-approval-tamper",
        source_revision="rev1",
        quarantine_root=quarantine_root,
    )
    scanned = scan_package(store, manifest.package_id, quarantine_root=quarantine_root)
    copied = package_directory(quarantine_root, manifest.package_id) / "SKILL.md"
    copied.write_text("# Modified after scan\n", encoding="utf-8")

    with pytest.raises(PackageTamperedError):
        approve_package(
            store,
            manifest.package_id,
            reviewer="reviewer",
            quarantine_root=quarantine_root,
        )
    assert store.get_package_manifest(manifest.package_id) == scanned
    store.close()


def test_scan_rejects_unlisted_file_added_after_quarantine(tmp_path: Path) -> None:
    source = tmp_path / "source-extra-file"
    source.mkdir()
    (source / "SKILL.md").write_text("# Safe skill\n", encoding="utf-8")
    store = _store(tmp_path, "extra-file.db")
    quarantine_root = tmp_path / "qe"
    manifest = quarantine_local_package(
        store,
        source,
        source_uri="file:///source-extra-file",
        source_revision="rev1",
        quarantine_root=quarantine_root,
    )
    package_dir = package_directory(quarantine_root, manifest.package_id)
    (package_dir / "injected.txt").write_text("unexpected\n", encoding="utf-8")

    with pytest.raises(PackageTamperedError):
        scan_package(store, manifest.package_id, quarantine_root=quarantine_root)
    store.close()

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from personal_predictive_ai.skills.ids import package_id_for
from personal_predictive_ai.skills.models import (
    PackageSourceType,
    PackageTrustState,
    SkillPackageManifest,
)
from personal_predictive_ai.skills.safety import validate_safe_structured_text
from personal_predictive_ai.storage.knowledge_skill_store import KnowledgeSkillStore


class UnsafePackagePathError(ValueError):
    pass


class PackageScanBlockedError(RuntimeError):
    pass


class PackageTamperedError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def package_directory(quarantine_root: Path, package_id: str) -> Path:
    return quarantine_root / package_id.replace(":", "_")

def validate_package_reference_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or path.drive or path.root or ".." in path.parts:
        raise UnsafePackagePathError(value)
    if not value or value in {".", ".."}:
        raise UnsafePackagePathError(value)
    return path


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_hash(entries: list[tuple[str, str]]) -> str:
    payload = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"

def quarantine_local_package(
    store: KnowledgeSkillStore,
    root: Path,
    *,
    source_uri: str,
    source_revision: str,
    quarantine_root: Path,
) -> SkillPackageManifest:
    root = root.resolve()
    entries: list[tuple[str, str]] = []
    files: list[tuple[Path, str]] = []
    for item in sorted(root.rglob("*"), key=lambda path: path.as_posix()):
        if _is_link_like(item):
            raise UnsafePackagePathError(str(item))
        if item.is_dir():
            continue
        if not item.is_file():
            raise UnsafePackagePathError(str(item))
        resolved = item.resolve()
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise UnsafePackagePathError(str(item)) from exc
        validate_package_reference_path(relative)
        file_hash = _hash_file(resolved)
        entries.append((relative, file_hash))
        files.append((resolved, relative))

    content_hash = _package_hash(entries)
    package_id = package_id_for(
        PackageSourceType.PROJECT.value,
        source_uri,
        source_revision,
        content_hash,
    )
    destination = package_directory(quarantine_root, package_id)
    destination.mkdir(parents=True, exist_ok=False)
    for source, relative in files:
        target = destination / Path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    manifest = SkillPackageManifest(
        package_id=package_id,
        source_type=PackageSourceType.PROJECT,
        source_uri=source_uri,
        source_revision=source_revision,
        content_hash=content_hash,
        imported_at=_utc_now(),
        importer="human",
        referenced_files=[relative for _, relative in files],
        trust_state=PackageTrustState.QUARANTINED,
    )
    store.put_package_manifest(manifest)
    return manifest


def verify_package_content(
    manifest: SkillPackageManifest,
    *,
    quarantine_root: Path,
) -> Path:
    package_dir = package_directory(quarantine_root, manifest.package_id)
    if _is_link_like(package_dir) or not package_dir.is_dir():
        raise PackageTamperedError(manifest.package_id)

    expected_paths = sorted(
        validate_package_reference_path(relative).as_posix()
        for relative in manifest.referenced_files
    )
    entries: list[tuple[str, str]] = []
    package_root = package_dir.resolve()
    for path in sorted(package_dir.rglob("*"), key=lambda item: item.as_posix()):
        if _is_link_like(path):
            raise PackageTamperedError(str(path))
        if path.is_dir():
            continue
        if not path.is_file():
            raise PackageTamperedError(str(path))
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(package_root).as_posix()
        except ValueError as exc:
            raise PackageTamperedError(str(path)) from exc
        entries.append((relative, _hash_file(resolved)))

    if sorted(relative for relative, _ in entries) != expected_paths:
        raise PackageTamperedError(manifest.package_id)
    if _package_hash(sorted(entries)) != manifest.content_hash:
        raise PackageTamperedError(manifest.package_id)
    return package_dir


def _scan_text(relative: str, text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    try:
        validate_safe_structured_text(text)
    except ValueError:
        findings.append(
            {
                "code": "sensitive_text",
                "severity": "blocking",
                "path": relative,
            }
        )
    invisible = {"\u200b", "\u200c", "\u200d", "\ufeff"}
    has_bidi_control = any("\u202a" <= char <= "\u202e" for char in text)
    if any(char in text for char in invisible) or has_bidi_control:
        findings.append(
            {
                "code": "invisible_unicode",
                "severity": "blocking",
                "path": relative,
            }
        )
    return findings

def scan_package(
    store: KnowledgeSkillStore,
    package_id: str,
    *,
    quarantine_root: Path,
) -> SkillPackageManifest:
    manifest = store.get_package_manifest(package_id)
    if manifest is None:
        raise KeyError(package_id)
    package_dir = verify_package_content(manifest, quarantine_root=quarantine_root)
    findings: list[dict[str, str]] = []
    for relative in manifest.referenced_files:
        safe_relative = validate_package_reference_path(relative)
        path = package_dir / safe_relative
        if _is_link_like(path) or not path.is_file():
            raise UnsafePackagePathError(str(path))
        resolved = path.resolve()
        try:
            resolved.relative_to(package_dir.resolve())
        except ValueError as exc:
            raise UnsafePackagePathError(str(path)) from exc
        try:
            text = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(_scan_text(relative, text))

    scanned = manifest.model_copy(
        update={
            "scanner_version": "ppa.skill-package-scan/v1",
            "scanner_findings": findings,
            "trust_state": PackageTrustState.SCANNED,
        }
    )
    store.put_package_manifest(scanned)
    return scanned


def approve_package(
    store: KnowledgeSkillStore,
    package_id: str,
    *,
    reviewer: str,
    quarantine_root: Path,
) -> SkillPackageManifest:
    manifest = store.get_package_manifest(package_id)
    if manifest is None:
        raise KeyError(package_id)
    if manifest.trust_state is not PackageTrustState.SCANNED:
        raise PackageScanBlockedError("package must be scanned before approval")
    if any(item.get("severity") == "blocking" for item in manifest.scanner_findings):
        raise PackageScanBlockedError("blocking scanner findings remain")
    verify_package_content(manifest, quarantine_root=quarantine_root)
    approved = manifest.model_copy(
        update={
            "trust_state": PackageTrustState.APPROVED,
            "approved_by": reviewer,
            "approved_at": _utc_now(),
        }
    )
    store.put_package_manifest(approved)
    return approved

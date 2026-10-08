from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from personal_predictive_ai.skills.models import (
    PackageTrustState,
    RiskClass,
    SkillKind,
    SkillScope,
    SkillStatus,
    VerificationSpec,
)
from personal_predictive_ai.skills.packages import (
    PackageTamperedError,
    UnsafePackagePathError,
    validate_package_reference_path,
    verify_package_content,
)
from personal_predictive_ai.storage.knowledge_skill_store import KnowledgeSkillStore


class SkillReferenceAccessError(RuntimeError):
    pass


class SkillIndexEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    skill_id: str
    name: str
    purpose: str
    kind: SkillKind
    risk_class: RiskClass
    status: SkillStatus
    version: int


class SkillCoreView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    skill_id: str
    version: int
    name: str
    purpose: str
    kind: SkillKind
    initiation_conditions: list[str]
    preconditions: list[str]
    procedure_steps: list[str]
    required_capabilities: list[str]
    termination_conditions: list[str]
    success_conditions: list[str]
    verification_spec: VerificationSpec
    scope: SkillScope
    risk_class: RiskClass
    status: SkillStatus
    source_package_id: str | None = None


class SkillReferenceView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    skill_id: str
    version: int
    package_id: str
    reference_path: str
    content: str

def list_skill_index(
    store: KnowledgeSkillStore,
    *,
    statuses: set[SkillStatus] | None = None,
) -> list[SkillIndexEntry]:
    result: list[SkillIndexEntry] = []
    for record in store.iter_latest_skills():
        if statuses is not None and record.status not in statuses:
            continue
        result.append(
            SkillIndexEntry(
                skill_id=record.skill_id,
                name=record.name,
                purpose=record.purpose,
                kind=record.kind,
                risk_class=record.risk_class,
                status=record.status,
                version=record.version,
            )
        )
    return result


def get_skill_core(
    store: KnowledgeSkillStore,
    skill_id: str,
    *,
    version: int | None = None,
) -> SkillCoreView:
    record = store.get_skill(skill_id, version)
    if record is None:
        raise KeyError(skill_id)
    return SkillCoreView(
        skill_id=record.skill_id,
        version=record.version,
        name=record.name,
        purpose=record.purpose,
        kind=record.kind,
        initiation_conditions=record.initiation_conditions,
        preconditions=record.preconditions,
        procedure_steps=record.procedure_steps,
        required_capabilities=record.required_capabilities,
        termination_conditions=record.termination_conditions,
        success_conditions=record.success_conditions,
        verification_spec=record.verification_spec,
        scope=record.scope,
        risk_class=record.risk_class,
        status=record.status,
        source_package_id=record.source_package_id,
    )


def get_skill_reference(
    store: KnowledgeSkillStore,
    package_root: Path,
    skill_id: str,
    reference_path: str,
    *,
    version: int | None = None,
) -> SkillReferenceView:
    record = store.get_skill(skill_id, version)
    if record is None or record.source_package_id is None:
        raise SkillReferenceAccessError(skill_id)
    manifest = store.get_package_manifest(record.source_package_id)
    if manifest is None or manifest.trust_state is not PackageTrustState.APPROVED:
        raise SkillReferenceAccessError(record.source_package_id)
    try:
        safe_path = validate_package_reference_path(reference_path)
    except UnsafePackagePathError as exc:
        raise SkillReferenceAccessError(reference_path) from exc
    normalized = safe_path.as_posix()
    if normalized not in manifest.referenced_files:
        raise SkillReferenceAccessError(reference_path)

    try:
        package_dir = verify_package_content(manifest, quarantine_root=package_root)
    except (PackageTamperedError, UnsafePackagePathError) as exc:
        raise SkillReferenceAccessError(manifest.package_id) from exc
    target = package_dir / safe_path
    if target.is_symlink() or bool(getattr(target, "is_junction", lambda: False)()):
        raise SkillReferenceAccessError(reference_path)
    if not target.is_file():
        raise SkillReferenceAccessError(reference_path)
    try:
        target.resolve().relative_to(package_dir.resolve())
    except ValueError as exc:
        raise SkillReferenceAccessError(reference_path) from exc
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SkillReferenceAccessError(reference_path) from exc
    return SkillReferenceView(
        skill_id=record.skill_id,
        version=record.version,
        package_id=manifest.package_id,
        reference_path=normalized,
        content=content,
    )

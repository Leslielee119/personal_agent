from __future__ import annotations

import json
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SkillKind(str, Enum):
    PLANNER = "planner"
    EXECUTOR = "executor"


class RiskClass(str, Enum):
    READ_ONLY = "read_only"
    WRITE_LOCAL = "write_local"
    ACT_LOCAL = "act_local"
    EXTERNAL_EFFECT = "external_effect"
    UNKNOWN = "unknown"


class SkillStatus(str, Enum):
    DRAFT = "draft"
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    ACTIVE = "active"
    NEEDS_REVALIDATION = "needs_revalidation"
    SUPERSEDED = "superseded"
    RETIRED = "retired"
    INVALID = "invalid"


class VerificationMethod(str, Enum):
    STATIC = "static"
    EVIDENCE_CONSISTENCY = "evidence_consistency"
    OFFLINE_REPLAY = "offline_replay"
    HELD_OUT_SESSION = "held_out_session"
    READ_ONLY_LIVE = "read_only_live"


class MutationKind(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    RETIRE = "retire"
    SUPERSEDE = "supersede"
    INVALIDATE = "invalidate"


class ProposalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    INVALID = "invalid"


class PackageTrustState(str, Enum):
    QUARANTINED = "quarantined"
    SCANNED = "scanned"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class PackageSourceType(str, Enum):
    LOCAL_HUMAN_AUTHORED = "local_human_authored"
    PROJECT = "project"
    GITHUB = "github"
    SKILL_REGISTRY = "skill_registry"
    HERMES_IMPORT = "hermes_import"
    OTHER_EXTERNAL = "other_external"
    UNKNOWN = "unknown"


class SkillScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scope_type: str = Field(min_length=1)
    scope_id: str = Field(min_length=1)


class VerificationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    schema_version: Literal["ppa.skill-verification/v1"] = "ppa.skill-verification/v1"
    verification_id: str = Field(min_length=1)
    method: VerificationMethod
    expected_observation: str = Field(min_length=1)
    evidence_requirements: list[str] = Field(default_factory=list)
    allowed_risk_class: RiskClass
    timeout: float | None = Field(default=None, gt=0)
    failure_conditions: list[str] = Field(default_factory=list)
    independence_requirement: str = Field(min_length=1)


class _SkillCore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    canonical_name: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: SkillKind
    purpose: str = Field(min_length=1)
    initiation_conditions: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    procedure_steps: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    termination_conditions: list[str] = Field(default_factory=list)
    success_conditions: list[str] = Field(default_factory=list)
    verification_spec: VerificationSpec
    scope: SkillScope
    risk_class: RiskClass
    evidence_refs: list[str] = Field(default_factory=list)
    contradiction_refs: list[str] = Field(default_factory=list)
    provenance_summary: dict[str, Any] = Field(default_factory=dict)
    support_sessions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_package_id: str | None = None

    @field_validator("parameters", "provenance_summary")
    @classmethod
    def _require_json_safe(cls, value: Any) -> Any:
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("skill fields must be strict JSON-safe data") from exc
        return value


class SkillDraft(_SkillCore):
    schema_version: Literal["ppa.skill-draft/v1"] = "ppa.skill-draft/v1"


class SkillRecord(_SkillCore):
    schema_version: Literal["ppa.skill/v1"] = "ppa.skill/v1"
    skill_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    status: SkillStatus = SkillStatus.DRAFT
    valid_from: int = Field(ge=0)
    valid_to: int | None = Field(default=None, ge=0)
    supersedes: str | None = None
    created_by: str = Field(min_length=1)
    created_at: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_interval(self) -> "SkillRecord":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be greater than or equal to valid_from")
        return self


class SkillMutationProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    schema_version: Literal["ppa.skill-mutation/v1"] = "ppa.skill-mutation/v1"
    proposal_id: str = Field(min_length=1)
    target_skill_id: str = Field(min_length=1)
    base_version: int | None = Field(default=None, ge=1)
    mutation_kind: MutationKind
    proposed_patch: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(default="", max_length=2000)
    evidence_refs: list[str] = Field(default_factory=list)
    contradiction_refs: list[str] = Field(default_factory=list)
    proposed_by: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    validation_result: dict[str, Any] = Field(default_factory=dict)
    approval_status: ProposalStatus = ProposalStatus.PENDING
    approved_by: str | None = None
    approved_at: str | None = None
    resulting_version: int | None = Field(default=None, ge=1)

    @field_validator("proposed_patch", "validation_result")
    @classmethod
    def _require_json_safe_maps(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("proposal fields must be strict JSON-safe data") from exc
        return value


class SkillPackageManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    schema_version: Literal["ppa.skill-package/v1"] = "ppa.skill-package/v1"
    package_id: str = Field(min_length=1)
    skill_id: str | None = None
    source_type: PackageSourceType
    source_uri: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    imported_at: str = Field(min_length=1)
    importer: str = Field(min_length=1)
    scanner_version: str | None = None
    scanner_findings: list[dict[str, Any]] = Field(default_factory=list)
    referenced_files: list[str] = Field(default_factory=list)
    trust_state: PackageTrustState = PackageTrustState.QUARANTINED
    approved_by: str | None = None
    approved_at: str | None = None

    @field_validator("scanner_findings")
    @classmethod
    def _require_json_safe_findings(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("scanner findings must be strict JSON-safe data") from exc
        return value


class SkillAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.skill-audit/v1"] = "ppa.skill-audit/v1"
    audit_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    occurred_at: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class SkillProjectionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.skill-projection/v1"] = "ppa.skill-projection/v1"
    projection_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    output_path: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    created_at: str = Field(min_length=1)

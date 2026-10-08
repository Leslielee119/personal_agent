from __future__ import annotations

import json
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FieldProvenance(str, Enum):
    OBSERVED = "observed"
    USER_DECLARED = "user_declared"
    DERIVED = "derived"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class ApplicabilityStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    NEEDS_REVALIDATION = "needs_revalidation"
    UNSUPPORTED = "unsupported"


class EvidenceAvailability(str, Enum):
    AVAILABLE = "available"
    EXPIRED_BY_TTL = "expired_by_ttl"
    USER_DELETED = "user_deleted"
    INTEGRITY_INVALID = "integrity_invalid"


class ContinuityRecordStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    INVALID = "invalid"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)


class ProjectRecord(_FrozenModel):
    schema_version: Literal["ppa.continuity-project/v1"] = "ppa.continuity-project/v1"
    project_id: str = Field(min_length=1)
    project_key: str = Field(min_length=1)
    created_at_ns: int = Field(ge=0)
    last_seen_at_ns: int = Field(ge=0)
    status: ContinuityRecordStatus = ContinuityRecordStatus.ACTIVE


class WorkCopyRecord(_FrozenModel):
    schema_version: Literal["ppa.continuity-workcopy/v1"] = "ppa.continuity-workcopy/v1"
    workcopy_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    canonical_root: str = Field(min_length=1)
    created_at_ns: int = Field(ge=0)
    last_seen_at_ns: int = Field(ge=0)
    vcs_branch_or_revision_hint: str | None = None
    status: ContinuityRecordStatus = ContinuityRecordStatus.ACTIVE


class TaskRecord(_FrozenModel):
    schema_version: Literal["ppa.continuity-task/v1"] = "ppa.continuity-task/v1"
    task_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    workcopy_id: str | None = None
    title: str = Field(min_length=1)
    created_at_ns: int = Field(ge=0)
    status: ContinuityRecordStatus = ContinuityRecordStatus.ACTIVE


class EvidenceRecord(_FrozenModel):
    schema_version: Literal["ppa.continuity-evidence/v1"] = "ppa.continuity-evidence/v1"
    evidence_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    observed_at_ns: int = Field(ge=0)
    available_at_ns: int = Field(ge=0)
    project_id: str = Field(min_length=1)
    workcopy_id: str | None = None
    task_id: str | None = None
    scope: str = Field(min_length=1)
    provenance: FieldProvenance
    availability: EvidenceAvailability = EvidenceAvailability.AVAILABLE
    content: Any

    @field_validator("content")
    @classmethod
    def _json_safe_content(cls, value: Any) -> Any:
        json.dumps(value, allow_nan=False)
        return value


class TaskStateFieldVersion(_FrozenModel):
    schema_version: Literal["ppa.continuity-field/v1"] = "ppa.continuity-field/v1"
    field_version_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    workcopy_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    field_name: str = Field(min_length=1)
    value: Any
    provenance: FieldProvenance
    applicability: ApplicabilityStatus = ApplicabilityStatus.CURRENT
    evidence_ids: list[str] = Field(default_factory=list)
    created_at_ns: int = Field(ge=0)
    supersedes: str | None = None
    status: ContinuityRecordStatus = ContinuityRecordStatus.ACTIVE

    @field_validator("value")
    @classmethod
    def _json_safe_value(cls, value: Any) -> Any:
        json.dumps(value, allow_nan=False)
        return value


class VerifiedResultRecord(_FrozenModel):
    schema_version: Literal["ppa.continuity-verified-result/v1"] = (
        "ppa.continuity-verified-result/v1"
    )
    result_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    workcopy_id: str = Field(min_length=1)
    task_id: str | None = None
    check_kind: str = Field(min_length=1)
    command_or_adapter_scope: str = Field(min_length=1)
    environment_fingerprint: str = Field(min_length=1)
    code_state_fingerprint: str = Field(min_length=1)
    observed_at_ns: int = Field(ge=0)
    outcome: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    applicability: ApplicabilityStatus = ApplicabilityStatus.CURRENT


class GitWorkCopyState(_FrozenModel):
    schema_version: Literal["ppa.continuity-git-state/v1"] = "ppa.continuity-git-state/v1"
    workcopy_id: str = Field(min_length=1)
    head_commit: str = Field(min_length=1)
    branch_hint: str = Field(min_length=1)
    is_dirty: bool
    tracked_diff_digest: str = Field(min_length=1)
    untracked_digest: str = Field(min_length=1)
    code_state_fingerprint: str = Field(min_length=1)
    observed_at_ns: int = Field(ge=0)


class FieldConflict(_FrozenModel):
    schema_version: Literal["ppa.continuity-field-conflict/v1"] = (
        "ppa.continuity-field-conflict/v1"
    )
    field_name: str = Field(min_length=1)
    field_version_ids: list[str] = Field(min_length=2)
    evidence_ids: list[str] = Field(default_factory=list)
    values: list[Any] = Field(min_length=2)


class TaskSnapshot(_FrozenModel):
    schema_version: Literal["ppa.continuity-snapshot/v1"] = "ppa.continuity-snapshot/v1"
    snapshot_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    workcopy_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    captured_at_ns: int = Field(ge=0)
    current_goal: str | None = None
    last_position: str | None = None
    candidate_next_step: str | None = None
    blockers: list[str] = Field(default_factory=list)
    pending_items: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    field_version_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    verified_result_ids: list[str] = Field(default_factory=list)
    verification_applicability: dict[str, ApplicabilityStatus] = Field(default_factory=dict)
    conflicts: list[FieldConflict] = Field(default_factory=list)


class ResumeBriefRecord(_FrozenModel):
    schema_version: Literal["ppa.continuity-brief/v1"] = "ppa.continuity-brief/v1"
    brief_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    workcopy_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    created_at_ns: int = Field(ge=0)
    sections: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)


class DeletionTombstoneRecord(_FrozenModel):
    schema_version: Literal["ppa.continuity-deletion/v1"] = "ppa.continuity-deletion/v1"
    deletion_id: str = Field(min_length=1)
    scope_type: str = Field(min_length=1)
    scope_hash: str = Field(min_length=1)
    deleted_at_ns: int = Field(ge=0)

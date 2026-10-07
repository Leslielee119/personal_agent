from __future__ import annotations

import json
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MemoryKind(str, Enum):
    FACT = "fact"
    HABIT = "habit"
    PROCEDURE = "procedure"
    STYLE = "style"


class MemoryStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    INVALID = "invalid"
    NEEDS_REVALIDATION = "needs_revalidation"


class DependencyRelation(str, Enum):
    DERIVED_FROM = "derived_from"
    SUPPORTS = "supports"
    CONSTRAINS = "constrains"


class EvidenceRole(str, Enum):
    SUPPORT = "support"
    CONTRADICTION = "contradiction"


class MemoryScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scope_type: str = Field(min_length=1)
    scope_id: str = Field(min_length=1)


class ProvenanceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    human_physical_support: int = Field(default=0, ge=0)
    ai_suggested_accepted_support: int = Field(default=0, ge=0)
    ai_suggested_modified_support: int = Field(default=0, ge=0)
    ai_executed_support: int = Field(default=0, ge=0)
    system_support: int = Field(default=0, ge=0)
    external_support: int = Field(default=0, ge=0)
    unknown_support: int = Field(default=0, ge=0)


class _MemoryClaimBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    memory_id: str = Field(min_length=1)
    kind: MemoryKind
    key: str = Field(min_length=1)
    value: Any
    scope: MemoryScope
    observed_from: int = Field(ge=0)
    valid_from: int = Field(ge=0)
    valid_to: int | None = Field(default=None, ge=0)
    created_seq: int = Field(ge=1)
    last_supported_seq: int = Field(ge=1)
    evidence_ids: list[str] = Field(default_factory=list)
    provenance_summary: ProvenanceSummary = Field(default_factory=ProvenanceSummary)
    support_count: int = Field(default=0, ge=0)
    contradiction_count: int = Field(default=0, ge=0)
    session_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    extractor_id: str = Field(min_length=1)
    config_version: str = Field(default="ppa.memory-config/v1", min_length=1)
    eligible_support_count: int = Field(default=0, ge=0)
    eligible_human_support_count: int = Field(default=0, ge=0)

    @field_validator("value")
    @classmethod
    def _require_json_safe_value(cls, value: Any) -> Any:
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("memory value must be strict JSON-safe data") from exc
        return value

    @model_validator(mode="after")
    def _validate_interval_and_sequences(self) -> "_MemoryClaimBase":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be greater than or equal to valid_from")
        if self.last_supported_seq < self.created_seq:
            raise ValueError("last_supported_seq cannot precede created_seq")
        return self


class MemoryCandidate(_MemoryClaimBase):
    schema_version: Literal["ppa.memory-candidate/v1"] = "ppa.memory-candidate/v1"


class MemoryRecord(_MemoryClaimBase):
    schema_version: Literal["ppa.memory/v1"] = "ppa.memory/v1"
    status: MemoryStatus = MemoryStatus.CANDIDATE


class MemoryEvidenceLink(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.memory-evidence/v1"] = "ppa.memory-evidence/v1"
    memory_id: str = Field(min_length=1)
    evidence_type: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    role: EvidenceRole


class MemoryDependency(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.memory-dependency/v1"] = "ppa.memory-dependency/v1"
    dependency_id: str = Field(min_length=1)
    parent_memory_id: str = Field(min_length=1)
    child_memory_id: str = Field(min_length=1)
    relation: DependencyRelation
    evidence_ids: list[str] = Field(default_factory=list)
    created_seq: int = Field(ge=1)
    active: bool = True


class SupersessionEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.memory-supersession/v1"] = "ppa.memory-supersession/v1"
    supersession_id: str = Field(min_length=1)
    new_memory_id: str = Field(min_length=1)
    old_memory_id: str = Field(min_length=1)
    created_seq: int = Field(ge=1)


class MemoryAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.memory-audit/v1"] = "ppa.memory-audit/v1"
    audit_id: str = Field(min_length=1)
    memory_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    source_seq: int = Field(ge=1)
    reason_code: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def _require_json_safe_details(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("audit details must be strict JSON-safe data") from exc
        return value


class ConsolidationConfigV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.memory-config/v1"] = "ppa.memory-config/v1"
    fact_min_support: Literal[3] = 3
    fact_min_sessions: Literal[2] = 2
    fact_min_ratio: Literal[0.8] = 0.8
    habit_min_support: Literal[5] = 5
    habit_min_sessions: Literal[3] = 3
    habit_min_ratio: Literal[0.7] = 0.7

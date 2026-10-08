from __future__ import annotations

import json
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class KnowledgeSourceClass(str, Enum):
    HUMAN_DECLARED = "human_declared"
    HUMAN_APPROVED_IMPORT = "human_approved_import"
    DERIVED_FROM_B2 = "derived_from_b2"
    AI_PROPOSED = "ai_proposed"
    SYSTEM = "system"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class KnowledgeStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    INVALID = "invalid"


class KnowledgeScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scope_type: str = Field(min_length=1)
    scope_id: str = Field(min_length=1)


class KnowledgeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    schema_version: Literal["ppa.knowledge/v1"] = "ppa.knowledge/v1"
    knowledge_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    key: str = Field(min_length=1)
    value: Any
    scope: KnowledgeScope
    source_class: KnowledgeSourceClass
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(min_length=1)
    created_seq: int = Field(ge=1)
    valid_from: int = Field(ge=0)
    valid_to: int | None = Field(default=None, ge=0)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    status: KnowledgeStatus = KnowledgeStatus.DRAFT
    supersedes: str | None = None
    superseded_by: str | None = None

    @field_validator("value", "provenance")
    @classmethod
    def _require_json_safe(cls, value: Any) -> Any:
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("knowledge fields must be strict JSON-safe data") from exc
        return value

    @model_validator(mode="after")
    def _validate_interval(self) -> "KnowledgeRecord":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be greater than or equal to valid_from")
        return self

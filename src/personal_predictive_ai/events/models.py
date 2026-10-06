from __future__ import annotations

import json
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventOrigin(str, Enum):
    ENDOGENOUS = "endogenous"
    EXOGENOUS = "exogenous"


class PrivacyTier(str, Enum):
    STANDARD = "standard"
    SENSITIVE = "sensitive"
    SECRET = "secret"


class RetentionClass(str, Enum):
    EPHEMERAL_RAW = "ephemeral_raw"
    STRUCTURED_SHORT = "structured_short"
    STRUCTURED_LONG = "structured_long"
    NEVER_STORE = "never_store"


class CanonicalEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    schema_version: Literal["ppa.event/v1"] = "ppa.event/v1"
    event_id: str = Field(min_length=1)
    timestamp_ns: int = Field(ge=0)
    monotonic_seq: int = Field(ge=1)
    source: str = Field(min_length=1)
    modality: str = Field(min_length=1)
    origin: EventOrigin
    event_type: str = Field(min_length=1)
    app: dict[str, Any] | None = None
    process: dict[str, Any] | None = None
    window: dict[str, Any] | None = None
    session_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    privacy_tier: PrivacyTier = PrivacyTier.STANDARD
    retention_class: RetentionClass = RetentionClass.STRUCTURED_LONG
    raw_ref: str | None = None
    causal_parent_ids: list[str] = Field(default_factory=list)

    @field_validator("app", "process", "window", "payload")
    @classmethod
    def _require_json_safe(cls, value: Any) -> Any:
        if value is None:
            return value
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("event fields must be strict JSON-safe values") from exc
        return value

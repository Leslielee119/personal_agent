from __future__ import annotations

import json
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EventOrigin(str, Enum):
    ENDOGENOUS = "endogenous"
    EXOGENOUS = "exogenous"


class EventActor(str, Enum):
    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class EventProvenance(str, Enum):
    HUMAN_PHYSICAL = "human_physical"
    AI_SUGGESTED_ACCEPTED = "ai_suggested_accepted"
    AI_SUGGESTED_MODIFIED = "ai_suggested_modified"
    AI_EXECUTED = "ai_executed"
    SYSTEM = "system"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


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

    schema_version: Literal["ppa.event/v2"] = "ppa.event/v2"
    event_id: str = Field(min_length=1)
    timestamp_ns: int = Field(ge=0)
    monotonic_seq: int = Field(ge=1)
    source: str = Field(min_length=1)
    modality: str = Field(min_length=1)
    origin: EventOrigin
    event_type: str = Field(min_length=1)
    actor: EventActor = EventActor.UNKNOWN
    provenance: EventProvenance = EventProvenance.UNKNOWN
    device: dict[str, Any] | None = None
    injected: bool | None = None
    app: dict[str, Any] | None = None
    process: dict[str, Any] | None = None
    window: dict[str, Any] | None = None
    session_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    privacy_tier: PrivacyTier = PrivacyTier.STANDARD
    retention_class: RetentionClass = RetentionClass.STRUCTURED_LONG
    raw_ref: str | None = None
    causal_parent_ids: list[str] = Field(default_factory=list)

    @field_validator("device", "app", "process", "window", "payload")
    @classmethod
    def _require_json_safe(cls, value: Any) -> Any:
        if value is None:
            return value
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("event fields must be strict JSON-safe values") from exc
        return value

    @model_validator(mode="after")
    def _validate_provenance(self) -> "CanonicalEvent":
        expected_actor = {
            EventProvenance.HUMAN_PHYSICAL: EventActor.HUMAN,
            EventProvenance.AI_SUGGESTED_ACCEPTED: EventActor.HUMAN,
            EventProvenance.AI_SUGGESTED_MODIFIED: EventActor.HUMAN,
            EventProvenance.AI_EXECUTED: EventActor.AI,
            EventProvenance.SYSTEM: EventActor.SYSTEM,
            EventProvenance.EXTERNAL: EventActor.EXTERNAL,
        }.get(self.provenance)
        if expected_actor is not None and self.actor is not expected_actor:
            raise ValueError(
                f"provenance {self.provenance.value} requires actor {expected_actor.value}"
            )
        if self.provenance is EventProvenance.HUMAN_PHYSICAL and self.injected is not False:
            raise ValueError("human_physical provenance requires injected=False")
        return self

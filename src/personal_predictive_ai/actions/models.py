from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from personal_predictive_ai.events.models import EventActor, EventProvenance


class ActionLevel(str, Enum):
    INTENT = "intent"
    APPLICATION = "application"
    OPERATION = "operation"
    CONCRETE = "concrete"
    FINE = "fine"


class NormalizedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    schema_version: Literal["ppa.action/v1"] = "ppa.action/v1"
    action_id: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)
    timestamp_ns: int = Field(ge=0)
    monotonic_seq: int = Field(ge=1)
    actor: EventActor
    provenance: EventProvenance
    intent: str | None = None
    application: str | None = None
    operation: str = Field(min_length=1)
    concrete: str | None = None
    fine: dict[str, Any] | None = None
    context: dict[str, Any] | None = None

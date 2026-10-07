from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from personal_predictive_ai.events.models import EventActor, EventProvenance


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    schema_version: Literal["ppa.transition/v1"] = "ppa.transition/v1"
    transition_id: str = Field(min_length=1)
    session_id: str | None = None
    pre_state_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    exogenous_event_ids: list[str] = Field(default_factory=list)
    post_state_id: str | None = None
    actor: EventActor
    provenance: EventProvenance
    start_seq: int = Field(ge=1)
    end_seq: int = Field(ge=1)

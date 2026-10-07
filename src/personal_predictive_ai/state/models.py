from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.state/v1"] = "ppa.state/v1"
    state_id: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)
    timestamp_ns: int = Field(ge=0)
    monotonic_seq: int = Field(ge=1)
    foreground_app: dict[str, Any] | None = None
    foreground_process: dict[str, Any] | None = None
    foreground_window: dict[str, Any] | None = None
    focused_ui_summary: dict[str, Any] | None = None
    recent_action_ids: list[str] = Field(default_factory=list)
    active_processes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    active_exogenous_event_ids: list[str] = Field(default_factory=list)
    recent_visual_event_ids: list[str] = Field(default_factory=list)
    last_activity_ns: int | None = None
    idle_ns: int | None = None
    session_id: str | None = None

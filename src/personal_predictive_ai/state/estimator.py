from __future__ import annotations

from typing import Any

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.events.models import CanonicalEvent, EventOrigin
from personal_predictive_ai.state.models import StateSnapshot


class ExplicitStateEstimator:
    def __init__(
        self,
        *,
        max_recent_actions: int = 32,
        max_exogenous_events: int = 32,
        max_visual_refs: int = 8,
    ) -> None:
        self._max_recent_actions = max_recent_actions
        self._max_exogenous_events = max_exogenous_events
        self._max_visual_refs = max_visual_refs
        self._foreground_app: dict[str, Any] | None = None
        self._foreground_process: dict[str, Any] | None = None
        self._foreground_window: dict[str, Any] | None = None
        self._focused_ui_summary: dict[str, Any] | None = None
        self._recent_action_ids: list[str] = []
        self._active_processes: dict[str, dict[str, Any]] = {}
        self._active_exogenous_event_ids: list[str] = []
        self._recent_visual_event_ids: list[str] = []
        self._last_activity_ns: int | None = None
        self._session_id: str | None = None
        self._current: StateSnapshot | None = None

    def current(self) -> StateSnapshot | None:
        return self._current

    def apply(
        self,
        event: CanonicalEvent,
        action: NormalizedAction | None,
    ) -> StateSnapshot:
        if event.event_type.startswith("window.foreground."):
            self._foreground_app = dict(event.app) if event.app is not None else None
            self._foreground_process = (
                dict(event.process) if event.process is not None else None
            )
            self._foreground_window = (
                dict(event.window) if event.window is not None else None
            )

        if event.event_type == "process.started" and event.process is not None:
            self._active_processes[self._process_key(event.process)] = dict(event.process)
        elif event.event_type == "process.exited" and event.process is not None:
            self._active_processes.pop(self._process_key(event.process), None)

        summary = self._focused_summary(event)
        if summary is not None:
            self._focused_ui_summary = summary

        if action is not None:
            self._recent_action_ids.append(action.action_id)
            self._recent_action_ids = self._recent_action_ids[-self._max_recent_actions :]
            self._last_activity_ns = event.timestamp_ns

        if event.origin is EventOrigin.EXOGENOUS:
            self._active_exogenous_event_ids.append(event.event_id)
            self._active_exogenous_event_ids = self._active_exogenous_event_ids[
                -self._max_exogenous_events :
            ]

        if event.event_type == "screen.snapshot":
            self._recent_visual_event_ids.append(event.event_id)
            self._recent_visual_event_ids = self._recent_visual_event_ids[-self._max_visual_refs :]

        if event.session_id is not None:
            self._session_id = event.session_id

        idle_ns = None
        if self._last_activity_ns is not None:
            idle_ns = max(0, event.timestamp_ns - self._last_activity_ns)

        snapshot = StateSnapshot(
            state_id=f"state:{event.monotonic_seq}:{event.event_id}",
            source_event_id=event.event_id,
            timestamp_ns=event.timestamp_ns,
            monotonic_seq=event.monotonic_seq,
            foreground_app=self._foreground_app,
            foreground_process=self._foreground_process,
            foreground_window=self._foreground_window,
            focused_ui_summary=self._focused_ui_summary,
            recent_action_ids=list(self._recent_action_ids),
            active_processes={key: dict(value) for key, value in self._active_processes.items()},
            active_exogenous_event_ids=list(self._active_exogenous_event_ids),
            recent_visual_event_ids=list(self._recent_visual_event_ids),
            last_activity_ns=self._last_activity_ns,
            idle_ns=idle_ns,
            session_id=self._session_id,
        )
        self._current = snapshot
        return snapshot

    @staticmethod
    def _process_key(process: dict[str, Any]) -> str:
        pid = process.get("pid")
        create_time = process.get("create_time")
        return f"{pid}:{create_time}" if create_time is not None else str(pid)

    @staticmethod
    def _focused_summary(event: CanonicalEvent) -> dict[str, Any] | None:
        structural = event.payload.get("structural")
        if not isinstance(structural, dict):
            return None
        target = structural.get("target")
        if not isinstance(target, dict):
            return None
        allowed = ("control_type", "role", "name", "automation_id", "class_name", "bounds")
        summary = {key: target[key] for key in allowed if key in target}
        return summary or None

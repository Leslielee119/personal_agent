from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from personal_predictive_ai.events.models import CanonicalEvent
from personal_predictive_ai.state.models import StateSnapshot


class SessionSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(min_length=1)
    start_event_id: str = Field(min_length=1)
    start_ns: int = Field(ge=0)
    end_event_id: str = Field(min_length=1)
    end_ns: int = Field(ge=0)
    reason: str = Field(min_length=1)


class SessionBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    closed_segment: SessionSegment | None = None


class SessionSegmenter:
    def __init__(self, *, inactivity_seconds: int = 30 * 60) -> None:
        if inactivity_seconds < 1:
            raise ValueError("inactivity_seconds must be positive")
        self._inactivity_ns = inactivity_seconds * 1_000_000_000
        self._session_id: str | None = None
        self._start_event_id: str | None = None
        self._start_ns: int | None = None
        self._last_event_id: str | None = None
        self._last_ns: int | None = None
        self._last_seq = 0

    @property
    def current_session_id(self) -> str | None:
        return self._session_id

    def observe(
        self,
        event: CanonicalEvent,
        state: StateSnapshot,
    ) -> SessionBoundary | None:
        del state
        if event.monotonic_seq <= self._last_seq:
            raise ValueError("session events must have increasing monotonic_seq")

        if self._session_id is None:
            self._open(event)
            return SessionBoundary(
                session_id=self._session_id,
                reason="first_event",
            )

        reason: str | None = None
        if event.event_type == "runtime.restart":
            reason = "runtime_restart"
        elif self._last_ns is not None:
            gap = event.timestamp_ns - self._last_ns
            if gap >= self._inactivity_ns:
                reason = "inactivity_gap"

        if reason is None:
            self._advance(event)
            return None

        closed = self._close(reason)
        self._open(event)
        return SessionBoundary(
            session_id=self._session_id,
            reason=reason,
            closed_segment=closed,
        )

    def flush(self) -> SessionSegment | None:
        if self._session_id is None:
            return None
        segment = self._close("end_of_stream")
        self._session_id = None
        self._start_event_id = None
        self._start_ns = None
        self._last_event_id = None
        self._last_ns = None
        return segment

    def _open(self, event: CanonicalEvent) -> None:
        self._session_id = f"session:{event.event_id}"
        self._start_event_id = event.event_id
        self._start_ns = event.timestamp_ns
        self._advance(event)

    def _advance(self, event: CanonicalEvent) -> None:
        self._last_event_id = event.event_id
        self._last_ns = event.timestamp_ns
        self._last_seq = event.monotonic_seq

    def _close(self, reason: str) -> SessionSegment:
        assert self._session_id is not None
        assert self._start_event_id is not None
        assert self._start_ns is not None
        assert self._last_event_id is not None
        assert self._last_ns is not None
        return SessionSegment(
            session_id=self._session_id,
            start_event_id=self._start_event_id,
            start_ns=self._start_ns,
            end_event_id=self._last_event_id,
            end_ns=self._last_ns,
            reason=reason,
        )

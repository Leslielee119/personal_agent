from __future__ import annotations

import threading
import uuid
from typing import Any

from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventActor,
    EventOrigin,
    EventProvenance,
    PrivacyTier,
    RetentionClass,
)


class EventFactory:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sequence = 0

    def ensure_at_least(self, sequence: int) -> None:
        if sequence < 0:
            raise ValueError("sequence floor must be non-negative")
        with self._lock:
            if sequence > self._sequence:
                self._sequence = sequence

    def next(
        self,
        *,
        timestamp_ns: int,
        source: str,
        modality: str,
        origin: EventOrigin,
        event_type: str,
        actor: EventActor = EventActor.UNKNOWN,
        provenance: EventProvenance = EventProvenance.UNKNOWN,
        device: dict[str, Any] | None = None,
        injected: bool | None = None,
        app: dict[str, Any] | None = None,
        process: dict[str, Any] | None = None,
        window: dict[str, Any] | None = None,
        session_id: str | None = None,
        payload: dict[str, Any] | None = None,
        privacy_tier: PrivacyTier = PrivacyTier.STANDARD,
        retention_class: RetentionClass = RetentionClass.STRUCTURED_LONG,
        raw_ref: str | None = None,
        causal_parent_ids: list[str] | None = None,
    ) -> CanonicalEvent:
        with self._lock:
            self._sequence += 1
            sequence = self._sequence

        event_id = f"{uuid.uuid4()}:{sequence}"
        return CanonicalEvent(
            event_id=event_id,
            timestamp_ns=timestamp_ns,
            monotonic_seq=sequence,
            source=source,
            modality=modality,
            origin=origin,
            event_type=event_type,
            actor=actor,
            provenance=provenance,
            device=device,
            injected=injected,
            app=app,
            process=process,
            window=window,
            session_id=session_id,
            payload=payload or {},
            privacy_tier=privacy_tier,
            retention_class=retention_class,
            raw_ref=raw_ref,
            causal_parent_ids=causal_parent_ids or [],
        )

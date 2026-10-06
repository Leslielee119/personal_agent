from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventActor,
    EventProvenance,
)


def parse_canonical_event(data: Mapping[str, Any]) -> CanonicalEvent:
    payload = dict(data)
    version = payload.get("schema_version", "ppa.event/v1")
    if version == "ppa.event/v1":
        payload["schema_version"] = "ppa.event/v2"
        payload.setdefault("actor", EventActor.UNKNOWN.value)
        payload.setdefault("provenance", EventProvenance.UNKNOWN.value)
        payload.setdefault("device", None)
        payload.setdefault("injected", None)
    return CanonicalEvent.model_validate(payload)

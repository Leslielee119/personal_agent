from __future__ import annotations

import json
from collections.abc import Iterator

from personal_predictive_ai.events.models import CanonicalEvent
from personal_predictive_ai.privacy.policy import PrivacyPolicy
from personal_predictive_ai.privacy.sanitizer import sanitize_event
from personal_predictive_ai.storage.raw_ring import RawRing
from personal_predictive_ai.storage.sqlite_store import EventStore


def _app_label(event: CanonicalEvent) -> str:
    app_name = (event.app or {}).get("name")
    if app_name:
        return str(app_name)
    process_name = (event.process or {}).get("name")
    return str(process_name) if process_name else "-"


def _payload_summary(event: CanonicalEvent, *, max_chars: int = 240) -> str:
    encoded = json.dumps(
        event.payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(encoded) <= max_chars:
        return encoded
    return encoded[: max_chars - 1] + "…"


def format_replay_line(
    event: CanonicalEvent,
    *,
    raw_ring: RawRing | None = None,
    privacy_policy: PrivacyPolicy | None = None,
) -> str | None:
    """Format one persisted event without exposing raw artifacts or unsafe fields."""

    sanitized = sanitize_event(event, privacy_policy or PrivacyPolicy())
    if sanitized is None:
        return None

    suffix = ""
    if sanitized.raw_ref:
        raw_state = "unknown"
        if raw_ring is not None:
            raw_state = "available" if raw_ring.resolve(sanitized.raw_ref) else "expired"
        suffix = f" | raw={raw_state}"

    return (
        f"{sanitized.timestamp_ns} | {sanitized.origin.value} | "
        f"{_app_label(sanitized)} | {sanitized.event_type} | "
        f"{_payload_summary(sanitized)}{suffix}"
    )


def iter_replay_lines(
    store: EventStore,
    *,
    raw_ring: RawRing | None = None,
    privacy_policy: PrivacyPolicy | None = None,
    limit: int | None = None,
) -> Iterator[str]:
    for event in store.iter_events(limit=limit):
        line = format_replay_line(
            event,
            raw_ring=raw_ring,
            privacy_policy=privacy_policy,
        )
        if line is not None:
            yield line

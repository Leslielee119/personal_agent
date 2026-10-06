from __future__ import annotations

from typing import Any

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.events.models import CanonicalEvent

_KEY_FIELDS = (
    "canonical_key_char",
    "canonical_key_name",
    "canonical_key_vk",
    "key_char",
    "key_name",
    "key_vk",
)


def _application(event: CanonicalEvent) -> str | None:
    app_name = (event.app or {}).get("name")
    if app_name is not None:
        return str(app_name)
    process_name = (event.process or {}).get("name")
    return str(process_name) if process_name is not None else None


def _context(event: CanonicalEvent) -> dict[str, Any] | None:
    context: dict[str, Any] = {}
    if event.app is not None:
        context["app"] = event.app
    if event.process is not None:
        context["process"] = event.process
    if event.window is not None:
        context["window"] = event.window
    return context or None


def _select(payload: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any] | None:
    selected = {field: payload[field] for field in fields if field in payload}
    return selected or None


def normalize_action(event: CanonicalEvent) -> NormalizedAction | None:
    operation: str
    concrete: str | None
    fine: dict[str, Any] | None

    if event.event_type == "key.down":
        operation = "key_input"
        fine = _select(event.payload, _KEY_FIELDS)
        concrete = None
        if fine is not None:
            for field in _KEY_FIELDS:
                value = fine.get(field)
                if value is not None:
                    concrete = str(value)
                    break
    elif event.event_type == "mouse.down":
        operation = "click"
        fine = _select(event.payload, ("x", "y", "button"))
        button = event.payload.get("button")
        concrete = str(button) if button is not None else None
    elif event.event_type == "mouse.scroll":
        operation = "scroll"
        fine = _select(event.payload, ("x", "y", "dx", "dy"))
        concrete = None
    elif event.event_type == "mouse.move":
        operation = "pointer_move"
        fine = _select(event.payload, ("x", "y"))
        concrete = None
    else:
        return None

    return NormalizedAction(
        action_id=f"action:{event.event_id}",
        source_event_id=event.event_id,
        timestamp_ns=event.timestamp_ns,
        monotonic_seq=event.monotonic_seq,
        actor=event.actor,
        provenance=event.provenance,
        intent=None,
        application=_application(event),
        operation=operation,
        concrete=concrete,
        fine=fine,
        context=_context(event),
    )

from personal_predictive_ai.actions.normalize import normalize_action
from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventActor,
    EventOrigin,
    EventProvenance,
)


def _event(
    event_type: str,
    *,
    modality: str,
    payload=None,
    actor=EventActor.HUMAN,
    provenance=EventProvenance.HUMAN_PHYSICAL,
    app=None,
    process=None,
    window=None,
    injected=False,
):
    if provenance is EventProvenance.UNKNOWN:
        injected = None
    return CanonicalEvent(
        event_id=f"evt-{event_type}",
        timestamp_ns=100,
        monotonic_seq=1,
        source="unit",
        modality=modality,
        origin=EventOrigin.ENDOGENOUS,
        event_type=event_type,
        actor=actor,
        provenance=provenance,
        injected=injected,
        payload=payload or {},
        app=app,
        process=process,
        window=window,
    )


def test_keyboard_key_down_normalizes_without_inventing_intent() -> None:
    event = _event(
        "key.down",
        modality="keyboard",
        payload={"canonical_key_char": "a", "canonical_key_vk": "65"},
        app={"name": "Code.exe"},
    )

    action = normalize_action(event)

    assert action is not None
    assert action.action_id == "action:evt-key.down"
    assert action.source_event_id == event.event_id
    assert action.operation == "key_input"
    assert action.concrete == "a"
    assert action.fine == {"canonical_key_char": "a", "canonical_key_vk": "65"}
    assert action.application == "Code.exe"
    assert action.intent is None
    assert action.provenance is EventProvenance.HUMAN_PHYSICAL


def test_mouse_click_and_scroll_normalize_deterministically() -> None:
    click = _event(
        "mouse.down",
        modality="mouse",
        payload={"x": 10.0, "y": 20.0, "button": "left"},
    )
    scroll = click.model_copy(
        update={
            "event_id": "evt-scroll",
            "event_type": "mouse.scroll",
            "payload": {"x": 10.0, "y": 20.0, "dx": 0.0, "dy": -1.0},
        }
    )

    click_action = normalize_action(click)
    scroll_action = normalize_action(scroll)

    assert click_action is not None
    assert click_action.operation == "click"
    assert click_action.concrete == "left"
    assert click_action.fine == {"x": 10.0, "y": 20.0, "button": "left"}
    assert scroll_action is not None
    assert scroll_action.operation == "scroll"
    assert scroll_action.concrete is None
    assert scroll_action.fine["dy"] == -1.0


def test_system_observations_do_not_become_actions() -> None:
    process = _event(
        "process.started",
        modality="process",
        actor=EventActor.SYSTEM,
        provenance=EventProvenance.SYSTEM,
        injected=None,
    )
    foreground = process.model_copy(
        update={
            "event_id": "evt-window",
            "event_type": "window.foreground.changed",
            "modality": "window",
        }
    )

    assert normalize_action(process) is None
    assert normalize_action(foreground) is None


def test_missing_context_and_unknown_provenance_are_preserved_not_fabricated() -> None:
    event = _event(
        "key.down",
        modality="keyboard",
        payload={"canonical_key_name": "enter"},
        actor=EventActor.UNKNOWN,
        provenance=EventProvenance.UNKNOWN,
        app=None,
        process=None,
        window=None,
    )

    action = normalize_action(event)

    assert action is not None
    assert action.actor is EventActor.UNKNOWN
    assert action.provenance is EventProvenance.UNKNOWN
    assert action.application is None
    assert action.context is None
    assert action.intent is None


def test_key_up_is_evidence_but_not_a_separate_normalized_action() -> None:
    event = _event("key.up", modality="keyboard", payload={"canonical_key_char": "a"})
    assert normalize_action(event) is None

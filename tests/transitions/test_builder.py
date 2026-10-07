from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventActor,
    EventOrigin,
    EventProvenance,
)
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.transitions.builder import TransitionBuilder


def _state(seq: int, *, session_id: str = "s1", timestamp_ns: int | None = None):
    return StateSnapshot(
        state_id=f"state-{seq}",
        source_event_id=f"evt-{seq}",
        timestamp_ns=seq if timestamp_ns is None else timestamp_ns,
        monotonic_seq=max(1, seq),
        session_id=session_id,
    )


def _event(
    seq: int,
    event_type: str,
    *,
    origin=EventOrigin.EXOGENOUS,
    actor=EventActor.SYSTEM,
    provenance=EventProvenance.SYSTEM,
    timestamp_ns: int = 100,
):
    injected = False if provenance is EventProvenance.HUMAN_PHYSICAL else None
    return CanonicalEvent(
        event_id=f"evt-{seq}",
        timestamp_ns=timestamp_ns,
        monotonic_seq=seq,
        source="unit",
        modality=event_type.split(".", 1)[0],
        origin=origin,
        event_type=event_type,
        actor=actor,
        provenance=provenance,
        injected=injected,
    )


def _action(
    seq: int,
    *,
    actor=EventActor.HUMAN,
    provenance=EventProvenance.HUMAN_PHYSICAL,
):
    return NormalizedAction(
        action_id=f"action-{seq}",
        source_event_id=f"evt-{seq}",
        timestamp_ns=100,
        monotonic_seq=seq,
        actor=actor,
        provenance=provenance,
        operation="key_input",
    )


def test_transition_attaches_exogenous_events_until_next_action() -> None:
    builder = TransitionBuilder()
    action_event = _event(
        2,
        "key.down",
        origin=EventOrigin.ENDOGENOUS,
        actor=EventActor.HUMAN,
        provenance=EventProvenance.HUMAN_PHYSICAL,
    )
    process_event = _event(3, "process.exited")
    next_action_event = _event(
        4,
        "key.down",
        origin=EventOrigin.ENDOGENOUS,
        actor=EventActor.HUMAN,
        provenance=EventProvenance.HUMAN_PHYSICAL,
    )

    assert builder.observe(action_event, _action(2), _state(1), _state(2)) == []
    assert builder.observe(process_event, None, _state(2), _state(3)) == []
    emitted = builder.observe(next_action_event, _action(4), _state(3), _state(4))

    assert len(emitted) == 1
    transition = emitted[0]
    assert transition.pre_state_id == "state-1"
    assert transition.action_id == "action-2"
    assert transition.exogenous_event_ids == ["evt-3"]
    assert transition.post_state_id == "state-3"
    assert transition.start_seq == 2
    assert transition.end_seq == 3
    assert transition.provenance is EventProvenance.HUMAN_PHYSICAL


def test_equal_timestamp_exogenous_events_preserve_sequence_order() -> None:
    builder = TransitionBuilder()
    action_event = _event(
        2,
        "mouse.down",
        origin=EventOrigin.ENDOGENOUS,
        actor=EventActor.HUMAN,
        provenance=EventProvenance.HUMAN_PHYSICAL,
        timestamp_ns=100,
    )
    builder.observe(action_event, _action(2), _state(1), _state(2))
    builder.observe(_event(3, "process.started", timestamp_ns=100), None, _state(2), _state(3))
    builder.observe(
        _event(4, "window.foreground.changed", timestamp_ns=100), None, _state(3), _state(4)
    )

    transition = builder.flush()[0]

    assert transition.exogenous_event_ids == ["evt-3", "evt-4"]
    assert transition.end_seq == 4


def test_missing_post_context_is_preserved_as_unknown() -> None:
    builder = TransitionBuilder()
    action_event = _event(
        2,
        "key.down",
        origin=EventOrigin.ENDOGENOUS,
        actor=EventActor.UNKNOWN,
        provenance=EventProvenance.UNKNOWN,
    )

    builder.observe(
        action_event,
        _action(2, actor=EventActor.UNKNOWN, provenance=EventProvenance.UNKNOWN),
        _state(1),
        None,
    )
    transition = builder.flush()[0]

    assert transition.post_state_id is None
    assert transition.actor is EventActor.UNKNOWN
    assert transition.provenance is EventProvenance.UNKNOWN


def test_session_change_flushes_pending_transition() -> None:
    builder = TransitionBuilder()
    action_event = _event(
        2,
        "key.down",
        origin=EventOrigin.ENDOGENOUS,
        actor=EventActor.HUMAN,
        provenance=EventProvenance.HUMAN_PHYSICAL,
    )
    builder.observe(
        action_event, _action(2), _state(1, session_id="s1"), _state(2, session_id="s1")
    )

    boundary_event = _event(3, "process.started")
    emitted = builder.observe(
        boundary_event,
        None,
        _state(2, session_id="s2"),
        _state(3, session_id="s2"),
    )

    assert len(emitted) == 1
    assert emitted[0].session_id == "s1"
    assert emitted[0].post_state_id == "state-2"


def test_ai_executed_action_keeps_ai_provenance() -> None:
    builder = TransitionBuilder()
    event = _event(
        2,
        "key.down",
        origin=EventOrigin.ENDOGENOUS,
        actor=EventActor.AI,
        provenance=EventProvenance.AI_EXECUTED,
    )
    action = _action(2, actor=EventActor.AI, provenance=EventProvenance.AI_EXECUTED)

    builder.observe(event, action, _state(1), _state(2))
    transition = builder.flush()[0]

    assert transition.actor is EventActor.AI
    assert transition.provenance is EventProvenance.AI_EXECUTED

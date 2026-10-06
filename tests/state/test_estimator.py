from personal_predictive_ai.actions.normalize import normalize_action
from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventActor,
    EventOrigin,
    EventProvenance,
)
from personal_predictive_ai.state.estimator import ExplicitStateEstimator


def _system_event(seq: int, event_type: str, *, timestamp_ns=None, **kwargs):
    return CanonicalEvent(
        event_id=f"evt-{seq}",
        timestamp_ns=seq if timestamp_ns is None else timestamp_ns,
        monotonic_seq=seq,
        source="unit",
        modality=event_type.split(".", 1)[0],
        origin=EventOrigin.EXOGENOUS,
        event_type=event_type,
        actor=EventActor.SYSTEM,
        provenance=EventProvenance.SYSTEM,
        **kwargs,
    )


def _human_key(seq: int, *, timestamp_ns=None):
    return CanonicalEvent(
        event_id=f"evt-{seq}",
        timestamp_ns=seq if timestamp_ns is None else timestamp_ns,
        monotonic_seq=seq,
        source="unit",
        modality="keyboard",
        origin=EventOrigin.ENDOGENOUS,
        event_type="key.down",
        actor=EventActor.HUMAN,
        provenance=EventProvenance.HUMAN_PHYSICAL,
        injected=False,
        payload={"canonical_key_char": "a"},
    )


def test_foreground_and_process_state_update_incrementally() -> None:
    estimator = ExplicitStateEstimator()
    foreground = _system_event(
        1,
        "window.foreground.changed",
        app={"name": "Code.exe"},
        process={"pid": 10, "name": "Code.exe"},
        window={"handle": 7, "title": "Editor"},
    )
    started = _system_event(
        2,
        "process.started",
        process={"pid": 20, "create_time": 2.0, "name": "pytest.exe"},
    )
    exited = _system_event(
        3,
        "process.exited",
        process={"pid": 20, "create_time": 2.0, "name": "pytest.exe"},
    )

    first = estimator.apply(foreground, None)
    second = estimator.apply(started, None)
    third = estimator.apply(exited, None)

    assert first.foreground_app == {"name": "Code.exe"}
    assert first.foreground_process == {"pid": 10, "name": "Code.exe"}
    assert first.foreground_window == {"handle": 7, "title": "Editor"}
    assert "20:2.0" in second.active_processes
    assert "20:2.0" not in third.active_processes


def test_keyboard_activity_updates_recent_action_ids_without_fabricating_context() -> None:
    estimator = ExplicitStateEstimator(max_recent_actions=3)
    event = _human_key(1, timestamp_ns=100)
    action = normalize_action(event)

    state = estimator.apply(event, action)

    assert action is not None
    assert state.recent_action_ids == [action.action_id]
    assert state.last_activity_ns == 100
    assert state.foreground_app is None
    assert state.focused_ui_summary is None


def test_screen_snapshot_keeps_only_event_reference_not_raw_bytes() -> None:
    estimator = ExplicitStateEstimator(max_visual_refs=2)
    screen = _system_event(
        1,
        "screen.snapshot",
        raw_ref="raw/secret.png",
        payload={"width": 10, "height": 10},
    )

    state = estimator.apply(screen, None)

    assert state.recent_visual_event_ids == [screen.event_id]
    assert "secret.png" not in state.model_dump_json()


def test_exogenous_event_ids_are_bounded_and_preserved() -> None:
    estimator = ExplicitStateEstimator(max_exogenous_events=2)
    states = [
        estimator.apply(_system_event(i, "process.started", process={"pid": i}), None)
        for i in (1, 2, 3)
    ]

    assert states[-1].active_exogenous_event_ids == ["evt-2", "evt-3"]


def test_backward_wall_clock_does_not_break_sequence_progression() -> None:
    estimator = ExplicitStateEstimator()
    first_event = _human_key(1, timestamp_ns=200)
    first = estimator.apply(first_event, normalize_action(first_event))
    second_event = _human_key(2, timestamp_ns=100)
    second = estimator.apply(second_event, normalize_action(second_event))

    assert first.monotonic_seq == 1
    assert second.monotonic_seq == 2
    assert first.state_id != second.state_id
    assert second.timestamp_ns == 100
    assert estimator.current() == second


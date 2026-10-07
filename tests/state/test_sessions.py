from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventActor,
    EventOrigin,
    EventProvenance,
)
from personal_predictive_ai.state.estimator import ExplicitStateEstimator
from personal_predictive_ai.state.sessions import SessionSegmenter

MINUTE_NS = 60 * 1_000_000_000


def _event(seq: int, timestamp_ns: int, event_type: str = "process.started") -> CanonicalEvent:
    return CanonicalEvent(
        event_id=f"evt-{seq}",
        timestamp_ns=timestamp_ns,
        monotonic_seq=seq,
        source="unit",
        modality="system",
        origin=EventOrigin.EXOGENOUS,
        event_type=event_type,
        actor=EventActor.SYSTEM,
        provenance=EventProvenance.SYSTEM,
    )


def _state(event: CanonicalEvent):
    return ExplicitStateEstimator().apply(event, None)


def test_first_event_opens_deterministic_session() -> None:
    event = _event(1, 100)
    segmenter = SessionSegmenter()

    boundary = segmenter.observe(event, _state(event))

    assert boundary is not None
    assert boundary.reason == "first_event"
    assert boundary.session_id == "session:evt-1"
    assert boundary.closed_segment is None
    assert segmenter.current_session_id == "session:evt-1"


def test_29_minute_gap_stays_in_session_and_30_minute_gap_rotates() -> None:
    segmenter = SessionSegmenter(inactivity_seconds=30 * 60)
    first = _event(1, 0)
    second = _event(2, 29 * MINUTE_NS)
    third = _event(3, 59 * MINUTE_NS)

    segmenter.observe(first, _state(first))
    assert segmenter.observe(second, _state(second)) is None
    boundary = segmenter.observe(third, _state(third))

    assert boundary is not None
    assert boundary.reason == "inactivity_gap"
    assert boundary.session_id == "session:evt-3"
    assert boundary.closed_segment is not None
    assert boundary.closed_segment.start_event_id == "evt-1"
    assert boundary.closed_segment.end_event_id == "evt-2"


def test_runtime_restart_marker_forces_new_session() -> None:
    segmenter = SessionSegmenter()
    first = _event(1, 100)
    restart = _event(2, 101, "runtime.restart")

    segmenter.observe(first, _state(first))
    boundary = segmenter.observe(restart, _state(restart))

    assert boundary is not None
    assert boundary.reason == "runtime_restart"
    assert boundary.session_id == "session:evt-2"


def test_backward_wall_clock_with_increasing_sequence_does_not_split() -> None:
    segmenter = SessionSegmenter()
    first = _event(1, 200)
    backward = _event(2, 100)

    segmenter.observe(first, _state(first))
    boundary = segmenter.observe(backward, _state(backward))

    assert boundary is None
    assert segmenter.current_session_id == "session:evt-1"


def test_flush_returns_final_segment() -> None:
    segmenter = SessionSegmenter()
    first = _event(1, 100)
    second = _event(2, 200)
    segmenter.observe(first, _state(first))
    segmenter.observe(second, _state(second))

    final = segmenter.flush()

    assert final is not None
    assert final.session_id == "session:evt-1"
    assert final.start_event_id == "evt-1"
    assert final.end_event_id == "evt-2"
    assert final.reason == "end_of_stream"

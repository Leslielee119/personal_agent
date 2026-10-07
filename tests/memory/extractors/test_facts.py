from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventActor,
    EventOrigin,
    EventProvenance,
)
from personal_predictive_ai.memory.extractors.facts import extract_foreground_application_facts
from personal_predictive_ai.memory.models import ConsolidationConfigV1, MemoryKind
from personal_predictive_ai.state.models import StateSnapshot


def _event(
    event_id: str,
    seq: int,
    app_name: str | None,
    *,
    timestamp_ns: int | None = None,
    event_type: str = "window.foreground.changed",
) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        timestamp_ns=seq if timestamp_ns is None else timestamp_ns,
        monotonic_seq=seq,
        source="unit",
        modality="window",
        origin=EventOrigin.EXOGENOUS,
        event_type=event_type,
        actor=EventActor.SYSTEM,
        provenance=EventProvenance.SYSTEM,
        app={"name": app_name} if app_name is not None else None,
        window={"title": "PRIVATE WINDOW TITLE"},
        payload={"secure_text": "NEVER_COPY_ME"},
        raw_ref="raw/never-copy.png",
    )


def _snapshot(event: CanonicalEvent, session_id: str) -> StateSnapshot:
    return StateSnapshot(
        state_id=f"state-{event.monotonic_seq}",
        source_event_id=event.event_id,
        timestamp_ns=event.timestamp_ns,
        monotonic_seq=event.monotonic_seq,
        session_id=session_id,
    )


def test_extracts_foreground_application_candidates_with_counts_and_sessions() -> None:
    events = [
        _event("e1", 1, "Code.exe"),
        _event("e2", 2, "Chrome.exe"),
        _event("e3", 3, "Code.exe"),
        _event("e4", 4, "Code.exe"),
        _event("e5", 5, "Chrome.exe"),
    ]
    snapshots = [
        _snapshot(events[0], "s1"),
        _snapshot(events[1], "s1"),
        _snapshot(events[2], "s2"),
        _snapshot(events[3], "s2"),
        _snapshot(events[4], "s2"),
    ]

    candidates = extract_foreground_application_facts(
        events,
        snapshots,
        config=ConsolidationConfigV1(),
    )

    assert [item.value for item in candidates] == ["Code.exe", "Chrome.exe"]
    code, chrome = candidates
    assert code.kind is MemoryKind.FACT
    assert code.key == "foreground_application.primary"
    assert code.scope.scope_type == "global"
    assert code.support_count == 3
    assert code.contradiction_count == 2
    assert code.session_ids == ["s1", "s2"]
    assert code.evidence_ids == ["e1", "e3", "e4"]
    assert code.provenance_summary.system_support == 3
    assert code.created_seq == 1
    assert code.last_supported_seq == 4
    assert code.confidence == 0.6
    assert chrome.support_count == 2
    assert chrome.contradiction_count == 3


def test_filters_missing_app_and_unrelated_events_and_breaks_ties_deterministically() -> None:
    first = _event("e1", 1, "Beta.exe")
    second = _event("e2", 2, "Alpha.exe")
    missing = _event("e3", 3, None)
    unrelated = _event("e4", 4, "Ignored.exe", event_type="process.started")
    snapshots = [
        _snapshot(first, "s1"),
        _snapshot(second, "s1"),
        _snapshot(missing, "s1"),
        _snapshot(unrelated, "s1"),
    ]

    candidates = extract_foreground_application_facts(
        [first, second, missing, unrelated],
        snapshots,
        config=ConsolidationConfigV1(),
    )
    assert [item.value for item in candidates] == ["Beta.exe", "Alpha.exe"]


def test_candidate_identity_and_source_order_ignore_wall_clock_regression() -> None:
    e1 = _event("e1", 1, "Code.exe", timestamp_ns=200)
    e2 = _event("e2", 2, "Code.exe", timestamp_ns=100)
    snapshots = [_snapshot(e1, "s1"), _snapshot(e2, "s2")]

    first = extract_foreground_application_facts(
        [e1, e2],
        snapshots,
        config=ConsolidationConfigV1(),
    )[0]
    second = extract_foreground_application_facts(
        [e2, e1],
        list(reversed(snapshots)),
        config=ConsolidationConfigV1(),
    )[0]

    assert first.memory_id == second.memory_id
    assert first.evidence_ids == ["e1", "e2"]
    assert second.evidence_ids == ["e1", "e2"]
    assert first.created_seq == second.created_seq == 1
    assert first.observed_from == second.observed_from == 200


def test_extractor_does_not_copy_window_payload_or_raw_reference() -> None:
    event = _event("e1", 1, "Code.exe")
    candidate = extract_foreground_application_facts(
        [event],
        [_snapshot(event, "s1")],
        config=ConsolidationConfigV1(),
    )[0]
    encoded = candidate.model_dump_json()
    assert "PRIVATE WINDOW TITLE" not in encoded
    assert "NEVER_COPY_ME" not in encoded
    assert "raw/never-copy.png" not in encoded

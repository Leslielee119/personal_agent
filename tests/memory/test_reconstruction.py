from __future__ import annotations

from pathlib import Path

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventActor,
    EventOrigin,
    EventProvenance,
)
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.state.sessions import SessionSegment
from personal_predictive_ai.storage.derived_store import DerivedStore
from personal_predictive_ai.storage.sqlite_store import EventStore


def _load_api():
    from personal_predictive_ai.memory.reconstruction import build_b2_snapshot

    return build_b2_snapshot


def _event(seq: int, *, app: str | None = None) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=f"evt-{seq}",
        timestamp_ns=1_000 + seq,
        monotonic_seq=seq,
        source="c-prefix-test",
        modality="window" if app else "keyboard",
        origin=EventOrigin.EXOGENOUS if app else EventOrigin.ENDOGENOUS,
        event_type="window.foreground.changed" if app else "keyboard.key",
        actor=EventActor.SYSTEM if app else EventActor.HUMAN,
        provenance=EventProvenance.SYSTEM if app else EventProvenance.HUMAN_PHYSICAL,
        injected=None if app else False,
        app={"name": app} if app else None,
    )


def _action(seq: int, session_id: str, operation: str) -> tuple[NormalizedAction, StateSnapshot]:
    action = NormalizedAction(
        action_id=f"act-{seq}",
        source_event_id=f"evt-{seq}",
        timestamp_ns=1_000 + seq,
        monotonic_seq=seq,
        actor=EventActor.HUMAN,
        provenance=EventProvenance.HUMAN_PHYSICAL,
        application="Code.exe",
        operation=operation,
    )
    snapshot = StateSnapshot(
        state_id=f"state-{seq}",
        source_event_id=action.source_event_id,
        timestamp_ns=action.timestamp_ns,
        monotonic_seq=seq,
        session_id=session_id,
    )
    return action, snapshot


def _session(session_id: str, start: int, end: int) -> SessionSegment:
    return SessionSegment(
        session_id=session_id,
        start_event_id=f"start-{session_id}",
        start_ns=start,
        end_event_id=f"end-{session_id}",
        end_ns=end,
        reason="fixture",
    )


def _seed(db: Path) -> None:
    events = [_event(1, app="Code.exe"), _event(2, app="Code.exe"), _event(3, app="Code.exe")]
    actions: list[NormalizedAction] = []
    snapshots: list[StateSnapshot] = [
        StateSnapshot(
            state_id=f"state-f-{seq}",
            source_event_id=f"evt-{seq}",
            timestamp_ns=1_000 + seq,
            monotonic_seq=seq,
            session_id="s1",
        )
        for seq in (1, 2, 3)
    ]
    sessions = [_session("s1", 0, 9_999), _session("s2", 10_000, 20_000)]
    for seq, session_id, operation in (
        (10, "s1", "save"),
        (11, "s1", "run"),
        (12, "s1", "save"),
        (13, "s1", "run"),
        (14, "s2", "save"),
        (15, "s2", "run"),
    ):
        action, snapshot = _action(seq, session_id, operation)
        actions.append(action)
        snapshots.append(snapshot)
        events.append(_event(seq))

    event_store = EventStore(db)
    event_store.append_many(events)
    event_store.close()
    derived = DerivedStore(db)
    derived.replace_run("b1", 15, snapshots, actions, sessions, [])
    derived.close()


def test_prefix_snapshot_never_uses_evidence_beyond_requested_high_water(tmp_path: Path) -> None:
    build_b2_snapshot = _load_api()
    db = tmp_path / "events.db"
    _seed(db)

    prefix = build_b2_snapshot(db, source_b1_run_id="b1", source_high_water=12)
    full = build_b2_snapshot(db, source_b1_run_id="b1", source_high_water=15)

    assert prefix.source_high_water == 12
    assert all(record.last_supported_seq <= 12 for record in prefix.records)
    assert all(record.created_seq <= 12 for record in prefix.records)
    assert prefix.source_event_count < full.source_event_count
    assert {link.evidence_id for link in prefix.evidence_links}.isdisjoint(
        {"evt-13", "evt-14", "evt-15"}
    )


def test_snapshot_rejects_high_water_beyond_source_b1_run(tmp_path: Path) -> None:
    build_b2_snapshot = _load_api()
    db = tmp_path / "events.db"
    _seed(db)

    try:
        build_b2_snapshot(db, source_b1_run_id="b1", source_high_water=16)
    except ValueError as exc:
        assert "source_high_water" in str(exc)
    else:
        raise AssertionError("snapshot must reject a cutoff beyond the source B1 run")

import sqlite3
from pathlib import Path

import pytest

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
from personal_predictive_ai.transitions.models import Transition


def _snapshot(seq: int) -> StateSnapshot:
    return StateSnapshot(
        state_id=f"state-{seq}",
        source_event_id=f"evt-{seq}",
        timestamp_ns=seq,
        monotonic_seq=seq,
        session_id="session-1",
    )


def _action(seq: int) -> NormalizedAction:
    return NormalizedAction(
        action_id=f"action-{seq}",
        source_event_id=f"evt-{seq}",
        timestamp_ns=seq,
        monotonic_seq=seq,
        actor=EventActor.HUMAN,
        provenance=EventProvenance.HUMAN_PHYSICAL,
        operation="key_input",
    )


def _session() -> SessionSegment:
    return SessionSegment(
        session_id="session-1",
        start_event_id="evt-1",
        start_ns=1,
        end_event_id="evt-2",
        end_ns=2,
        reason="end_of_stream",
    )


def _transition() -> Transition:
    return Transition(
        transition_id="transition-1",
        session_id="session-1",
        pre_state_id="state-1",
        action_id="action-2",
        exogenous_event_ids=["evt-3"],
        post_state_id="state-2",
        actor=EventActor.HUMAN,
        provenance=EventProvenance.HUMAN_PHYSICAL,
        start_seq=2,
        end_seq=3,
    )


def test_round_trip_and_restart_persistence(tmp_path: Path) -> None:
    db_path = tmp_path / "events.db"
    store = DerivedStore(db_path)
    snapshots = [_snapshot(1), _snapshot(2)]
    actions = [_action(2)]
    sessions = [_session()]
    transitions = [_transition()]

    store.replace_run("run-1", 9, snapshots, actions, sessions, transitions)
    assert list(store.iter_snapshots("run-1")) == snapshots
    assert list(store.iter_actions("run-1")) == actions
    assert list(store.iter_sessions("run-1")) == sessions
    assert list(store.iter_transitions("run-1")) == transitions
    assert store.get_run("run-1").source_high_water == 9
    store.close()

    reopened = DerivedStore(db_path)
    assert list(reopened.iter_snapshots("run-1")) == snapshots
    assert list(reopened.iter_transitions("run-1")) == transitions
    assert reopened.integrity_check() == "ok"
    reopened.close()


def test_replace_run_is_idempotent_for_same_run_and_high_water(tmp_path: Path) -> None:
    store = DerivedStore(tmp_path / "events.db")
    args = ("run-1", 9, [_snapshot(1)], [_action(2)], [_session()], [_transition()])

    store.replace_run(*args)
    store.replace_run(*args)

    assert len(list(store.iter_snapshots("run-1"))) == 1
    assert len(list(store.iter_actions("run-1"))) == 1
    assert len(list(store.iter_sessions("run-1"))) == 1
    assert len(list(store.iter_transitions("run-1"))) == 1
    store.close()


def test_failed_replace_rolls_back_to_previous_complete_run(tmp_path: Path) -> None:
    store = DerivedStore(tmp_path / "events.db")
    store.replace_run("run-1", 5, [_snapshot(1)], [], [], [])

    with pytest.raises(sqlite3.IntegrityError):
        store.replace_run("run-1", 6, [_snapshot(2), _snapshot(2)], [], [], [])

    assert store.get_run("run-1").source_high_water == 5
    assert list(store.iter_snapshots("run-1")) == [_snapshot(1)]
    store.close()


def test_derived_reconstruction_never_mutates_canonical_evidence(tmp_path: Path) -> None:
    db_path = tmp_path / "events.db"
    canonical = EventStore(db_path)
    event = CanonicalEvent(
        event_id="evt-1",
        timestamp_ns=1,
        monotonic_seq=1,
        source="unit",
        modality="screen",
        origin=EventOrigin.EXOGENOUS,
        event_type="screen.snapshot",
        actor=EventActor.SYSTEM,
        provenance=EventProvenance.SYSTEM,
        raw_ref="raw/already-expired.png",
    )
    canonical.append(event)
    before = canonical.get("evt-1")

    derived = DerivedStore(db_path)
    derived.replace_run("run-1", 1, [_snapshot(1)], [], [], [])
    derived.delete_run("run-1")

    assert canonical.count() == 1
    assert canonical.get("evt-1") == before
    assert derived.get_run("run-1") is None
    derived.close()
    canonical.close()

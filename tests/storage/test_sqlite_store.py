import sqlite3
from pathlib import Path

import pytest

from personal_predictive_ai.events.models import CanonicalEvent, EventOrigin
from personal_predictive_ai.storage.sqlite_store import EventStore


def _event(event_id: str, timestamp_ns: int, monotonic_seq: int) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        timestamp_ns=timestamp_ns,
        monotonic_seq=monotonic_seq,
        source="unit",
        modality="system",
        origin=EventOrigin.EXOGENOUS,
        event_type="system.test",
        app={"name": "test-app"},
        payload={"n": monotonic_seq},
    )


def test_append_read_round_trip_and_restart_persistence(tmp_path: Path) -> None:
    db_path = tmp_path / "events.db"
    event = _event("evt-1", 100, 1)

    store = EventStore(db_path)
    store.append(event)
    assert store.get("evt-1") == event
    store.close()

    reopened = EventStore(db_path)
    assert reopened.get("evt-1") == event
    reopened.close()


def test_iteration_orders_by_timestamp_then_monotonic_sequence(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.db")
    store.append(_event("evt-a", 200, 1))
    store.append(_event("evt-b", 100, 2))
    store.append(_event("evt-c", 100, 3))

    ids = [event.event_id for event in store.iter_events()]

    assert ids == ["evt-b", "evt-c", "evt-a"]
    store.close()


def test_batch_insert_rolls_back_on_constraint_failure(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.db")
    first = _event("duplicate", 100, 1)
    duplicate = _event("duplicate", 101, 2)

    with pytest.raises(sqlite3.IntegrityError):
        store.append_many([first, duplicate])

    assert list(store.iter_events()) == []
    store.close()


def test_integrity_check_reports_ok(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.db")
    store.append(_event("evt-1", 100, 1))

    assert store.integrity_check() == "ok"
    store.close()

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


def test_expire_structured_short_removes_only_expired_short_rows(tmp_path: Path) -> None:
    from personal_predictive_ai.events.models import RetentionClass

    store = EventStore(tmp_path / "events.db")
    old_short = _event("old-short", 1_000_000_000, 1).model_copy(
        update={"retention_class": RetentionClass.STRUCTURED_SHORT}
    )
    fresh_short = _event("fresh-short", 9_000_000_000, 2).model_copy(
        update={"retention_class": RetentionClass.STRUCTURED_SHORT}
    )
    old_long = _event("old-long", 1_000_000_000, 3).model_copy(
        update={"retention_class": RetentionClass.STRUCTURED_LONG}
    )
    store.append_many([old_short, fresh_short, old_long])

    expired = store.expire_structured_short(
        now_ns=10_000_000_000,
        ttl_seconds=5,
    )

    assert expired == 1
    assert store.get("old-short") is None
    assert store.get("fresh-short") is not None
    assert store.get("old-long") is not None
    store.close()


def test_sequence_high_water_survives_short_row_expiry_and_restart(tmp_path: Path) -> None:
    from personal_predictive_ai.events.models import RetentionClass

    db_path = tmp_path / "events.db"
    store = EventStore(db_path)
    event = _event("latest-short", 1_000_000_000, 9).model_copy(
        update={"retention_class": RetentionClass.STRUCTURED_SHORT}
    )
    store.append(event)

    assert store.sequence_high_water() == 9
    assert store.expire_structured_short(now_ns=10_000_000_000, ttl_seconds=5) == 1
    assert store.count() == 0
    assert store.sequence_high_water() == 9
    store.close()

    reopened = EventStore(db_path)
    assert reopened.sequence_high_water() == 9
    reopened.close()

from pathlib import Path

from personal_predictive_ai.diagnostics.replay import iter_replay_lines
from personal_predictive_ai.events.models import CanonicalEvent, EventOrigin, RetentionClass
from personal_predictive_ai.storage.raw_ring import RawRing
from personal_predictive_ai.storage.sqlite_store import EventStore


def _event(
    event_id: str,
    timestamp_ns: int,
    monotonic_seq: int,
    *,
    origin: EventOrigin,
    payload: dict,
    raw_ref: str | None = None,
    retention_class: RetentionClass = RetentionClass.STRUCTURED_LONG,
) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        timestamp_ns=timestamp_ns,
        monotonic_seq=monotonic_seq,
        source="fixture",
        modality="system",
        origin=origin,
        event_type=f"fixture.{event_id}",
        app={"name": "Editor"},
        payload=payload,
        raw_ref=raw_ref,
        retention_class=retention_class,
    )


def test_replay_is_chronological_and_defensively_redacts_sensitive_fields(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.db")
    ring = RawRing(tmp_path / "raw", ttl_seconds=1, max_bytes=1024)
    raw_ref = ring.put(b"secret-image-bytes", ".bin")
    created_ns = int(raw_ref.split("-", 1)[0])
    ring.expire(now_ns=created_ns + 2_000_000_000)

    store.append(
        _event(
            "late",
            200,
            2,
            origin=EventOrigin.ENDOGENOUS,
            payload={"password": "replay-secret", "action": "save"},
            raw_ref=raw_ref,
        )
    )
    store.append(
        _event(
            "early",
            100,
            1,
            origin=EventOrigin.EXOGENOUS,
            payload={"status": "finished"},
        )
    )

    lines = list(iter_replay_lines(store, raw_ring=ring))

    assert len(lines) == 2
    assert lines[0].startswith("100 | exogenous | Editor | fixture.early |")
    assert lines[1].startswith("200 | endogenous | Editor | fixture.late |")
    joined = "\n".join(lines)
    assert "replay-secret" not in joined
    assert "[REDACTED]" in joined
    assert "secret-image-bytes" not in joined
    assert "raw=expired" in joined
    store.close()


def test_replay_omits_never_store_rows_even_if_database_was_manually_polluted(
    tmp_path: Path,
) -> None:
    store = EventStore(tmp_path / "events.db")
    store.append(
        _event(
            "forbidden",
            1,
            1,
            origin=EventOrigin.ENDOGENOUS,
            payload={"text": "must-not-appear"},
            retention_class=RetentionClass.NEVER_STORE,
        )
    )

    assert list(iter_replay_lines(store)) == []
    store.close()

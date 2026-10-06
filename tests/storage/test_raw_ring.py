from pathlib import Path

from personal_predictive_ai.events.models import CanonicalEvent, EventOrigin
from personal_predictive_ai.storage.raw_ring import RawRing
from personal_predictive_ai.storage.sqlite_store import EventStore


class Clock:
    def __init__(self, values: list[int]) -> None:
        self._values = iter(values)

    def __call__(self) -> int:
        return next(self._values)


def test_raw_artifact_expires_by_ttl_and_resolve_returns_none(tmp_path: Path) -> None:
    clock = Clock([1_000_000_000])
    ring = RawRing(tmp_path / "raw", ttl_seconds=10, max_bytes=100, clock_ns=clock)
    ref = ring.put(b"secret-ish pixels", ".bin")

    assert ring.resolve(ref) is not None
    assert ring.expire(now_ns=12_000_000_000) == 1
    assert ring.resolve(ref) is None


def test_raw_ring_evicts_oldest_artifacts_to_enforce_byte_bound(tmp_path: Path) -> None:
    clock = Clock([1, 2])
    ring = RawRing(tmp_path / "raw", ttl_seconds=60, max_bytes=5, clock_ns=clock)

    first = ring.put(b"1234", ".bin")
    second = ring.put(b"5678", ".bin")

    assert ring.resolve(first) is None
    assert ring.resolve(second) is not None
    assert ring.total_bytes() <= 5


def test_structured_event_survives_raw_artifact_expiry(tmp_path: Path) -> None:
    clock = Clock([1_000_000_000])
    ring = RawRing(tmp_path / "raw", ttl_seconds=1, max_bytes=100, clock_ns=clock)
    ref = ring.put(b"frame", ".png")
    event = CanonicalEvent(
        event_id="evt-raw",
        timestamp_ns=1,
        monotonic_seq=1,
        source="unit",
        modality="screen",
        origin=EventOrigin.ENDOGENOUS,
        event_type="screen.frame",
        raw_ref=ref,
    )
    store = EventStore(tmp_path / "events.db")
    store.append(event)

    ring.expire(now_ns=3_000_000_000)
    persisted = store.get("evt-raw")

    assert persisted is not None
    assert persisted.raw_ref == ref
    assert ring.resolve(ref) is None
    store.close()


def test_invalid_or_missing_reference_never_escapes_ring_root(tmp_path: Path) -> None:
    ring = RawRing(tmp_path / "raw", ttl_seconds=60, max_bytes=100)

    assert ring.resolve("../outside.txt") is None
    assert ring.resolve("missing.bin") is None

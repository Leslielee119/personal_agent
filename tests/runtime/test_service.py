import time
from pathlib import Path

from personal_predictive_ai.collector.base import CollectorHealth
from personal_predictive_ai.config import Settings
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import EventOrigin
from personal_predictive_ai.runtime.service import CaptureService


class FakeCollector:
    def __init__(self, *, name: str, event=None, fail_start: bool = False) -> None:
        self.name = name
        self.event = event
        self.fail_start = fail_start
        self.running = False
        self.stop_calls = 0

    def start(self, publish) -> None:
        if self.fail_start:
            raise RuntimeError(f"{self.name} failed")
        self.running = True
        if self.event is not None:
            publish(self.event)

    def stop(self) -> None:
        self.running = False
        self.stop_calls += 1

    def health(self) -> CollectorHealth:
        return CollectorHealth(available=not self.fail_start, running=self.running)


def _settings(tmp_path: Path, *, offline: bool = False) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        raw_ttl_seconds=1,
        structured_retention_days=30,
        offline_mode=offline,
    )


def test_service_starts_stops_and_persists_collector_events(tmp_path: Path) -> None:
    factory = EventFactory()
    event = factory.next(
        timestamp_ns=100,
        source="fake",
        modality="system",
        origin=EventOrigin.EXOGENOUS,
        event_type="system.ready",
    )
    collector = FakeCollector(name="healthy", event=event)
    service = CaptureService(
        settings=_settings(tmp_path),
        collectors=[collector],
        event_factory=factory,
    )

    service.start()
    status = service.status()

    assert status.running is True
    assert status.event_count == 1
    assert service.event_store.get(event.event_id) == event
    service.stop()
    assert collector.stop_calls == 1
    assert service.status().running is False


def test_provider_start_failure_is_isolated_from_healthy_provider(tmp_path: Path) -> None:
    factory = EventFactory()
    event = factory.next(
        timestamp_ns=100,
        source="fake",
        modality="system",
        origin=EventOrigin.EXOGENOUS,
        event_type="system.healthy",
    )
    broken = FakeCollector(name="broken", fail_start=True)
    healthy = FakeCollector(name="healthy", event=event)
    service = CaptureService(
        settings=_settings(tmp_path),
        collectors=[broken, healthy],
        event_factory=factory,
    )

    service.start()
    status = service.status()

    assert status.running is True
    assert "broken" in status.provider_errors
    assert status.event_count == 1
    assert healthy.running is True
    service.stop()
    assert broken.stop_calls == 0
    assert healthy.stop_calls == 1


def test_service_expires_raw_artifacts_without_invalidating_structured_rows(
    tmp_path: Path,
) -> None:
    factory = EventFactory()
    service = CaptureService(
        settings=_settings(tmp_path),
        collectors=[],
        event_factory=factory,
        raw_max_bytes=1024,
    )
    service.start()
    ref = service.raw_ring.put(b"frame", ".bin")
    event = factory.next(
        timestamp_ns=100,
        source="fake",
        modality="screen",
        origin=EventOrigin.ENDOGENOUS,
        event_type="screen.frame",
        raw_ref=ref,
    )
    service.publish(event)

    expired = service.expire_raw(now_ns=time.time_ns() + 2_000_000_000)

    assert expired == 1
    assert service.raw_ring.resolve(ref) is None
    assert service.event_store.get(event.event_id) is not None
    service.stop()


def test_shared_factory_produces_deterministic_unique_sequences_across_collectors(
    tmp_path: Path,
) -> None:
    factory = EventFactory()
    first = factory.next(
        timestamp_ns=100,
        source="first",
        modality="system",
        origin=EventOrigin.EXOGENOUS,
        event_type="system.first",
    )
    second = factory.next(
        timestamp_ns=100,
        source="second",
        modality="system",
        origin=EventOrigin.EXOGENOUS,
        event_type="system.second",
    )
    service = CaptureService(
        settings=_settings(tmp_path),
        collectors=[
            FakeCollector(name="first", event=first),
            FakeCollector(name="second", event=second),
        ],
        event_factory=factory,
    )

    service.start()
    stored = list(service.event_store.iter_events())

    assert [event.monotonic_seq for event in stored] == [1, 2]
    assert [event.event_type for event in stored] == ["system.first", "system.second"]
    service.stop()


def test_collector_factory_runs_after_offline_guard_is_installed(tmp_path: Path) -> None:
    import socket

    from personal_predictive_ai.runtime.offline_guard import OfflineNetworkError

    observed = {"guard_active": False}

    def collector_factory(_factory: EventFactory):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            try:
                sock.connect(("8.8.8.8", 53))
            except OfflineNetworkError:
                observed["guard_active"] = True
        finally:
            sock.close()
        return []

    service = CaptureService(
        settings=_settings(tmp_path, offline=True),
        collectors=[],
        event_factory=EventFactory(),
        collector_factory=collector_factory,
    )

    service.start()
    try:
        assert observed["guard_active"] is True
    finally:
        service.stop()

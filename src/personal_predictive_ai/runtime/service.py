from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from personal_predictive_ai.collector.base import Collector, CollectorHealth
from personal_predictive_ai.config import Settings
from personal_predictive_ai.events.bus import EventBus, PublishResult
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import CanonicalEvent
from personal_predictive_ai.privacy.policy import PrivacyPolicy
from personal_predictive_ai.privacy.sanitizer import sanitize_event
from personal_predictive_ai.runtime.offline_guard import OfflineNetworkGuard
from personal_predictive_ai.storage.raw_ring import RawRing
from personal_predictive_ai.storage.sqlite_store import EventStore

CollectorFactory = Callable[[EventFactory], Iterable[Collector]]


@dataclass(frozen=True, slots=True)
class ServiceStatus:
    running: bool
    event_count: int
    raw_bytes: int
    bus_errors: int
    provider_errors: dict[str, str]
    collector_health: dict[str, CollectorHealth]


class CaptureService:
    def __init__(
        self,
        *,
        settings: Settings,
        collectors: Iterable[Collector],
        event_factory: EventFactory | None = None,
        collector_factory: CollectorFactory | None = None,
        privacy_policy: PrivacyPolicy | None = None,
        raw_max_bytes: int = 256 * 1024 * 1024,
    ) -> None:
        self.settings = settings
        self.event_factory = event_factory or EventFactory()
        self._static_collectors = list(collectors)
        self._collectors = list(self._static_collectors)
        self._collector_factory = collector_factory
        self._privacy_policy = privacy_policy or PrivacyPolicy()
        data_dir = Path(settings.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        self.event_store = EventStore(data_dir / "events.db")
        self.raw_ring = RawRing(
            data_dir / "raw",
            ttl_seconds=settings.raw_ttl_seconds,
            max_bytes=raw_max_bytes,
        )
        self._bus = EventBus(
            store=self.event_store,
            sanitizer=lambda event: sanitize_event(event, self._privacy_policy),
        )
        self._offline_guard = OfflineNetworkGuard() if settings.offline_mode else None
        self._running = False
        self._closed = False
        self._started_collectors: list[Collector] = []
        self._provider_errors: dict[str, str] = {}

    def start(self) -> None:
        if self._closed:
            raise RuntimeError("capture service is closed")
        if self._running:
            return
        if self._offline_guard is not None:
            self._offline_guard.install()

        self._provider_errors = {}
        self._started_collectors = []
        self._collectors = list(self._static_collectors)
        if self._collector_factory is not None:
            try:
                self._collectors.extend(self._collector_factory(self.event_factory))
            except Exception as exc:
                self._provider_errors["collector_factory"] = f"{type(exc).__name__}: {exc}"

        for collector in self._collectors:
            name = self._collector_name(collector)
            try:
                collector.start(self.publish)
            except Exception as exc:
                self._provider_errors[name] = f"{type(exc).__name__}: {exc}"
                continue
            self._started_collectors.append(collector)
        self._running = True

    def stop(self) -> None:
        if not self._running:
            if self._offline_guard is not None:
                self._offline_guard.remove()
            return
        for collector in reversed(self._started_collectors):
            name = self._collector_name(collector)
            try:
                collector.stop()
            except Exception as exc:
                self._provider_errors[f"{name}:stop"] = f"{type(exc).__name__}: {exc}"
        self._started_collectors = []
        self._running = False
        if self._offline_guard is not None:
            self._offline_guard.remove()

    def close(self) -> None:
        if self._closed:
            return
        self.stop()
        self.event_store.close()
        self._closed = True

    def publish(self, event: CanonicalEvent) -> PublishResult:
        if self._closed:
            return PublishResult(accepted=False, rejected_reason="service_closed")
        return self._bus.publish(event)

    def expire_raw(self, *, now_ns: int | None = None) -> int:
        return self.raw_ring.expire(now_ns=now_ns)

    def status(self) -> ServiceStatus:
        event_count = self.event_store.count() if not self._closed else 0
        raw_bytes = self.raw_ring.total_bytes()
        health: dict[str, CollectorHealth] = {}
        for collector in self._collectors:
            name = self._collector_name(collector)
            try:
                health[name] = collector.health()
            except Exception as exc:
                self._provider_errors[f"{name}:health"] = f"{type(exc).__name__}: {exc}"
        return ServiceStatus(
            running=self._running,
            event_count=event_count,
            raw_bytes=raw_bytes,
            bus_errors=self._bus.error_count,
            provider_errors=dict(self._provider_errors),
            collector_health=health,
        )

    def __enter__(self) -> "CaptureService":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    @staticmethod
    def _collector_name(collector: Collector) -> str:
        value = getattr(collector, "name", None)
        if isinstance(value, str) and value:
            return value
        return type(collector).__name__

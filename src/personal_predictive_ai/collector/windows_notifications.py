from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol

from personal_predictive_ai.collector.base import CollectorHealth, PublishCallback
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import (
    EventOrigin,
    PrivacyTier,
    RetentionClass,
)


@dataclass(frozen=True, slots=True)
class NotificationRecord:
    app_name: str | None
    title: str | None
    body: str | None
    notification_id: str | None
    timestamp_ns: int


class NotificationBackend(Protocol):
    available: bool
    detail: str

    def drain(self) -> list[NotificationRecord]: ...


class _UnavailableBackend:
    available = False
    detail = "Windows notification backend not configured"

    def drain(self) -> list[NotificationRecord]:
        return []


class WindowsNotificationCollector:
    def __init__(
        self,
        *,
        factory: EventFactory,
        backend: NotificationBackend | None = None,
        retain_body: bool = False,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._factory = factory
        self._backend = backend or _UnavailableBackend()
        self._retain_body = retain_body
        self._poll_interval_seconds = poll_interval_seconds
        self._publish: PublishCallback | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._events_published = 0

    def set_publish(self, publish: PublishCallback) -> None:
        with self._lock:
            self._publish = publish

    def start(self, publish: PublishCallback) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._publish = publish
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="ppa-notifications",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
            self._stop_event.set()
        if thread is not None:
            thread.join(timeout=max(1.0, self._poll_interval_seconds * 2))

    def health(self) -> CollectorHealth:
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
            return CollectorHealth(
                available=bool(self._backend.available),
                running=running,
                detail=str(self._backend.detail),
                events_published=self._events_published,
            )

    def poll_once(self) -> int:
        if not self._backend.available:
            return 0
        try:
            records = self._backend.drain()
        except Exception:
            return 0
        emitted = 0
        for record in records:
            emitted += self._emit(record)
        return emitted

    def _emit(self, record: NotificationRecord) -> int:
        publish = self._publish
        if publish is None:
            return 0
        payload: dict[str, object] = {}
        if record.notification_id is not None:
            payload["notification_id"] = record.notification_id
        if record.title is not None:
            payload["title"] = record.title
        privacy_tier = PrivacyTier.STANDARD
        retention_class = RetentionClass.STRUCTURED_LONG
        if self._retain_body and record.body is not None:
            payload["body"] = record.body
            privacy_tier = PrivacyTier.SENSITIVE
            retention_class = RetentionClass.STRUCTURED_SHORT

        event = self._factory.next(
            timestamp_ns=record.timestamp_ns,
            source="windows_notification",
            modality="notification",
            origin=EventOrigin.EXOGENOUS,
            event_type="notification.received",
            app={"name": record.app_name} if record.app_name else None,
            payload=payload,
            privacy_tier=privacy_tier,
            retention_class=retention_class,
        )
        publish(event)
        with self._lock:
            self._events_published += 1
        return 1

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.poll_once()
            self._stop_event.wait(self._poll_interval_seconds)

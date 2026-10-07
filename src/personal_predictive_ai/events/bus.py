from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from personal_predictive_ai.events.models import CanonicalEvent
from personal_predictive_ai.storage.sqlite_store import EventStore

EventHandler = Callable[[CanonicalEvent], None]
Sanitizer = Callable[[CanonicalEvent], CanonicalEvent | None]


@dataclass(frozen=True, slots=True)
class PublishResult:
    accepted: bool
    dropped: bool = False
    rejected_reason: str | None = None
    subscriber_errors: tuple[str, ...] = ()


class EventBus:
    def __init__(
        self,
        *,
        store: EventStore,
        sanitizer: Sanitizer,
    ) -> None:
        self._store = store
        self._sanitizer = sanitizer
        self._subscribers: list[EventHandler] = []
        self._lock = threading.RLock()
        self._error_count = 0

    @property
    def error_count(self) -> int:
        with self._lock:
            return self._error_count

    def subscribe(self, handler: EventHandler) -> None:
        with self._lock:
            self._subscribers.append(handler)

    def publish(self, event: CanonicalEvent) -> PublishResult:
        if not isinstance(event, CanonicalEvent):
            return PublishResult(accepted=False, rejected_reason="invalid_event_type")

        with self._lock:
            try:
                sanitized = self._sanitizer(event)
            except Exception as exc:  # boundary: sanitizer must not crash providers
                self._error_count += 1
                return PublishResult(
                    accepted=False,
                    rejected_reason=f"sanitizer_error:{type(exc).__name__}",
                )

            if sanitized is None:
                return PublishResult(accepted=False, dropped=True)

            try:
                self._store.append(sanitized)
            except Exception as exc:  # storage rejection preserves prior commits
                self._error_count += 1
                return PublishResult(
                    accepted=False,
                    rejected_reason=f"storage_error:{type(exc).__name__}",
                )

            errors: list[str] = []
            for handler in tuple(self._subscribers):
                try:
                    handler(sanitized)
                except Exception as exc:  # subscribers are observational side effects
                    self._error_count += 1
                    errors.append(f"{type(exc).__name__}:{exc}")

            return PublishResult(
                accepted=True,
                subscriber_errors=tuple(errors),
            )

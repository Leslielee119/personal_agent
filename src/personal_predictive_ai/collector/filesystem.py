from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from personal_predictive_ai.collector.base import CollectorHealth, PublishCallback
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import (
    EventActor,
    EventOrigin,
    EventProvenance,
)

ClockNs = Callable[[], int]


class FilesystemCollector:
    def __init__(
        self,
        *,
        factory: EventFactory,
        roots: Iterable[str | Path],
        excluded_paths: Iterable[str | Path] = (),
        clock_ns: ClockNs = time.time_ns,
        debounce_ms: int = 100,
    ) -> None:
        self._factory = factory
        self._roots = tuple(Path(path).resolve() for path in roots)
        self._excluded = tuple(Path(path).resolve() for path in excluded_paths)
        self._clock_ns = clock_ns
        self._debounce_ns = max(0, debounce_ms) * 1_000_000
        self._publish: PublishCallback | None = None
        self._observer: Observer | None = None
        self._last_seen: dict[tuple[str, str, str | None], int] = {}
        self._lock = threading.RLock()
        self._events_published = 0
        self._available = True
        self._detail = ""

    def set_publish(self, publish: PublishCallback) -> None:
        with self._lock:
            self._publish = publish

    def start(self, publish: PublishCallback) -> None:
        with self._lock:
            if self._observer is not None:
                return
            self._publish = publish
            handler = _WatchdogHandler(self)
            observer = Observer()
            try:
                for root in self._roots:
                    root.mkdir(parents=True, exist_ok=True)
                    observer.schedule(handler, str(root), recursive=True)
                observer.start()
            except Exception as exc:
                self._available = False
                self._detail = f"filesystem watcher unavailable: {type(exc).__name__}: {exc}"
                observer.stop()
                raise
            self._observer = observer

    def stop(self) -> None:
        with self._lock:
            observer = self._observer
            self._observer = None
        if observer is not None:
            observer.stop()
            observer.join(timeout=3.0)

    def health(self) -> CollectorHealth:
        with self._lock:
            return CollectorHealth(
                available=self._available,
                running=self._observer is not None and self._observer.is_alive(),
                detail=self._detail,
                events_published=self._events_published,
            )

    def observe_change(
        self,
        kind: str,
        src_path: str | Path,
        dest_path: str | Path | None = None,
        *,
        is_directory: bool = False,
    ) -> bool:
        if kind not in {"created", "modified", "deleted", "moved"}:
            raise ValueError(f"unsupported filesystem event kind: {kind}")
        src = Path(src_path).resolve()
        dest = Path(dest_path).resolve() if dest_path is not None else None
        if not self._in_scope(src) or self._excluded_path(src):
            return False
        if dest is not None and self._excluded_path(dest):
            return False

        now_ns = self._clock_ns()
        key = (kind, str(src), str(dest) if dest is not None else None)
        with self._lock:
            previous_ns = self._last_seen.get(key)
            if previous_ns is not None and now_ns - previous_ns < self._debounce_ns:
                return False
            self._last_seen[key] = now_ns
            publish = self._publish
        if publish is None:
            return False

        payload: dict[str, object] = {"src_path": str(src), "is_directory": is_directory}
        if dest is not None:
            payload["dest_path"] = str(dest)
        event = self._factory.next(
            timestamp_ns=now_ns,
            source="watchdog",
            modality="filesystem",
            origin=EventOrigin.EXOGENOUS,
            actor=EventActor.SYSTEM,
            provenance=EventProvenance.SYSTEM,
            event_type=f"filesystem.{kind}",
            payload=payload,
        )
        publish(event)
        with self._lock:
            self._events_published += 1
        return True

    def _in_scope(self, path: Path) -> bool:
        return any(_is_relative_to(path, root) for root in self._roots)

    def _excluded_path(self, path: Path) -> bool:
        return any(_is_relative_to(path, root) for root in self._excluded)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


class _WatchdogHandler(FileSystemEventHandler):
    def __init__(self, collector: FilesystemCollector) -> None:
        super().__init__()
        self._collector = collector

    def on_created(self, event) -> None:
        self._collector.observe_change("created", event.src_path, is_directory=event.is_directory)

    def on_modified(self, event) -> None:
        self._collector.observe_change("modified", event.src_path, is_directory=event.is_directory)

    def on_deleted(self, event) -> None:
        self._collector.observe_change("deleted", event.src_path, is_directory=event.is_directory)

    def on_moved(self, event) -> None:
        self._collector.observe_change(
            "moved",
            event.src_path,
            event.dest_path,
            is_directory=event.is_directory,
        )

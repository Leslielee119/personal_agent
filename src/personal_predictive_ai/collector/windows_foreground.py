from __future__ import annotations

import ctypes
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import psutil

from personal_predictive_ai.collector.base import CollectorHealth, PublishCallback
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import EventOrigin


@dataclass(frozen=True, slots=True)
class WindowSample:
    handle: int
    title: str | None
    pid: int | None
    process_name: str | None


SnapshotProvider = Callable[[], WindowSample | None]
ClockNs = Callable[[], int]


def _windows_foreground_snapshot() -> WindowSample | None:
    if sys.platform != "win32":
        raise OSError("foreground window provider requires Windows")

    user32 = ctypes.windll.user32
    hwnd = int(user32.GetForegroundWindow() or 0)
    if hwnd == 0:
        return None

    title_length = int(user32.GetWindowTextLengthW(hwnd))
    title_buffer = ctypes.create_unicode_buffer(title_length + 1)
    user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
    title = title_buffer.value or None

    pid_value = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_value))
    pid = int(pid_value.value) if pid_value.value else None
    process_name = None
    if pid is not None:
        try:
            process_name = psutil.Process(pid).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            process_name = None

    return WindowSample(
        handle=hwnd,
        title=title,
        pid=pid,
        process_name=process_name,
    )


class ForegroundWindowCollector:
    def __init__(
        self,
        *,
        factory: EventFactory,
        snapshot_provider: SnapshotProvider = _windows_foreground_snapshot,
        clock_ns: ClockNs = time.time_ns,
        poll_interval_seconds: float = 0.25,
    ) -> None:
        self._factory = factory
        self._snapshot_provider = snapshot_provider
        self._clock_ns = clock_ns
        self._poll_interval_seconds = poll_interval_seconds
        self._publish: PublishCallback | None = None
        self._previous: WindowSample | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._available = True
        self._detail = ""
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
                name="ppa-foreground-window",
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
                available=self._available,
                running=running,
                detail=self._detail,
                events_published=self._events_published,
            )

    def poll_once(self) -> int:
        try:
            current = self._snapshot_provider()
        except Exception as exc:
            with self._lock:
                self._available = False
                self._detail = f"foreground snapshot failed: {type(exc).__name__}: {exc}"
            return 0

        if current is None:
            return 0
        previous = self._previous
        if previous == current:
            return 0
        self._previous = current

        publish = self._publish
        if publish is None:
            return 0
        payload = {}
        event_type = "window.foreground.current"
        if previous is not None:
            event_type = "window.foreground.changed"
            payload["previous_handle"] = previous.handle

        event = self._factory.next(
            timestamp_ns=self._clock_ns(),
            source="windows_foreground",
            modality="window",
            origin=EventOrigin.EXOGENOUS,
            event_type=event_type,
            app={"name": current.process_name} if current.process_name else None,
            process={
                key: value
                for key, value in {
                    "pid": current.pid,
                    "name": current.process_name,
                }.items()
                if value is not None
            }
            or None,
            window={
                key: value
                for key, value in {
                    "handle": current.handle,
                    "title": current.title,
                }.items()
                if value is not None
            },
            payload=payload,
        )
        publish(event)
        with self._lock:
            self._events_published += 1
            self._available = True
            self._detail = ""
        return 1

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.poll_once()
            self._stop_event.wait(self._poll_interval_seconds)

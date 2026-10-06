from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import psutil

from personal_predictive_ai.collector.base import CollectorHealth, PublishCallback
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import EventOrigin


@dataclass(frozen=True, slots=True)
class ProcessSample:
    pid: int
    create_time: float
    name: str | None = None

    @property
    def identity(self) -> tuple[int, float]:
        return self.pid, self.create_time


SnapshotProvider = Callable[[], Iterable[ProcessSample]]
ClockNs = Callable[[], int]


def _psutil_snapshot() -> Iterable[ProcessSample]:
    samples: list[ProcessSample] = []
    for proc in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            info = proc.info
            samples.append(
                ProcessSample(
                    pid=int(info["pid"]),
                    create_time=float(info["create_time"]),
                    name=str(info["name"]) if info.get("name") else None,
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, TypeError):
            continue
    return samples


class ProcessCollector:
    def __init__(
        self,
        *,
        factory: EventFactory,
        snapshot_provider: SnapshotProvider = _psutil_snapshot,
        clock_ns: ClockNs = time.time_ns,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._factory = factory
        self._snapshot_provider = snapshot_provider
        self._clock_ns = clock_ns
        self._poll_interval_seconds = poll_interval_seconds
        self._publish: PublishCallback | None = None
        self._previous: dict[tuple[int, float], ProcessSample] | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._events_published = 0
        self._available = True
        self._detail = ""

    def set_publish(self, publish: PublishCallback) -> None:
        with self._lock:
            self._publish = publish

    def start(self, publish: PublishCallback) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._publish = publish
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="ppa-process", daemon=True)
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
            current_samples = list(self._snapshot_provider())
        except Exception as exc:
            with self._lock:
                self._available = False
                self._detail = f"process snapshot failed: {type(exc).__name__}: {exc}"
            return 0

        current = {sample.identity: sample for sample in current_samples}
        previous = self._previous
        self._previous = current
        if previous is None:
            return 0

        started = sorted(current.keys() - previous.keys())
        exited = sorted(previous.keys() - current.keys())
        if not started and not exited:
            return 0

        timestamp_ns = self._clock_ns()
        emitted = 0
        for identity in exited:
            emitted += self._emit("process.exited", previous[identity], timestamp_ns, exited=True)
        for identity in started:
            emitted += self._emit("process.started", current[identity], timestamp_ns, exited=False)
        return emitted

    def _emit(
        self,
        event_type: str,
        sample: ProcessSample,
        timestamp_ns: int,
        *,
        exited: bool,
    ) -> int:
        publish = self._publish
        if publish is None:
            return 0
        event = self._factory.next(
            timestamp_ns=timestamp_ns,
            source="windows_process",
            modality="process",
            origin=EventOrigin.EXOGENOUS,
            event_type=event_type,
            app={"name": sample.name} if sample.name else None,
            process={
                "pid": sample.pid,
                "create_time": sample.create_time,
                **({"name": sample.name} if sample.name else {}),
            },
            payload={"completion_evidence": exited},
        )
        publish(event)
        with self._lock:
            self._events_published += 1
        return 1

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.poll_once()
            self._stop_event.wait(self._poll_interval_seconds)

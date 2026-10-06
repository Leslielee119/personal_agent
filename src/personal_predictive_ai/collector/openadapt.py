from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Protocol

from openadapt_capture.events import BaseEvent, KeyDownEvent, MouseDownEvent
from openadapt_capture.input import InputListener
from openadapt_capture.structural import (
    StructuralObservationRequest,
    create_structural_observer,
)

from personal_predictive_ai.collector.base import CollectorHealth, PublishCallback
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import CanonicalEvent, EventOrigin


class Snapshotter(Protocol):
    def capture(self, *, reason: str, timestamp_ns: int | None = None) -> CanonicalEvent: ...


ListenerFactory = Callable[[Callable[[BaseEvent], None], bool], Any]


def _default_listener_factory(
    callback: Callable[[BaseEvent], None],
    capture_mouse_moves: bool,
) -> InputListener:
    return InputListener(callback, capture_mouse_moves=capture_mouse_moves)


class OpenAdaptCollector:
    def __init__(
        self,
        *,
        factory: EventFactory,
        capture_structural: bool = True,
        capture_mouse_moves: bool = False,
        session_id: str | None = None,
        snapshotter: Snapshotter | None = None,
        listener_factory: ListenerFactory = _default_listener_factory,
        capture_initial_screen: bool = True,
        typing_pause_seconds: float = 0.75,
        pointer_snapshot_delay: float = 0.05,
    ) -> None:
        self._factory = factory
        self._capture_structural = capture_structural
        self._capture_mouse_moves = capture_mouse_moves
        self._session_id = session_id
        self._snapshotter = snapshotter
        self._listener_factory = listener_factory
        self._capture_initial_screen = capture_initial_screen
        self._typing_pause_seconds = max(0.0, typing_pause_seconds)
        self._pointer_snapshot_delay = max(0.0, pointer_snapshot_delay)
        self._listener: Any | None = None
        self._structural_observer = None
        self._publish: PublishCallback | None = None
        self._snapshot_timer: threading.Timer | None = None
        self._lock = threading.RLock()
        self._running = False
        self._available = True
        self._detail = ""
        self._events_published = 0
        self._structural_available = False
        self._structural_observations = 0
        self._screen_observations = 0

    def start(self, publish: PublishCallback) -> None:
        with self._lock:
            if self._running:
                return
            self._publish = publish
            if self._capture_structural:
                self._structural_observer = create_structural_observer(enabled=True)
                self._structural_available = self._structural_observer is not None
                if not self._structural_available:
                    self._detail = "native structural observer unavailable"
            try:
                self._listener = self._listener_factory(
                    self._handle_upstream,
                    self._capture_mouse_moves,
                )
                self._listener.start()
            except Exception as exc:
                self._available = False
                self._detail = f"input listener unavailable: {type(exc).__name__}: {exc}"
                self._listener = None
                self._publish = None
                raise
            self._running = True

        if self._capture_initial_screen and self._snapshotter is not None:
            self._schedule_snapshot("session.start", 0.0)

    def stop(self) -> None:
        with self._lock:
            listener = self._listener
            timer = self._snapshot_timer
            self._listener = None
            self._snapshot_timer = None
            self._running = False
            self._publish = None
        if timer is not None:
            timer.cancel()
        if listener is not None:
            listener.stop()

    def health(self) -> CollectorHealth:
        with self._lock:
            return CollectorHealth(
                available=self._available,
                running=self._running,
                detail=self._detail,
                events_published=self._events_published,
                structural_available=self._structural_available,
                structural_observations=self._structural_observations,
                screen_observations=self._screen_observations,
            )

    def translate(self, upstream: BaseEvent) -> CanonicalEvent:
        event_type = upstream.type.value if hasattr(upstream.type, "value") else str(upstream.type)
        modality = self._modality(event_type)
        data = upstream.model_dump(mode="json", exclude_none=True)
        data.pop("timestamp", None)
        data.pop("type", None)
        data.pop("source_ordinal", None)
        structural = data.pop("structural_observation", None)

        app = None
        process = None
        window = None
        if structural is not None:
            data["structural"] = structural
            process_data = structural.get("process") or {}
            process = {
                key: value
                for key, value in {
                    "pid": process_data.get("process_id"),
                    "name": process_data.get("process_name"),
                }.items()
                if value is not None
            } or None
            window_data = structural.get("window") or {}
            window = {
                key: value
                for key, value in {
                    "title": window_data.get("title"),
                    "automation_id": window_data.get("automation_id"),
                    "class_name": window_data.get("class_name"),
                    "handle": window_data.get("native_window_handle"),
                }.items()
                if value is not None
            } or None
            if process and process.get("name"):
                app = {"name": process["name"]}

        return self._factory.next(
            timestamp_ns=round(float(upstream.timestamp) * 1_000_000_000),
            source="openadapt_capture",
            modality=modality,
            origin=EventOrigin.ENDOGENOUS,
            event_type=event_type,
            app=app,
            process=process,
            window=window,
            session_id=self._session_id,
            payload=data,
        )

    def _handle_upstream(self, upstream: BaseEvent) -> None:
        enriched = upstream
        if self._capture_structural and isinstance(upstream, (KeyDownEvent, MouseDownEvent)):
            enriched = self._attach_structural(upstream)
        mapped = self.translate(enriched)
        publish = self._publish
        if publish is not None:
            publish(mapped)
            with self._lock:
                self._events_published += 1

        if isinstance(upstream, MouseDownEvent):
            self._schedule_snapshot("mouse.down", self._pointer_snapshot_delay)
        elif isinstance(upstream, KeyDownEvent):
            self._schedule_snapshot("typing.pause", self._typing_pause_seconds)

    def _schedule_snapshot(self, reason: str, delay: float) -> None:
        if self._snapshotter is None:
            return
        with self._lock:
            if not self._running or self._publish is None:
                return
            previous = self._snapshot_timer
            if previous is not None:
                previous.cancel()
            timer = threading.Timer(delay, self._emit_snapshot, args=(reason,))
            timer.daemon = True
            self._snapshot_timer = timer
            timer.start()

    def _emit_snapshot(self, reason: str) -> None:
        with self._lock:
            if not self._running:
                return
            snapshotter = self._snapshotter
            publish = self._publish
            self._snapshot_timer = None
        if snapshotter is None or publish is None:
            return
        try:
            event = snapshotter.capture(reason=reason)
            publish(event)
        except Exception as exc:
            with self._lock:
                self._detail = f"screen snapshot failed: {type(exc).__name__}: {exc}"
            return
        with self._lock:
            self._events_published += 1
            self._screen_observations += 1

    def _attach_structural(self, upstream: BaseEvent) -> BaseEvent:
        observer = self._structural_observer
        if observer is None:
            return upstream
        x = getattr(upstream, "x", None)
        y = getattr(upstream, "y", None)
        query_kind = "point" if x is not None and y is not None else "focused"
        event_type = upstream.type.value if hasattr(upstream.type, "value") else str(upstream.type)
        request = StructuralObservationRequest(
            event_timestamp=float(upstream.timestamp),
            action_name=event_type,
            x=x,
            y=y,
            query_kind=query_kind,
        )
        try:
            observation = observer.observe(request)
        except Exception as exc:
            with self._lock:
                self._structural_available = False
                self._detail = f"structural observation failed: {type(exc).__name__}: {exc}"
            return upstream
        if observation is None:
            with self._lock:
                self._structural_available = False
                self._detail = "structural observer returned no evidence"
            return upstream
        with self._lock:
            self._structural_observations += 1
        return upstream.model_copy(update={"structural_observation": observation})

    @staticmethod
    def _modality(event_type: str) -> str:
        prefix = event_type.split(".", 1)[0]
        return {
            "key": "keyboard",
            "mouse": "mouse",
            "screen": "screen",
            "audio": "audio",
        }.get(prefix, "desktop")

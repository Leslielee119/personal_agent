import time

from openadapt_capture.events import KeyDownEvent, MouseDownEvent

from personal_predictive_ai.collector.openadapt import OpenAdaptCollector
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import EventOrigin


class FakeListener:
    def __init__(self, callback):
        self.callback = callback
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def emit(self, event):
        self.callback(event)


class FakeSnapshotter:
    def __init__(self, factory: EventFactory):
        self.factory = factory
        self.reasons = []

    def capture(self, *, reason: str, timestamp_ns=None):
        self.reasons.append(reason)
        return self.factory.next(
            timestamp_ns=time.time_ns() if timestamp_ns is None else timestamp_ns,
            source="fake_screen",
            modality="screen",
            origin=EventOrigin.EXOGENOUS,
            event_type="screen.snapshot",
            payload={"trigger": reason},
        )


def test_mouse_input_schedules_nonblocking_screen_snapshot() -> None:
    factory = EventFactory()
    snapshotter = FakeSnapshotter(factory)
    holder = {}

    def listener_factory(callback, capture_mouse_moves):
        assert capture_mouse_moves is False
        holder["listener"] = FakeListener(callback)
        return holder["listener"]

    events = []
    collector = OpenAdaptCollector(
        factory=factory,
        capture_structural=False,
        snapshotter=snapshotter,
        listener_factory=listener_factory,
        capture_initial_screen=False,
        pointer_snapshot_delay=0.01,
    )
    collector.start(events.append)
    try:
        holder["listener"].emit(MouseDownEvent(timestamp=1.0, x=10, y=20, button="left"))
        time.sleep(0.05)
    finally:
        collector.stop()

    assert any(event.modality == "mouse" for event in events)
    screens = [event for event in events if event.modality == "screen"]
    assert len(screens) == 1
    assert screens[0].origin is EventOrigin.EXOGENOUS
    assert screens[0].payload["trigger"] == "mouse.down"
    assert snapshotter.reasons == ["mouse.down"]
    assert collector.health().screen_observations == 1


def test_keyboard_burst_coalesces_to_one_typing_pause_snapshot() -> None:
    factory = EventFactory()
    snapshotter = FakeSnapshotter(factory)
    holder = {}

    def listener_factory(callback, capture_mouse_moves):
        holder["listener"] = FakeListener(callback)
        return holder["listener"]

    events = []
    collector = OpenAdaptCollector(
        factory=factory,
        capture_structural=False,
        snapshotter=snapshotter,
        listener_factory=listener_factory,
        capture_initial_screen=False,
        typing_pause_seconds=0.03,
    )
    collector.start(events.append)
    try:
        for char in "abc":
            holder["listener"].emit(KeyDownEvent(timestamp=1.0, key_char=char))
            time.sleep(0.005)
        time.sleep(0.07)
    finally:
        collector.stop()

    assert len([event for event in events if event.modality == "keyboard"]) == 3
    assert len([event for event in events if event.modality == "screen"]) == 1
    assert snapshotter.reasons == ["typing.pause"]

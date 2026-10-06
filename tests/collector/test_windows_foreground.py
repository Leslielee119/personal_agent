from personal_predictive_ai.collector.windows_foreground import (
    ForegroundWindowCollector,
    WindowSample,
)
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import EventOrigin


class Samples:
    def __init__(self, values):
        self._values = iter(values)

    def __call__(self):
        return next(self._values)


def test_foreground_window_emits_initial_and_changed_state_only() -> None:
    provider = Samples(
        [
            WindowSample(handle=1, title="Editor", pid=10, process_name="editor.exe"),
            WindowSample(handle=1, title="Editor", pid=10, process_name="editor.exe"),
            WindowSample(handle=2, title="Terminal", pid=20, process_name="terminal.exe"),
        ]
    )
    events = []
    collector = ForegroundWindowCollector(
        factory=EventFactory(),
        snapshot_provider=provider,
        clock_ns=iter([100, 200]).__next__,
    )
    collector.set_publish(events.append)

    assert collector.poll_once() == 1
    assert collector.poll_once() == 0
    assert collector.poll_once() == 1

    assert [event.event_type for event in events] == [
        "window.foreground.current",
        "window.foreground.changed",
    ]
    assert all(event.origin is EventOrigin.EXOGENOUS for event in events)
    assert events[0].window == {"handle": 1, "title": "Editor"}
    assert events[0].process == {"pid": 10, "name": "editor.exe"}
    assert events[1].app == {"name": "terminal.exe"}
    assert events[1].payload["previous_handle"] == 1


def test_foreground_provider_failure_degrades_health_without_fabricating_event() -> None:
    def broken_provider():
        raise OSError("foreground API unavailable")

    events = []
    collector = ForegroundWindowCollector(
        factory=EventFactory(),
        snapshot_provider=broken_provider,
    )
    collector.set_publish(events.append)

    assert collector.poll_once() == 0
    assert events == []
    health = collector.health()
    assert health.available is False
    assert "foreground API unavailable" in health.detail

from dataclasses import dataclass
from pathlib import Path

from openadapt_capture.events import EventType, KeyDownEvent, MouseDownEvent

from personal_predictive_ai.collector.filesystem import FilesystemCollector
from personal_predictive_ai.collector.openadapt import OpenAdaptCollector
from personal_predictive_ai.collector.process import ProcessCollector, ProcessSample
from personal_predictive_ai.collector.screen import ScreenSnapshotter
from personal_predictive_ai.collector.windows_foreground import (
    ForegroundWindowCollector,
    WindowSample,
)
from personal_predictive_ai.collector.windows_notifications import (
    NotificationRecord,
    WindowsNotificationCollector,
)
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import EventActor, EventProvenance
from personal_predictive_ai.storage.raw_ring import RawRing


class FakeImage:
    width = 10
    height = 10

    def save(self, handle, *, format: str) -> None:
        assert format == "PNG"
        handle.write(b"png")


class SnapshotFeed:
    def __init__(self, snapshots):
        self._snapshots = iter(snapshots)

    def __call__(self):
        return next(self._snapshots)


@dataclass
class NotificationBackend:
    records: list[NotificationRecord]
    available: bool = True
    detail: str = ""

    def drain(self) -> list[NotificationRecord]:
        records, self.records = self.records, []
        return records


class InjectedFixture:
    timestamp = 1.0
    type = EventType.KEY_DOWN
    injected = True

    def model_dump(self, **_kwargs):
        return {"timestamp": self.timestamp, "type": self.type.value, "key_char": "x"}


def test_openadapt_native_key_and_mouse_are_physical_human() -> None:
    collector = OpenAdaptCollector(factory=EventFactory(), capture_structural=False)

    key = collector.translate(KeyDownEvent(timestamp=1.0, key_char="a"))
    mouse = collector.translate(MouseDownEvent(timestamp=2.0, x=10, y=20, button="left"))

    for event in (key, mouse):
        assert event.actor is EventActor.HUMAN
        assert event.provenance is EventProvenance.HUMAN_PHYSICAL
        assert event.injected is False


def test_openadapt_injected_fixture_is_not_physical_human() -> None:
    event = OpenAdaptCollector(
        factory=EventFactory(), capture_structural=False
    ).translate(InjectedFixture())

    assert event.actor is EventActor.UNKNOWN
    assert event.provenance is EventProvenance.UNKNOWN
    assert event.injected is True


def test_system_collectors_emit_system_provenance(tmp_path: Path) -> None:
    process_events = []
    process = ProcessCollector(
        factory=EventFactory(),
        snapshot_provider=SnapshotFeed(
            [[], [ProcessSample(pid=2, create_time=1.0, name="job.exe")]]
        ),
        clock_ns=lambda: 100,
    )
    process.set_publish(process_events.append)
    process.poll_once()
    process.poll_once()

    file_events = []
    filesystem = FilesystemCollector(
        factory=EventFactory(), roots=[tmp_path], clock_ns=lambda: 200, debounce_ms=0
    )
    filesystem.set_publish(file_events.append)
    filesystem.observe_change("created", tmp_path / "x.txt")

    foreground_events = []
    foreground = ForegroundWindowCollector(
        factory=EventFactory(),
        snapshot_provider=SnapshotFeed(
            [WindowSample(handle=1, title="Editor", pid=3, process_name="editor.exe")]
        ),
        clock_ns=lambda: 300,
    )
    foreground.set_publish(foreground_events.append)
    foreground.poll_once()

    screen = ScreenSnapshotter(
        factory=EventFactory(),
        raw_ring=RawRing(tmp_path / "raw", ttl_seconds=60, max_bytes=1024),
        screenshot_provider=FakeImage,
        topology_provider=lambda: {"monitor_count": 1},
    ).capture(reason="test", timestamp_ns=400)

    events = [process_events[0], file_events[0], foreground_events[0], screen]
    assert all(event.actor is EventActor.SYSTEM for event in events)
    assert all(event.provenance is EventProvenance.SYSTEM for event in events)


def test_notification_external_mapping_requires_explicit_backend_evidence() -> None:
    records = [
        NotificationRecord(
            app_name="Mail",
            title="Remote",
            body=None,
            notification_id="n1",
            timestamp_ns=1,
            external_source=True,
        ),
        NotificationRecord(
            app_name="Local",
            title="Local",
            body=None,
            notification_id="n2",
            timestamp_ns=2,
            external_source=False,
        ),
        NotificationRecord(
            app_name="Unknown",
            title="Unknown",
            body=None,
            notification_id="n3",
            timestamp_ns=3,
            external_source=None,
        ),
    ]
    backend = NotificationBackend(records=records)
    events = []
    collector = WindowsNotificationCollector(factory=EventFactory(), backend=backend)
    collector.set_publish(events.append)

    assert collector.poll_once() == 3
    assert (events[0].actor, events[0].provenance) == (
        EventActor.EXTERNAL,
        EventProvenance.EXTERNAL,
    )
    assert (events[1].actor, events[1].provenance) == (
        EventActor.SYSTEM,
        EventProvenance.SYSTEM,
    )
    assert (events[2].actor, events[2].provenance) == (
        EventActor.UNKNOWN,
        EventProvenance.UNKNOWN,
    )

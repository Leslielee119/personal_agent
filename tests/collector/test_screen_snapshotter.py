from personal_predictive_ai.collector.screen import ScreenSnapshotter
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import EventOrigin, PrivacyTier, RetentionClass
from personal_predictive_ai.storage.raw_ring import RawRing


class FakeImage:
    width = 320
    height = 200

    def save(self, handle, *, format: str) -> None:
        assert format == "PNG"
        handle.write(b"fake-png-bytes")


def test_screen_snapshot_writes_only_raw_reference_into_canonical_event(tmp_path) -> None:
    ring = RawRing(tmp_path / "raw", ttl_seconds=60, max_bytes=1024)
    snapshotter = ScreenSnapshotter(
        factory=EventFactory(),
        raw_ring=ring,
        screenshot_provider=FakeImage,
        topology_provider=lambda: {
            "viewport": [320, 200],
            "origin": [0, 0],
            "monitor_count": 1,
        },
    )

    event = snapshotter.capture(reason="mouse.click", timestamp_ns=123)

    assert event.timestamp_ns == 123
    assert event.origin is EventOrigin.EXOGENOUS
    assert event.modality == "screen"
    assert event.event_type == "screen.snapshot"
    assert event.privacy_tier is PrivacyTier.SENSITIVE
    assert event.retention_class is RetentionClass.STRUCTURED_SHORT
    assert event.payload["trigger"] == "mouse.click"
    assert event.payload["width"] == 320
    assert event.payload["height"] == 200
    assert event.payload["topology"]["monitor_count"] == 1
    assert "fake-png-bytes" not in str(event.payload)
    assert event.raw_ref is not None
    raw_path = ring.resolve(event.raw_ref)
    assert raw_path is not None
    assert raw_path.read_bytes() == b"fake-png-bytes"

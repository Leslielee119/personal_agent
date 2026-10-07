from dataclasses import dataclass

from personal_predictive_ai.collector.windows_notifications import (
    NotificationRecord,
    WindowsNotificationCollector,
)
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import EventOrigin


@dataclass
class FakeBackend:
    available: bool
    records: list[NotificationRecord]
    detail: str = ""

    def drain(self) -> list[NotificationRecord]:
        records, self.records = self.records, []
        return records


def test_unavailable_notification_backend_is_reported_without_fabrication() -> None:
    collector = WindowsNotificationCollector(
        factory=EventFactory(),
        backend=FakeBackend(available=False, records=[], detail="permission unavailable"),
    )
    events = []
    collector.set_publish(events.append)

    assert collector.poll_once() == 0
    health = collector.health()
    assert health.available is False
    assert "permission unavailable" in health.detail
    assert events == []


def test_notification_metadata_maps_without_forcing_message_body_persistence() -> None:
    backend = FakeBackend(
        available=True,
        records=[
            NotificationRecord(
                app_name="Mail",
                title="New message",
                body="private body that must remain optional",
                notification_id="n-1",
                timestamp_ns=123,
            )
        ],
    )
    collector = WindowsNotificationCollector(
        factory=EventFactory(),
        backend=backend,
        retain_body=False,
    )
    events = []
    collector.set_publish(events.append)

    assert collector.poll_once() == 1
    event = events[0]
    assert event.origin is EventOrigin.EXOGENOUS
    assert event.event_type == "notification.received"
    assert event.app == {"name": "Mail"}
    assert event.payload == {"notification_id": "n-1", "title": "New message"}
    assert "private body" not in str(event.model_dump(mode="json"))

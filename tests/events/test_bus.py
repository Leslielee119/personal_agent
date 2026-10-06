from pathlib import Path

from personal_predictive_ai.events.bus import EventBus
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import EventOrigin
from personal_predictive_ai.privacy.policy import PrivacyPolicy
from personal_predictive_ai.privacy.sanitizer import sanitize_event
from personal_predictive_ai.storage.sqlite_store import EventStore


def _setup(tmp_path: Path) -> tuple[EventBus, EventStore, EventFactory]:
    store = EventStore(tmp_path / "events.db")
    policy = PrivacyPolicy(excluded_apps={"secret-app"})
    bus = EventBus(store=store, sanitizer=lambda event: sanitize_event(event, policy))
    return bus, store, EventFactory()


def _event(factory: EventFactory, *, n: int, app: str = "editor"):
    return factory.next(
        timestamp_ns=n,
        source="unit",
        modality="system",
        origin=EventOrigin.EXOGENOUS,
        event_type="system.test",
        app={"name": app},
        payload={"n": n},
    )


def test_publish_is_ordered_and_multiple_subscribers_receive_sanitized_event(
    tmp_path: Path,
) -> None:
    bus, store, factory = _setup(tmp_path)
    first_seen: list[str] = []
    second_seen: list[str] = []
    bus.subscribe(lambda event: first_seen.append(event.event_id))
    bus.subscribe(lambda event: second_seen.append(event.event_id))

    first = _event(factory, n=1)
    second = _event(factory, n=2)
    first_result = bus.publish(first)
    second_result = bus.publish(second)

    assert first_result.accepted is True
    assert second_result.accepted is True
    assert first_seen == [first.event_id, second.event_id]
    assert second_seen == first_seen
    assert [item.event_id for item in store.iter_events()] == first_seen
    store.close()


def test_failing_subscriber_does_not_stop_other_subscribers_or_future_publish(
    tmp_path: Path,
) -> None:
    bus, store, factory = _setup(tmp_path)
    healthy: list[str] = []

    def broken(_event) -> None:
        raise RuntimeError("subscriber failure")

    bus.subscribe(broken)
    bus.subscribe(lambda event: healthy.append(event.event_id))

    first = _event(factory, n=1)
    second = _event(factory, n=2)
    first_result = bus.publish(first)
    second_result = bus.publish(second)

    assert first_result.accepted is True
    assert len(first_result.subscriber_errors) == 1
    assert second_result.accepted is True
    assert healthy == [first.event_id, second.event_id]
    assert store.get(first.event_id) == first
    assert store.get(second.event_id) == second
    assert bus.error_count == 2
    store.close()


def test_sanitizer_drop_never_reaches_storage_or_subscribers(tmp_path: Path) -> None:
    bus, store, factory = _setup(tmp_path)
    seen: list[str] = []
    bus.subscribe(lambda event: seen.append(event.event_id))

    event = _event(factory, n=1, app="secret-app")
    result = bus.publish(event)

    assert result.accepted is False
    assert result.dropped is True
    assert store.count() == 0
    assert seen == []
    store.close()


def test_malformed_publish_is_rejected_without_touching_storage(tmp_path: Path) -> None:
    bus, store, _factory = _setup(tmp_path)

    result = bus.publish({"not": "an event"})  # type: ignore[arg-type]

    assert result.accepted is False
    assert result.dropped is False
    assert result.rejected_reason == "invalid_event_type"
    assert store.count() == 0
    store.close()

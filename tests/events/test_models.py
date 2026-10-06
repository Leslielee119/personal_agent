import pytest
from pydantic import ValidationError

from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventOrigin,
    PrivacyTier,
    RetentionClass,
)


def test_canonical_event_schema_and_json_safe_payload() -> None:
    event = CanonicalEvent(
        event_id="evt-1",
        timestamp_ns=123,
        monotonic_seq=1,
        source="unit",
        modality="keyboard",
        origin=EventOrigin.ENDOGENOUS,
        event_type="key.down",
        payload={"key": "a", "nested": [1, True, None]},
        privacy_tier=PrivacyTier.STANDARD,
        retention_class=RetentionClass.STRUCTURED_LONG,
    )

    assert event.schema_version == "ppa.event/v2"
    assert event.payload["key"] == "a"

    with pytest.raises(ValidationError):
        CanonicalEvent(
            event_id="evt-bad",
            timestamp_ns=123,
            monotonic_seq=2,
            source="unit",
            modality="keyboard",
            origin=EventOrigin.ENDOGENOUS,
            event_type="key.down",
            payload={"not_json": {1, 2, 3}},
        )


def test_factory_assigns_increasing_sequence_for_equal_timestamps() -> None:
    factory = EventFactory()
    first = factory.next(
        timestamp_ns=100,
        source="unit",
        modality="mouse",
        origin=EventOrigin.ENDOGENOUS,
        event_type="mouse.move",
    )
    second = factory.next(
        timestamp_ns=100,
        source="unit",
        modality="mouse",
        origin=EventOrigin.ENDOGENOUS,
        event_type="mouse.move",
    )

    assert first.monotonic_seq == 1
    assert second.monotonic_seq == 2
    assert first.event_id != second.event_id


def test_factory_sequence_remains_monotonic_when_wall_clock_moves_backward() -> None:
    factory = EventFactory()
    newer_clock = factory.next(
        timestamp_ns=200,
        source="unit",
        modality="system",
        origin=EventOrigin.EXOGENOUS,
        event_type="clock.sample",
    )
    older_clock = factory.next(
        timestamp_ns=100,
        source="unit",
        modality="system",
        origin=EventOrigin.EXOGENOUS,
        event_type="clock.sample",
    )

    assert newer_clock.timestamp_ns > older_clock.timestamp_ns
    assert newer_clock.monotonic_seq < older_clock.monotonic_seq


def test_negative_or_zero_monotonic_sequence_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CanonicalEvent(
            event_id="evt-invalid",
            timestamp_ns=1,
            monotonic_seq=0,
            source="unit",
            modality="system",
            origin=EventOrigin.EXOGENOUS,
            event_type="system.test",
        )


def test_factory_can_advance_to_persisted_sequence_floor_without_going_backward() -> None:
    factory = EventFactory()
    factory.ensure_at_least(41)

    first = factory.next(
        timestamp_ns=1,
        source="unit",
        modality="system",
        origin=EventOrigin.EXOGENOUS,
        event_type="system.test",
    )
    factory.ensure_at_least(3)
    second = factory.next(
        timestamp_ns=2,
        source="unit",
        modality="system",
        origin=EventOrigin.EXOGENOUS,
        event_type="system.test",
    )

    assert first.monotonic_seq == 42
    assert second.monotonic_seq == 43

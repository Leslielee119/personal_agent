import pytest
from pydantic import ValidationError

from personal_predictive_ai.events.migration import parse_canonical_event
from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventActor,
    EventOrigin,
    EventProvenance,
)


def _base_v2(**overrides):
    data = {
        "event_id": "evt-1",
        "timestamp_ns": 123,
        "monotonic_seq": 1,
        "source": "unit",
        "modality": "keyboard",
        "origin": EventOrigin.ENDOGENOUS,
        "event_type": "key.down",
        "actor": EventActor.HUMAN,
        "provenance": EventProvenance.HUMAN_PHYSICAL,
        "device": {"kind": "keyboard", "id": "kbd-1"},
        "injected": False,
    }
    data.update(overrides)
    return data


def test_v2_round_trip_preserves_provenance_and_device() -> None:
    event = CanonicalEvent(**_base_v2())
    reparsed = parse_canonical_event(event.model_dump(mode="json"))

    assert event.schema_version == "ppa.event/v2"
    assert reparsed == event
    assert reparsed.actor is EventActor.HUMAN
    assert reparsed.provenance is EventProvenance.HUMAN_PHYSICAL
    assert reparsed.device == {"kind": "keyboard", "id": "kbd-1"}
    assert reparsed.injected is False


def test_device_must_be_strict_json_safe() -> None:
    with pytest.raises(ValidationError):
        CanonicalEvent(**_base_v2(device={"bad": {1, 2, 3}}))


def test_legacy_v1_endogenous_event_upgrades_conservatively() -> None:
    legacy = {
        "schema_version": "ppa.event/v1",
        "event_id": "legacy-1",
        "timestamp_ns": 100,
        "monotonic_seq": 7,
        "source": "legacy",
        "modality": "keyboard",
        "origin": "endogenous",
        "event_type": "key.down",
        "payload": {"key_char": "x"},
    }

    event = parse_canonical_event(legacy)

    assert event.schema_version == "ppa.event/v2"
    assert event.actor is EventActor.UNKNOWN
    assert event.provenance is EventProvenance.UNKNOWN
    assert event.injected is None
    assert event.device is None


def test_injected_event_cannot_claim_human_physical_provenance() -> None:
    with pytest.raises(ValidationError):
        CanonicalEvent(**_base_v2(injected=True))


def test_ai_executed_event_cannot_claim_human_actor() -> None:
    with pytest.raises(ValidationError):
        CanonicalEvent(
            **_base_v2(
                provenance=EventProvenance.AI_EXECUTED,
                actor=EventActor.HUMAN,
                injected=None,
            )
        )

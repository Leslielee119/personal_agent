import json
from pathlib import Path

import pytest

from personal_predictive_ai.diagnostics.health import build_health_report
from personal_predictive_ai.events.models import CanonicalEvent, EventOrigin
from personal_predictive_ai.storage.sqlite_store import EventStore


def _event(event_id: str, seq: int, payload: dict) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        timestamp_ns=seq,
        monotonic_seq=seq,
        source="fixture",
        modality="system",
        origin=EventOrigin.EXOGENOUS,
        event_type=f"fixture.{event_id}",
        payload=payload,
    )


def test_health_report_detects_order_privacy_resource_and_network_evidence(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.db")
    store.append(_event("one", 1, {"status": "ok"}))
    store.append(_event("three", 3, {"password": "health-secret"}))
    store.append(_event("two", 2, {"status": "late-write"}))
    store.close()

    samples_path = tmp_path / "soak_samples.jsonl"
    samples = [
        {
            "timestamp_ns": 0,
            "cpu_total_seconds": 1.0,
            "logical_cpu_count": 4,
            "rss_bytes": 100,
            "data_bytes": 1000,
            "external_established": 0,
        },
        {
            "timestamp_ns": 2_000_000_000,
            "cpu_total_seconds": 1.2,
            "logical_cpu_count": 4,
            "rss_bytes": 120,
            "data_bytes": 1200,
            "external_established": 1,
        },
    ]
    samples_path.write_text(
        "\n".join(json.dumps(item) for item in samples) + "\n",
        encoding="utf-8",
    )
    status_path = tmp_path / "runtime_status.json"
    status_path.write_text(
        json.dumps(
            {
                "provider_errors": {"broken": "fixture failure"},
                "bus_errors": 2,
                "offline_mode": True,
            }
        ),
        encoding="utf-8",
    )

    report = build_health_report(
        tmp_path,
        samples_path=samples_path,
        runtime_status_path=status_path,
        forbidden_strings=("health-secret",),
    )

    assert report["event_count"] == 3
    assert report["sqlite_integrity"] == "ok"
    assert report["ordering"]["violations"] == 1
    assert report["ordering"]["consistency"] == 0.5
    assert report["privacy_violations"] == 1
    assert report["forbidden_string_hits"] == 1
    assert report["cpu"]["avg_percent"] == pytest.approx(2.5)
    assert report["rss"]["growth_bytes"] == 20
    assert report["data_bytes"]["growth_bytes"] == 200
    assert report["external_network"]["max_established"] == 1
    assert report["provider_errors"] == {"broken": "fixture failure"}
    assert report["bus_errors"] == 2
    assert report["offline_mode"] is True


def test_health_report_flags_raw_artifacts_older_than_ttl(tmp_path: Path) -> None:
    from personal_predictive_ai.storage.raw_ring import RawRing

    ring = RawRing(
        tmp_path / "raw",
        ttl_seconds=10,
        max_bytes=1024,
        clock_ns=lambda: 1_000_000_000,
    )
    ring.put(b"frame", ".png")

    report = build_health_report(
        tmp_path,
        raw_ttl_seconds=10,
        now_ns=12_000_000_000,
    )

    assert report["raw_artifacts"]["count"] == 1
    assert report["raw_artifacts"]["ttl_violations"] == 1
    assert report["raw_artifacts"]["oldest_age_seconds"] == pytest.approx(11.0)
    assert report["bus_errors"] is None
    assert report["offline_mode"] is None

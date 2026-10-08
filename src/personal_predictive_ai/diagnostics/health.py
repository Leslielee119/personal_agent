from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from personal_predictive_ai.events.models import CanonicalEvent
from personal_predictive_ai.privacy.policy import PrivacyPolicy
from personal_predictive_ai.privacy.sanitizer import sanitize_event
from personal_predictive_ai.storage.sqlite_store import EventStore


def _load_samples(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    samples: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            samples.append(value)
    return samples


def _load_status(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    lines = [line for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _resource_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    cpu_values: list[float] = []
    for previous, current in zip(samples, samples[1:]):
        try:
            delta_ns = int(current["timestamp_ns"]) - int(previous["timestamp_ns"])
            delta_cpu = float(current["cpu_total_seconds"]) - float(
                previous["cpu_total_seconds"]
            )
            logical = max(1, int(current.get("logical_cpu_count") or 1))
        except (KeyError, TypeError, ValueError):
            continue
        if delta_ns <= 0 or delta_cpu < 0:
            continue
        wall_seconds = delta_ns / 1_000_000_000
        cpu_values.append((delta_cpu / wall_seconds) * 100.0 / logical)

    rss_values = [
        int(sample["rss_bytes"])
        for sample in samples
        if isinstance(sample.get("rss_bytes"), (int, float))
    ]
    data_values = [
        int(sample["data_bytes"])
        for sample in samples
        if isinstance(sample.get("data_bytes"), (int, float))
    ]
    external_values = [
        int(sample.get("external_established", 0))
        for sample in samples
        if isinstance(sample.get("external_established", 0), (int, float))
    ]

    return {
        "cpu": {
            "samples": len(cpu_values),
            "avg_percent": (sum(cpu_values) / len(cpu_values)) if cpu_values else 0.0,
            "max_percent": max(cpu_values, default=0.0),
        },
        "rss": {
            "samples": len(rss_values),
            "start_bytes": rss_values[0] if rss_values else 0,
            "end_bytes": rss_values[-1] if rss_values else 0,
            "max_bytes": max(rss_values, default=0),
            "growth_bytes": (rss_values[-1] - rss_values[0]) if rss_values else 0,
        },
        "data_bytes": {
            "samples": len(data_values),
            "start_bytes": data_values[0] if data_values else 0,
            "end_bytes": data_values[-1] if data_values else 0,
            "max_bytes": max(data_values, default=0),
            "growth_bytes": (data_values[-1] - data_values[0]) if data_values else 0,
        },
        "external_network": {
            "samples": len(external_values),
            "max_established": max(external_values, default=0),
            "samples_with_external": sum(1 for value in external_values if value > 0),
        },
    }


def _raw_inventory(
    raw_dir: Path,
    *,
    now_ns: int,
    ttl_seconds: int | None,
) -> dict[str, Any]:
    if not raw_dir.exists():
        return {
            "count": 0,
            "bytes": 0,
            "oldest_age_seconds": 0.0,
            "ttl_seconds": ttl_seconds,
            "ttl_violations": 0,
            "malformed_metadata": 0,
        }

    count = 0
    total_bytes = 0
    oldest_age_ns = 0
    ttl_violations = 0
    malformed = 0
    ttl_ns = ttl_seconds * 1_000_000_000 if ttl_seconds is not None else None

    for meta_path in raw_dir.glob("*.meta.json"):
        try:
            item = json.loads(meta_path.read_text(encoding="utf-8"))
            ref = str(item["ref"])
            created_ns = int(item["created_ns"])
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            malformed += 1
            continue
        data_path = raw_dir / ref
        if not data_path.is_file():
            continue
        age_ns = max(0, now_ns - created_ns)
        count += 1
        total_bytes += data_path.stat().st_size
        oldest_age_ns = max(oldest_age_ns, age_ns)
        if ttl_ns is not None and age_ns >= ttl_ns:
            ttl_violations += 1

    return {
        "count": count,
        "bytes": total_bytes,
        "oldest_age_seconds": oldest_age_ns / 1_000_000_000,
        "ttl_seconds": ttl_seconds,
        "ttl_violations": ttl_violations,
        "malformed_metadata": malformed,
    }


def build_health_report(
    data_dir: str | Path,
    *,
    samples_path: str | Path | None = None,
    runtime_status_path: str | Path | None = None,
    forbidden_strings: tuple[str, ...] = (),
    raw_ttl_seconds: int | None = None,
    now_ns: int | None = None,
) -> dict[str, Any]:
    root = Path(data_dir)
    db_path = root / "events.db"
    samples = _load_samples(Path(samples_path) if samples_path is not None else None)
    status = _load_status(
        Path(runtime_status_path) if runtime_status_path is not None else None
    )

    store = EventStore(db_path)
    try:
        events = list(store.iter_events())
        integrity = store.integrity_check()
    finally:
        store.close()

    with sqlite3.connect(db_path) as conn:
        insertion_rows = conn.execute(
            "SELECT data_json FROM canonical_events ORDER BY rowid ASC"
        ).fetchall()

    insertion_events = [CanonicalEvent.model_validate(json.loads(row[0])) for row in insertion_rows]
    comparisons = max(0, len(insertion_events) - 1)
    ordering_violations = sum(
        1
        for previous, current in zip(insertion_events, insertion_events[1:])
        if current.monotonic_seq <= previous.monotonic_seq
    )
    ordering_consistency = (
        1.0 if comparisons == 0 else 1.0 - (ordering_violations / comparisons)
    )

    policy = PrivacyPolicy()
    privacy_violations = 0
    forbidden_hits = 0
    origin_counts = {"endogenous": 0, "exogenous": 0}
    for event in events:
        origin_counts[event.origin.value] = origin_counts.get(event.origin.value, 0) + 1
        sanitized = sanitize_event(event, policy)
        if sanitized is None or sanitized.model_dump(mode="json") != event.model_dump(mode="json"):
            privacy_violations += 1
        encoded = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
        if any(value and value in encoded for value in forbidden_strings):
            forbidden_hits += 1

    resources = _resource_metrics(samples)
    provider_errors = status.get("provider_errors", {})
    if not isinstance(provider_errors, dict):
        provider_errors = {"status_parse": "provider_errors was not an object"}

    raw_bus_errors = status.get("bus_errors")
    bus_errors = (
        raw_bus_errors
        if isinstance(raw_bus_errors, int)
        and not isinstance(raw_bus_errors, bool)
        and raw_bus_errors >= 0
        else None
    )
    raw_offline_mode = status.get("offline_mode")
    offline_mode = raw_offline_mode if isinstance(raw_offline_mode, bool) else None

    raw_artifacts = _raw_inventory(
        root / "raw",
        now_ns=time.time_ns() if now_ns is None else now_ns,
        ttl_seconds=raw_ttl_seconds,
    )

    return {
        "event_count": len(events),
        "origin_counts": origin_counts,
        "sqlite_integrity": integrity,
        "ordering": {
            "comparisons": comparisons,
            "violations": ordering_violations,
            "consistency": ordering_consistency,
        },
        "privacy_violations": privacy_violations,
        "forbidden_string_hits": forbidden_hits,
        "raw_bytes": raw_artifacts["bytes"],
        "raw_artifacts": raw_artifacts,
        "provider_errors": provider_errors,
        "bus_errors": bus_errors,
        "offline_mode": offline_mode,
        **resources,
    }

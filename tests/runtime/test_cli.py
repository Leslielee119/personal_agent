from __future__ import annotations

import json
from pathlib import Path

from personal_predictive_ai.cli import main
from personal_predictive_ai.storage.raw_ring import RawRing


def test_status_reports_local_store_without_starting_collectors(tmp_path: Path, capsys) -> None:
    code = main(["--data-dir", str(tmp_path), "status"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["running"] is False
    assert payload["event_count"] == 0
    assert payload["offline_mode"] is True


def test_expire_raw_removes_expired_artifacts(tmp_path: Path, capsys) -> None:
    ring = RawRing(
        tmp_path / "raw",
        ttl_seconds=1,
        max_bytes=1024,
        clock_ns=lambda: 1_000_000_000,
    )
    raw_ref = ring.put(b"secret-free", ".bin")
    assert ring.resolve(raw_ref) is not None

    code = main(
        [
            "--data-dir",
            str(tmp_path),
            "--raw-ttl-seconds",
            "1",
            "expire-raw",
            "--now-ns",
            "3000000000",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["expired"] == 1
    assert ring.resolve(raw_ref) is None


def test_capture_duration_starts_and_stops_offline_runtime(tmp_path: Path, capsys) -> None:
    code = main(
        [
            "--data-dir",
            str(tmp_path),
            "capture",
            "--duration",
            "0.05",
            "--no-openadapt",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["running"] is False
    assert payload["offline_mode"] is True
    assert payload["provider_errors"] == {}

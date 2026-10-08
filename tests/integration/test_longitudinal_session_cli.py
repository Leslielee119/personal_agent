from __future__ import annotations

import json
from pathlib import Path

from personal_predictive_ai.cli import main
from personal_predictive_ai.storage.derived_store import DerivedStore


def _run_session(data_dir: Path, capsys) -> dict[str, object]:
    code = main(
        [
            "--data-dir",
            str(data_dir),
            "longitudinal-session",
            "--duration",
            "0",
            "--no-openadapt",
        ]
    )
    assert code == 0
    return json.loads(capsys.readouterr().out)


def test_longitudinal_session_captures_then_reports_progress(tmp_path: Path, capsys) -> None:
    payload = _run_session(tmp_path, capsys)

    assert payload["capture"]["running"] is False
    assert payload["capture"]["offline_mode"] is True
    assert payload["longitudinal"]["source_b1_run_id"] == "longitudinal-current"
    assert payload["longitudinal"]["session_count"] == 1
    assert payload["longitudinal"]["human_physical_actions"] == 0
    application_reasons = payload["longitudinal"]["readiness"]["targets"]["application"][
        "c0_reasons"
    ]
    assert "classes<2" in application_reasons
    assert "classes<3" not in application_reasons
    assert payload["longitudinal"]["progress"]["operation"]["screening_status"] == (
        "SCREENING_NOT_READY"
    )


def test_longitudinal_session_reuses_database_and_accumulates_sessions(
    tmp_path: Path,
    capsys,
) -> None:
    first = _run_session(tmp_path, capsys)
    second = _run_session(tmp_path, capsys)

    assert first["longitudinal"]["session_count"] == 1
    assert second["longitudinal"]["session_count"] == 2
    assert second["longitudinal"]["source_high_water"] > first["longitudinal"]["source_high_water"]

    store = DerivedStore(tmp_path / "events.db")
    try:
        run = store.get_run("longitudinal-current")
        assert run is not None
        assert run.source_high_water == second["longitudinal"]["source_high_water"]
        assert len(list(store.iter_sessions("longitudinal-current"))) == 2
    finally:
        store.close()

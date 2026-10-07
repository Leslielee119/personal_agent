from __future__ import annotations

import json
from pathlib import Path

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.cli import main
from personal_predictive_ai.events.models import EventActor, EventProvenance
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.state.sessions import SessionSegment
from personal_predictive_ai.storage.derived_store import DerivedStore


def _seed_five_sessions(db: Path) -> None:
    actions = []
    snapshots = []
    sessions = []
    seq = 1
    for session_index in range(5):
        session_id = f"s{session_index + 1}"
        start_ns = (session_index + 1) * 1_000_000
        first_event_id = f"evt-{seq}"
        for offset in range(50):
            application = ("Code.exe", "chrome.exe")[offset % 2]
            operation = ("save", "run", "inspect")[offset % 3]
            timestamp_ns = start_ns + offset
            actions.append(
                NormalizedAction(
                    action_id=f"act-{seq}",
                    source_event_id=f"evt-{seq}",
                    timestamp_ns=timestamp_ns,
                    monotonic_seq=seq,
                    actor=EventActor.HUMAN,
                    provenance=EventProvenance.HUMAN_PHYSICAL,
                    application=application,
                    operation=operation,
                )
            )
            snapshots.append(
                StateSnapshot(
                    state_id=f"state-{seq}",
                    source_event_id=f"evt-{seq}",
                    timestamp_ns=timestamp_ns,
                    monotonic_seq=seq,
                    foreground_app={"name": application},
                    active_processes={"1": {"name": application, "pid": 1}},
                    session_id=session_id,
                )
            )
            seq += 1
        sessions.append(
            SessionSegment(
                session_id=session_id,
                start_event_id=first_event_id,
                start_ns=start_ns,
                end_event_id=f"evt-{seq - 1}",
                end_ns=start_ns + 49,
                reason="fixture",
            )
        )
    store = DerivedStore(db)
    try:
        store.replace_run("b1", seq - 1, snapshots, actions, sessions, [])
    finally:
        store.close()


def test_longitudinal_status_cli_is_read_only_and_reports_readiness(tmp_path: Path, capsys) -> None:
    db = tmp_path / "events.db"
    _seed_five_sessions(db)

    result = main(
        [
            "--data-dir",
            str(tmp_path),
            "longitudinal-status",
            "--source-b1-run-id",
            "b1",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_b1_run_id"] == "b1"
    assert payload["screening_status"] == "SCREENING_READY"
    assert payload["confirmatory_status"] == "CONFIRMATORY_NOT_READY"
    assert payload["targets"]["operation"]["rolling_test_folds"] == 2
    assert not (tmp_path / "prediction_runs").exists()

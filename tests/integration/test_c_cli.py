from __future__ import annotations

import json
from pathlib import Path

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.cli import main
from personal_predictive_ai.events.models import EventActor, EventProvenance
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.state.sessions import SessionSegment
from personal_predictive_ai.storage.derived_store import DerivedStore


def _seed(db: Path, *, count: int = 20) -> None:
    actions = [
        NormalizedAction(
            action_id=f"act-{seq}",
            source_event_id=f"evt-{seq}",
            timestamp_ns=1_000 + seq,
            monotonic_seq=seq,
            actor=EventActor.HUMAN,
            provenance=EventProvenance.HUMAN_PHYSICAL,
            application="chrome.exe",
            operation="key_input",
        )
        for seq in range(1, count + 1)
    ]
    snapshots = [
        StateSnapshot(
            state_id=f"state-{seq}",
            source_event_id=f"evt-{seq}",
            timestamp_ns=1_000 + seq,
            monotonic_seq=seq,
            foreground_app={"name": "chrome.exe"},
            active_processes={"1": {"name": "chrome.exe", "pid": 1}},
            session_id="s1",
        )
        for seq in range(1, count + 1)
    ]
    sessions = [
        SessionSegment(
            session_id="s1",
            start_event_id="evt-1",
            start_ns=1_001,
            end_event_id=f"evt-{count}",
            end_ns=1_000 + count,
            reason="fixture",
        )
    ]
    store = DerivedStore(db)
    store.replace_run("b1", count, snapshots, actions, sessions, [])
    store.close()


def test_benchmark_c_cli_returns_explicit_target_statuses(tmp_path: Path, capsys) -> None:
    db = tmp_path / "events.db"
    _seed(db)

    result = main(
        [
            "--data-dir",
            str(tmp_path),
            "benchmark-c",
            "--source-b1-run-id",
            "b1",
            "--run-id",
            "cli-c",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == "cli-c"
    assert payload["source_b1_run_id"] == "b1"
    assert set(payload["target_space_statuses"]) == {"application", "operation", "joint"}
    assert set(payload["target_space_statuses"].values()) == {"INSUFFICIENT_PREDICTIVE_DIVERSITY"}
    assert (tmp_path / "prediction_runs" / "cli-c" / "validity_audit.json").exists()

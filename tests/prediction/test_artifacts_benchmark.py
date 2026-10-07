from __future__ import annotations

import json
from pathlib import Path

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.events.models import EventActor, EventProvenance
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.state.sessions import SessionSegment
from personal_predictive_ai.storage.derived_store import DerivedStore

SENTINEL = "PRIVATE_SENTINEL_DO_NOT_PERSIST"
EXPECTED_ARTIFACTS = (
    "dataset_manifest.json",
    "validity_audit.json",
    "split_manifest.json",
    "baseline_predictions.jsonl",
    "metrics.json",
    "ablation.json",
)


def _seed_degenerate_b1(db: Path, *, count: int = 20) -> None:
    actions = []
    snapshots = []
    for seq in range(1, count + 1):
        actions.append(
            NormalizedAction(
                action_id=f"act-{seq}",
                source_event_id=f"evt-{seq}",
                timestamp_ns=1_000 + seq,
                monotonic_seq=seq,
                actor=EventActor.HUMAN,
                provenance=EventProvenance.HUMAN_PHYSICAL,
                application="chrome.exe",
                operation="key_input",
                concrete=SENTINEL,
                fine={"exact": SENTINEL},
                context={"window_title": SENTINEL},
            )
        )
        snapshots.append(
            StateSnapshot(
                state_id=f"state-{seq}",
                source_event_id=f"evt-{seq}",
                timestamp_ns=1_000 + seq,
                monotonic_seq=seq,
                foreground_app={"name": "chrome.exe"},
                foreground_window={"title": SENTINEL},
                focused_ui_summary={"name": SENTINEL},
                active_processes={"1": {"name": "chrome.exe", "pid": 1}},
                session_id="s1",
            )
        )
    sessions = [
        SessionSegment(
            session_id="s1",
            start_event_id="evt-1",
            start_ns=1_000,
            end_event_id=f"evt-{count}",
            end_ns=1_000 + count,
            reason="fixture",
        )
    ]
    store = DerivedStore(db)
    store.replace_run("b1", count, snapshots, actions, sessions, [])
    store.close()


def _artifact_bytes(root: Path) -> dict[str, bytes]:
    return {name: (root / name).read_bytes() for name in EXPECTED_ARTIFACTS}


def test_c0_failure_writes_deterministic_safe_artifacts_and_never_claims_pass(
    tmp_path: Path,
) -> None:
    from personal_predictive_ai.prediction.benchmark import run_milestone_c

    db = tmp_path / "events.db"
    _seed_degenerate_b1(db)

    first = run_milestone_c(
        db,
        source_b1_run_id="b1",
        source_b2_run_id=None,
        run_id="c-run",
        output_root=tmp_path,
    )
    artifact_root = tmp_path / "prediction_runs" / "c-run"
    first_bytes = _artifact_bytes(artifact_root)
    second = run_milestone_c(
        db,
        source_b1_run_id="b1",
        source_b2_run_id=None,
        run_id="c-run",
        output_root=tmp_path,
    )
    second_bytes = _artifact_bytes(artifact_root)

    assert first == second
    assert first_bytes == second_bytes
    assert set(first.target_space_statuses.values()) == {"INSUFFICIENT_PREDICTIVE_DIVERSITY"}
    assert json.loads(first_bytes["metrics.json"]) == []
    assert first_bytes["baseline_predictions.jsonl"] == b""
    combined = b"".join(first_bytes.values())
    assert SENTINEL.encode() not in combined
    assert b'"PASS"' not in first_bytes["ablation.json"]


def test_manifest_records_source_high_water_and_all_target_spaces(tmp_path: Path) -> None:
    from personal_predictive_ai.prediction.benchmark import run_milestone_c

    db = tmp_path / "events.db"
    _seed_degenerate_b1(db, count=12)
    run_milestone_c(
        db,
        source_b1_run_id="b1",
        source_b2_run_id=None,
        run_id="manifest",
        output_root=tmp_path,
    )

    root = tmp_path / "prediction_runs" / "manifest"
    manifest = json.loads((root / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_b1_run_id"] == "b1"
    assert manifest["source_high_water"] == 12
    assert set(manifest["target_spaces"]) == {"application", "operation", "joint"}
    assert all(
        space["formal_target_provenance"] == "human_physical"
        for space in manifest["target_spaces"].values()
    )


def _seed_valid_b1(db: Path) -> None:
    actions = []
    snapshots = []
    sessions = []
    seq = 1
    labels = ("save", "run", "inspect")
    for session_index in range(5):
        session_id = f"s{session_index + 1}"
        start_ts = (session_index + 1) * 100_000
        for offset in range(50):
            ts = start_ts + offset
            operation = labels[offset % len(labels)]
            actions.append(
                NormalizedAction(
                    action_id=f"act-{seq}",
                    source_event_id=f"evt-{seq}",
                    timestamp_ns=ts,
                    monotonic_seq=seq,
                    actor=EventActor.HUMAN,
                    provenance=EventProvenance.HUMAN_PHYSICAL,
                    application="Code.exe",
                    operation=operation,
                )
            )
            snapshots.append(
                StateSnapshot(
                    state_id=f"state-{seq}",
                    source_event_id=f"evt-{seq}",
                    timestamp_ns=ts,
                    monotonic_seq=seq,
                    foreground_app={"name": "Code.exe"},
                    active_processes={"1": {"name": "Code.exe", "pid": 1}},
                    session_id=session_id,
                )
            )
            seq += 1
        sessions.append(
            SessionSegment(
                session_id=session_id,
                start_event_id=f"start-{session_id}",
                start_ns=start_ts,
                end_event_id=f"end-{session_id}",
                end_ns=start_ts + 49,
                reason="fixture",
            )
        )
    store = DerivedStore(db)
    store.replace_run("b1-valid", seq - 1, snapshots, actions, sessions, [])
    store.close()


def test_formal_pipeline_emits_transition_only_diagnostics(tmp_path: Path) -> None:
    from personal_predictive_ai.prediction.benchmark import run_milestone_c

    db = tmp_path / "events.db"
    _seed_valid_b1(db)
    summary = run_milestone_c(
        db,
        source_b1_run_id="b1-valid",
        source_b2_run_id=None,
        run_id="formal",
        output_root=tmp_path,
    )

    root = tmp_path / "prediction_runs" / "formal"
    metrics = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
    operation_metrics = [row for row in metrics if row["target_space"] == "operation"]
    assert operation_metrics
    assert any(row["split"] == "validation" for row in operation_metrics)
    assert any(row["split"] == "test" for row in operation_metrics)
    assert any(row["slice_name"] == "transition_only" for row in operation_metrics)
    ablation = json.loads((root / "ablation.json").read_text(encoding="utf-8"))
    assert "gate1" in ablation["targets"]["operation"]
    assert summary.target_space_statuses["operation"] != "INSUFFICIENT_PREDICTIVE_DIVERSITY"

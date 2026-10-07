from __future__ import annotations

import json
from pathlib import Path

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.events.models import EventActor, EventProvenance
from personal_predictive_ai.prediction.benchmark import run_milestone_c
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.state.sessions import SessionSegment
from personal_predictive_ai.storage.derived_store import DerivedStore


def _seed_real_shape(db: Path) -> None:
    actions: list[NormalizedAction] = []
    snapshots: list[StateSnapshot] = []
    for seq in range(1, 183):
        event_id = f"evt-{seq}"
        actions.append(
            NormalizedAction(
                action_id=f"action-{seq}",
                source_event_id=event_id,
                timestamp_ns=1_000_000 + seq,
                monotonic_seq=seq,
                actor=EventActor.HUMAN,
                provenance=EventProvenance.HUMAN_PHYSICAL,
                application="chrome.exe",
                operation="key_input",
            )
        )
        snapshots.append(
            StateSnapshot(
                state_id=f"state-{seq}",
                source_event_id=event_id,
                timestamp_ns=1_000_000 + seq,
                monotonic_seq=seq,
                foreground_app={"name": "chrome.exe"},
                session_id="session-1",
            )
        )

    session = SessionSegment(
        session_id="session-1",
        start_event_id="evt-1",
        start_ns=1_000_001,
        end_event_id="evt-182",
        end_ns=1_000_182,
        reason="end_of_stream",
    )
    store = DerivedStore(db)
    try:
        store.replace_run("b1-real-shape", 182, snapshots, actions, [session], [])
    finally:
        store.close()


def test_real_qualification_shape_cannot_produce_formal_prediction_pass(tmp_path: Path) -> None:
    db = tmp_path / "events.db"
    _seed_real_shape(db)

    summary = run_milestone_c(
        db,
        source_b1_run_id="b1-real-shape",
        source_b2_run_id=None,
        run_id="real-shape",
        output_root=tmp_path,
    )

    statuses = summary.target_space_statuses
    assert set(statuses) == {"application", "operation", "joint"}
    for target_space, status in statuses.items():
        assert status != "PASS", target_space
        assert status == "INSUFFICIENT_PREDICTIVE_DIVERSITY"

    audit = json.loads(
        (Path(summary.artifact_dir) / "validity_audit.json").read_text(encoding="utf-8")
    )
    for target_space in ("application", "operation", "joint"):
        report = audit["targets"][target_space]
        assert report["generalization_status"] == "NON_GENERALIZATION_DIAGNOSTIC"
        assert report["eligible_target_actions"] == 182
        assert report["session_count"] == 1

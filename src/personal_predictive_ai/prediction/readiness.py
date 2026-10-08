from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.prediction.config import PredictionConfigV1
from personal_predictive_ai.prediction.dataset import build_prediction_examples
from personal_predictive_ai.prediction.models import TargetSpace
from personal_predictive_ai.prediction.splits import build_session_forward_folds
from personal_predictive_ai.prediction.validity import audit_validity
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.state.sessions import SessionSegment


class TargetLongitudinalReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.longitudinal-target-readiness/v1"] = (
        "ppa.longitudinal-target-readiness/v1"
    )
    target_space: TargetSpace
    session_count: int = Field(ge=0)
    eligible_human_physical_actions: int = Field(ge=0)
    class_count: int = Field(ge=0)
    dominant_class_ratio: float = Field(ge=0.0, le=1.0)
    normalized_entropy: float = Field(ge=0.0, le=1.0)
    rolling_test_folds: int = Field(ge=0)
    independent_test_sessions: int = Field(ge=0)
    c0_status: str = Field(min_length=1)
    c0_reasons: tuple[str, ...] = ()
    screening_status: Literal["SCREENING_READY", "SCREENING_NOT_READY"]
    screening_reasons: tuple[str, ...] = ()
    confirmatory_status: Literal["CONFIRMATORY_READY", "CONFIRMATORY_NOT_READY"]
    confirmatory_reasons: tuple[str, ...] = ()


class LongitudinalReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.longitudinal-readiness/v1"] = "ppa.longitudinal-readiness/v1"
    source_b1_run_id: str = Field(min_length=1)
    source_high_water: int = Field(ge=0)
    targets: dict[str, TargetLongitudinalReadiness]
    screening_status: Literal["SCREENING_READY", "SCREENING_NOT_READY"]
    confirmatory_status: Literal["CONFIRMATORY_READY", "CONFIRMATORY_NOT_READY"]
    screening_ready_target_spaces: tuple[str, ...] = ()
    confirmatory_ready_target_spaces: tuple[str, ...] = ()


def read_b1_run(
    db_path: str | Path,
    source_b1_run_id: str,
) -> tuple[int, list[NormalizedAction], list[StateSnapshot], list[SessionSegment]]:
    path = Path(db_path)
    if not path.is_file():
        raise ValueError(f"database not found: {path}")
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    try:
        row = conn.execute(
            "SELECT source_high_water FROM derived_runs WHERE run_id = ?",
            (source_b1_run_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"B1 run not found: {source_b1_run_id}")
        source_high_water = int(row[0])
        action_rows = conn.execute(
            "SELECT data_json FROM b1_actions WHERE run_id = ? ORDER BY monotonic_seq, action_id",
            (source_b1_run_id,),
        ).fetchall()
        snapshot_rows = conn.execute(
            "SELECT data_json FROM b1_state_snapshots "
            "WHERE run_id = ? ORDER BY monotonic_seq, state_id",
            (source_b1_run_id,),
        ).fetchall()
        session_rows = conn.execute(
            "SELECT data_json FROM b1_sessions WHERE run_id = ? ORDER BY start_ns, session_id",
            (source_b1_run_id,),
        ).fetchall()
    finally:
        conn.close()

    actions = [NormalizedAction.model_validate_json(row[0]) for row in action_rows]
    snapshots = [StateSnapshot.model_validate_json(row[0]) for row in snapshot_rows]
    sessions = [SessionSegment.model_validate_json(row[0]) for row in session_rows]
    return source_high_water, actions, snapshots, sessions


def _target_readiness(
    *,
    target_space: TargetSpace,
    actions: list[NormalizedAction],
    snapshots: list[StateSnapshot],
    sessions: list[SessionSegment],
    config: PredictionConfigV1,
) -> TargetLongitudinalReadiness:
    examples = build_prediction_examples(
        actions,
        snapshots,
        sessions,
        target_space=target_space,
    )
    folds = build_session_forward_folds(examples)
    validity = audit_validity(examples, folds, config, target_space=target_space)
    independent_test_sessions = len(
        {session_id for fold in folds for session_id in fold.test_session_ids}
    )

    screening_reasons: list[str] = []
    if validity.session_count < 5:
        screening_reasons.append("sessions<5")
    if len(folds) < 2:
        screening_reasons.append("rolling_test_folds<2")
    screening_ready = not screening_reasons

    confirmatory_reasons: list[str] = []
    if validity.session_count < 8:
        confirmatory_reasons.append("sessions<8")
    if independent_test_sessions < 5:
        confirmatory_reasons.append("independent_test_sessions<5")
    if validity.decision.status != "PASS":
        confirmatory_reasons.append("c0_not_pass")
    confirmatory_ready = not confirmatory_reasons

    return TargetLongitudinalReadiness(
        target_space=target_space,
        session_count=validity.session_count,
        eligible_human_physical_actions=validity.eligible_target_actions,
        class_count=validity.class_count,
        dominant_class_ratio=validity.dominant_class_ratio,
        normalized_entropy=validity.normalized_entropy,
        rolling_test_folds=len(folds),
        independent_test_sessions=independent_test_sessions,
        c0_status=validity.decision.status,
        c0_reasons=validity.decision.reasons,
        screening_status="SCREENING_READY" if screening_ready else "SCREENING_NOT_READY",
        screening_reasons=tuple(screening_reasons),
        confirmatory_status=(
            "CONFIRMATORY_READY" if confirmatory_ready else "CONFIRMATORY_NOT_READY"
        ),
        confirmatory_reasons=tuple(confirmatory_reasons),
    )


def audit_longitudinal_status(
    db_path: str | Path,
    *,
    source_b1_run_id: str,
    config: PredictionConfigV1 | None = None,
) -> LongitudinalReadinessReport:
    cfg = config or PredictionConfigV1()
    source_high_water, actions, snapshots, sessions = read_b1_run(
        db_path,
        source_b1_run_id,
    )
    targets = {
        target_space.value: _target_readiness(
            target_space=target_space,
            actions=actions,
            snapshots=snapshots,
            sessions=sessions,
            config=cfg,
        )
        for target_space in TargetSpace
    }
    screening_ready = tuple(
        key for key, target in targets.items() if target.screening_status == "SCREENING_READY"
    )
    confirmatory_ready = tuple(
        key
        for key, target in targets.items()
        if target.confirmatory_status == "CONFIRMATORY_READY"
    )
    return LongitudinalReadinessReport(
        source_b1_run_id=source_b1_run_id,
        source_high_water=source_high_water,
        targets=targets,
        screening_status="SCREENING_READY" if screening_ready else "SCREENING_NOT_READY",
        confirmatory_status=(
            "CONFIRMATORY_READY" if confirmatory_ready else "CONFIRMATORY_NOT_READY"
        ),
        screening_ready_target_spaces=screening_ready,
        confirmatory_ready_target_spaces=confirmatory_ready,
    )


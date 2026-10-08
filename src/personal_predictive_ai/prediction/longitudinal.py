from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from personal_predictive_ai.diagnostics.state_replay import derive_b1
from personal_predictive_ai.events.models import EventProvenance
from personal_predictive_ai.prediction.config import PredictionConfigV1
from personal_predictive_ai.prediction.dataset import target_label
from personal_predictive_ai.prediction.models import TargetSpace
from personal_predictive_ai.prediction.readiness import (
    LongitudinalReadinessReport,
    audit_longitudinal_status,
    read_b1_run,
)

_SCREENING_MIN_SESSIONS = 5
_CONFIRMATORY_MIN_SESSIONS = 8


class LongitudinalTargetProgress(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.longitudinal-target-progress/v1"] = (
        "ppa.longitudinal-target-progress/v1"
    )
    target_space: TargetSpace
    label_counts: dict[str, int]
    target_count_shortfall: int = Field(ge=0)
    classes_to_c0: int = Field(ge=0)
    minority_actions_needed_for_dominant_ratio: int = Field(ge=0)
    dominant_ratio_excess: float = Field(ge=0.0)
    normalized_entropy_shortfall: float = Field(ge=0.0)
    sessions_to_screening: int = Field(ge=0)
    rolling_test_folds_to_screening: int = Field(ge=0)
    sessions_to_confirmatory: int = Field(ge=0)
    independent_test_sessions_to_confirmatory: int = Field(ge=0)
    c0_status: str = Field(min_length=1)
    c0_reasons: tuple[str, ...] = ()
    screening_status: str = Field(min_length=1)
    screening_reasons: tuple[str, ...] = ()
    confirmatory_status: str = Field(min_length=1)
    confirmatory_reasons: tuple[str, ...] = ()


class LongitudinalCycleReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.longitudinal-cycle/v1"] = "ppa.longitudinal-cycle/v1"
    source_b1_run_id: str = Field(min_length=1)
    source_high_water: int = Field(ge=0)
    session_count: int = Field(ge=0)
    human_physical_actions: int = Field(ge=0)
    application_counts: dict[str, int]
    operation_counts: dict[str, int]
    joint_counts: dict[str, int]
    readiness: LongitudinalReadinessReport
    progress: dict[str, LongitudinalTargetProgress]


def _sorted_counts(values: list[str]) -> dict[str, int]:
    counts = Counter(values)
    return {key: counts[key] for key in sorted(counts, key=str.casefold)}


def _minority_actions_needed_for_ratio(
    label_counts: dict[str, int],
    *,
    max_ratio: float,
) -> int:
    total = sum(label_counts.values())
    if total <= 0:
        return 0
    dominant = max(label_counts.values())
    if dominant / total <= max_ratio:
        return 0
    return max(0, math.ceil(dominant / max_ratio - total))


def _progress_for_target(
    readiness: LongitudinalReadinessReport,
    target_space: TargetSpace,
    label_counts: dict[str, int],
    config: PredictionConfigV1,
) -> LongitudinalTargetProgress:
    target = readiness.targets[target_space.value]
    required_classes = 2 if target_space is TargetSpace.APPLICATION else config.c0_min_classes
    screening_ready = target.screening_status == "SCREENING_READY" and target.c0_status == "PASS"
    screening_reasons = list(target.screening_reasons)
    if target.c0_status != "PASS":
        screening_reasons.extend(
            reason for reason in target.c0_reasons if reason not in screening_reasons
        )

    return LongitudinalTargetProgress(
        target_space=target_space,
        label_counts=label_counts,
        target_count_shortfall=max(
            0, config.c0_min_targets - target.eligible_human_physical_actions
        ),
        classes_to_c0=max(0, required_classes - target.class_count),
        minority_actions_needed_for_dominant_ratio=_minority_actions_needed_for_ratio(
            label_counts,
            max_ratio=config.c0_max_dominant_ratio,
        ),
        dominant_ratio_excess=max(0.0, target.dominant_class_ratio - config.c0_max_dominant_ratio),
        normalized_entropy_shortfall=max(
            0.0, config.c0_min_normalized_entropy - target.normalized_entropy
        ),
        sessions_to_screening=max(0, _SCREENING_MIN_SESSIONS - target.session_count),
        rolling_test_folds_to_screening=max(
            0, config.min_rolling_test_folds - target.rolling_test_folds
        ),
        sessions_to_confirmatory=max(0, _CONFIRMATORY_MIN_SESSIONS - target.session_count),
        independent_test_sessions_to_confirmatory=max(
            0,
            config.confirmatory_min_independent_test_sessions - target.independent_test_sessions,
        ),
        c0_status=target.c0_status,
        c0_reasons=target.c0_reasons,
        screening_status="SCREENING_READY" if screening_ready else "SCREENING_NOT_READY",
        screening_reasons=tuple(screening_reasons),
        confirmatory_status=target.confirmatory_status,
        confirmatory_reasons=target.confirmatory_reasons,
    )


def summarize_longitudinal_run(
    db_path: str | Path,
    *,
    source_b1_run_id: str,
    config: PredictionConfigV1 | None = None,
) -> LongitudinalCycleReport:
    cfg = config or PredictionConfigV1()
    readiness = audit_longitudinal_status(
        db_path,
        source_b1_run_id=source_b1_run_id,
        config=cfg,
    )
    _, all_actions, _, sessions = read_b1_run(db_path, source_b1_run_id)
    actions = [
        action
        for action in all_actions
        if action.provenance is EventProvenance.HUMAN_PHYSICAL
    ]

    counts_by_target: dict[TargetSpace, dict[str, int]] = {}
    for target_space in TargetSpace:
        labels = [
            label
            for action in actions
            if (label := target_label(action, target_space)) is not None
        ]
        counts_by_target[target_space] = _sorted_counts(labels)
    progress = {
        target_space.value: _progress_for_target(
            readiness,
            target_space,
            counts_by_target[target_space],
            cfg,
        )
        for target_space in TargetSpace
    }
    return LongitudinalCycleReport(
        source_b1_run_id=source_b1_run_id,
        source_high_water=readiness.source_high_water,
        session_count=len(sessions),
        human_physical_actions=len(actions),
        application_counts=counts_by_target[TargetSpace.APPLICATION],
        operation_counts=counts_by_target[TargetSpace.OPERATION],
        joint_counts=counts_by_target[TargetSpace.JOINT],
        readiness=readiness,
        progress=progress,
    )


def run_longitudinal_cycle(
    db_path: str | Path,
    *,
    run_id: str,
    config: PredictionConfigV1 | None = None,
) -> LongitudinalCycleReport:
    derive_b1(db_path, run_id=run_id)
    return summarize_longitudinal_run(
        db_path,
        source_b1_run_id=run_id,
        config=config,
    )

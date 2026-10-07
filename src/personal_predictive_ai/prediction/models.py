from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TargetSpace(str, Enum):
    APPLICATION = "application"
    OPERATION = "operation"
    JOINT = "joint"


class StructuredContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.structured-context/v1"] = "ppa.structured-context/v1"
    foreground_application: str | None = None
    previous_operation: str | None = None
    recent_joint_actions: tuple[str, ...] = ()
    active_process_names: tuple[str, ...] = ()
    recent_exogenous_event_types: tuple[str, ...] = ()
    exogenous_event_type_availability: Literal[
        "AVAILABLE", "UNAVAILABLE_FROM_B1_V1"
    ] = "UNAVAILABLE_FROM_B1_V1"
    idle_bucket: str | None = None
    time_of_day_bucket: str | None = None


class PredictionExample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    schema_version: Literal["ppa.prediction-example/v1"] = "ppa.prediction-example/v1"
    sample_id: str = Field(min_length=1)
    source_b1_run_id: str | None = None
    target_space: TargetSpace
    session_id: str = Field(min_length=1)
    cutoff_seq: int = Field(ge=1)
    target_timestamp_ns: int = Field(ge=0)
    target_action_id: str = Field(min_length=1)
    target_label: str = Field(min_length=1)
    history_labels: tuple[str, ...] = ()
    joint_history: tuple[str, ...] = ()
    pre_state_id: str | None = None
    context: StructuredContext
    eligible_memory_ids: tuple[str, ...] = ()


class PredictionVocabulary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    schema_version: Literal["ppa.prediction-vocabulary/v1"] = "ppa.prediction-vocabulary/v1"
    target_space: TargetSpace
    labels: tuple[str, ...]
    unseen_token: str = Field(default="__UNSEEN__", min_length=1)


class PredictionDistribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    schema_version: Literal["ppa.prediction-distribution/v1"] = (
        "ppa.prediction-distribution/v1"
    )
    predictor_id: str = Field(min_length=1)
    target_space: TargetSpace
    probabilities: dict[str, float]
    sample_id: str | None = None


class PredictionFold(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.prediction-fold/v1"] = "ppa.prediction-fold/v1"
    fold_id: str = Field(min_length=1)
    train_session_ids: tuple[str, ...] = ()
    validation_session_ids: tuple[str, ...] = ()
    test_session_ids: tuple[str, ...] = ()
    train_sample_ids: tuple[str, ...] = ()
    validation_sample_ids: tuple[str, ...] = ()
    test_sample_ids: tuple[str, ...] = ()
    train_high_water: int = Field(default=0, ge=0)
    validation_start_seq: int | None = Field(default=None, ge=1)
    test_start_seq: int | None = Field(default=None, ge=1)


class ValidityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.validity-decision/v1"] = "ppa.validity-decision/v1"
    status: str = Field(min_length=1)
    eligible_for_formal_comparison: bool
    reasons: tuple[str, ...] = ()


class MetricReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    schema_version: Literal["ppa.metric-report/v1"] = "ppa.metric-report/v1"
    predictor_id: str = Field(min_length=1)
    fold_id: str = Field(min_length=1)
    target_space: TargetSpace
    slice_name: str = "all"
    sample_count: int = Field(ge=0)
    top1_accuracy: float = Field(ge=0.0, le=1.0)
    hit_rate_at_3: float = Field(ge=0.0, le=1.0)
    mrr: float = Field(ge=0.0, le=1.0)
    nll: float = Field(ge=0.0)
    macro_f1: float | None = Field(default=None, ge=0.0, le=1.0)
    coverage: float = Field(ge=0.0, le=1.0)
    unseen_target_rate: float = Field(ge=0.0, le=1.0)


class GateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.gate-decision/v1"] = "ppa.gate-decision/v1"
    gate_name: str = Field(min_length=1)
    status: str = Field(min_length=1)
    passed: bool
    fold_count: int = Field(default=0, ge=0)
    positive_fold_count: int = Field(default=0, ge=0)
    median_delta_nll: float | None = None
    effect_threshold: float | None = Field(default=None, ge=0.0)
    inferential_status: str = Field(default="DESCRIPTIVE_ONLY", min_length=1)
    reasons: tuple[str, ...] = ()

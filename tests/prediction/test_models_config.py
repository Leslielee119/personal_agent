from __future__ import annotations

import importlib.util

import pytest
from pydantic import ValidationError


def _load_contracts():
    models_spec = importlib.util.find_spec("personal_predictive_ai.prediction.models")
    config_spec = importlib.util.find_spec("personal_predictive_ai.prediction.config")
    assert models_spec is not None, "prediction models module must exist"
    assert config_spec is not None, "prediction config module must exist"

    from personal_predictive_ai.prediction.config import PredictionConfigV1
    from personal_predictive_ai.prediction.models import StructuredContext, TargetSpace

    return PredictionConfigV1, StructuredContext, TargetSpace


def test_target_spaces_and_frozen_thresholds_are_exact() -> None:
    PredictionConfigV1, _, TargetSpace = _load_contracts()

    assert [item.value for item in TargetSpace] == ["application", "operation", "joint"]

    config = PredictionConfigV1()
    assert config.schema_version == "ppa.prediction-config/v1"
    assert config.c0_min_sessions == 4
    assert config.c0_min_targets == 200
    assert config.c0_min_classes == 3
    assert config.c0_max_dominant_ratio == 0.90
    assert config.c0_min_normalized_entropy == 0.25
    assert config.c0_min_test_classes == 2
    assert config.c0_min_test_samples == 40
    assert config.suffix_ks == (1, 2, 3, 5)
    assert config.unseen_token == "__UNSEEN__"
    assert config.primary_metric == "nll"
    assert config.nll_absolute_min_effect == 0.01
    assert config.nll_relative_min_effect == 0.01
    assert config.min_rolling_test_folds == 2
    assert config.confirmatory_min_independent_test_sessions == 5
    assert config.memory_min_available_samples == 40
    assert config.memory_min_coverage == 0.20
    assert config.memory_min_exposed_test_sessions == 2
    assert config.memory_min_distinct_active_memories == 2

    with pytest.raises(ValidationError):
        config.c0_min_sessions = 3


def test_structured_context_is_strict_frozen_and_allowlisted() -> None:
    _, StructuredContext, _ = _load_contracts()

    context = StructuredContext(
        foreground_application="Code.exe",
        previous_operation="key_input",
        recent_joint_actions=("Code.exe::key_input",),
        active_process_names=("Code.exe", "python.exe"),
        recent_exogenous_event_types=(),
        exogenous_event_type_availability="UNAVAILABLE_FROM_B1_V1",
        idle_bucket="lt_10s",
        time_of_day_bucket=None,
    )
    assert context.foreground_application == "Code.exe"

    with pytest.raises(ValidationError):
        context.previous_operation = "mouse_click"

    with pytest.raises(ValidationError):
        StructuredContext(
            foreground_application="Code.exe",
            previous_operation=None,
            recent_joint_actions=(),
            active_process_names=(),
            recent_exogenous_event_types=(),
            exogenous_event_type_availability="UNAVAILABLE_FROM_B1_V1",
            idle_bucket=None,
            time_of_day_bucket=None,
            window_title="secret title",
        )

    forbidden = {
        "exact_key_text",
        "window_title",
        "screenshot",
        "clipboard",
        "ui_text",
        "credential",
    }
    assert forbidden.isdisjoint(StructuredContext.model_fields)


def test_prediction_contract_models_are_strict_and_frozen() -> None:
    _load_contracts()
    from personal_predictive_ai.prediction.models import (
        GateDecision,
        MetricReport,
        PredictionDistribution,
        PredictionExample,
        PredictionFold,
        PredictionVocabulary,
        ValidityDecision,
    )

    assert {
        "PredictionExample",
        "PredictionVocabulary",
        "PredictionDistribution",
        "PredictionFold",
        "ValidityDecision",
        "MetricReport",
        "GateDecision",
    }

    for model_type in (
        PredictionExample,
        PredictionVocabulary,
        PredictionDistribution,
        PredictionFold,
        ValidityDecision,
        MetricReport,
        GateDecision,
    ):
        assert model_type.model_config.get("extra") == "forbid"
        assert model_type.model_config.get("frozen") is True

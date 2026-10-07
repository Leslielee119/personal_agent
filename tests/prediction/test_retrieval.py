from __future__ import annotations

import importlib.util

from personal_predictive_ai.prediction.baselines import GlobalFrequencyPredictor
from personal_predictive_ai.prediction.config import PredictionConfigV1
from personal_predictive_ai.prediction.metrics import build_vocabulary
from personal_predictive_ai.prediction.models import (
    PredictionExample,
    StructuredContext,
    TargetSpace,
)


def _load_api():
    assert importlib.util.find_spec("personal_predictive_ai.prediction.retrieval") is not None
    from personal_predictive_ai.prediction.retrieval import (
        StructuredRetrievalPredictor,
        structured_similarity,
    )

    return StructuredRetrievalPredictor, structured_similarity


def _example(
    sample_id: str,
    seq: int,
    label: str,
    *,
    app: str = "Code.exe",
    previous: str = "save",
    actions: tuple[str, ...] = ("Code.exe::save",),
    processes: tuple[str, ...] = ("Code.exe",),
    idle: str = "lt_10s",
) -> PredictionExample:
    return PredictionExample(
        sample_id=sample_id,
        target_space=TargetSpace.OPERATION,
        session_id="s1",
        cutoff_seq=seq,
        target_timestamp_ns=seq,
        target_action_id=f"act-{sample_id}",
        target_label=label,
        history_labels=tuple(item.split("::")[-1] for item in actions),
        joint_history=actions,
        context=StructuredContext(
            foreground_application=app,
            previous_operation=previous,
            recent_joint_actions=actions[-3:],
            active_process_names=processes,
            recent_exogenous_event_types=(),
            idle_bucket=idle,
        ),
    )


def test_retrieval_constants_are_frozen() -> None:
    _load_api()
    config = PredictionConfigV1()
    assert config.retrieval_top_k == 20
    assert config.retrieval_neighbor_mass == 0.99
    assert config.retrieval_weight_foreground_application == 1.0
    assert config.retrieval_weight_previous_operation == 1.0
    assert config.retrieval_weight_process_jaccard == 1.0
    assert config.retrieval_weight_exogenous_jaccard == 1.0
    assert config.retrieval_weight_suffix == 1.0
    assert config.retrieval_weight_idle_bucket == 1.0
    assert config.retrieval_weight_time_of_day == 0.0


def test_similarity_is_deterministic_and_set_order_independent() -> None:
    _, structured_similarity = _load_api()
    config = PredictionConfigV1()
    left = StructuredContext(
        foreground_application="Code.exe",
        previous_operation="save",
        recent_joint_actions=("Code.exe::edit", "Code.exe::save"),
        active_process_names=("Code.exe", "python.exe"),
        recent_exogenous_event_types=("notification", "filesystem"),
        idle_bucket="lt_10s",
    )
    right = StructuredContext(
        foreground_application="Code.exe",
        previous_operation="save",
        recent_joint_actions=("Code.exe::edit", "Code.exe::save"),
        active_process_names=("python.exe", "Code.exe"),
        recent_exogenous_event_types=("filesystem", "notification"),
        idle_bucket="lt_10s",
    )

    first = structured_similarity(left, right, config)
    second = structured_similarity(left, right, config)

    assert first == second
    assert first > 0.0


def test_predictor_excludes_self_and_future_candidates_even_if_fit_pool_contains_them() -> None:
    StructuredRetrievalPredictor, _ = _load_api()
    train = [
        _example("past", 5, "a"),
        _example("query", 10, "b"),
        _example("future", 20, "b"),
    ]
    vocabulary = build_vocabulary(train)
    predictor = StructuredRetrievalPredictor().fit(train, vocabulary)
    query = _example("query", 10, "a")

    distribution = predictor.predict(query)

    assert distribution.probabilities["a"] > distribution.probabilities["b"]


def test_empty_neighbor_case_matches_global_frequency_backoff() -> None:
    StructuredRetrievalPredictor, _ = _load_api()
    train = [
        _example("one", 1, "a", app="Code.exe", previous="save"),
        _example("two", 2, "b", app="Code.exe", previous="save"),
    ]
    vocabulary = build_vocabulary(train)
    retrieval = StructuredRetrievalPredictor().fit(train, vocabulary)
    global_predictor = GlobalFrequencyPredictor().fit(train, vocabulary)
    query = _example(
        "query",
        10,
        "a",
        app="Browser.exe",
        previous="click",
        actions=("Browser.exe::click",),
        processes=("Browser.exe",),
        idle="ge_5m",
    )

    assert retrieval.predict(query).probabilities == global_predictor.predict(query).probabilities


def test_training_order_permutations_produce_identical_predictions() -> None:
    StructuredRetrievalPredictor, _ = _load_api()
    train = [
        _example("one", 1, "a", previous="save"),
        _example("two", 2, "b", previous="run"),
        _example("three", 3, "a", previous="save"),
    ]
    vocabulary = build_vocabulary(train)
    query = _example("query", 10, "a", previous="save")

    first = StructuredRetrievalPredictor().fit(train, vocabulary).predict(query)
    second = StructuredRetrievalPredictor().fit(list(reversed(train)), vocabulary).predict(query)

    assert first.probabilities == second.probabilities

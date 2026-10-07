from __future__ import annotations

import importlib.util

from personal_predictive_ai.prediction.config import PredictionConfigV1
from personal_predictive_ai.prediction.metrics import (
    build_vocabulary,
    score_predictions,
    transition_only_slice,
)
from personal_predictive_ai.prediction.models import (
    MetricReport,
    PredictionExample,
    StructuredContext,
    TargetSpace,
)


def _load_baselines():
    assert importlib.util.find_spec("personal_predictive_ai.prediction.baselines") is not None
    from personal_predictive_ai.prediction.baselines import (
        BigramPredictor,
        ContextualFrequencyPredictor,
        GlobalFrequencyPredictor,
        PersistencePredictor,
        TrigramBackoffPredictor,
        select_action_only_baseline,
    )

    return (
        GlobalFrequencyPredictor,
        PersistencePredictor,
        ContextualFrequencyPredictor,
        BigramPredictor,
        TrigramBackoffPredictor,
        select_action_only_baseline,
    )


def _example(
    seq: int,
    label: str,
    *,
    history: tuple[str, ...] = (),
    app: str = "Code.exe",
    previous_operation: str | None = None,
) -> PredictionExample:
    return PredictionExample(
        sample_id=f"sample-{seq}",
        target_space=TargetSpace.OPERATION,
        session_id="s1",
        cutoff_seq=seq,
        target_timestamp_ns=seq,
        target_action_id=f"act-{seq}",
        target_label=label,
        history_labels=history,
        joint_history=tuple(f"{app}::{item}" for item in history),
        context=StructuredContext(
            foreground_application=app,
            previous_operation=(
                previous_operation
                if previous_operation is not None
                else (history[-1] if history else None)
            ),
            recent_joint_actions=tuple(f"{app}::{item}" for item in history[-3:]),
            active_process_names=(app,),
        ),
    )


def _metric(predictor_id: str, nll: float, *, top1: float = 0.5) -> MetricReport:
    return MetricReport(
        predictor_id=predictor_id,
        fold_id="validation",
        target_space=TargetSpace.OPERATION,
        sample_count=10,
        top1_accuracy=top1,
        hit_rate_at_3=top1,
        mrr=top1,
        nll=nll,
        macro_f1=top1,
        coverage=1.0,
        unseen_target_rate=0.0,
    )


def test_baseline_smoothing_constants_are_frozen_in_config() -> None:
    _load_baselines()
    config = PredictionConfigV1()
    assert config.predictor_unseen_mass == 0.01
    assert config.persistence_copy_mass == 0.99
    assert config.ngram_absolute_discount == 0.75


def test_global_frequency_outputs_full_normalized_distribution() -> None:
    GlobalFrequencyPredictor, *_ = _load_baselines()
    train = [_example(1, "a"), _example(2, "a", history=("a",)), _example(3, "b")]
    vocabulary = build_vocabulary(train)
    predictor = GlobalFrequencyPredictor().fit(train, vocabulary)

    distribution = predictor.predict(_example(10, "a", history=("a",)))

    assert set(distribution.probabilities) == set(vocabulary.labels)
    assert abs(sum(distribution.probabilities.values()) - 1.0) < 1e-12
    assert distribution.probabilities["a"] > distribution.probabilities["b"]
    assert distribution.probabilities["__UNSEEN__"] > 0.0


def test_persistence_copies_prior_label_and_safely_backs_off_without_history() -> None:
    GlobalFrequencyPredictor, PersistencePredictor, *_ = _load_baselines()
    train = [_example(1, "a"), _example(2, "b", history=("a",))]
    vocabulary = build_vocabulary(train)
    global_predictor = GlobalFrequencyPredictor().fit(train, vocabulary)
    persistence = PersistencePredictor().fit(train, vocabulary)

    copied = persistence.predict(_example(10, "b", history=("a",)))
    fallback_query = _example(11, "b", history=())
    fallback = persistence.predict(fallback_query)
    global_fallback = global_predictor.predict(fallback_query)

    assert max(copied.probabilities, key=copied.probabilities.get) == "a"
    assert fallback.probabilities == global_fallback.probabilities


def test_bigram_and_trigram_predictions_do_not_depend_on_evaluation_target_label() -> None:
    *_, BigramPredictor, TrigramBackoffPredictor, _ = _load_baselines()
    train = [
        _example(1, "a"),
        _example(2, "b", history=("a",)),
        _example(3, "c", history=("a", "b")),
        _example(4, "b", history=("a", "b", "c")),
    ]
    vocabulary = build_vocabulary(train)
    for predictor_type in (BigramPredictor, TrigramBackoffPredictor):
        predictor = predictor_type().fit(train, vocabulary)
        query_a = _example(10, "a", history=("a", "b"))
        query_c = _example(10, "c", history=("a", "b"))
        assert predictor.predict(query_a).probabilities == predictor.predict(query_c).probabilities


def test_trigram_unseen_context_backs_off_to_bigram_deterministically() -> None:
    *_, BigramPredictor, TrigramBackoffPredictor, _ = _load_baselines()
    train = [
        _example(1, "a"),
        _example(2, "b", history=("a",)),
        _example(3, "c", history=("a", "b")),
        _example(4, "c", history=("b",)),
    ]
    vocabulary = build_vocabulary(train)
    bigram = BigramPredictor().fit(train, vocabulary)
    trigram = TrigramBackoffPredictor().fit(train, vocabulary)
    query = _example(20, "c", history=("never-seen", "b"))

    assert trigram.predict(query).probabilities == bigram.predict(query).probabilities


def test_validation_selection_uses_lowest_nll_with_lexical_tie_break() -> None:
    *_, select_action_only_baseline = _load_baselines()
    reports = [
        _metric("z-model", 0.8, top1=0.99),
        _metric("b-model", 0.6, top1=0.10),
        _metric("a-model", 0.6, top1=0.05),
    ]

    assert select_action_only_baseline(reports) == "a-model"


def test_persistence_heavy_all_sample_score_collapses_on_transition_only_slice() -> None:
    _, PersistencePredictor, *_ = _load_baselines()
    train = [
        _example(1, "a"),
        _example(2, "a", history=("a",)),
        _example(3, "b", history=("a", "a")),
        _example(4, "b", history=("a", "a", "b")),
    ]
    vocabulary = build_vocabulary(train)
    predictor = PersistencePredictor().fit(train, vocabulary)
    evaluation = [
        _example(10, "a", history=("a",)),
        _example(11, "a", history=("a", "a")),
        _example(12, "a", history=("a", "a", "a")),
        _example(13, "b", history=("a", "a", "a", "a")),
    ]
    all_distributions = [predictor.predict(item) for item in evaluation]
    all_report = score_predictions(
        evaluation,
        all_distributions,
        vocabulary,
        fold_id="all",
    )
    switches = transition_only_slice(evaluation)
    switch_report = score_predictions(
        switches,
        [predictor.predict(item) for item in switches],
        vocabulary,
        fold_id="switch",
        slice_name="transition_only",
    )

    assert all_report.top1_accuracy > switch_report.top1_accuracy
    assert switch_report.top1_accuracy == 0.0

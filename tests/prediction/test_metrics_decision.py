from __future__ import annotations

import importlib.util
import math

from personal_predictive_ai.prediction.models import (
    MetricReport,
    PredictionDistribution,
    PredictionExample,
    PredictionVocabulary,
    StructuredContext,
    TargetSpace,
)


def _load_api():
    assert importlib.util.find_spec("personal_predictive_ai.prediction.metrics") is not None
    assert importlib.util.find_spec("personal_predictive_ai.prediction.decision") is not None
    from personal_predictive_ai.prediction.decision import (
        evaluate_gate,
        nll_effect_threshold,
    )
    from personal_predictive_ai.prediction.metrics import (
        build_vocabulary,
        score_predictions,
        transition_only_slice,
    )

    return (
        build_vocabulary,
        score_predictions,
        transition_only_slice,
        nll_effect_threshold,
        evaluate_gate,
    )


def _example(
    sample_id: str,
    label: str,
    *,
    history: tuple[str, ...] = (),
) -> PredictionExample:
    return PredictionExample(
        sample_id=sample_id,
        target_space=TargetSpace.OPERATION,
        session_id="s1",
        cutoff_seq=int(sample_id.rsplit("-", 1)[-1]),
        target_timestamp_ns=1,
        target_action_id=f"act-{sample_id}",
        target_label=label,
        history_labels=history,
        joint_history=tuple(f"Code::{item}" for item in history),
        context=StructuredContext(previous_operation=history[-1] if history else None),
    )


def _metric(fold_id: str, nll: float, *, top1: float = 0.5) -> MetricReport:
    return MetricReport(
        predictor_id="p",
        fold_id=fold_id,
        target_space=TargetSpace.OPERATION,
        sample_count=100,
        top1_accuracy=top1,
        hit_rate_at_3=top1,
        mrr=top1,
        nll=nll,
        macro_f1=top1,
        coverage=1.0,
        unseen_target_rate=0.0,
    )


def test_vocabulary_is_training_only_sorted_with_reserved_unseen_token() -> None:
    build_vocabulary, *_ = _load_api()
    vocabulary = build_vocabulary([_example("sample-1", "z"), _example("sample-2", "a")])

    assert vocabulary.labels == ("a", "z", "__UNSEEN__")
    assert vocabulary.unseen_token == "__UNSEEN__"


def test_unseen_target_uses_unseen_probability_for_nll_but_never_ranking_hit() -> None:
    _, score_predictions, *_ = _load_api()
    example = _example("sample-1", "new-label")
    vocabulary = PredictionVocabulary(
        target_space=TargetSpace.OPERATION,
        labels=("a", "b", "__UNSEEN__"),
    )
    distribution = PredictionDistribution(
        predictor_id="test",
        target_space=TargetSpace.OPERATION,
        sample_id=example.sample_id,
        probabilities={"a": 0.1, "b": 0.2, "__UNSEEN__": 0.7},
    )

    report = score_predictions([example], [distribution], vocabulary, fold_id="fold-1")

    assert math.isclose(report.nll, -math.log(0.7))
    assert report.top1_accuracy == 0.0
    assert report.hit_rate_at_3 == 0.0
    assert report.mrr == 0.0
    assert report.unseen_target_rate == 1.0
    assert report.coverage == 0.0


def test_transition_only_slice_excludes_first_and_self_transitions() -> None:
    _, _, transition_only_slice, *_ = _load_api()
    examples = [
        _example("sample-1", "a", history=()),
        _example("sample-2", "a", history=("a",)),
        _example("sample-3", "b", history=("a", "a")),
    ]

    assert [item.sample_id for item in transition_only_slice(examples)] == ["sample-3"]


def test_two_fold_gate_requires_both_positive_and_effect_threshold() -> None:
    *_, nll_effect_threshold, evaluate_gate = _load_api()
    reference = [_metric("f1", 1.0), _metric("f2", 1.0)]
    passing = [_metric("f1", 0.98), _metric("f2", 0.99)]
    direction_fail = [_metric("f1", 0.97), _metric("f2", 1.01)]
    effect_fail = [_metric("f1", 0.999), _metric("f2", 0.999)]

    assert nll_effect_threshold(1.0) == 0.01
    assert evaluate_gate(passing, reference, independent_test_sessions=5).passed is True
    assert evaluate_gate(direction_fail, reference, independent_test_sessions=5).passed is False
    assert evaluate_gate(effect_fail, reference, independent_test_sessions=5).passed is False


def test_three_fold_gate_allows_one_negative_when_two_thirds_and_median_pass() -> None:
    *_, evaluate_gate = _load_api()
    reference = [_metric("f1", 1.0), _metric("f2", 1.0), _metric("f3", 1.0)]
    candidate = [_metric("f1", 0.98), _metric("f2", 0.98), _metric("f3", 1.01)]

    decision = evaluate_gate(candidate, reference, independent_test_sessions=5)

    assert decision.passed is True
    assert decision.positive_fold_count == 2
    assert math.isclose(decision.median_delta_nll, 0.02)


def test_secondary_metrics_cannot_rescue_nll_failure_and_four_sessions_are_descriptive() -> None:
    *_, evaluate_gate = _load_api()
    reference = [_metric("f1", 1.0, top1=0.1), _metric("f2", 1.0, top1=0.1)]
    candidate = [_metric("f1", 1.1, top1=0.99), _metric("f2", 1.1, top1=0.99)]

    decision = evaluate_gate(candidate, reference, independent_test_sessions=4)

    assert decision.passed is False
    assert decision.inferential_status == "DESCRIPTIVE_ONLY"

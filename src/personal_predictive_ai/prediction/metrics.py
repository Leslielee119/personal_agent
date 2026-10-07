from __future__ import annotations

import math
from collections.abc import Iterable

from personal_predictive_ai.prediction.models import (
    MetricReport,
    PredictionDistribution,
    PredictionExample,
    PredictionVocabulary,
)


def build_vocabulary(
    train_examples: Iterable[PredictionExample],
    *,
    unseen_token: str = "__UNSEEN__",
) -> PredictionVocabulary:
    examples = list(train_examples)
    if not examples:
        raise ValueError("training examples are required to build a vocabulary")
    target_space = examples[0].target_space
    if any(item.target_space is not target_space for item in examples):
        raise ValueError("vocabulary requires one target space at a time")
    labels = {item.target_label for item in examples}
    if unseen_token in labels:
        raise ValueError("reserved unseen token collides with a training label")
    ordered = tuple(sorted(labels)) + (unseen_token,)
    return PredictionVocabulary(
        target_space=target_space,
        labels=ordered,
        unseen_token=unseen_token,
    )


def _ranked_labels(distribution: PredictionDistribution) -> list[str]:
    return [
        label
        for label, _ in sorted(
            distribution.probabilities.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]


def _validate_distribution(
    distribution: PredictionDistribution,
    vocabulary: PredictionVocabulary,
) -> None:
    expected = set(vocabulary.labels)
    observed = set(distribution.probabilities)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise ValueError(f"distribution vocabulary mismatch: missing={missing} extra={extra}")
    if distribution.target_space is not vocabulary.target_space:
        raise ValueError("distribution target space does not match vocabulary")
    values = list(distribution.probabilities.values())
    if any((not math.isfinite(value)) or value < 0.0 for value in values):
        raise ValueError("distribution probabilities must be finite and nonnegative")
    if not math.isclose(sum(values), 1.0, rel_tol=1e-9, abs_tol=1e-12):
        raise ValueError("distribution probabilities must sum to one")


def _macro_f1(
    examples: list[PredictionExample],
    predictions: list[str],
    vocabulary: PredictionVocabulary,
) -> float | None:
    labels = [label for label in vocabulary.labels if label != vocabulary.unseen_token]
    if len(labels) < 2:
        return None
    scores: list[float] = []
    for label in labels:
        tp = fp = fn = 0
        for example, predicted in zip(examples, predictions, strict=True):
            actual = example.target_label
            if predicted == label and actual == label:
                tp += 1
            elif predicted == label and actual != label:
                fp += 1
            elif predicted != label and actual == label:
                fn += 1
        denominator = (2 * tp) + fp + fn
        scores.append((2 * tp / denominator) if denominator else 0.0)
    return sum(scores) / len(scores)


def score_predictions(
    examples: Iterable[PredictionExample],
    distributions: Iterable[PredictionDistribution],
    vocabulary: PredictionVocabulary,
    *,
    fold_id: str = "fold",
    slice_name: str = "all",
) -> MetricReport:
    example_list = list(examples)
    distribution_list = list(distributions)
    if len(example_list) != len(distribution_list):
        raise ValueError("examples and distributions must have equal length")
    if not example_list:
        raise ValueError("at least one example is required for scoring")
    if any(item.target_space is not vocabulary.target_space for item in example_list):
        raise ValueError("example target space does not match vocabulary")

    known_labels = set(vocabulary.labels) - {vocabulary.unseen_token}
    top1_hits = 0
    top3_hits = 0
    reciprocal_rank_sum = 0.0
    nll_sum = 0.0
    unseen_count = 0
    predicted_labels: list[str] = []
    predictor_ids: set[str] = set()

    for example, distribution in zip(example_list, distribution_list, strict=True):
        _validate_distribution(distribution, vocabulary)
        if distribution.sample_id is not None and distribution.sample_id != example.sample_id:
            raise ValueError("distribution sample_id does not match example")
        predictor_ids.add(distribution.predictor_id)
        ranked = _ranked_labels(distribution)
        predicted_labels.append(ranked[0])

        is_seen = example.target_label in known_labels
        scoring_label = example.target_label if is_seen else vocabulary.unseen_token
        probability = distribution.probabilities[scoring_label]
        if probability <= 0.0:
            raise ValueError("scored target probability must be strictly positive")
        nll_sum -= math.log(probability)

        if not is_seen:
            unseen_count += 1
            continue
        if ranked[0] == example.target_label:
            top1_hits += 1
        top3 = ranked[:3]
        if example.target_label in top3:
            top3_hits += 1
        rank = ranked.index(example.target_label) + 1
        reciprocal_rank_sum += 1.0 / rank

    if len(predictor_ids) != 1:
        raise ValueError("one MetricReport cannot mix predictor IDs")
    count = len(example_list)
    coverage = (count - unseen_count) / count
    return MetricReport(
        predictor_id=next(iter(predictor_ids)),
        fold_id=fold_id,
        target_space=vocabulary.target_space,
        slice_name=slice_name,
        sample_count=count,
        top1_accuracy=top1_hits / count,
        hit_rate_at_3=top3_hits / count,
        mrr=reciprocal_rank_sum / count,
        nll=nll_sum / count,
        macro_f1=_macro_f1(example_list, predicted_labels, vocabulary),
        coverage=coverage,
        unseen_target_rate=unseen_count / count,
    )


def transition_only_slice(
    examples: Iterable[PredictionExample],
) -> list[PredictionExample]:
    return [
        item
        for item in examples
        if item.history_labels and item.target_label != item.history_labels[-1]
    ]

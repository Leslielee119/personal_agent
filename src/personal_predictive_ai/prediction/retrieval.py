from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

from personal_predictive_ai.prediction.baselines import GlobalFrequencyPredictor
from personal_predictive_ai.prediction.config import PredictionConfigV1
from personal_predictive_ai.prediction.models import (
    PredictionDistribution,
    PredictionExample,
    PredictionVocabulary,
    StructuredContext,
)

_WEIGHT_NAMES = (
    "foreground_application",
    "previous_operation",
    "process_jaccard",
    "exogenous_jaccard",
    "suffix",
    "idle_bucket",
    "time_of_day",
)


def _default_weights(config: PredictionConfigV1) -> dict[str, float]:
    return {
        "foreground_application": config.retrieval_weight_foreground_application,
        "previous_operation": config.retrieval_weight_previous_operation,
        "process_jaccard": config.retrieval_weight_process_jaccard,
        "exogenous_jaccard": config.retrieval_weight_exogenous_jaccard,
        "suffix": config.retrieval_weight_suffix,
        "idle_bucket": config.retrieval_weight_idle_bucket,
        "time_of_day": config.retrieval_weight_time_of_day,
    }


def _resolve_weights(
    config: PredictionConfigV1,
    weights: Mapping[str, float] | None,
) -> dict[str, float]:
    resolved = _default_weights(config)
    if weights is None:
        return resolved
    unknown = set(weights) - set(_WEIGHT_NAMES)
    if unknown:
        raise ValueError(f"unknown retrieval weights: {sorted(unknown)}")
    for name, value in weights.items():
        numeric = float(value)
        if numeric < 0.0:
            raise ValueError("retrieval weights must be nonnegative")
        resolved[name] = numeric
    return resolved


def _exact_match(left: str | None, right: str | None) -> float:
    return 1.0 if left is not None and right is not None and left == right else 0.0


def _jaccard(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    left_set = set(left)
    right_set = set(right)
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def _suffix_match(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    matches = 0
    for left_item, right_item in zip(reversed(left[-3:]), reversed(right[-3:]), strict=False):
        if left_item != right_item:
            break
        matches += 1
    return matches / 3.0


def _structured_similarity_with_weights(
    query: StructuredContext,
    candidate: StructuredContext,
    weights: Mapping[str, float],
) -> float:
    score = 0.0
    score += weights["foreground_application"] * _exact_match(
        query.foreground_application,
        candidate.foreground_application,
    )
    score += weights["previous_operation"] * _exact_match(
        query.previous_operation,
        candidate.previous_operation,
    )
    score += weights["process_jaccard"] * _jaccard(
        query.active_process_names,
        candidate.active_process_names,
    )
    score += weights["exogenous_jaccard"] * _jaccard(
        query.recent_exogenous_event_types,
        candidate.recent_exogenous_event_types,
    )
    score += weights["suffix"] * _suffix_match(
        query.recent_joint_actions,
        candidate.recent_joint_actions,
    )
    score += weights["idle_bucket"] * _exact_match(
        query.idle_bucket,
        candidate.idle_bucket,
    )
    score += weights["time_of_day"] * _exact_match(
        query.time_of_day_bucket,
        candidate.time_of_day_bucket,
    )
    return score


def structured_similarity(
    query: StructuredContext,
    candidate: StructuredContext,
    config: PredictionConfigV1,
) -> float:
    return _structured_similarity_with_weights(
        query,
        candidate,
        _default_weights(config),
    )


class StructuredRetrievalPredictor:
    predictor_id = "structured_retrieval"

    def __init__(
        self,
        top_k: int | None = None,
        weights: Mapping[str, float] | None = None,
        config: PredictionConfigV1 | None = None,
    ) -> None:
        self.config = config or PredictionConfigV1()
        self.top_k = self.config.retrieval_top_k if top_k is None else top_k
        if self.top_k < 1:
            raise ValueError("top_k must be positive")
        self.weights = _resolve_weights(self.config, weights)
        self._global = GlobalFrequencyPredictor(self.config)
        self._vocabulary: PredictionVocabulary | None = None
        self._train_examples: list[PredictionExample] = []

    def fit(
        self,
        train_examples: Iterable[PredictionExample],
        vocabulary: PredictionVocabulary,
    ) -> "StructuredRetrievalPredictor":
        examples = list(train_examples)
        self._global.fit(examples, vocabulary)
        self._vocabulary = vocabulary
        self._train_examples = sorted(
            examples,
            key=lambda item: (item.cutoff_seq, item.sample_id),
        )
        return self

    def _neighbors(
        self,
        example: PredictionExample,
    ) -> list[tuple[float, PredictionExample]]:
        scored: list[tuple[float, PredictionExample]] = []
        for candidate in self._train_examples:
            if candidate.sample_id == example.sample_id:
                continue
            if candidate.cutoff_seq >= example.cutoff_seq:
                continue
            score = _structured_similarity_with_weights(
                example.context,
                candidate.context,
                self.weights,
            )
            if score > 0.0:
                scored.append((score, candidate))
        scored.sort(
            key=lambda item: (
                -item[0],
                item[1].cutoff_seq,
                item[1].sample_id,
            )
        )
        return scored[: self.top_k]

    def predict(self, example: PredictionExample) -> PredictionDistribution:
        if self._vocabulary is None:
            raise RuntimeError("predictor must be fit before predict")
        global_distribution = self._global.predict(example)
        neighbors = self._neighbors(example)
        if not neighbors:
            return PredictionDistribution(
                predictor_id=self.predictor_id,
                target_space=self._vocabulary.target_space,
                sample_id=example.sample_id,
                probabilities=dict(global_distribution.probabilities),
            )

        votes: Counter[str] = Counter()
        for score, neighbor in neighbors:
            votes[neighbor.target_label] += score
        vote_total = sum(votes.values())
        neighbor_mass = self.config.retrieval_neighbor_mass
        backoff_mass = 1.0 - neighbor_mass
        probabilities = {
            label: backoff_mass * global_distribution.probabilities[label]
            + neighbor_mass * (votes[label] / vote_total)
            for label in self._vocabulary.labels
        }
        return PredictionDistribution(
            predictor_id=self.predictor_id,
            target_space=self._vocabulary.target_space,
            sample_id=example.sample_id,
            probabilities=probabilities,
        )

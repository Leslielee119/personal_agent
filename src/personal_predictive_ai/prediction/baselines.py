from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Protocol, Self

from personal_predictive_ai.prediction.config import PredictionConfigV1
from personal_predictive_ai.prediction.models import (
    MetricReport,
    PredictionDistribution,
    PredictionExample,
    PredictionVocabulary,
)


class Predictor(Protocol):
    def fit(
        self,
        train_examples: Iterable[PredictionExample],
        vocabulary: PredictionVocabulary,
    ) -> Self: ...

    def predict(self, example: PredictionExample) -> PredictionDistribution: ...


def _validate_training_examples(
    train_examples: Iterable[PredictionExample],
    vocabulary: PredictionVocabulary,
) -> list[PredictionExample]:
    examples = list(train_examples)
    if not examples:
        raise ValueError("training examples are required")
    if any(item.target_space is not vocabulary.target_space for item in examples):
        raise ValueError("training target space does not match vocabulary")
    expected_labels = set(vocabulary.labels) - {vocabulary.unseen_token}
    observed_labels = {item.target_label for item in examples}
    if expected_labels != observed_labels:
        raise ValueError("prediction vocabulary must be built from the training examples")
    return examples


def _global_probabilities(
    examples: list[PredictionExample],
    vocabulary: PredictionVocabulary,
    config: PredictionConfigV1,
) -> dict[str, float]:
    counts = Counter(item.target_label for item in examples)
    total = sum(counts.values())
    known_mass = 1.0 - config.predictor_unseen_mass
    probabilities = {
        label: known_mass * (counts[label] / total)
        for label in vocabulary.labels
        if label != vocabulary.unseen_token
    }
    probabilities[vocabulary.unseen_token] = config.predictor_unseen_mass
    return probabilities


def _discounted_distribution(
    counts: Counter[str],
    backoff: dict[str, float],
    *,
    discount: float,
) -> dict[str, float]:
    total = sum(counts.values())
    if total <= 0:
        return dict(backoff)
    observed_types = sum(count > 0 for count in counts.values())
    backoff_mass = discount * observed_types / total
    return {
        label: max(counts.get(label, 0) - discount, 0.0) / total + backoff_mass * backoff[label]
        for label in backoff
    }


class GlobalFrequencyPredictor:
    predictor_id = "global_frequency"

    def __init__(self, config: PredictionConfigV1 | None = None) -> None:
        self.config = config or PredictionConfigV1()
        self._vocabulary: PredictionVocabulary | None = None
        self._probabilities: dict[str, float] | None = None

    def fit(
        self,
        train_examples: Iterable[PredictionExample],
        vocabulary: PredictionVocabulary,
    ) -> Self:
        examples = _validate_training_examples(train_examples, vocabulary)
        self._vocabulary = vocabulary
        self._probabilities = _global_probabilities(examples, vocabulary, self.config)
        return self

    def predict(self, example: PredictionExample) -> PredictionDistribution:
        if self._vocabulary is None or self._probabilities is None:
            raise RuntimeError("predictor must be fit before predict")
        if example.target_space is not self._vocabulary.target_space:
            raise ValueError("example target space does not match fitted predictor")
        return PredictionDistribution(
            predictor_id=self.predictor_id,
            target_space=self._vocabulary.target_space,
            sample_id=example.sample_id,
            probabilities=dict(self._probabilities),
        )


class PersistencePredictor:
    predictor_id = "persistence"

    def __init__(self, config: PredictionConfigV1 | None = None) -> None:
        self.config = config or PredictionConfigV1()
        self._global = GlobalFrequencyPredictor(self.config)
        self._vocabulary: PredictionVocabulary | None = None

    def fit(
        self,
        train_examples: Iterable[PredictionExample],
        vocabulary: PredictionVocabulary,
    ) -> Self:
        examples = list(train_examples)
        self._global.fit(examples, vocabulary)
        self._vocabulary = vocabulary
        return self

    def predict(self, example: PredictionExample) -> PredictionDistribution:
        if self._vocabulary is None:
            raise RuntimeError("predictor must be fit before predict")
        global_distribution = self._global.predict(example)
        probabilities = dict(global_distribution.probabilities)
        previous = example.history_labels[-1] if example.history_labels else None
        known_labels = set(self._vocabulary.labels) - {self._vocabulary.unseen_token}
        if previous in known_labels:
            residual = 1.0 - self.config.persistence_copy_mass
            probabilities = {label: residual * value for label, value in probabilities.items()}
            probabilities[previous] += self.config.persistence_copy_mass
        return PredictionDistribution(
            predictor_id=self.predictor_id,
            target_space=self._vocabulary.target_space,
            sample_id=example.sample_id,
            probabilities=probabilities,
        )


class ContextualFrequencyPredictor:
    predictor_id = "contextual_frequency"

    def __init__(self, config: PredictionConfigV1 | None = None) -> None:
        self.config = config or PredictionConfigV1()
        self._global = GlobalFrequencyPredictor(self.config)
        self._vocabulary: PredictionVocabulary | None = None
        self._application_counts: dict[str, Counter[str]] = defaultdict(Counter)
        self._operation_counts: dict[str, Counter[str]] = defaultdict(Counter)
        self._pair_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)

    def fit(
        self,
        train_examples: Iterable[PredictionExample],
        vocabulary: PredictionVocabulary,
    ) -> Self:
        examples = _validate_training_examples(train_examples, vocabulary)
        self._global.fit(examples, vocabulary)
        self._vocabulary = vocabulary
        self._application_counts.clear()
        self._operation_counts.clear()
        self._pair_counts.clear()
        for example in examples:
            application = example.context.foreground_application
            previous_operation = example.context.previous_operation
            if application is not None:
                self._application_counts[application][example.target_label] += 1
            if previous_operation is not None:
                self._operation_counts[previous_operation][example.target_label] += 1
            if application is not None and previous_operation is not None:
                self._pair_counts[(application, previous_operation)][example.target_label] += 1
        return self

    def predict(self, example: PredictionExample) -> PredictionDistribution:
        if self._vocabulary is None:
            raise RuntimeError("predictor must be fit before predict")
        global_probabilities = self._global.predict(example).probabilities
        application = example.context.foreground_application
        previous_operation = example.context.previous_operation

        app_probabilities = dict(global_probabilities)
        if application is not None and application in self._application_counts:
            app_probabilities = _discounted_distribution(
                self._application_counts[application],
                global_probabilities,
                discount=self.config.ngram_absolute_discount,
            )

        operation_probabilities = dict(global_probabilities)
        if previous_operation is not None and previous_operation in self._operation_counts:
            operation_probabilities = _discounted_distribution(
                self._operation_counts[previous_operation],
                global_probabilities,
                discount=self.config.ngram_absolute_discount,
            )

        probabilities: dict[str, float]
        pair = (
            (application, previous_operation)
            if application is not None and previous_operation is not None
            else None
        )
        if pair is not None and pair in self._pair_counts:
            pair_backoff = (
                app_probabilities
                if application in self._application_counts
                else operation_probabilities
            )
            probabilities = _discounted_distribution(
                self._pair_counts[pair],
                pair_backoff,
                discount=self.config.ngram_absolute_discount,
            )
        elif application is not None and application in self._application_counts:
            probabilities = app_probabilities
        elif previous_operation is not None and previous_operation in self._operation_counts:
            probabilities = operation_probabilities
        else:
            probabilities = dict(global_probabilities)

        return PredictionDistribution(
            predictor_id=self.predictor_id,
            target_space=self._vocabulary.target_space,
            sample_id=example.sample_id,
            probabilities=probabilities,
        )


class BigramPredictor:
    predictor_id = "bigram"

    def __init__(self, config: PredictionConfigV1 | None = None) -> None:
        self.config = config or PredictionConfigV1()
        self._global = GlobalFrequencyPredictor(self.config)
        self._vocabulary: PredictionVocabulary | None = None
        self._counts: dict[str, Counter[str]] = defaultdict(Counter)

    def fit(
        self,
        train_examples: Iterable[PredictionExample],
        vocabulary: PredictionVocabulary,
    ) -> Self:
        examples = _validate_training_examples(train_examples, vocabulary)
        self._global.fit(examples, vocabulary)
        self._vocabulary = vocabulary
        self._counts.clear()
        for example in examples:
            if example.history_labels:
                self._counts[example.history_labels[-1]][example.target_label] += 1
        return self

    def predict(self, example: PredictionExample) -> PredictionDistribution:
        if self._vocabulary is None:
            raise RuntimeError("predictor must be fit before predict")
        backoff = self._global.predict(example).probabilities
        previous = example.history_labels[-1] if example.history_labels else None
        probabilities = dict(backoff)
        if previous is not None and previous in self._counts:
            probabilities = _discounted_distribution(
                self._counts[previous],
                backoff,
                discount=self.config.ngram_absolute_discount,
            )
        return PredictionDistribution(
            predictor_id=self.predictor_id,
            target_space=self._vocabulary.target_space,
            sample_id=example.sample_id,
            probabilities=probabilities,
        )


class TrigramBackoffPredictor:
    predictor_id = "trigram_backoff"

    def __init__(self, config: PredictionConfigV1 | None = None) -> None:
        self.config = config or PredictionConfigV1()
        self._global = GlobalFrequencyPredictor(self.config)
        self._vocabulary: PredictionVocabulary | None = None
        self._bigram_counts: dict[str, Counter[str]] = defaultdict(Counter)
        self._trigram_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)

    def fit(
        self,
        train_examples: Iterable[PredictionExample],
        vocabulary: PredictionVocabulary,
    ) -> Self:
        examples = _validate_training_examples(train_examples, vocabulary)
        self._global.fit(examples, vocabulary)
        self._vocabulary = vocabulary
        self._bigram_counts.clear()
        self._trigram_counts.clear()
        for example in examples:
            if example.history_labels:
                self._bigram_counts[example.history_labels[-1]][example.target_label] += 1
            if len(example.history_labels) >= 2:
                context = (example.history_labels[-2], example.history_labels[-1])
                self._trigram_counts[context][example.target_label] += 1
        return self

    def predict(self, example: PredictionExample) -> PredictionDistribution:
        if self._vocabulary is None:
            raise RuntimeError("predictor must be fit before predict")
        global_probabilities = self._global.predict(example).probabilities
        previous = example.history_labels[-1] if example.history_labels else None
        bigram_probabilities = dict(global_probabilities)
        if previous is not None and previous in self._bigram_counts:
            bigram_probabilities = _discounted_distribution(
                self._bigram_counts[previous],
                global_probabilities,
                discount=self.config.ngram_absolute_discount,
            )

        probabilities = bigram_probabilities
        if len(example.history_labels) >= 2:
            context = (example.history_labels[-2], example.history_labels[-1])
            if context in self._trigram_counts:
                probabilities = _discounted_distribution(
                    self._trigram_counts[context],
                    bigram_probabilities,
                    discount=self.config.ngram_absolute_discount,
                )
        return PredictionDistribution(
            predictor_id=self.predictor_id,
            target_space=self._vocabulary.target_space,
            sample_id=example.sample_id,
            probabilities=probabilities,
        )


def select_action_only_baseline(validation_reports: Iterable[MetricReport]) -> str:
    grouped: dict[str, list[float]] = defaultdict(list)
    for report in validation_reports:
        grouped[report.predictor_id].append(report.nll)
    if not grouped:
        raise ValueError("validation reports are required")
    ranked = sorted(
        (statistics.mean(values), predictor_id) for predictor_id, values in grouped.items()
    )
    return ranked[0][1]

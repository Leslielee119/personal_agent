from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from personal_predictive_ai.prediction.config import PredictionConfigV1
from personal_predictive_ai.prediction.models import (
    PredictionExample,
    PredictionFold,
    TargetSpace,
    ValidityDecision,
)


class ValidityAuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    schema_version: Literal["ppa.validity-audit/v1"] = "ppa.validity-audit/v1"
    target_space: TargetSpace
    decision: ValidityDecision
    generalization_status: str = Field(min_length=1)
    session_count: int = Field(ge=0)
    eligible_target_actions: int = Field(ge=0)
    class_count: int = Field(ge=0)
    dominant_class_ratio: float = Field(ge=0.0, le=1.0)
    shannon_entropy: float = Field(ge=0.0)
    normalized_entropy: float = Field(ge=0.0, le=1.0)
    effective_classes: float = Field(ge=0.0)
    chronological_test_samples: int = Field(ge=0)
    chronological_test_classes: int = Field(ge=0)
    train_target_coverage: float = Field(ge=0.0, le=1.0)
    validation_target_coverage: float = Field(ge=0.0, le=1.0)
    test_target_coverage: float = Field(ge=0.0, le=1.0)
    full_prefix_duplicate_rate: float = Field(ge=0.0, le=1.0)
    full_prefix_unseen_rate: float = Field(ge=0.0, le=1.0)
    suffix_duplicate_rates: dict[int, float]
    suffix_unseen_rates: dict[int, float]
    empirical_conditional_entropy: float = Field(ge=0.0)
    deterministic_prefix_fraction: float = Field(ge=0.0, le=1.0)
    multi_continuation_fraction: float = Field(ge=0.0, le=1.0)
    empirical_test_oracle_ceiling: float = Field(ge=0.0, le=1.0)
    empirical_test_oracle_diagnostic_only: bool = True
    fold_count: int = Field(ge=0)


def _entropy(counts: Counter[str]) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    result = 0.0
    for count in counts.values():
        if count <= 0:
            continue
        probability = count / total
        result -= probability * math.log(probability)
    return result


def _target_diversity(
    examples: list[PredictionExample],
) -> tuple[int, float, float, float, float]:
    counts = Counter(example.target_label for example in examples)
    total = len(examples)
    class_count = len(counts)
    if total == 0:
        return 0, 0.0, 0.0, 0.0, 0.0
    dominant = max(counts.values()) / total
    entropy = _entropy(counts)
    normalized = entropy / math.log(class_count) if class_count > 1 else 0.0
    effective = math.exp(entropy)
    return class_count, dominant, entropy, normalized, effective


def _examples_for_ids(
    sample_ids: tuple[str, ...],
    by_id: dict[str, PredictionExample],
) -> list[PredictionExample]:
    return [by_id[sample_id] for sample_id in sample_ids]


def _coverage_metrics(
    folds: list[PredictionFold],
    by_id: dict[str, PredictionExample],
    all_labels: set[str],
) -> tuple[float, float, float]:
    if not folds or not all_labels:
        return 0.0, 0.0, 0.0

    train_union: set[str] = set()
    validation_seen = 0
    validation_total = 0
    test_seen = 0
    test_total = 0
    for fold in folds:
        train_examples = _examples_for_ids(fold.train_sample_ids, by_id)
        validation_examples = _examples_for_ids(fold.validation_sample_ids, by_id)
        test_examples = _examples_for_ids(fold.test_sample_ids, by_id)
        train_labels = {item.target_label for item in train_examples}
        train_union.update(train_labels)
        validation_total += len(validation_examples)
        validation_seen += sum(item.target_label in train_labels for item in validation_examples)
        test_total += len(test_examples)
        test_seen += sum(item.target_label in train_labels for item in test_examples)

    return (
        len(train_union) / len(all_labels),
        validation_seen / validation_total if validation_total else 0.0,
        test_seen / test_total if test_total else 0.0,
    )


def _leakage_and_ambiguity(
    folds: list[PredictionFold],
    by_id: dict[str, PredictionExample],
    suffix_ks: tuple[int, ...],
) -> tuple[float, dict[int, float], float, float, float, float]:
    test_total = 0
    full_duplicates = 0
    suffix_duplicates = {k: 0 for k in suffix_ks}
    conditional_entropies: list[float] = []
    deterministic_seen = 0
    multi_seen = 0
    seen_prefix_samples = 0
    oracle_correct = 0

    for fold in folds:
        train_examples = _examples_for_ids(fold.train_sample_ids, by_id)
        test_examples = _examples_for_ids(fold.test_sample_ids, by_id)
        train_prefixes = {tuple(item.joint_history) for item in train_examples}
        train_suffixes = {
            k: {tuple(item.joint_history[-k:]) for item in train_examples} for k in suffix_ks
        }
        continuation_counts: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
        for item in train_examples:
            continuation_counts[tuple(item.joint_history)][item.target_label] += 1

        test_groups: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
        for item in test_examples:
            prefix = tuple(item.joint_history)
            test_groups[prefix][item.target_label] += 1
            test_total += 1
            if prefix in train_prefixes:
                full_duplicates += 1
            for k in suffix_ks:
                if tuple(item.joint_history[-k:]) in train_suffixes[k]:
                    suffix_duplicates[k] += 1

            historical = continuation_counts.get(prefix)
            if historical:
                seen_prefix_samples += 1
                conditional_entropies.append(_entropy(historical))
                if len(historical) == 1:
                    deterministic_seen += 1
                else:
                    multi_seen += 1

        oracle_correct += sum(max(counts.values()) for counts in test_groups.values())

    if test_total == 0:
        return 0.0, {k: 0.0 for k in suffix_ks}, 0.0, 0.0, 0.0, 0.0

    full_duplicate_rate = full_duplicates / test_total
    suffix_rates = {k: suffix_duplicates[k] / test_total for k in suffix_ks}
    conditional_entropy = (
        sum(conditional_entropies) / len(conditional_entropies) if conditional_entropies else 0.0
    )
    deterministic_fraction = (
        deterministic_seen / seen_prefix_samples if seen_prefix_samples else 0.0
    )
    multi_fraction = multi_seen / seen_prefix_samples if seen_prefix_samples else 0.0
    oracle_ceiling = oracle_correct / test_total
    return (
        full_duplicate_rate,
        suffix_rates,
        conditional_entropy,
        deterministic_fraction,
        multi_fraction,
        oracle_ceiling,
    )


def audit_validity(
    examples: Iterable[PredictionExample],
    folds: Iterable[PredictionFold],
    config: PredictionConfigV1,
    *,
    target_space: TargetSpace | None = None,
) -> ValidityAuditReport:
    ordered = sorted(examples, key=lambda item: (item.cutoff_seq, item.sample_id))
    fold_list = list(folds)
    if ordered:
        observed_target_space = ordered[0].target_space
        if any(item.target_space is not observed_target_space for item in ordered):
            raise ValueError("validity audit requires one target space at a time")
        if target_space is not None and target_space is not observed_target_space:
            raise ValueError("explicit target space disagrees with prediction examples")
        target_space = observed_target_space
    elif target_space is None:
        target_space = TargetSpace.OPERATION

    session_count = len({item.session_id for item in ordered})
    class_count, dominant, entropy, normalized_entropy, effective = _target_diversity(ordered)
    by_id = {item.sample_id: item for item in ordered}
    test_examples = [
        item for fold in fold_list for item in _examples_for_ids(fold.test_sample_ids, by_id)
    ]
    chronological_test_samples = len(test_examples)
    chronological_test_classes = len({item.target_label for item in test_examples})
    all_labels = {item.target_label for item in ordered}
    train_coverage, validation_coverage, test_coverage = _coverage_metrics(
        fold_list, by_id, all_labels
    )

    (
        full_duplicate_rate,
        suffix_duplicate_rates,
        conditional_entropy,
        deterministic_fraction,
        multi_fraction,
        oracle_ceiling,
    ) = _leakage_and_ambiguity(fold_list, by_id, config.suffix_ks)

    reasons: list[str] = []
    if session_count < config.c0_min_sessions:
        reasons.append(f"sessions<{config.c0_min_sessions}")
    if len(ordered) < config.c0_min_targets:
        reasons.append(f"targets<{config.c0_min_targets}")
    min_classes = 2 if target_space is TargetSpace.APPLICATION else config.c0_min_classes
    if class_count < min_classes:
        reasons.append(f"classes<{min_classes}")
    if dominant > config.c0_max_dominant_ratio:
        reasons.append(f"dominant>{config.c0_max_dominant_ratio}")
    if normalized_entropy < config.c0_min_normalized_entropy:
        reasons.append(f"normalized_entropy<{config.c0_min_normalized_entropy}")
    if chronological_test_classes < config.c0_min_test_classes:
        reasons.append(f"test_classes<{config.c0_min_test_classes}")
    if chronological_test_samples < config.c0_min_test_samples:
        reasons.append(f"test_samples<{config.c0_min_test_samples}")

    eligible = not reasons and bool(fold_list)
    status = "PASS" if eligible else "INSUFFICIENT_PREDICTIVE_DIVERSITY"
    generalization_status = (
        "FORMAL_SESSION_FORWARD" if fold_list else "NON_GENERALIZATION_DIAGNOSTIC"
    )
    decision = ValidityDecision(
        status=status,
        eligible_for_formal_comparison=eligible,
        reasons=tuple(reasons),
    )

    return ValidityAuditReport(
        target_space=target_space,
        decision=decision,
        generalization_status=generalization_status,
        session_count=session_count,
        eligible_target_actions=len(ordered),
        class_count=class_count,
        dominant_class_ratio=dominant,
        shannon_entropy=entropy,
        normalized_entropy=normalized_entropy,
        effective_classes=effective,
        chronological_test_samples=chronological_test_samples,
        chronological_test_classes=chronological_test_classes,
        train_target_coverage=train_coverage,
        validation_target_coverage=validation_coverage,
        test_target_coverage=test_coverage,
        full_prefix_duplicate_rate=full_duplicate_rate,
        full_prefix_unseen_rate=(1.0 - full_duplicate_rate if test_examples else 0.0),
        suffix_duplicate_rates=suffix_duplicate_rates,
        suffix_unseen_rates={k: 1.0 - rate for k, rate in suffix_duplicate_rates.items()},
        empirical_conditional_entropy=conditional_entropy,
        deterministic_prefix_fraction=deterministic_fraction,
        multi_continuation_fraction=multi_fraction,
        empirical_test_oracle_ceiling=oracle_ceiling,
        empirical_test_oracle_diagnostic_only=True,
        fold_count=len(fold_list),
    )

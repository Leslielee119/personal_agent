from __future__ import annotations

import math
import statistics
from collections.abc import Iterable

from personal_predictive_ai.prediction.models import GateDecision, MetricReport


def nll_effect_threshold(reference_nll: float) -> float:
    if reference_nll < 0.0 or not math.isfinite(reference_nll):
        raise ValueError("reference_nll must be finite and nonnegative")
    return max(0.01, 0.01 * reference_nll)


def evaluate_gate(
    candidate_reports: Iterable[MetricReport],
    reference_reports: Iterable[MetricReport],
    *,
    independent_test_sessions: int,
    gate_name: str = "NLL_GAIN",
) -> GateDecision:
    candidates = {item.fold_id: item for item in candidate_reports}
    references = {item.fold_id: item for item in reference_reports}
    if set(candidates) != set(references):
        raise ValueError("candidate/reference reports must cover the same folds")
    if any(
        candidates[fold_id].target_space is not references[fold_id].target_space
        for fold_id in candidates
    ):
        raise ValueError("candidate/reference target spaces must match")

    fold_ids = sorted(candidates)
    deltas = [references[fold_id].nll - candidates[fold_id].nll for fold_id in fold_ids]
    reference_nlls = [references[fold_id].nll for fold_id in fold_ids]
    fold_count = len(deltas)
    positive_count = sum(delta > 0.0 for delta in deltas)
    median_delta = statistics.median(deltas) if deltas else None
    reference_median = statistics.median(reference_nlls) if reference_nlls else 0.0
    threshold = nll_effect_threshold(reference_median)

    if fold_count == 2:
        direction_pass = positive_count == 2
    elif fold_count >= 3:
        direction_pass = positive_count >= math.ceil((2 * fold_count) / 3)
    else:
        direction_pass = False
    effect_pass = median_delta is not None and median_delta >= threshold
    passed = fold_count >= 2 and direction_pass and effect_pass

    reasons: list[str] = []
    if fold_count < 2:
        reasons.append("fewer_than_two_test_folds")
    if fold_count >= 2 and not direction_pass:
        reasons.append("fold_direction_consistency_failed")
    if fold_count >= 2 and not effect_pass:
        reasons.append("median_nll_effect_below_threshold")

    inferential_status = (
        "DESCRIPTIVE_ONLY" if independent_test_sessions < 5 else "CONFIRMATORY_ELIGIBLE"
    )
    status = "PASS" if passed else "FAIL"
    if fold_count < 2:
        status = "INSUFFICIENT_EVALUATION_FOLDS"

    return GateDecision(
        gate_name=gate_name,
        status=status,
        passed=passed,
        fold_count=fold_count,
        positive_fold_count=positive_count,
        median_delta_nll=median_delta,
        effect_threshold=threshold,
        inferential_status=inferential_status,
        reasons=tuple(reasons),
    )

from __future__ import annotations

import importlib.util

from personal_predictive_ai.prediction.config import PredictionConfigV1
from personal_predictive_ai.prediction.models import (
    PredictionExample,
    StructuredContext,
    TargetSpace,
)


def _load_api():
    assert importlib.util.find_spec("personal_predictive_ai.prediction.splits") is not None
    assert importlib.util.find_spec("personal_predictive_ai.prediction.validity") is not None
    from personal_predictive_ai.prediction.splits import build_session_forward_folds
    from personal_predictive_ai.prediction.validity import audit_validity

    return build_session_forward_folds, audit_validity


def _example(
    session_id: str,
    seq: int,
    label: str,
    *,
    history: tuple[str, ...] = (),
) -> PredictionExample:
    joint_history = tuple(f"Code.exe::{item}" for item in history)
    return PredictionExample(
        sample_id=f"sample-{session_id}-{seq}",
        target_space=TargetSpace.OPERATION,
        session_id=session_id,
        cutoff_seq=seq,
        target_timestamp_ns=seq * 1_000,
        target_action_id=f"act-{session_id}-{seq}",
        target_label=label,
        history_labels=history,
        joint_history=joint_history,
        context=StructuredContext(
            foreground_application="Code.exe",
            previous_operation=history[-1] if history else None,
            recent_joint_actions=joint_history[-3:],
            active_process_names=("Code.exe",),
        ),
    )


def _session_examples(session_id: str, start_seq: int, count: int) -> list[PredictionExample]:
    labels = ("save", "run", "inspect")
    history: list[str] = []
    result: list[PredictionExample] = []
    for offset in range(count):
        label = labels[offset % len(labels)]
        result.append(
            _example(
                session_id,
                start_seq + offset,
                label,
                history=tuple(history),
            )
        )
        history.append(label)
    return result


def test_session_forward_folds_keep_sessions_whole_and_advance_only_forward() -> None:
    build_session_forward_folds, _ = _load_api()
    examples: list[PredictionExample] = []
    for index, session_id in enumerate(("s1", "s2", "s3", "s4", "s5"), start=1):
        examples.extend(_session_examples(session_id, index * 100, 2))

    folds = build_session_forward_folds(examples, min_train_sessions=2)

    assert len(folds) == 2
    assert folds[0].train_session_ids == ("s1", "s2")
    assert folds[0].validation_session_ids == ("s3",)
    assert folds[0].test_session_ids == ("s4",)
    assert folds[1].train_session_ids == ("s1", "s2", "s3")
    assert folds[1].validation_session_ids == ("s4",)
    assert folds[1].test_session_ids == ("s5",)

    for fold in folds:
        assert set(fold.train_session_ids).isdisjoint(fold.validation_session_ids)
        assert set(fold.train_session_ids).isdisjoint(fold.test_session_ids)
        assert set(fold.validation_session_ids).isdisjoint(fold.test_session_ids)
        assert fold.train_high_water < fold.validation_start_seq < fold.test_start_seq


def test_degenerate_single_session_is_not_eligible_for_formal_comparison() -> None:
    build_session_forward_folds, audit_validity = _load_api()
    examples = [
        _example("only", seq, "key_input", history=("key_input",) * (seq - 1))
        for seq in range(1, 183)
    ]

    report = audit_validity(
        examples,
        build_session_forward_folds(examples),
        PredictionConfigV1(),
    )

    assert report.generalization_status == "NON_GENERALIZATION_DIAGNOSTIC"
    assert report.decision.status == "INSUFFICIENT_PREDICTIVE_DIVERSITY"
    assert report.decision.eligible_for_formal_comparison is False
    assert report.session_count == 1
    assert report.eligible_target_actions == 182
    assert report.class_count == 1
    assert report.dominant_class_ratio == 1.0


def test_valid_four_session_three_class_fixture_passes_c0() -> None:
    build_session_forward_folds, audit_validity = _load_api()
    examples: list[PredictionExample] = []
    for index, session_id in enumerate(("s1", "s2", "s3", "s4"), start=1):
        examples.extend(_session_examples(session_id, index * 1_000, 60))

    folds = build_session_forward_folds(examples, min_train_sessions=2)
    report = audit_validity(examples, folds, PredictionConfigV1())

    assert len(folds) == 1
    assert report.decision.status == "PASS"
    assert report.decision.eligible_for_formal_comparison is True
    assert report.session_count == 4
    assert report.eligible_target_actions == 240
    assert report.class_count == 3
    assert report.chronological_test_samples == 60
    assert report.chronological_test_classes == 3
    assert report.normalized_entropy >= 0.25


def test_full_prefix_and_suffix_leakage_are_reported_separately() -> None:
    build_session_forward_folds, audit_validity = _load_api()
    examples: list[PredictionExample] = []
    for index, session_id in enumerate(("s1", "s2", "s3", "s4"), start=1):
        examples.extend(_session_examples(session_id, index * 1_000, 60))

    report = audit_validity(
        examples,
        build_session_forward_folds(examples, min_train_sessions=2),
        PredictionConfigV1(),
    )

    assert 0.0 <= report.full_prefix_duplicate_rate <= 1.0
    assert report.full_prefix_unseen_rate == 1.0 - report.full_prefix_duplicate_rate
    assert set(report.suffix_duplicate_rates) == {1, 2, 3, 5}
    assert set(report.suffix_unseen_rates) == {1, 2, 3, 5}
    for k in (1, 2, 3, 5):
        assert report.suffix_unseen_rates[k] == 1.0 - report.suffix_duplicate_rates[k]
    assert report.empirical_test_oracle_diagnostic_only is True

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from personal_predictive_ai.prediction.models import PredictionExample, PredictionFold


def build_session_forward_folds(
    examples: Iterable[PredictionExample],
    *,
    min_train_sessions: int = 2,
) -> list[PredictionFold]:
    if min_train_sessions < 1:
        raise ValueError("min_train_sessions must be positive")

    grouped: dict[str, list[PredictionExample]] = defaultdict(list)
    for example in examples:
        grouped[example.session_id].append(example)
    if len(grouped) < min_train_sessions + 2:
        return []

    for session_examples in grouped.values():
        session_examples.sort(key=lambda item: (item.cutoff_seq, item.sample_id))

    ordered_sessions = sorted(
        grouped,
        key=lambda session_id: (
            grouped[session_id][0].cutoff_seq,
            grouped[session_id][0].target_timestamp_ns,
            session_id,
        ),
    )

    folds: list[PredictionFold] = []
    for validation_index in range(min_train_sessions, len(ordered_sessions) - 1):
        train_sessions = tuple(ordered_sessions[:validation_index])
        validation_sessions = (ordered_sessions[validation_index],)
        test_sessions = (ordered_sessions[validation_index + 1],)

        train_examples = [item for session in train_sessions for item in grouped[session]]
        validation_examples = [item for session in validation_sessions for item in grouped[session]]
        test_examples = [item for session in test_sessions for item in grouped[session]]

        train_high_water = max(item.cutoff_seq for item in train_examples)
        validation_start_seq = min(item.cutoff_seq for item in validation_examples)
        test_start_seq = min(item.cutoff_seq for item in test_examples)
        folds.append(
            PredictionFold(
                fold_id=f"fold-{len(folds) + 1:03d}",
                train_session_ids=train_sessions,
                validation_session_ids=validation_sessions,
                test_session_ids=test_sessions,
                train_sample_ids=tuple(item.sample_id for item in train_examples),
                validation_sample_ids=tuple(item.sample_id for item in validation_examples),
                test_sample_ids=tuple(item.sample_id for item in test_examples),
                train_high_water=train_high_water,
                validation_start_seq=validation_start_seq,
                test_start_seq=test_start_seq,
            )
        )
    return folds

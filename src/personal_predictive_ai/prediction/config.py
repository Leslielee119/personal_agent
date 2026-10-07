from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class PredictionConfigV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.prediction-config/v1"] = "ppa.prediction-config/v1"

    c0_min_sessions: Literal[4] = 4
    c0_min_targets: Literal[200] = 200
    c0_min_classes: Literal[3] = 3
    c0_max_dominant_ratio: Literal[0.9] = 0.9
    c0_min_normalized_entropy: Literal[0.25] = 0.25
    c0_min_test_classes: Literal[2] = 2
    c0_min_test_samples: Literal[40] = 40

    suffix_ks: tuple[Literal[1], Literal[2], Literal[3], Literal[5]] = (1, 2, 3, 5)
    unseen_token: Literal["__UNSEEN__"] = "__UNSEEN__"
    primary_metric: Literal["nll"] = "nll"

    nll_absolute_min_effect: Literal[0.01] = 0.01
    nll_relative_min_effect: Literal[0.01] = 0.01
    min_rolling_test_folds: Literal[2] = 2
    confirmatory_min_independent_test_sessions: Literal[5] = 5

    predictor_unseen_mass: Literal[0.01] = 0.01
    persistence_copy_mass: Literal[0.99] = 0.99
    ngram_absolute_discount: Literal[0.75] = 0.75

    retrieval_top_k: Literal[20] = 20
    retrieval_neighbor_mass: Literal[0.99] = 0.99
    retrieval_weight_foreground_application: Literal[1.0] = 1.0
    retrieval_weight_previous_operation: Literal[1.0] = 1.0
    retrieval_weight_process_jaccard: Literal[1.0] = 1.0
    retrieval_weight_exogenous_jaccard: Literal[1.0] = 1.0
    retrieval_weight_suffix: Literal[1.0] = 1.0
    retrieval_weight_idle_bucket: Literal[1.0] = 1.0
    retrieval_weight_time_of_day: Literal[0.0] = 0.0

    memory_min_available_samples: Literal[40] = 40
    memory_min_coverage: Literal[0.2] = 0.2
    memory_min_exposed_test_sessions: Literal[2] = 2
    memory_min_distinct_active_memories: Literal[2] = 2

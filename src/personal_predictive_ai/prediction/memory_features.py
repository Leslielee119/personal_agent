from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from personal_predictive_ai.events.models import EventProvenance
from personal_predictive_ai.memory.models import MemoryKind, MemoryScope
from personal_predictive_ai.memory.reconstruction import B2Snapshot
from personal_predictive_ai.memory.retrieval import MemoryQuery, retrieve_memories
from personal_predictive_ai.prediction.config import PredictionConfigV1
from personal_predictive_ai.prediction.models import PredictionExample
from personal_predictive_ai.prediction.retrieval import (
    StructuredRetrievalPredictor,
    _structured_similarity_with_weights,
)


class MemoryFeature(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    schema_version: Literal["ppa.memory-feature/v1"] = "ppa.memory-feature/v1"
    memory_id: str = Field(min_length=1)
    kind: MemoryKind
    key: str = Field(min_length=1)
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    scope_rank: int = Field(ge=0, le=1)

    @field_validator("value")
    @classmethod
    def _require_json_safe_value(cls, value: Any) -> Any:
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("memory feature value must be strict JSON-safe data") from exc
        return value


class ExampleMemoryFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.example-memory-features/v1"] = "ppa.example-memory-features/v1"
    sample_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    features: tuple[MemoryFeature, ...] = ()


class MemoryExposureReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.memory-exposure/v1"] = "ppa.memory-exposure/v1"
    total_samples: int = Field(ge=0)
    memory_available_samples: int = Field(ge=0)
    memory_coverage: float = Field(ge=0.0, le=1.0)
    memory_exposed_test_sessions: int = Field(ge=0)
    distinct_active_memory_ids: int = Field(ge=0)
    status: str = Field(min_length=1)
    eligible: bool
    reasons: tuple[str, ...] = ()


def _query_scope(example: PredictionExample) -> MemoryScope:
    application = example.context.foreground_application
    if application:
        return MemoryScope(scope_type="application", scope_id=application)
    return MemoryScope(scope_type="global", scope_id="user")


def _scope_rank(record_scope: MemoryScope, query_scope: MemoryScope) -> int:
    return 0 if record_scope == query_scope else 1


def memory_features_for_example(
    example: PredictionExample,
    snapshot: B2Snapshot,
    *,
    allowed_provenance: set[EventProvenance],
    limit: int,
) -> tuple[MemoryFeature, ...]:
    if limit < 1:
        raise ValueError("limit must be positive")
    if not allowed_provenance:
        return ()

    query_scope = _query_scope(example)
    safe_records = [
        record
        for record in snapshot.records
        if record.created_seq < example.cutoff_seq
        and record.last_supported_seq < example.cutoff_seq
    ]
    query = MemoryQuery(
        scope=query_scope,
        as_of_ns=max(0, example.target_timestamp_ns - 1),
        allowed_provenance=allowed_provenance,
        kinds={MemoryKind.FACT, MemoryKind.HABIT},
        limit=limit,
        include_historical=True,
    )
    records = retrieve_memories(safe_records, list(snapshot.dependencies), query)
    return tuple(
        MemoryFeature(
            memory_id=record.memory_id,
            kind=record.kind,
            key=record.key,
            value=record.value,
            confidence=record.confidence,
            scope_rank=_scope_rank(record.scope, query_scope),
        )
        for record in records
    )


def audit_memory_exposure(
    examples_with_features: Iterable[ExampleMemoryFeatures],
    config: PredictionConfigV1,
) -> MemoryExposureReport:
    rows = list(examples_with_features)
    available_rows = [row for row in rows if row.features]
    total = len(rows)
    available = len(available_rows)
    coverage = available / total if total else 0.0
    exposed_sessions = {row.session_id for row in available_rows}
    memory_ids = {feature.memory_id for row in available_rows for feature in row.features}

    reasons: list[str] = []
    if available < config.memory_min_available_samples:
        reasons.append(f"available_samples<{config.memory_min_available_samples}")
    if coverage < config.memory_min_coverage:
        reasons.append(f"coverage<{config.memory_min_coverage}")
    if len(exposed_sessions) < config.memory_min_exposed_test_sessions:
        reasons.append(f"exposed_sessions<{config.memory_min_exposed_test_sessions}")
    if len(memory_ids) < config.memory_min_distinct_active_memories:
        reasons.append(f"distinct_memories<{config.memory_min_distinct_active_memories}")

    eligible = not reasons
    return MemoryExposureReport(
        total_samples=total,
        memory_available_samples=available,
        memory_coverage=coverage,
        memory_exposed_test_sessions=len(exposed_sessions),
        distinct_active_memory_ids=len(memory_ids),
        status="PASS" if eligible else "INSUFFICIENT_MEMORY_EXPOSURE",
        eligible=eligible,
        reasons=tuple(reasons),
    )


class MemoryAugmentedRetrievalPredictor(StructuredRetrievalPredictor):
    predictor_id = "structured_retrieval_memory"

    def __init__(
        self,
        *,
        memory_features_by_sample_id: Mapping[str, tuple[MemoryFeature, ...]],
        top_k: int | None = None,
        weights: Mapping[str, float] | None = None,
        config: PredictionConfigV1 | None = None,
    ) -> None:
        super().__init__(top_k=top_k, weights=weights, config=config)
        self._memory_features_by_sample_id = {
            sample_id: tuple(features)
            for sample_id, features in memory_features_by_sample_id.items()
        }

    def _memory_similarity(
        self,
        query_sample_id: str,
        candidate_sample_id: str,
    ) -> float:
        query_ids = {
            feature.memory_id
            for feature in self._memory_features_by_sample_id.get(query_sample_id, ())
        }
        candidate_ids = {
            feature.memory_id
            for feature in self._memory_features_by_sample_id.get(candidate_sample_id, ())
        }
        union = query_ids | candidate_ids
        if not union:
            return 0.0
        return len(query_ids & candidate_ids) / len(union)

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
            score += self.config.memory_similarity_weight * self._memory_similarity(
                example.sample_id,
                candidate.sample_id,
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

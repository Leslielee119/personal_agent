from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field

from personal_predictive_ai.events.models import EventProvenance
from personal_predictive_ai.memory.models import (
    DependencyRelation,
    MemoryDependency,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
)


class MemoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: MemoryScope
    as_of_ns: int = Field(ge=0)
    allowed_provenance: set[EventProvenance]
    kinds: set[MemoryKind]
    limit: int = Field(ge=1)
    include_historical: bool = False


_PROVENANCE_FIELD = {
    EventProvenance.HUMAN_PHYSICAL: "human_physical_support",
    EventProvenance.AI_SUGGESTED_ACCEPTED: "ai_suggested_accepted_support",
    EventProvenance.AI_SUGGESTED_MODIFIED: "ai_suggested_modified_support",
    EventProvenance.AI_EXECUTED: "ai_executed_support",
    EventProvenance.SYSTEM: "system_support",
    EventProvenance.EXTERNAL: "external_support",
    EventProvenance.UNKNOWN: "unknown_support",
}


def _scope_rank(record: MemoryRecord, query: MemoryQuery) -> int | None:
    if record.scope == query.scope:
        return 0
    if record.scope.scope_type == "global":
        return 1
    return None


def _in_valid_interval(record: MemoryRecord, as_of_ns: int) -> bool:
    if as_of_ns < record.valid_from:
        return False
    if record.valid_to is not None and as_of_ns >= record.valid_to:
        return False
    return True


def _status_allowed(record: MemoryRecord, query: MemoryQuery) -> bool:
    if record.status is MemoryStatus.ACTIVE:
        return True
    return query.include_historical and record.status is MemoryStatus.SUPERSEDED


def _provenance_allowed(record: MemoryRecord, query: MemoryQuery) -> bool:
    return any(
        getattr(record.provenance_summary, _PROVENANCE_FIELD[item]) > 0
        for item in query.allowed_provenance
    )


def _passes_base_gates(record: MemoryRecord, query: MemoryQuery) -> bool:
    return (
        _scope_rank(record, query) is not None
        and record.kind in query.kinds
        and _in_valid_interval(record, query.as_of_ns)
        and _status_allowed(record, query)
        and _provenance_allowed(record, query)
    )


def retrieve_memories(
    records: list[MemoryRecord],
    dependencies: list[MemoryDependency],
    query: MemoryQuery,
) -> list[MemoryRecord]:
    by_id = {record.memory_id: record for record in records}
    parents_by_child: dict[str, list[str]] = defaultdict(list)
    for dependency in dependencies:
        if dependency.active and dependency.relation is DependencyRelation.DERIVED_FROM:
            parents_by_child[dependency.child_memory_id].append(dependency.parent_memory_id)
    for child_id in parents_by_child:
        parents_by_child[child_id].sort()

    def dependency_consistent(memory_id: str, trail: set[str]) -> bool:
        if memory_id in trail:
            return True
        next_trail = set(trail)
        next_trail.add(memory_id)
        for parent_id in parents_by_child.get(memory_id, []):
            parent = by_id.get(parent_id)
            if parent is None or not _passes_base_gates(parent, query):
                return False
            if not dependency_consistent(parent_id, next_trail):
                return False
        return True

    eligible = [
        record
        for record in records
        if _passes_base_gates(record, query)
        and dependency_consistent(record.memory_id, set())
    ]
    eligible.sort(
        key=lambda record: (
            _scope_rank(record, query),
            -record.confidence,
            -record.last_supported_seq,
            record.memory_id,
        )
    )
    return eligible[: query.limit]

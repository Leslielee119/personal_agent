from __future__ import annotations

from collections import defaultdict, deque

from pydantic import BaseModel, ConfigDict, Field

from personal_predictive_ai.memory.models import (
    DependencyRelation,
    MemoryAuditEvent,
    MemoryDependency,
    MemoryRecord,
    MemoryStatus,
)
from personal_predictive_ai.memory.temporal import mark_needs_revalidation


class GraphUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    updated_records: list[MemoryRecord] = Field(default_factory=list)
    audit_events: list[MemoryAuditEvent] = Field(default_factory=list)
    recompute_support_ids: list[str] = Field(default_factory=list)
    scope_recheck_ids: list[str] = Field(default_factory=list)


class MemoryGraph:
    def __init__(
        self,
        records: list[MemoryRecord],
        dependencies: list[MemoryDependency],
    ) -> None:
        self._records = {record.memory_id: record for record in records}
        outgoing: dict[str, list[MemoryDependency]] = defaultdict(list)
        for dependency in dependencies:
            if dependency.active:
                outgoing[dependency.parent_memory_id].append(dependency)
        for parent_id, edges in outgoing.items():
            edges.sort(key=self._edge_sort_key)
            outgoing[parent_id] = edges
        self._outgoing = dict(outgoing)

    def _edge_sort_key(self, edge: MemoryDependency) -> tuple[int, str, str, str]:
        child = self._records.get(edge.child_memory_id)
        created_seq = child.created_seq if child is not None else 2**63 - 1
        return (
            created_seq,
            edge.child_memory_id,
            edge.relation.value,
            edge.dependency_id,
        )

    def propagate_parent_change(
        self,
        parent_id: str,
        *,
        source_seq: int,
        reason_code: str,
    ) -> GraphUpdate:
        records = dict(self._records)
        queue: deque[str] = deque([parent_id])
        visited = {parent_id}
        updated_records: list[MemoryRecord] = []
        audit_events: list[MemoryAuditEvent] = []
        recompute_support_ids: list[str] = []
        scope_recheck_ids: list[str] = []
        recompute_seen: set[str] = set()
        scope_seen: set[str] = set()

        while queue:
            current = queue.popleft()
            for edge in self._outgoing.get(current, []):
                child_id = edge.child_memory_id
                if edge.relation is DependencyRelation.SUPPORTS:
                    if child_id not in recompute_seen:
                        recompute_seen.add(child_id)
                        recompute_support_ids.append(child_id)
                    continue
                if edge.relation is DependencyRelation.CONSTRAINS:
                    if child_id not in scope_seen:
                        scope_seen.add(child_id)
                        scope_recheck_ids.append(child_id)
                    continue
                if edge.relation is not DependencyRelation.DERIVED_FROM:
                    continue
                if child_id in visited:
                    continue
                visited.add(child_id)
                child = records.get(child_id)
                if child is None:
                    continue
                if child.status is MemoryStatus.ACTIVE:
                    updated, audit = mark_needs_revalidation(
                        child,
                        source_seq=source_seq,
                        reason_code=reason_code,
                    )
                    records[child_id] = updated
                    updated_records.append(updated)
                    audit_events.append(audit)
                    queue.append(child_id)

        return GraphUpdate(
            updated_records=updated_records,
            audit_events=audit_events,
            recompute_support_ids=recompute_support_ids,
            scope_recheck_ids=scope_recheck_ids,
        )

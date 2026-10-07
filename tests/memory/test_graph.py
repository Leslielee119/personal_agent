from personal_predictive_ai.memory.graph import MemoryGraph
from personal_predictive_ai.memory.models import (
    DependencyRelation,
    MemoryDependency,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    ProvenanceSummary,
)


def _record(memory_id: str, seq: int, status: MemoryStatus = MemoryStatus.ACTIVE) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        kind=MemoryKind.FACT,
        key=memory_id,
        value=memory_id,
        scope=MemoryScope(scope_type="global", scope_id="user"),
        observed_from=seq,
        valid_from=seq,
        created_seq=seq,
        last_supported_seq=seq,
        evidence_ids=[f"evt-{seq}"],
        provenance_summary=ProvenanceSummary(system_support=3),
        support_count=3,
        contradiction_count=0,
        session_ids=["s1", "s2"],
        confidence=1.0,
        status=status,
        extractor_id="unit/v1",
    )


def _dep(parent: str, child: str, relation: DependencyRelation, seq: int) -> MemoryDependency:
    return MemoryDependency(
        dependency_id=f"dep-{parent}-{child}-{relation.value}",
        parent_memory_id=parent,
        child_memory_id=child,
        relation=relation,
        created_seq=seq,
    )


def test_one_level_derived_from_marks_active_child_for_revalidation() -> None:
    graph = MemoryGraph(
        [_record("A", 1), _record("B", 2)],
        [_dep("A", "B", DependencyRelation.DERIVED_FROM, 3)],
    )
    update = graph.propagate_parent_change(
        "A",
        source_seq=10,
        reason_code="parent_superseded",
    )
    assert [(item.memory_id, item.status) for item in update.updated_records] == [
        ("B", MemoryStatus.NEEDS_REVALIDATION)
    ]
    assert [event.memory_id for event in update.audit_events] == ["B"]
    assert update.recompute_support_ids == []
    assert update.scope_recheck_ids == []


def test_three_level_derived_from_propagates_in_created_order() -> None:
    records = [_record("A", 1), _record("B", 2), _record("C", 3), _record("D", 4)]
    dependencies = [
        _dep("A", "B", DependencyRelation.DERIVED_FROM, 5),
        _dep("B", "C", DependencyRelation.DERIVED_FROM, 6),
        _dep("C", "D", DependencyRelation.DERIVED_FROM, 7),
    ]
    update = MemoryGraph(records, dependencies).propagate_parent_change(
        "A", source_seq=20, reason_code="root_changed"
    )
    assert [item.memory_id for item in update.updated_records] == ["B", "C", "D"]
    assert all(item.status is MemoryStatus.NEEDS_REVALIDATION for item in update.updated_records)


def test_supports_and_constrains_return_recompute_sets_without_inventing_state() -> None:
    records = [_record("A", 1), _record("B", 2), _record("C", 3)]
    dependencies = [
        _dep("A", "B", DependencyRelation.SUPPORTS, 4),
        _dep("A", "C", DependencyRelation.CONSTRAINS, 5),
    ]
    update = MemoryGraph(records, dependencies).propagate_parent_change(
        "A", source_seq=10, reason_code="parent_changed"
    )
    assert update.updated_records == []
    assert update.audit_events == []
    assert update.recompute_support_ids == ["B"]
    assert update.scope_recheck_ids == ["C"]


def test_cycle_terminates_deterministically_and_updates_each_reachable_child_once() -> None:
    records = [_record("A", 1), _record("B", 2), _record("C", 3)]
    dependencies = [
        _dep("A", "B", DependencyRelation.DERIVED_FROM, 4),
        _dep("B", "C", DependencyRelation.DERIVED_FROM, 5),
        _dep("C", "A", DependencyRelation.DERIVED_FROM, 6),
    ]
    first = MemoryGraph(records, dependencies).propagate_parent_change(
        "A", source_seq=30, reason_code="cycle_test"
    )
    second = MemoryGraph(records, list(reversed(dependencies))).propagate_parent_change(
        "A", source_seq=30, reason_code="cycle_test"
    )
    assert [item.memory_id for item in first.updated_records] == ["B", "C"]
    assert [item.memory_id for item in second.updated_records] == ["B", "C"]
    assert [event.audit_id for event in first.audit_events] == [
        event.audit_id for event in second.audit_events
    ]
    assert len({item.memory_id for item in first.updated_records}) == len(first.updated_records)

from personal_predictive_ai.events.models import EventProvenance
from personal_predictive_ai.memory.models import (
    DependencyRelation,
    MemoryDependency,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    ProvenanceSummary,
)
from personal_predictive_ai.memory.retrieval import MemoryQuery, retrieve_memories


def _record(
    memory_id: str,
    *,
    scope: MemoryScope,
    kind: MemoryKind = MemoryKind.FACT,
    status: MemoryStatus = MemoryStatus.ACTIVE,
    valid_from: int = 10,
    valid_to: int | None = None,
    confidence: float = 0.8,
    last_supported_seq: int = 10,
    provenance: ProvenanceSummary | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        kind=kind,
        key="k",
        value=memory_id,
        scope=scope,
        observed_from=valid_from,
        valid_from=valid_from,
        valid_to=valid_to,
        created_seq=1,
        last_supported_seq=last_supported_seq,
        evidence_ids=[f"e-{memory_id}"],
        provenance_summary=provenance or ProvenanceSummary(system_support=1),
        support_count=1,
        contradiction_count=0,
        session_ids=["s1"],
        confidence=confidence,
        status=status,
        extractor_id="unit/v1",
    )


def _query(**overrides) -> MemoryQuery:
    data = {
        "scope": MemoryScope(scope_type="application", scope_id="Code.exe"),
        "as_of_ns": 100,
        "allowed_provenance": {EventProvenance.SYSTEM},
        "kinds": {MemoryKind.FACT},
        "limit": 10,
    }
    data.update(overrides)
    return MemoryQuery(**data)


def test_scope_temporal_status_provenance_kind_and_limit_gates() -> None:
    exact = _record(
        "exact",
        scope=MemoryScope(scope_type="application", scope_id="Code.exe"),
        confidence=0.7,
    )
    global_record = _record(
        "global",
        scope=MemoryScope(scope_type="global", scope_id="user"),
        confidence=0.9,
    )
    wrong_scope = _record(
        "wrong-scope",
        scope=MemoryScope(scope_type="application", scope_id="Chrome.exe"),
    )
    expired = _record(
        "expired",
        scope=exact.scope,
        valid_from=10,
        valid_to=100,
    )
    future = _record("future", scope=exact.scope, valid_from=101)
    pending = _record("pending", scope=exact.scope, status=MemoryStatus.NEEDS_REVALIDATION)
    wrong_kind = _record("habit", scope=exact.scope, kind=MemoryKind.HABIT)
    wrong_source = _record(
        "external",
        scope=exact.scope,
        provenance=ProvenanceSummary(external_support=1),
    )

    result = retrieve_memories(
        [global_record, wrong_scope, expired, future, pending, wrong_kind, wrong_source, exact],
        [],
        _query(limit=2),
    )
    assert [item.memory_id for item in result] == ["exact", "global"]


def test_rank_is_exact_scope_then_confidence_then_recency_then_id() -> None:
    scope = MemoryScope(scope_type="application", scope_id="Code.exe")
    records = [
        _record("b", scope=scope, confidence=0.9, last_supported_seq=20),
        _record("a", scope=scope, confidence=0.9, last_supported_seq=20),
        _record("recent", scope=scope, confidence=0.9, last_supported_seq=30),
        _record("high", scope=scope, confidence=1.0, last_supported_seq=1),
        _record("global", scope=MemoryScope(scope_type="global", scope_id="user"), confidence=1.0),
    ]
    result = retrieve_memories(records, [], _query(limit=5))
    assert [item.memory_id for item in result] == ["high", "recent", "a", "b", "global"]


def test_historical_query_returns_old_fact_only_inside_its_former_interval() -> None:
    scope = MemoryScope(scope_type="application", scope_id="Code.exe")
    old = _record(
        "old",
        scope=scope,
        status=MemoryStatus.SUPERSEDED,
        valid_from=10,
        valid_to=50,
    )
    new = _record("new", scope=scope, valid_from=50)

    now = retrieve_memories([old, new], [], _query(as_of_ns=100, include_historical=False))
    historical = retrieve_memories(
        [old, new],
        [],
        _query(as_of_ns=25, include_historical=True),
    )
    boundary = retrieve_memories(
        [old, new],
        [],
        _query(as_of_ns=50, include_historical=True),
    )
    assert [item.memory_id for item in now] == ["new"]
    assert [item.memory_id for item in historical] == ["old"]
    assert [item.memory_id for item in boundary] == ["new"]


def test_dependency_consistency_filters_child_when_derived_parent_is_not_retrieval_valid() -> None:
    scope = MemoryScope(scope_type="application", scope_id="Code.exe")
    parent = _record("parent", scope=scope, status=MemoryStatus.SUPERSEDED, valid_to=50)
    child = _record("child", scope=scope)
    dependency = MemoryDependency(
        dependency_id="dep-1",
        parent_memory_id="parent",
        child_memory_id="child",
        relation=DependencyRelation.DERIVED_FROM,
        created_seq=5,
    )
    result = retrieve_memories([parent, child], [dependency], _query(as_of_ns=100))
    assert result == []


def test_provenance_allowlist_accepts_memory_with_at_least_one_allowed_support_source() -> None:
    scope = MemoryScope(scope_type="application", scope_id="Code.exe")
    mixed = _record(
        "mixed",
        scope=scope,
        provenance=ProvenanceSummary(system_support=1, external_support=4),
    )
    assert [item.memory_id for item in retrieve_memories([mixed], [], _query())] == ["mixed"]
    external_only_query = _query(allowed_provenance={EventProvenance.EXTERNAL})
    assert [item.memory_id for item in retrieve_memories([mixed], [], external_only_query)] == [
        "mixed"
    ]

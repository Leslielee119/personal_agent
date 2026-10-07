import pytest

from personal_predictive_ai.memory.models import (
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    ProvenanceSummary,
)
from personal_predictive_ai.memory.temporal import (
    activate,
    invalidate,
    mark_needs_revalidation,
    revalidate,
    supersede,
)


def _record(
    memory_id: str,
    *,
    status: MemoryStatus,
    value: str = "chrome",
    kind: MemoryKind = MemoryKind.FACT,
    observed_from: int = 100,
    valid_from: int = 100,
    created_seq: int = 1,
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        kind=kind,
        key="preferred_browser",
        value=value,
        scope=MemoryScope(scope_type="global", scope_id="user"),
        observed_from=observed_from,
        valid_from=valid_from,
        created_seq=created_seq,
        last_supported_seq=created_seq,
        evidence_ids=[f"evt-{created_seq}"],
        provenance_summary=ProvenanceSummary(system_support=3),
        support_count=3,
        contradiction_count=0,
        session_ids=["s1", "s2"],
        confidence=1.0,
        status=status,
        extractor_id="fact.foreground_application/v1",
    )


def test_candidate_can_activate_and_emits_audit() -> None:
    record = _record("m1", status=MemoryStatus.CANDIDATE)
    active, audit = activate(record, source_seq=5, reason_code="fact_gates_passed")
    assert active.status is MemoryStatus.ACTIVE
    assert record.status is MemoryStatus.CANDIDATE
    assert audit.memory_id == "m1"
    assert audit.event_type == "memory.consolidated"
    assert audit.source_seq == 5
    assert audit.reason_code == "fact_gates_passed"


def test_active_revalidation_round_trip_and_invalidation_are_explicit() -> None:
    active = _record("m1", status=MemoryStatus.ACTIVE)
    pending, pending_audit = mark_needs_revalidation(
        active,
        source_seq=6,
        reason_code="parent_superseded",
    )
    assert pending.status is MemoryStatus.NEEDS_REVALIDATION
    assert pending_audit.event_type == "memory.revalidation_required"

    restored, restored_audit = revalidate(
        pending,
        source_seq=7,
        reason_code="evidence_still_supports",
    )
    assert restored.status is MemoryStatus.ACTIVE
    assert restored_audit.event_type == "memory.revalidated"

    invalid, invalid_audit = invalidate(
        pending,
        source_seq=8,
        reason_code="evidence_no_longer_supports",
    )
    assert invalid.status is MemoryStatus.INVALID
    assert invalid_audit.event_type == "memory.invalidated"


def test_forbidden_state_transitions_raise() -> None:
    invalid = _record("m1", status=MemoryStatus.INVALID)
    active = _record("m2", status=MemoryStatus.ACTIVE)
    with pytest.raises(ValueError):
        activate(invalid, source_seq=5, reason_code="no")
    with pytest.raises(ValueError):
        revalidate(active, source_seq=5, reason_code="no")


def test_supersession_preserves_old_fact_and_interval_history() -> None:
    old = _record("m-old", status=MemoryStatus.ACTIVE, value="chrome", valid_from=100)
    new = _record(
        "m-new",
        status=MemoryStatus.ACTIVE,
        value="firefox",
        valid_from=200,
        created_seq=10,
    )
    old_after, new_after, edge, audits = supersede(old, new, source_seq=10)

    assert old.status is MemoryStatus.ACTIVE
    assert old_after.status is MemoryStatus.SUPERSEDED
    assert old_after.valid_to == 200
    assert new_after.status is MemoryStatus.ACTIVE
    assert new_after.valid_to is None
    assert edge.old_memory_id == "m-old"
    assert edge.new_memory_id == "m-new"
    assert edge.created_seq == 10
    assert [audit.event_type for audit in audits] == ["memory.superseded", "memory.supersedes"]

    again = supersede(old, new, source_seq=10)
    assert again[2].supersession_id == edge.supersession_id
    assert [item.audit_id for item in again[3]] == [item.audit_id for item in audits]


def test_supersession_rejects_incompatible_claims() -> None:
    old = _record("m-old", status=MemoryStatus.ACTIVE, value="chrome")
    same_value = _record("m-new", status=MemoryStatus.ACTIVE, value="chrome", created_seq=2)
    wrong_kind = _record(
        "m-habit",
        status=MemoryStatus.ACTIVE,
        value="firefox",
        kind=MemoryKind.HABIT,
        created_seq=3,
    )
    with pytest.raises(ValueError):
        supersede(old, same_value, source_seq=3)
    with pytest.raises(ValueError):
        supersede(old, wrong_kind, source_seq=3)


def test_clock_regression_does_not_control_supersession_or_audit_order() -> None:
    old = _record(
        "m-old",
        status=MemoryStatus.ACTIVE,
        value="chrome",
        observed_from=200,
        valid_from=200,
        created_seq=1,
    )
    new = _record(
        "m-new",
        status=MemoryStatus.ACTIVE,
        value="firefox",
        observed_from=100,
        valid_from=250,
        created_seq=20,
    )
    old_after, _, edge, audits = supersede(old, new, source_seq=20)
    assert old_after.valid_to == 250
    assert edge.created_seq == 20
    assert all(audit.source_seq == 20 for audit in audits)

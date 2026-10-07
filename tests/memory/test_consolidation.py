import pytest

from personal_predictive_ai.memory.consolidation import consolidate, reassess_active
from personal_predictive_ai.memory.models import (
    ConsolidationConfigV1,
    MemoryCandidate,
    MemoryKind,
    MemoryScope,
    MemoryStatus,
    ProvenanceSummary,
)


def _candidate(
    kind: MemoryKind,
    *,
    support: int,
    contradiction: int,
    sessions: int,
    eligible_support: int | None = None,
    eligible_human: int | None = None,
    provenance: ProvenanceSummary | None = None,
) -> MemoryCandidate:
    ratio = support / (support + contradiction) if support + contradiction else 0.0
    if provenance is None:
        provenance = (
            ProvenanceSummary(system_support=support)
            if kind is MemoryKind.FACT
            else ProvenanceSummary(human_physical_support=support)
        )
    if eligible_support is None:
        eligible_support = support if kind is MemoryKind.HABIT else 0
    if eligible_human is None:
        eligible_human = support if kind is MemoryKind.HABIT else 0
    return MemoryCandidate(
        memory_id=f"mem-{kind.value}",
        kind=kind,
        key="k",
        value="v",
        scope=MemoryScope(scope_type="global", scope_id="user"),
        observed_from=1,
        valid_from=1,
        created_seq=1,
        last_supported_seq=max(1, support + contradiction),
        evidence_ids=[f"e{i}" for i in range(support + contradiction)],
        provenance_summary=provenance,
        support_count=support,
        contradiction_count=contradiction,
        session_ids=[f"s{i}" for i in range(sessions)],
        confidence=ratio,
        extractor_id="unit/v1",
        eligible_support_count=eligible_support,
        eligible_human_support_count=eligible_human,
    )


@pytest.mark.parametrize(
    ("support", "contradiction", "sessions", "expected"),
    [
        (2, 0, 2, MemoryStatus.CANDIDATE),
        (3, 0, 1, MemoryStatus.CANDIDATE),
        (3, 0, 2, MemoryStatus.ACTIVE),
        (4, 1, 2, MemoryStatus.ACTIVE),
        (8, 1, 3, MemoryStatus.ACTIVE),
    ],
)
def test_fact_threshold_boundaries(support, contradiction, sessions, expected) -> None:
    record, audits = consolidate(
        _candidate(
            MemoryKind.FACT,
            support=support,
            contradiction=contradiction,
            sessions=sessions,
        ),
        config=ConsolidationConfigV1(),
    )
    assert record.status is expected
    assert audits


@pytest.mark.parametrize(
    ("support", "contradiction", "sessions", "expected"),
    [
        (4, 0, 3, MemoryStatus.CANDIDATE),
        (5, 0, 2, MemoryStatus.CANDIDATE),
        (5, 3, 3, MemoryStatus.CANDIDATE),
        (7, 3, 3, MemoryStatus.ACTIVE),
        (6, 0, 4, MemoryStatus.ACTIVE),
    ],
)
def test_habit_threshold_boundaries(support, contradiction, sessions, expected) -> None:
    record, audits = consolidate(
        _candidate(
            MemoryKind.HABIT,
            support=support,
            contradiction=contradiction,
            sessions=sessions,
        ),
        config=ConsolidationConfigV1(),
    )
    assert record.status is expected
    assert audits


def test_failed_candidate_audit_names_failed_gates() -> None:
    record, audits = consolidate(
        _candidate(MemoryKind.HABIT, support=4, contradiction=3, sessions=1),
        config=ConsolidationConfigV1(),
    )
    assert record.status is MemoryStatus.CANDIDATE
    failed = audits[-1].details["failed_gates"]
    assert "habit_min_support" in failed
    assert "habit_min_sessions" in failed
    assert "habit_min_ratio" in failed


def test_ai_executed_and_unknown_cannot_satisfy_human_support_gate() -> None:
    for provenance in (
        ProvenanceSummary(ai_executed_support=100),
        ProvenanceSummary(unknown_support=100),
    ):
        record, audits = consolidate(
            _candidate(
                MemoryKind.HABIT,
                support=100,
                contradiction=0,
                sessions=100,
                eligible_support=0,
                eligible_human=0,
                provenance=provenance,
            ),
            config=ConsolidationConfigV1(),
        )
        assert record.status is MemoryStatus.CANDIDATE
        assert "habit_min_eligible_support" in audits[-1].details["failed_gates"]
        assert "habit_human_support" in audits[-1].details["failed_gates"]


def test_active_memory_with_new_contradiction_requires_revalidation() -> None:
    good = _candidate(MemoryKind.HABIT, support=7, contradiction=3, sessions=3)
    active, _ = consolidate(good, config=ConsolidationConfigV1())
    assert active.status is MemoryStatus.ACTIVE

    degraded = _candidate(MemoryKind.HABIT, support=5, contradiction=5, sessions=3)
    updated, audits = reassess_active(active, degraded, config=ConsolidationConfigV1())
    assert updated.status is MemoryStatus.NEEDS_REVALIDATION
    assert updated.support_count == 5
    assert updated.contradiction_count == 5
    assert audits[-1].event_type == "memory.revalidation_required"

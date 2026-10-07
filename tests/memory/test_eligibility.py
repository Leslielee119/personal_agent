from personal_predictive_ai.events.models import EventProvenance
from personal_predictive_ai.memory.eligibility import (
    habit_support_eligible,
    learning_eligibility,
    summarize_provenance,
)
from personal_predictive_ai.memory.models import (
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    ProvenanceSummary,
)


def _memory(kind: MemoryKind, summary: ProvenanceSummary) -> MemoryRecord:
    return MemoryRecord(
        memory_id=f"mem-{kind.value}",
        kind=kind,
        key="k",
        value="v",
        scope=MemoryScope(scope_type="global", scope_id="user"),
        observed_from=1,
        valid_from=1,
        created_seq=1,
        last_supported_seq=1,
        evidence_ids=["e1"],
        provenance_summary=summary,
        support_count=sum(summary.model_dump().values()),
        contradiction_count=0,
        session_ids=["s1"],
        confidence=1.0,
        status=MemoryStatus.ACTIVE,
        extractor_id="unit/v1",
        eligible_support_count=(
            summary.human_physical_support
            + summary.ai_suggested_accepted_support
            + summary.ai_suggested_modified_support
        ),
        eligible_human_support_count=summary.human_physical_support,
    )


def test_summarize_provenance_counts_all_seven_classes() -> None:
    values = [
        EventProvenance.HUMAN_PHYSICAL,
        EventProvenance.AI_SUGGESTED_ACCEPTED,
        EventProvenance.AI_SUGGESTED_MODIFIED,
        EventProvenance.AI_EXECUTED,
        EventProvenance.SYSTEM,
        EventProvenance.EXTERNAL,
        EventProvenance.UNKNOWN,
        EventProvenance.HUMAN_PHYSICAL,
    ]
    summary = summarize_provenance(values)
    assert summary == ProvenanceSummary(
        human_physical_support=2,
        ai_suggested_accepted_support=1,
        ai_suggested_modified_support=1,
        ai_executed_support=1,
        system_support=1,
        external_support=1,
        unknown_support=1,
    )


def test_habit_support_eligible_matches_frozen_v1_set() -> None:
    eligible = {
        EventProvenance.HUMAN_PHYSICAL,
        EventProvenance.AI_SUGGESTED_ACCEPTED,
        EventProvenance.AI_SUGGESTED_MODIFIED,
    }
    for provenance in EventProvenance:
        assert habit_support_eligible(provenance) is (provenance in eligible)


def test_ai_executed_and_unknown_repetition_never_become_habit_support() -> None:
    assert not any(habit_support_eligible(EventProvenance.AI_EXECUTED) for _ in range(100))
    assert not any(habit_support_eligible(EventProvenance.UNKNOWN) for _ in range(100))


def test_learning_eligibility_distinguishes_memory_kind_and_source() -> None:
    system_fact = _memory(MemoryKind.FACT, ProvenanceSummary(system_support=3))
    external_fact = _memory(MemoryKind.FACT, ProvenanceSummary(external_support=3))
    human_habit = _memory(MemoryKind.HABIT, ProvenanceSummary(human_physical_support=5))
    ai_habit = _memory(MemoryKind.HABIT, ProvenanceSummary(ai_executed_support=100))
    unknown_habit = _memory(MemoryKind.HABIT, ProvenanceSummary(unknown_support=100))
    human_style = _memory(MemoryKind.STYLE, ProvenanceSummary(human_physical_support=5))

    assert learning_eligibility(system_fact, "world_state")
    assert not learning_eligibility(external_fact, "world_state")
    assert learning_eligibility(human_habit, "personal_policy")
    assert not learning_eligibility(ai_habit, "personal_policy")
    assert not learning_eligibility(unknown_habit, "personal_policy")
    assert learning_eligibility(human_style, "generator_style")
    assert not learning_eligibility(human_habit, "generator_style")


def test_non_active_memory_is_not_learning_eligible() -> None:
    candidate = _memory(
        MemoryKind.HABIT,
        ProvenanceSummary(human_physical_support=5),
    ).model_copy(update={"status": MemoryStatus.CANDIDATE})
    assert not learning_eligibility(candidate, "personal_policy")

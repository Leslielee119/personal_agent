from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from personal_predictive_ai.events.models import EventProvenance
from personal_predictive_ai.memory.models import (
    MemoryKind,
    MemoryRecord,
    MemoryStatus,
    ProvenanceSummary,
)

_COUNTER_BY_PROVENANCE = {
    EventProvenance.HUMAN_PHYSICAL: "human_physical_support",
    EventProvenance.AI_SUGGESTED_ACCEPTED: "ai_suggested_accepted_support",
    EventProvenance.AI_SUGGESTED_MODIFIED: "ai_suggested_modified_support",
    EventProvenance.AI_EXECUTED: "ai_executed_support",
    EventProvenance.SYSTEM: "system_support",
    EventProvenance.EXTERNAL: "external_support",
    EventProvenance.UNKNOWN: "unknown_support",
}

_HABIT_SUPPORT_ELIGIBLE = {
    EventProvenance.HUMAN_PHYSICAL,
    EventProvenance.AI_SUGGESTED_ACCEPTED,
    EventProvenance.AI_SUGGESTED_MODIFIED,
}


def summarize_provenance(items: Iterable[EventProvenance]) -> ProvenanceSummary:
    counts = {field: 0 for field in _COUNTER_BY_PROVENANCE.values()}
    for provenance in items:
        counts[_COUNTER_BY_PROVENANCE[provenance]] += 1
    return ProvenanceSummary(**counts)


def habit_support_eligible(provenance: EventProvenance) -> bool:
    return provenance in _HABIT_SUPPORT_ELIGIBLE


def _eligible_human_support(summary: ProvenanceSummary) -> int:
    return (
        summary.human_physical_support
        + summary.ai_suggested_accepted_support
        + summary.ai_suggested_modified_support
    )


def learning_eligibility(
    memory: MemoryRecord,
    target: Literal["world_state", "personal_policy", "generator_style"],
) -> bool:
    if memory.status is not MemoryStatus.ACTIVE:
        return False

    if target == "world_state":
        return memory.kind is MemoryKind.FACT and memory.provenance_summary.system_support > 0
    if target == "personal_policy":
        return memory.kind is MemoryKind.HABIT and _eligible_human_support(
            memory.provenance_summary
        ) > 0
    if target == "generator_style":
        return memory.kind is MemoryKind.STYLE and _eligible_human_support(
            memory.provenance_summary
        ) > 0
    return False

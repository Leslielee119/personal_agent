from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.memory.eligibility import habit_support_eligible, summarize_provenance
from personal_predictive_ai.memory.ids import memory_id_for
from personal_predictive_ai.memory.models import (
    ConsolidationConfigV1,
    MemoryCandidate,
    MemoryKind,
    MemoryScope,
)
from personal_predictive_ai.state.sessions import SessionSegment

_EXTRACTOR_ID = "habit.next_operation/v1"


def _session_for_action(
    action: NormalizedAction,
    mapping: Mapping[str, str] | None,
) -> str | None:
    if mapping is not None:
        return mapping.get(action.source_event_id)
    if isinstance(action.context, dict):
        value = action.context.get("session_id")
        if isinstance(value, str) and value:
            return value
    return None


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def extract_next_operation_habits(
    actions: Iterable[NormalizedAction],
    sessions: Iterable[SessionSegment],
    *,
    config: ConsolidationConfigV1,
    session_id_by_event_id: Mapping[str, str] | None = None,
) -> list[MemoryCandidate]:
    valid_session_ids = {session.session_id for session in sessions}
    grouped: dict[str, list[NormalizedAction]] = defaultdict(list)
    for action in actions:
        session_id = _session_for_action(action, session_id_by_event_id)
        if session_id is not None and session_id in valid_session_ids:
            grouped[session_id].append(action)

    observations: dict[tuple[str, str], list[tuple[str, NormalizedAction, NormalizedAction]]] = (
        defaultdict(list)
    )
    for session_id in sorted(grouped):
        ordered = sorted(grouped[session_id], key=lambda item: item.monotonic_seq)
        for current, target in zip(ordered, ordered[1:], strict=False):
            application = current.application or "*"
            observations[(application, current.operation)].append((session_id, current, target))

    result: list[tuple[str, int, int, str, MemoryCandidate]] = []
    for (application, current_operation), pairs in observations.items():
        pairs.sort(key=lambda item: item[2].monotonic_seq)
        values = _unique(target.operation for _, _, target in pairs)
        for value in values:
            supporting = [item for item in pairs if item[2].operation == value]
            eligible_supporting = [
                item for item in supporting if habit_support_eligible(item[2].provenance)
            ]
            eligible_contradictions = [
                item
                for item in pairs
                if item[2].operation != value and habit_support_eligible(item[2].provenance)
            ]
            first = supporting[0][2]
            support_count = len(eligible_supporting)
            contradiction_count = len(eligible_contradictions)
            denominator = support_count + contradiction_count
            session_ids = _unique(item[0] for item in eligible_supporting)
            evidence_ids = _unique(
                evidence_id
                for _, current, target in supporting
                for evidence_id in (current.source_event_id, target.source_event_id)
            )
            contradiction_evidence_ids = _unique(
                evidence_id
                for _, current, target in eligible_contradictions
                for evidence_id in (current.source_event_id, target.source_event_id)
            )
            scope = (
                MemoryScope(scope_type="application", scope_id=application)
                if application != "*"
                else MemoryScope(scope_type="global", scope_id="user")
            )
            key = f"habit.next_operation:{application}:{current_operation}"
            memory_id = memory_id_for(MemoryKind.HABIT, scope, key, value, _EXTRACTOR_ID)
            candidate = MemoryCandidate(
                memory_id=memory_id,
                kind=MemoryKind.HABIT,
                key=key,
                value=value,
                scope=scope,
                observed_from=first.timestamp_ns,
                valid_from=first.timestamp_ns,
                created_seq=first.monotonic_seq,
                last_supported_seq=supporting[-1][2].monotonic_seq,
                evidence_ids=evidence_ids,
                contradiction_evidence_ids=contradiction_evidence_ids,
                provenance_summary=summarize_provenance(
                    target.provenance for _, _, target in supporting
                ),
                support_count=support_count,
                contradiction_count=contradiction_count,
                session_ids=session_ids,
                confidence=(support_count / denominator) if denominator else 0.0,
                extractor_id=_EXTRACTOR_ID,
                config_version=config.schema_version,
                eligible_support_count=support_count,
                eligible_human_support_count=support_count,
            )
            result.append((key, -support_count, first.monotonic_seq, value, candidate))

    result.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4].memory_id))
    return [item[4] for item in result]

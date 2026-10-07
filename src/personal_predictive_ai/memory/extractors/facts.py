from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from personal_predictive_ai.events.models import CanonicalEvent
from personal_predictive_ai.memory.eligibility import summarize_provenance
from personal_predictive_ai.memory.ids import memory_id_for
from personal_predictive_ai.memory.models import (
    ConsolidationConfigV1,
    MemoryCandidate,
    MemoryKind,
    MemoryScope,
)
from personal_predictive_ai.state.models import StateSnapshot

_EXTRACTOR_ID = "fact.foreground_application/v1"
_FOREGROUND_TYPES = {"window.foreground.current", "window.foreground.changed"}


def _unique_in_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def extract_foreground_application_facts(
    events: Iterable[CanonicalEvent],
    snapshots: Iterable[StateSnapshot],
    *,
    config: ConsolidationConfigV1,
) -> list[MemoryCandidate]:
    snapshot_by_event = {item.source_event_id: item for item in snapshots}
    ordered = sorted(events, key=lambda item: item.monotonic_seq)
    eligible = [
        event
        for event in ordered
        if event.event_type in _FOREGROUND_TYPES
        and isinstance((event.app or {}).get("name"), str)
        and bool(str((event.app or {}).get("name", "")).strip())
    ]
    by_app: dict[str, list[CanonicalEvent]] = defaultdict(list)
    for event in eligible:
        by_app[str(event.app["name"])].append(event)

    scope = MemoryScope(scope_type="global", scope_id="user")
    total = len(eligible)
    candidates: list[tuple[int, int, str, MemoryCandidate]] = []
    for app_name, supporting in by_app.items():
        first = supporting[0]
        support_count = len(supporting)
        contradiction_count = total - support_count
        session_ids = _unique_in_order(
            snapshot_by_event[event.event_id].session_id
            for event in supporting
            if event.event_id in snapshot_by_event
            and snapshot_by_event[event.event_id].session_id is not None
        )
        memory_id = memory_id_for(
            MemoryKind.FACT,
            scope,
            "foreground_application.primary",
            app_name,
            _EXTRACTOR_ID,
        )
        candidate = MemoryCandidate(
            memory_id=memory_id,
            kind=MemoryKind.FACT,
            key="foreground_application.primary",
            value=app_name,
            scope=scope,
            observed_from=first.timestamp_ns,
            valid_from=first.timestamp_ns,
            created_seq=first.monotonic_seq,
            last_supported_seq=supporting[-1].monotonic_seq,
            evidence_ids=[event.event_id for event in supporting],
            provenance_summary=summarize_provenance(event.provenance for event in supporting),
            support_count=support_count,
            contradiction_count=contradiction_count,
            session_ids=session_ids,
            confidence=(support_count / total) if total else 0.0,
            extractor_id=_EXTRACTOR_ID,
            config_version=config.schema_version,
        )
        candidates.append((-support_count, first.monotonic_seq, app_name.casefold(), candidate))

    candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3].memory_id))
    return [item[3] for item in candidates]

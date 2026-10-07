from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path

from personal_predictive_ai.diagnostics.state_replay import _source_version_counts
from personal_predictive_ai.memory.consolidation import consolidate
from personal_predictive_ai.memory.extractors.facts import extract_foreground_application_facts
from personal_predictive_ai.memory.extractors.habits import extract_next_operation_habits
from personal_predictive_ai.memory.models import (
    ConsolidationConfigV1,
    EvidenceRole,
    MemoryAuditEvent,
    MemoryEvidenceLink,
    MemoryKind,
    MemoryRecord,
    MemoryStatus,
    SupersessionEdge,
)
from personal_predictive_ai.memory.temporal import supersede
from personal_predictive_ai.storage.derived_store import DerivedStore
from personal_predictive_ai.storage.memory_store import MemoryRunMetadata, MemoryStore
from personal_predictive_ai.storage.sqlite_store import EventStore

_EXTRACTOR_VERSION = "b2-deterministic/v1"


def _apply_fact_supersession(
    records: list[MemoryRecord],
) -> tuple[list[MemoryRecord], list[SupersessionEdge], list[MemoryAuditEvent]]:
    by_id = {record.memory_id: record for record in records}
    groups: dict[tuple[str, str, str], list[MemoryRecord]] = defaultdict(list)
    for record in records:
        if record.kind is MemoryKind.FACT and record.status is MemoryStatus.ACTIVE:
            groups[(record.scope.scope_type, record.scope.scope_id, record.key)].append(record)

    edges: list[SupersessionEdge] = []
    audits: list[MemoryAuditEvent] = []
    for group_key in sorted(groups):
        group = groups[group_key]
        ordered = sorted(group, key=lambda item: (item.created_seq, item.memory_id))
        current = ordered[0]
        for newer in ordered[1:]:
            # A wall-clock regression must never fabricate a negative validity interval.
            # If temporal order is ambiguous, retain both claims for later revalidation.
            if newer.valid_from < current.valid_from:
                current = newer
                continue
            old_after, new_after, edge, new_audits = supersede(
                current,
                newer,
                source_seq=newer.created_seq,
            )
            by_id[old_after.memory_id] = old_after
            by_id[new_after.memory_id] = new_after
            edges.append(edge)
            audits.extend(new_audits)
            current = new_after

    output = sorted(by_id.values(), key=lambda item: (item.created_seq, item.memory_id))
    edges.sort(key=lambda item: (item.created_seq, item.supersession_id))
    return output, edges, audits


def _evidence_links(candidate) -> list[MemoryEvidenceLink]:
    links = [
        MemoryEvidenceLink(
            memory_id=candidate.memory_id,
            evidence_type="canonical_event",
            evidence_id=evidence_id,
            role=EvidenceRole.SUPPORT,
        )
        for evidence_id in candidate.evidence_ids
    ]
    links.extend(
        MemoryEvidenceLink(
            memory_id=candidate.memory_id,
            evidence_type="canonical_event",
            evidence_id=evidence_id,
            role=EvidenceRole.CONTRADICTION,
        )
        for evidence_id in candidate.contradiction_evidence_ids
    )
    return links


def derive_b2(
    db_path: str | Path,
    *,
    source_b1_run_id: str,
    run_id: str,
    config: ConsolidationConfigV1 | None = None,
) -> dict[str, object]:
    path = Path(db_path)
    cfg = config or ConsolidationConfigV1()
    event_store = EventStore(path)
    derived_store = DerivedStore(path)
    memory_store = MemoryStore(path)
    try:
        b1_run = derived_store.get_run(source_b1_run_id)
        if b1_run is None:
            raise ValueError(f"B1 run not found: {source_b1_run_id}")

        events = list(event_store.iter_events_by_sequence())
        snapshots = list(derived_store.iter_snapshots(source_b1_run_id))
        actions = list(derived_store.iter_actions(source_b1_run_id))
        sessions = list(derived_store.iter_sessions(source_b1_run_id))

        facts = extract_foreground_application_facts(events, snapshots, config=cfg)
        session_id_by_event_id = {
            snapshot.source_event_id: snapshot.session_id
            for snapshot in snapshots
            if snapshot.session_id is not None
        }
        habits = extract_next_operation_habits(
            actions,
            sessions,
            config=cfg,
            session_id_by_event_id=session_id_by_event_id,
        )
        candidates = sorted(
            [*facts, *habits],
            key=lambda item: (item.created_seq, item.memory_id),
        )

        records: list[MemoryRecord] = []
        links: list[MemoryEvidenceLink] = []
        audits: list[MemoryAuditEvent] = []
        for candidate in candidates:
            record, candidate_audits = consolidate(candidate, config=cfg)
            records.append(record)
            links.extend(_evidence_links(candidate))
            audits.extend(candidate_audits)

        records, supersessions, supersession_audits = _apply_fact_supersession(records)
        audits.extend(supersession_audits)
        audits.sort(key=lambda item: (item.source_seq, item.audit_id))
        links.sort(
            key=lambda item: (
                item.memory_id,
                item.evidence_type,
                item.evidence_id,
                item.role.value,
            )
        )

        # B2 V1 deliberately has no dependency extractor. The graph storage and
        # propagation semantics are implemented, but reconstruction does not invent edges.
        dependencies = []
        metadata = MemoryRunMetadata(
            run_id=run_id,
            source_b1_run_id=source_b1_run_id,
            source_high_water=b1_run.source_high_water,
            extractor_version=_EXTRACTOR_VERSION,
            config_version=cfg.schema_version,
        )
        memory_store.replace_run(
            metadata,
            records,
            links,
            dependencies,
            supersessions,
            audits,
        )

        status_counts = Counter(record.status.value for record in records)
        v1_count, v2_count = _source_version_counts(path)
        return {
            "run_id": run_id,
            "source_b1_run_id": source_b1_run_id,
            "source_high_water": b1_run.source_high_water,
            "source_event_count": len(events),
            "v1_count": v1_count,
            "v2_count": v2_count,
            "fact_candidates": len(facts),
            "fact_active": sum(
                record.kind is MemoryKind.FACT and record.status is MemoryStatus.ACTIVE
                for record in records
            ),
            "habit_candidates": len(habits),
            "habit_active": sum(
                record.kind is MemoryKind.HABIT and record.status is MemoryStatus.ACTIVE
                for record in records
            ),
            "status_counts": dict(sorted(status_counts.items())),
            "dependencies": len(dependencies),
            "supersessions": len(supersessions),
            "audit_events": len(audits),
            "ai_executed_support": sum(
                record.provenance_summary.ai_executed_support for record in records
            ),
            "unknown_support": sum(
                record.provenance_summary.unknown_support for record in records
            ),
            "extractor_version": _EXTRACTOR_VERSION,
            "config_version": cfg.schema_version,
            "integrity": memory_store.integrity_check(),
        }
    finally:
        memory_store.close()
        derived_store.close()
        event_store.close()


def iter_b2_replay_lines(
    store: MemoryStore,
    run_id: str,
    *,
    limit: int | None = None,
) -> Iterator[str]:
    reasons: dict[str, list[str]] = defaultdict(list)
    for audit in store.iter_audit_events(run_id):
        reasons[audit.memory_id].append(audit.reason_code)

    count = 0
    for record in store.iter_records(run_id):
        if limit is not None and count >= limit:
            return
        provenance = record.provenance_summary
        reason_text = ",".join(reasons.get(record.memory_id, [])) or "-"
        yield (
            f"{record.memory_id} | kind={record.kind.value} key={record.key} "
            f"status={record.status.value} support={record.support_count} "
            f"contradiction={record.contradiction_count} "
            f"prov=h{provenance.human_physical_support}/ai{provenance.ai_executed_support}/"
            f"u{provenance.unknown_support}/s{provenance.system_support} "
            f"reasons={reason_text}"
        )
        count += 1

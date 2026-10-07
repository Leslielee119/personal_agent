from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from personal_predictive_ai.memory.consolidation import consolidate
from personal_predictive_ai.memory.extractors.facts import extract_foreground_application_facts
from personal_predictive_ai.memory.extractors.habits import extract_next_operation_habits
from personal_predictive_ai.memory.models import (
    ConsolidationConfigV1,
    EvidenceRole,
    MemoryAuditEvent,
    MemoryDependency,
    MemoryEvidenceLink,
    MemoryKind,
    MemoryRecord,
    MemoryStatus,
    SupersessionEdge,
)
from personal_predictive_ai.memory.temporal import supersede
from personal_predictive_ai.storage.derived_store import DerivedStore
from personal_predictive_ai.storage.sqlite_store import EventStore

EXTRACTOR_VERSION = "b2-deterministic/v1"


class B2Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.b2-snapshot/v1"] = "ppa.b2-snapshot/v1"
    source_b1_run_id: str = Field(min_length=1)
    source_high_water: int = Field(ge=0)
    source_event_count: int = Field(ge=0)
    v1_count: int = Field(ge=0)
    v2_count: int = Field(ge=0)
    fact_candidates: int = Field(ge=0)
    habit_candidates: int = Field(ge=0)
    records: tuple[MemoryRecord, ...]
    evidence_links: tuple[MemoryEvidenceLink, ...]
    dependencies: tuple[MemoryDependency, ...]
    supersessions: tuple[SupersessionEdge, ...]
    audit_events: tuple[MemoryAuditEvent, ...]
    extractor_version: str = Field(min_length=1)
    config_version: str = Field(min_length=1)


def _source_version_counts_bounded(db_path: Path, source_high_water: int) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT data_json FROM canonical_events WHERE monotonic_seq <= ?",
            (source_high_water,),
        ).fetchall()
    finally:
        conn.close()
    v1 = 0
    v2 = 0
    for (encoded,) in rows:
        data = json.loads(encoded)
        if data.get("schema_version", "ppa.event/v1") == "ppa.event/v1":
            v1 += 1
        else:
            v2 += 1
    return v1, v2


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
        ordered = sorted(groups[group_key], key=lambda item: (item.created_seq, item.memory_id))
        current = ordered[0]
        for newer in ordered[1:]:
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


def build_b2_snapshot(
    db_path: str | Path,
    *,
    source_b1_run_id: str,
    source_high_water: int,
    config: ConsolidationConfigV1 | None = None,
) -> B2Snapshot:
    path = Path(db_path)
    cfg = config or ConsolidationConfigV1()
    event_store = EventStore(path)
    derived_store = DerivedStore(path)
    try:
        b1_run = derived_store.get_run(source_b1_run_id)
        if b1_run is None:
            raise ValueError(f"B1 run not found: {source_b1_run_id}")
        if source_high_water > b1_run.source_high_water:
            raise ValueError(
                "source_high_water cannot exceed source B1 run high-water "
                f"({source_high_water}>{b1_run.source_high_water})"
            )

        events = [
            event
            for event in event_store.iter_events_by_sequence()
            if event.monotonic_seq <= source_high_water
        ]
        snapshots = [
            item
            for item in derived_store.iter_snapshots(source_b1_run_id)
            if item.monotonic_seq <= source_high_water
        ]
        actions = [
            item
            for item in derived_store.iter_actions(source_b1_run_id)
            if item.monotonic_seq <= source_high_water
        ]
        visible_session_ids = {
            snapshot.session_id for snapshot in snapshots if snapshot.session_id is not None
        }
        sessions = [
            session
            for session in derived_store.iter_sessions(source_b1_run_id)
            if session.session_id in visible_session_ids
        ]

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
        dependencies: list[MemoryDependency] = []
        v1_count, v2_count = _source_version_counts_bounded(path, source_high_water)
        return B2Snapshot(
            source_b1_run_id=source_b1_run_id,
            source_high_water=source_high_water,
            source_event_count=len(events),
            v1_count=v1_count,
            v2_count=v2_count,
            fact_candidates=len(facts),
            habit_candidates=len(habits),
            records=tuple(records),
            evidence_links=tuple(links),
            dependencies=tuple(dependencies),
            supersessions=tuple(supersessions),
            audit_events=tuple(audits),
            extractor_version=EXTRACTOR_VERSION,
            config_version=cfg.schema_version,
        )
    finally:
        derived_store.close()
        event_store.close()

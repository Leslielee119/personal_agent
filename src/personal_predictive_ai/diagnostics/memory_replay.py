from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path

from personal_predictive_ai.memory.models import (
    ConsolidationConfigV1,
    MemoryKind,
    MemoryStatus,
)
from personal_predictive_ai.memory.reconstruction import (
    _apply_fact_supersession as _apply_fact_supersession,
)
from personal_predictive_ai.memory.reconstruction import (
    build_b2_snapshot,
)
from personal_predictive_ai.storage.derived_store import DerivedStore
from personal_predictive_ai.storage.memory_store import MemoryRunMetadata, MemoryStore


def derive_b2(
    db_path: str | Path,
    *,
    source_b1_run_id: str,
    run_id: str,
    config: ConsolidationConfigV1 | None = None,
) -> dict[str, object]:
    path = Path(db_path)
    cfg = config or ConsolidationConfigV1()
    derived_store = DerivedStore(path)
    try:
        b1_run = derived_store.get_run(source_b1_run_id)
        if b1_run is None:
            raise ValueError(f"B1 run not found: {source_b1_run_id}")
        source_high_water = b1_run.source_high_water
    finally:
        derived_store.close()

    snapshot = build_b2_snapshot(
        path,
        source_b1_run_id=source_b1_run_id,
        source_high_water=source_high_water,
        config=cfg,
    )
    metadata = MemoryRunMetadata(
        run_id=run_id,
        source_b1_run_id=source_b1_run_id,
        source_high_water=snapshot.source_high_water,
        extractor_version=snapshot.extractor_version,
        config_version=snapshot.config_version,
    )
    memory_store = MemoryStore(path)
    try:
        memory_store.replace_run(
            metadata,
            snapshot.records,
            snapshot.evidence_links,
            snapshot.dependencies,
            snapshot.supersessions,
            snapshot.audit_events,
        )
        integrity = memory_store.integrity_check()
    finally:
        memory_store.close()

    status_counts = Counter(record.status.value for record in snapshot.records)
    return {
        "run_id": run_id,
        "source_b1_run_id": source_b1_run_id,
        "source_high_water": snapshot.source_high_water,
        "source_event_count": snapshot.source_event_count,
        "v1_count": snapshot.v1_count,
        "v2_count": snapshot.v2_count,
        "fact_candidates": snapshot.fact_candidates,
        "fact_active": sum(
            record.kind is MemoryKind.FACT and record.status is MemoryStatus.ACTIVE
            for record in snapshot.records
        ),
        "habit_candidates": snapshot.habit_candidates,
        "habit_active": sum(
            record.kind is MemoryKind.HABIT and record.status is MemoryStatus.ACTIVE
            for record in snapshot.records
        ),
        "status_counts": dict(sorted(status_counts.items())),
        "dependencies": len(snapshot.dependencies),
        "supersessions": len(snapshot.supersessions),
        "audit_events": len(snapshot.audit_events),
        "ai_executed_support": sum(
            record.provenance_summary.ai_executed_support for record in snapshot.records
        ),
        "unknown_support": sum(
            record.provenance_summary.unknown_support for record in snapshot.records
        ),
        "extractor_version": snapshot.extractor_version,
        "config_version": snapshot.config_version,
        "integrity": integrity,
    }


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

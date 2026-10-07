import sqlite3
from pathlib import Path

import pytest

from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventOrigin,
    RetentionClass,
)
from personal_predictive_ai.memory.models import (
    DependencyRelation,
    EvidenceRole,
    MemoryAuditEvent,
    MemoryDependency,
    MemoryEvidenceLink,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    ProvenanceSummary,
    SupersessionEdge,
)
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.storage.derived_store import DerivedStore
from personal_predictive_ai.storage.memory_store import MemoryRunMetadata, MemoryStore
from personal_predictive_ai.storage.sqlite_store import EventStore


def _record(memory_id: str = "mem-1", *, created_seq: int = 1) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        kind=MemoryKind.FACT,
        key="foreground_application.primary",
        value="Code.exe",
        scope=MemoryScope(scope_type="global", scope_id="user"),
        observed_from=10,
        valid_from=10,
        created_seq=created_seq,
        last_supported_seq=created_seq,
        evidence_ids=["evt-1"],
        provenance_summary=ProvenanceSummary(system_support=1),
        support_count=1,
        contradiction_count=0,
        session_ids=["s1"],
        confidence=1.0,
        status=MemoryStatus.CANDIDATE,
        extractor_id="fact.foreground_application/v1",
    )


def _bundle():
    record = _record()
    evidence = MemoryEvidenceLink(
        memory_id=record.memory_id,
        evidence_type="canonical_event",
        evidence_id="evt-1",
        role=EvidenceRole.SUPPORT,
    )
    dependency = MemoryDependency(
        dependency_id="dep-1",
        parent_memory_id="mem-parent",
        child_memory_id=record.memory_id,
        relation=DependencyRelation.SUPPORTS,
        evidence_ids=["evt-1"],
        created_seq=2,
    )
    supersession = SupersessionEdge(
        supersession_id="sup-1",
        new_memory_id=record.memory_id,
        old_memory_id="mem-old",
        created_seq=3,
    )
    audit = MemoryAuditEvent(
        audit_id="audit-1",
        memory_id=record.memory_id,
        event_type="memory.created",
        source_seq=1,
        reason_code="extractor",
    )
    return record, evidence, dependency, supersession, audit


def _metadata() -> MemoryRunMetadata:
    return MemoryRunMetadata(
        run_id="run-b2",
        source_b1_run_id="run-b1",
        source_high_water=12,
        extractor_version="ppa.memory-extractors/v1",
        config_version="ppa.memory-config/v1",
    )


def test_memory_store_round_trip_restart_integrity_and_delete(tmp_path: Path) -> None:
    db = tmp_path / "events.db"
    record, evidence, dependency, supersession, audit = _bundle()
    store = MemoryStore(db)
    store.replace_run(_metadata(), [record], [evidence], [dependency], [supersession], [audit])

    assert store.get_run("run-b2") == _metadata()
    assert list(store.iter_records("run-b2")) == [record]
    assert list(store.iter_evidence_links("run-b2")) == [evidence]
    assert list(store.iter_dependencies("run-b2")) == [dependency]
    assert list(store.iter_supersessions("run-b2")) == [supersession]
    assert list(store.iter_audit_events("run-b2")) == [audit]
    assert store.integrity_check() == "ok"
    store.close()

    reopened = MemoryStore(db)
    assert list(reopened.iter_records("run-b2")) == [record]
    reopened.delete_run("run-b2")
    assert reopened.get_run("run-b2") is None
    assert list(reopened.iter_records("run-b2")) == []
    reopened.close()


def test_replace_run_is_idempotent_and_duplicate_batch_rolls_back(tmp_path: Path) -> None:
    db = tmp_path / "events.db"
    record, evidence, dependency, supersession, audit = _bundle()
    store = MemoryStore(db)
    args = (_metadata(), [record], [evidence], [dependency], [supersession], [audit])
    store.replace_run(*args)
    store.replace_run(*args)

    with pytest.raises(sqlite3.IntegrityError):
        store.replace_run(_metadata(), [record, record], [], [], [], [])

    assert store.get_run("run-b2") == _metadata()
    assert list(store.iter_records("run-b2")) == [record]
    store.close()


def test_b2_replace_and_delete_never_modify_canonical_or_b1_rows(tmp_path: Path) -> None:
    db = tmp_path / "events.db"
    canonical = EventStore(db)
    canonical.append(
        CanonicalEvent(
            event_id="evt-1",
            timestamp_ns=10,
            monotonic_seq=1,
            source="unit",
            modality="window",
            origin=EventOrigin.EXOGENOUS,
            event_type="window.foreground.changed",
            app={"name": "Code.exe"},
        )
    )
    canonical.close()

    b1 = DerivedStore(db)
    b1.replace_run(
        "run-b1",
        1,
        [
            StateSnapshot(
                state_id="state-1", source_event_id="evt-1", timestamp_ns=10, monotonic_seq=1
            )
        ],
        [],
        [],
        [],
    )
    b1.close()

    conn = sqlite3.connect(db)
    before_event = conn.execute(
        "SELECT data_json FROM canonical_events WHERE event_id='evt-1'"
    ).fetchone()[0]
    before_state = conn.execute(
        "SELECT data_json FROM b1_state_snapshots WHERE state_id='state-1'"
    ).fetchone()[0]
    conn.close()

    record, evidence, dependency, supersession, audit = _bundle()
    store = MemoryStore(db)
    store.replace_run(_metadata(), [record], [evidence], [dependency], [supersession], [audit])
    store.delete_run("run-b2")
    store.close()

    conn = sqlite3.connect(db)
    after_event = conn.execute(
        "SELECT data_json FROM canonical_events WHERE event_id='evt-1'"
    ).fetchone()[0]
    after_state = conn.execute(
        "SELECT data_json FROM b1_state_snapshots WHERE state_id='state-1'"
    ).fetchone()[0]
    conn.close()
    assert after_event == before_event
    assert after_state == before_state


def test_short_lived_sentinel_in_b1_is_not_copied_into_b2_tables(tmp_path: Path) -> None:
    db = tmp_path / "events.db"
    sentinel = "NEVER_PERSIST_THIS_KEY_CHAR"
    canonical = EventStore(db)
    canonical.append(
        CanonicalEvent(
            event_id="evt-sensitive",
            timestamp_ns=10,
            monotonic_seq=1,
            source="unit",
            modality="keyboard",
            origin=EventOrigin.ENDOGENOUS,
            event_type="key.down",
            retention_class=RetentionClass.STRUCTURED_SHORT,
            payload={"canonical_key_char": sentinel},
        )
    )
    canonical.close()

    record = _record()
    store = MemoryStore(db)
    store.replace_run(_metadata(), [record], [], [], [], [])
    store.close()

    conn = sqlite3.connect(db)
    rows = []
    for table in (
        "memory_runs",
        "memory_records",
        "memory_evidence_links",
        "memory_dependencies",
        "memory_supersessions",
        "memory_audit_events",
    ):
        rows.extend(str(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall())
    conn.close()
    assert sentinel not in "\n".join(rows)

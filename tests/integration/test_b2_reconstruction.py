import json
import sqlite3
from pathlib import Path

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.cli import main
from personal_predictive_ai.diagnostics.memory_replay import derive_b2
from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventActor,
    EventOrigin,
    EventProvenance,
    RetentionClass,
)
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.state.sessions import SessionSegment
from personal_predictive_ai.storage.derived_store import DerivedStore
from personal_predictive_ai.storage.memory_store import MemoryStore
from personal_predictive_ai.storage.sqlite_store import EventStore

SENTINEL = "SHORT_LIVED_EXACT_KEY_DO_NOT_COPY"
RAW_SENTINEL = "raw/private-expired.png"


def _event(
    event_id,
    seq,
    *,
    app=None,
    actor=EventActor.SYSTEM,
    provenance=EventProvenance.SYSTEM,
    raw_ref=None,
    payload=None,
):
    return CanonicalEvent(
        event_id=event_id,
        timestamp_ns=1000 - seq if seq == 2 else 1000 + seq,
        monotonic_seq=seq,
        source="b2-test",
        modality="window" if app else "keyboard",
        origin=EventOrigin.EXOGENOUS if actor is EventActor.SYSTEM else EventOrigin.ENDOGENOUS,
        event_type="window.foreground.changed" if app else "test.action",
        actor=actor,
        provenance=provenance,
        injected=False if provenance is EventProvenance.HUMAN_PHYSICAL else None,
        app={"name": app} if app else None,
        payload=payload or {},
        retention_class=(
            RetentionClass.STRUCTURED_SHORT
            if payload and SENTINEL in str(payload)
            else RetentionClass.STRUCTURED_LONG
        ),
        raw_ref=raw_ref,
    )


def _action(
    name,
    seq,
    operation,
    session_id,
    provenance=EventProvenance.HUMAN_PHYSICAL,
    *,
    concrete=None,
    fine=None,
):
    actor = EventActor.HUMAN
    if provenance is EventProvenance.AI_EXECUTED:
        actor = EventActor.AI
    elif provenance is EventProvenance.UNKNOWN:
        actor = EventActor.UNKNOWN
    event_id = f"evt-{name}"
    return NormalizedAction(
        action_id=f"action-{name}",
        source_event_id=event_id,
        timestamp_ns=2000 + seq,
        monotonic_seq=seq,
        actor=actor,
        provenance=provenance,
        application="Code.exe",
        operation=operation,
        concrete=concrete,
        fine=fine,
    ), StateSnapshot(
        state_id=f"state-{name}",
        source_event_id=event_id,
        timestamp_ns=2000 + seq,
        monotonic_seq=seq,
        session_id=session_id,
    )


def _session(session_id, start_seq, end_seq):
    return SessionSegment(
        session_id=session_id,
        start_event_id=f"evt-start-{session_id}",
        start_ns=start_seq,
        end_event_id=f"evt-end-{session_id}",
        end_ns=end_seq,
        reason="end_of_stream",
    )


def _seed(tmp_path: Path) -> Path:
    db = tmp_path / "events.db"
    events = [
        _event("evt-f1", 1, app="Code.exe", raw_ref=RAW_SENTINEL),
        _event("evt-f2", 2, app="Code.exe"),
        _event("evt-f3", 3, app="Chrome.exe"),
        _event("evt-f4", 4, app="Code.exe"),
        _event("evt-f5", 5, app="Code.exe"),
    ]
    actions = []
    snapshots = [
        StateSnapshot(
            state_id=f"state-f{i}",
            source_event_id=e.event_id,
            timestamp_ns=e.timestamp_ns,
            monotonic_seq=e.monotonic_seq,
            session_id="s1" if i <= 2 else "s2",
        )
        for i, e in enumerate(events, start=1)
    ]
    sessions = [
        _session("s1", 1, 13),
        _session("s2", 14, 17),
        _session("s3", 18, 19),
        _session("s4", 20, 21),
        _session("s5", 22, 23),
    ]
    specs = [
        ("a10", 10, "save", "s1", EventProvenance.HUMAN_PHYSICAL),
        ("a11", 11, "run_tests", "s1", EventProvenance.HUMAN_PHYSICAL),
        ("a12", 12, "save", "s1", EventProvenance.HUMAN_PHYSICAL),
        ("a13", 13, "run_tests", "s1", EventProvenance.HUMAN_PHYSICAL),
        ("a14", 14, "save", "s2", EventProvenance.HUMAN_PHYSICAL),
        ("a15", 15, "run_tests", "s2", EventProvenance.HUMAN_PHYSICAL),
        ("a16", 16, "save", "s2", EventProvenance.HUMAN_PHYSICAL),
        ("a17", 17, "run_tests", "s2", EventProvenance.HUMAN_PHYSICAL),
        ("a18", 18, "save", "s3", EventProvenance.HUMAN_PHYSICAL),
        ("a19", 19, "run_tests", "s3", EventProvenance.HUMAN_PHYSICAL),
        ("a20", 20, "save", "s4", EventProvenance.HUMAN_PHYSICAL),
        ("a21", 21, "run_tests", "s4", EventProvenance.AI_EXECUTED),
        ("a22", 22, "save", "s5", EventProvenance.HUMAN_PHYSICAL),
        ("a23", 23, "run_tests", "s5", EventProvenance.UNKNOWN),
    ]
    for name, seq, op, sid, prov in specs:
        concrete = SENTINEL if name == "a10" else None
        fine = {"private": SENTINEL} if name == "a10" else None
        action, snapshot = _action(name, seq, op, sid, prov, concrete=concrete, fine=fine)
        actions.append(action)
        snapshots.append(snapshot)
        events.append(
            _event(
                action.source_event_id,
                seq,
                actor=action.actor,
                provenance=prov,
                payload={"canonical_key_char": SENTINEL} if name == "a10" else {},
            )
        )

    event_store = EventStore(db)
    event_store.append_many(sorted(events, key=lambda x: x.monotonic_seq))
    event_store.close()
    derived = DerivedStore(db)
    derived.replace_run("b1-real", 23, snapshots, actions, sessions, [])
    derived.close()
    return db


def _source_bytes(db: Path):
    conn = sqlite3.connect(db)
    result = {}
    for table in (
        "canonical_events",
        "b1_state_snapshots",
        "b1_actions",
        "b1_sessions",
        "b1_transitions",
    ):
        result[table] = conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
    conn.close()
    return result


def _b2_bytes(db: Path):
    conn = sqlite3.connect(db)
    result = {}
    for table in (
        "memory_records",
        "memory_evidence_links",
        "memory_dependencies",
        "memory_supersessions",
        "memory_audit_events",
    ):
        result[table] = conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
    conn.close()
    return result


def test_b2_reconstruction_is_deterministic_private_and_preserves_sources(tmp_path: Path):
    db = _seed(tmp_path)
    before = _source_bytes(db)
    first = derive_b2(db, source_b1_run_id="b1-real", run_id="b2-run")
    first_rows = _b2_bytes(db)
    second = derive_b2(db, source_b1_run_id="b1-real", run_id="b2-run")
    second_rows = _b2_bytes(db)
    after = _source_bytes(db)

    assert before == after
    assert first == second
    assert first_rows == second_rows
    assert first["integrity"] == "ok"
    assert first["fact_active"] == 1
    assert first["habit_active"] >= 1
    assert first["ai_executed_support"] >= 1
    assert first["unknown_support"] >= 1

    store = MemoryStore(db)
    records = list(store.iter_records("b2-run"))
    links = list(store.iter_evidence_links("b2-run"))
    run_tests = next(
        r
        for r in records
        if r.kind.value == "habit" and r.value == "run_tests" and r.key.endswith(":save")
    )
    assert run_tests.status.value == "active"
    assert run_tests.support_count == 5
    assert run_tests.provenance_summary.ai_executed_support == 1
    assert run_tests.provenance_summary.unknown_support == 1
    code = next(r for r in records if r.kind.value == "fact" and r.value == "Code.exe")
    assert code.status.value == "active"
    assert any(
        link.memory_id == code.memory_id and link.role.value == "contradiction" for link in links
    )
    store.close()

    persisted = json.dumps(first_rows, ensure_ascii=False)
    assert SENTINEL not in persisted
    assert RAW_SENTINEL not in persisted


def test_missing_b1_run_is_rejected(tmp_path: Path):
    db = tmp_path / "events.db"
    EventStore(db).close()
    try:
        derive_b2(db, source_b1_run_id="missing", run_id="b2")
    except ValueError as exc:
        assert "B1 run" in str(exc)
    else:
        raise AssertionError("missing B1 run must be rejected")


def test_cli_derive_and_replay_b2_are_safe(tmp_path: Path, capsys):
    db = _seed(tmp_path)
    assert (
        main(
            [
                "--data-dir",
                str(db.parent),
                "derive-b2",
                "--source-b1-run-id",
                "b1-real",
                "--run-id",
                "cli-b2",
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["integrity"] == "ok"
    assert (
        main(["--data-dir", str(db.parent), "replay-b2", "--run-id", "cli-b2", "--limit", "3"]) == 0
    )
    replay = capsys.readouterr().out
    assert "status=" in replay
    assert SENTINEL not in replay
    assert RAW_SENTINEL not in replay


def test_b2_ignores_canonical_events_newer_than_source_b1_high_water(tmp_path: Path):
    db = _seed(tmp_path)
    store = EventStore(db)
    store.append_many(
        [
            _event("evt-late-24", 24, app="Chrome.exe"),
            _event("evt-late-25", 25, app="Chrome.exe"),
            _event("evt-late-26", 26, app="Chrome.exe"),
            _event("evt-late-27", 27, app="Chrome.exe"),
        ]
    )
    store.close()

    summary = derive_b2(db, source_b1_run_id="b1-real", run_id="bounded")
    assert summary["source_high_water"] == 23
    assert summary["source_event_count"] == 19
    assert summary["v2_count"] == 19

    memory_store = MemoryStore(db)
    records = list(memory_store.iter_records("bounded"))
    memory_store.close()
    code = next(r for r in records if r.kind.value == "fact" and r.value == "Code.exe")
    assert code.status.value == "active"
    assert all(
        r.value != "Chrome.exe" or r.support_count == 1 for r in records if r.kind.value == "fact"
    )

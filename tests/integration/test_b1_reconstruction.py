import json
import sqlite3
from pathlib import Path

from personal_predictive_ai.cli import main
from personal_predictive_ai.diagnostics.state_replay import derive_b1
from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventActor,
    EventOrigin,
    EventProvenance,
)
from personal_predictive_ai.storage.derived_store import DerivedStore
from personal_predictive_ai.storage.sqlite_store import EventStore

MINUTE_NS = 60 * 1_000_000_000


def _event(
    seq: int,
    event_type: str,
    *,
    timestamp_ns: int,
    modality: str,
    actor: EventActor,
    provenance: EventProvenance,
    origin: EventOrigin,
    payload=None,
    app=None,
    process=None,
    window=None,
    raw_ref=None,
):
    injected = False if provenance is EventProvenance.HUMAN_PHYSICAL else None
    return CanonicalEvent(
        event_id=f"evt-{seq}",
        timestamp_ns=timestamp_ns,
        monotonic_seq=seq,
        source="unit",
        modality=modality,
        origin=origin,
        event_type=event_type,
        actor=actor,
        provenance=provenance,
        injected=injected,
        payload=payload or {},
        app=app,
        process=process,
        window=window,
        raw_ref=raw_ref,
    )


def _fixture_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "events.db"
    store = EventStore(db_path)
    legacy = {
        "schema_version": "ppa.event/v1",
        "event_id": "evt-1",
        "timestamp_ns": 1,
        "monotonic_seq": 1,
        "source": "legacy",
        "modality": "window",
        "origin": "exogenous",
        "event_type": "window.foreground.current",
        "app": {"name": "Code.exe"},
        "window": {"title": "Editor", "handle": 10},
        "payload": {},
        "privacy_tier": "standard",
        "retention_class": "structured_long",
        "causal_parent_ids": [],
    }
    encoded = json.dumps(legacy, sort_keys=True, separators=(",", ":"))
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO canonical_events("
        "event_id, timestamp_ns, monotonic_seq, data_json"
        ") VALUES (?, ?, ?, ?)",
        ("evt-1", 1, 1, encoded),
    )
    conn.commit()
    conn.close()

    t0 = 100
    later = 31 * MINUTE_NS
    store.append_many(
        [
            _event(
                2,
                "key.down",
                timestamp_ns=t0,
                modality="keyboard",
                actor=EventActor.HUMAN,
                provenance=EventProvenance.HUMAN_PHYSICAL,
                origin=EventOrigin.ENDOGENOUS,
                payload={"canonical_key_char": "a"},
                app={"name": "Code.exe"},
            ),
            _event(
                3,
                "process.started",
                timestamp_ns=t0,
                modality="process",
                actor=EventActor.SYSTEM,
                provenance=EventProvenance.SYSTEM,
                origin=EventOrigin.EXOGENOUS,
                process={"pid": 20, "create_time": 2.0, "name": "pytest.exe"},
            ),
            _event(
                4,
                "mouse.down",
                timestamp_ns=t0,
                modality="mouse",
                actor=EventActor.HUMAN,
                provenance=EventProvenance.HUMAN_PHYSICAL,
                origin=EventOrigin.ENDOGENOUS,
                payload={"x": 10.0, "y": 20.0, "button": "left"},
            ),
            _event(
                5,
                "key.down",
                timestamp_ns=later,
                modality="keyboard",
                actor=EventActor.UNKNOWN,
                provenance=EventProvenance.UNKNOWN,
                origin=EventOrigin.ENDOGENOUS,
                payload={"canonical_key_name": "enter"},
            ),
            _event(
                6,
                "screen.snapshot",
                timestamp_ns=later + 1,
                modality="screen",
                actor=EventActor.SYSTEM,
                provenance=EventProvenance.SYSTEM,
                origin=EventOrigin.EXOGENOUS,
                raw_ref="raw/already-expired-secret.png",
            ),
        ]
    )
    store.close()
    return db_path


def _canonical_bytes(db_path: Path):
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT event_id, data_json FROM canonical_events ORDER BY monotonic_seq"
    ).fetchall()
    conn.close()
    return rows


def test_b1_reconstruction_is_deterministic_and_preserves_canonical_bytes(tmp_path: Path) -> None:
    db_path = _fixture_db(tmp_path)
    before = _canonical_bytes(db_path)

    first = derive_b1(db_path, run_id="run-1")
    second = derive_b1(db_path, run_id="run-1")
    after = _canonical_bytes(db_path)

    assert after == before
    assert first == second
    assert first["source_event_count"] == 6
    assert first["source_high_water"] == 6
    assert first["v1_count"] == 1
    assert first["v2_count"] == 5
    assert first["unknown_provenance_count"] == 2
    assert first["actions"] == 3
    assert first["sessions"] == 2
    assert first["transitions"] >= 1
    assert first["integrity"] == "ok"

    derived = DerivedStore(db_path)
    transitions = list(derived.iter_transitions("run-1"))
    assert transitions[0].exogenous_event_ids == ["evt-3"]
    derived.close()


def test_cli_derive_and_replay_are_offline_safe(tmp_path: Path, capsys) -> None:
    db_path = _fixture_db(tmp_path)
    data_dir = db_path.parent

    assert main(["--data-dir", str(data_dir), "derive-b1", "--run-id", "cli-run"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["integrity"] == "ok"

    assert main(["--data-dir", str(data_dir), "replay-b1", "--run-id", "cli-run"]) == 0
    replay = capsys.readouterr().out
    assert "HUMAN_PHYSICAL" in replay
    assert "raw/already-expired-secret.png" not in replay
    assert "canonical_key_char" not in replay


def test_b1_reconstruction_preserves_monotonic_source_order_across_wall_clock_regression(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "events.db"
    store = EventStore(db_path)
    store.append_many(
        [
            _event(
                1,
                "key.down",
                timestamp_ns=200,
                modality="keyboard",
                actor=EventActor.HUMAN,
                provenance=EventProvenance.HUMAN_PHYSICAL,
                origin=EventOrigin.ENDOGENOUS,
                payload={"canonical_key_name": "a"},
            ),
            _event(
                2,
                "key.down",
                timestamp_ns=100,
                modality="keyboard",
                actor=EventActor.HUMAN,
                provenance=EventProvenance.HUMAN_PHYSICAL,
                origin=EventOrigin.ENDOGENOUS,
                payload={"canonical_key_name": "b"},
            ),
        ]
    )
    store.close()

    derive_b1(db_path, run_id="clock-regression")

    derived = DerivedStore(db_path)
    snapshots = list(derived.iter_snapshots("clock-regression"))
    derived.close()

    assert [snapshot.source_event_id for snapshot in snapshots] == ["evt-1", "evt-2"]
    assert [snapshot.monotonic_seq for snapshot in snapshots] == [1, 2]

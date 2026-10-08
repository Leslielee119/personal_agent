from __future__ import annotations

import json
from pathlib import Path

from personal_predictive_ai.cli import main
from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventActor,
    EventOrigin,
    EventProvenance,
)
from personal_predictive_ai.storage.derived_store import DerivedStore
from personal_predictive_ai.storage.sqlite_store import EventStore


def _event(seq: int, timestamp_ns: int, event_type: str, *, app: str | None = None):
    human = event_type in {"key.down", "mouse.down", "mouse.scroll"}
    return CanonicalEvent(
        event_id=f"evt-{seq}", timestamp_ns=timestamp_ns, monotonic_seq=seq,
        source="fixture", modality="input" if human else "runtime",
        origin=EventOrigin.ENDOGENOUS if human else EventOrigin.EXOGENOUS,
        event_type=event_type,
        actor=EventActor.HUMAN if human else EventActor.SYSTEM,
        provenance=(EventProvenance.HUMAN_PHYSICAL if human else EventProvenance.SYSTEM),
        injected=False if human else None,
        app={"name": app} if app else None,
        payload=(
            {"canonical_key_name": "a"} if event_type == "key.down"
            else {"x": 1, "y": 2, "button": "left"} if event_type == "mouse.down"
            else {"x": 1, "y": 2, "dx": 0, "dy": 1} if event_type == "mouse.scroll"
            else {}
        ),
    )


def _append_session(store: EventStore, *, start_seq: int, start_ns: int, app: str) -> int:
    events = [
        _event(start_seq, start_ns, "runtime.restart"),
        _event(start_seq + 1, start_ns + 1, "key.down", app=app),
        _event(start_seq + 2, start_ns + 2, "mouse.down", app=app),
        _event(start_seq + 3, start_ns + 3, "mouse.scroll", app=app),
    ]
    store.append_many(events)
    return start_seq + 4


def _run_cycle(data_dir: Path, capsys) -> dict[str, object]:
    result = main(
        [
            "--data-dir", str(data_dir),
            "longitudinal-cycle", "--run-id", "longitudinal-current",
        ]
    )
    assert result == 0
    return json.loads(capsys.readouterr().out)


def test_repeated_capture_restarts_accumulate_sessions_and_replace_b1_run(
    tmp_path: Path, capsys,
) -> None:
    db = tmp_path / "events.db"
    store = EventStore(db)
    next_seq = _append_session(store, start_seq=1, start_ns=100, app="Code.exe")
    next_seq = _append_session(store, start_seq=next_seq, start_ns=1_000, app="chrome.exe")
    store.close()

    first = _run_cycle(tmp_path, capsys)
    assert first["session_count"] == 2
    assert first["human_physical_actions"] == 6
    assert first["source_high_water"] == 8
    assert first["progress"]["operation"]["screening_status"] == "SCREENING_NOT_READY"

    store = EventStore(db)
    _append_session(store, start_seq=next_seq, start_ns=2_000, app="Code.exe")
    store.close()

    second = _run_cycle(tmp_path, capsys)
    assert second["session_count"] == 3
    assert second["human_physical_actions"] == 9
    assert second["source_high_water"] == 12

    derived = DerivedStore(db)
    try:
        run = derived.get_run("longitudinal-current")
        assert run is not None
        assert run.source_high_water == 12
        assert len(list(derived.iter_sessions("longitudinal-current"))) == 3
    finally:
        derived.close()

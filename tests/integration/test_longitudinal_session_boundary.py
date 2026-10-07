from __future__ import annotations

import time
from pathlib import Path

from personal_predictive_ai.config import Settings
from personal_predictive_ai.diagnostics.state_replay import derive_b1
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import (
    EventActor,
    EventOrigin,
    EventProvenance,
    RetentionClass,
)
from personal_predictive_ai.runtime.service import CaptureService
from personal_predictive_ai.storage.derived_store import DerivedStore


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        raw_ttl_seconds=1,
        structured_retention_days=30,
        offline_mode=False,
    )


def _capture_one_key_action(settings: Settings) -> None:
    service = CaptureService(
        settings=settings,
        collectors=[],
        event_factory=EventFactory(),
    )
    service.start()
    try:
        event = service.event_factory.next(
            timestamp_ns=time.time_ns(),
            source="fixture.keyboard",
            modality="keyboard",
            origin=EventOrigin.ENDOGENOUS,
            event_type="key.down",
            actor=EventActor.HUMAN,
            provenance=EventProvenance.HUMAN_PHYSICAL,
            injected=False,
            payload={},
            retention_class=RetentionClass.STRUCTURED_SHORT,
        )
        service.publish(event)
    finally:
        service.close()


def test_two_independent_captures_create_two_b1_sessions_via_runtime_restart(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)

    _capture_one_key_action(settings)
    _capture_one_key_action(settings)

    db_path = settings.data_dir / "events.db"
    summary = derive_b1(db_path, run_id="longitudinal-b1")

    assert summary["source_event_count"] == 4
    assert summary["actions"] == 2
    assert summary["sessions"] == 2

    store = DerivedStore(db_path)
    try:
        sessions = list(store.iter_sessions("longitudinal-b1"))
    finally:
        store.close()

    assert [session.reason for session in sessions] == ["runtime_restart", "end_of_stream"]
    assert sessions[0].session_id != sessions[1].session_id

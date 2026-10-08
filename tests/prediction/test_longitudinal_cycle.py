from __future__ import annotations

import hashlib
from pathlib import Path

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.events.models import EventActor, EventProvenance
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.state.sessions import SessionSegment
from personal_predictive_ai.storage.derived_store import DerivedStore


def _seed_b1(
    db: Path,
    *,
    sessions: int,
    actions_per_session: int,
    collapsed: bool = False,
) -> None:
    actions: list[NormalizedAction] = []
    snapshots: list[StateSnapshot] = []
    segments: list[SessionSegment] = []
    seq = 1
    for session_index in range(sessions):
        session_id = f"s{session_index + 1}"
        start_ns = (session_index + 1) * 1_000_000
        first_event = f"evt-{seq}"
        for offset in range(actions_per_session):
            app = "chrome.exe" if collapsed else ("Code.exe", "chrome.exe")[offset % 2]
            operation = (
                "key_input" if collapsed else ("key_input", "click", "scroll")[offset % 3]
            )
            timestamp_ns = start_ns + offset
            actions.append(
                NormalizedAction(
                    action_id=f"act-{seq}", source_event_id=f"evt-{seq}",
                    timestamp_ns=timestamp_ns, monotonic_seq=seq,
                    actor=EventActor.HUMAN, provenance=EventProvenance.HUMAN_PHYSICAL,
                    application=app, operation=operation,
                )
            )
            snapshots.append(
                StateSnapshot(
                    state_id=f"state-{seq}", source_event_id=f"evt-{seq}",
                    timestamp_ns=timestamp_ns, monotonic_seq=seq,
                    foreground_app={"name": app},
                    active_processes={"1": {"name": app, "pid": 1}},
                    session_id=session_id,
                )
            )
            seq += 1
        # Deliberately add one non-human action per session; it must not affect progress.
        actions.append(
            NormalizedAction(
                action_id=f"ai-{session_index}", source_event_id=f"ai-evt-{session_index}",
                timestamp_ns=start_ns + actions_per_session - 1,
                monotonic_seq=seq, actor=EventActor.AI,
                provenance=EventProvenance.AI_EXECUTED,
                application="Code.exe", operation="click",
            )
        )
        seq += 1
        segments.append(
            SessionSegment(
                session_id=session_id, start_event_id=first_event, start_ns=start_ns,
                end_event_id=f"evt-{seq - 2}", end_ns=start_ns + actions_per_session - 1,
                reason="fixture",
            )
        )
    store = DerivedStore(db)
    try:
        store.replace_run("b1", seq - 1, snapshots, actions, segments, [])
    finally:
        store.close()


def test_progress_quantifies_deficits_and_filters_non_human_actions(tmp_path: Path) -> None:
    from personal_predictive_ai.prediction.longitudinal import summarize_longitudinal_run

    db = tmp_path / "events.db"
    _seed_b1(db, sessions=4, actions_per_session=20)
    report = summarize_longitudinal_run(db, source_b1_run_id="b1")

    assert report.session_count == 4
    assert report.human_physical_actions == 80
    assert sum(report.operation_counts.values()) == 80
    assert set(report.operation_counts) == {"key_input", "click", "scroll"}
    assert set(report.application_counts) == {"Code.exe", "chrome.exe"}

    operation = report.progress["operation"]
    assert operation.target_count_shortfall == 120
    assert operation.classes_to_c0 == 0
    assert operation.minority_actions_needed_for_dominant_ratio == 0
    assert operation.sessions_to_screening == 1
    assert operation.sessions_to_confirmatory == 4
    assert operation.screening_status == "SCREENING_NOT_READY"
    assert "sessions<5" in operation.screening_reasons


def test_progress_reports_screening_ready_without_overstating_confirmatory(tmp_path: Path) -> None:
    from personal_predictive_ai.prediction.longitudinal import summarize_longitudinal_run

    db = tmp_path / "events.db"
    _seed_b1(db, sessions=5, actions_per_session=50)
    report = summarize_longitudinal_run(db, source_b1_run_id="b1")

    operation = report.progress["operation"]
    assert operation.sessions_to_screening == 0
    assert operation.target_count_shortfall == 0
    assert operation.screening_status == "SCREENING_READY"
    assert operation.sessions_to_confirmatory == 3
    assert operation.independent_test_sessions_to_confirmatory == 3
    assert operation.confirmatory_status == "CONFIRMATORY_NOT_READY"


def test_five_collapsed_sessions_are_not_reported_as_data_ready(tmp_path: Path) -> None:
    from personal_predictive_ai.prediction.longitudinal import summarize_longitudinal_run

    db = tmp_path / "events.db"
    _seed_b1(db, sessions=5, actions_per_session=50, collapsed=True)
    report = summarize_longitudinal_run(db, source_b1_run_id="b1")

    operation = report.progress["operation"]
    assert operation.c0_status == "INSUFFICIENT_PREDICTIVE_DIVERSITY"
    assert operation.minority_actions_needed_for_dominant_ratio == 28
    assert operation.screening_status == "SCREENING_NOT_READY"
    assert "classes<3" in operation.screening_reasons
    assert "dominant>0.9" in operation.screening_reasons


def _db_family_hashes(db: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(db.parent.glob(f"{db.name}*")):
        if path.is_file():
            result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def test_summarize_longitudinal_run_is_database_read_only(tmp_path: Path) -> None:
    from personal_predictive_ai.prediction.longitudinal import summarize_longitudinal_run

    db = tmp_path / "events.db"
    _seed_b1(db, sessions=5, actions_per_session=50)
    before = _db_family_hashes(db)

    summarize_longitudinal_run(db, source_b1_run_id="b1")

    assert _db_family_hashes(db) == before


def test_summarize_does_not_open_writable_derived_store(tmp_path: Path, monkeypatch) -> None:
    from personal_predictive_ai.prediction.longitudinal import summarize_longitudinal_run
    from personal_predictive_ai.storage import derived_store

    db = tmp_path / "events.db"
    _seed_b1(db, sessions=5, actions_per_session=50)

    def reject_writable_open(*args, **kwargs):
        raise AssertionError("summary must use immutable read-only B1 access")

    monkeypatch.setattr(derived_store.DerivedStore, "__init__", reject_writable_open)
    report = summarize_longitudinal_run(db, source_b1_run_id="b1")

    assert report.source_high_water > 0
    assert report.session_count == 5

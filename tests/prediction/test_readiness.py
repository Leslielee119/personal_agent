from __future__ import annotations

import hashlib
from pathlib import Path

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.events.models import EventActor, EventProvenance
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.state.sessions import SessionSegment
from personal_predictive_ai.storage.derived_store import DerivedStore


def _seed_b1(db: Path, *, session_count: int, actions_per_session: int = 50) -> None:
    applications = ("Code.exe", "chrome.exe")
    operations = ("save", "run", "inspect")
    actions = []
    snapshots = []
    sessions = []
    seq = 1
    for session_index in range(session_count):
        session_id = f"s{session_index + 1}"
        start_ns = (session_index + 1) * 1_000_000
        first_event_id = f"evt-{seq}"
        for offset in range(actions_per_session):
            timestamp_ns = start_ns + offset
            application = applications[offset % len(applications)]
            operation = operations[offset % len(operations)]
            actions.append(
                NormalizedAction(
                    action_id=f"act-{seq}",
                    source_event_id=f"evt-{seq}",
                    timestamp_ns=timestamp_ns,
                    monotonic_seq=seq,
                    actor=EventActor.HUMAN,
                    provenance=EventProvenance.HUMAN_PHYSICAL,
                    application=application,
                    operation=operation,
                )
            )
            snapshots.append(
                StateSnapshot(
                    state_id=f"state-{seq}",
                    source_event_id=f"evt-{seq}",
                    timestamp_ns=timestamp_ns,
                    monotonic_seq=seq,
                    foreground_app={"name": application},
                    active_processes={"1": {"name": application, "pid": 1}},
                    session_id=session_id,
                )
            )
            seq += 1
        sessions.append(
            SessionSegment(
                session_id=session_id,
                start_event_id=first_event_id,
                start_ns=start_ns,
                end_event_id=f"evt-{seq - 1}",
                end_ns=start_ns + actions_per_session - 1,
                reason="fixture",
            )
        )
    store = DerivedStore(db)
    try:
        store.replace_run("b1", seq - 1, snapshots, actions, sessions, [])
    finally:
        store.close()


def _db_family_hashes(db: Path) -> dict[str, str]:
    result = {}
    for path in sorted(db.parent.glob(f"{db.name}*")):
        if path.is_file():
            result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def test_four_sessions_are_not_screening_ready(tmp_path: Path) -> None:
    from personal_predictive_ai.prediction.readiness import audit_longitudinal_status

    db = tmp_path / "events.db"
    _seed_b1(db, session_count=4)
    report = audit_longitudinal_status(db, source_b1_run_id="b1")

    assert report.screening_status == "SCREENING_NOT_READY"
    assert report.confirmatory_status == "CONFIRMATORY_NOT_READY"
    assert report.targets["operation"].session_count == 4
    assert report.targets["operation"].rolling_test_folds == 1
    assert "sessions<5" in report.targets["operation"].screening_reasons
    assert "rolling_test_folds<2" in report.targets["operation"].screening_reasons


def test_five_sessions_are_screening_ready_but_not_confirmatory(tmp_path: Path) -> None:
    from personal_predictive_ai.prediction.readiness import audit_longitudinal_status

    db = tmp_path / "events.db"
    _seed_b1(db, session_count=5)
    report = audit_longitudinal_status(db, source_b1_run_id="b1")

    assert report.screening_status == "SCREENING_READY"
    assert report.confirmatory_status == "CONFIRMATORY_NOT_READY"
    target = report.targets["operation"]
    assert target.session_count == 5
    assert target.eligible_human_physical_actions == 250
    assert target.rolling_test_folds == 2
    assert target.independent_test_sessions == 2
    assert target.c0_status == "PASS"
    assert target.screening_status == "SCREENING_READY"
    assert target.confirmatory_status == "CONFIRMATORY_NOT_READY"


def test_eight_sessions_and_c0_pass_are_confirmatory_ready(tmp_path: Path) -> None:
    from personal_predictive_ai.prediction.readiness import audit_longitudinal_status

    db = tmp_path / "events.db"
    _seed_b1(db, session_count=8)
    report = audit_longitudinal_status(db, source_b1_run_id="b1")

    assert report.screening_status == "SCREENING_READY"
    assert report.confirmatory_status == "CONFIRMATORY_READY"
    assert set(report.confirmatory_ready_target_spaces) == {"application", "operation", "joint"}
    for target in report.targets.values():
        assert target.session_count == 8
        assert target.rolling_test_folds == 5
        assert target.independent_test_sessions == 5
        assert target.c0_status == "PASS"
        assert target.confirmatory_status == "CONFIRMATORY_READY"


def test_longitudinal_status_is_database_read_only(tmp_path: Path) -> None:
    from personal_predictive_ai.prediction.readiness import audit_longitudinal_status

    db = tmp_path / "events.db"
    _seed_b1(db, session_count=5)
    before = _db_family_hashes(db)

    audit_longitudinal_status(db, source_b1_run_id="b1")

    assert _db_family_hashes(db) == before

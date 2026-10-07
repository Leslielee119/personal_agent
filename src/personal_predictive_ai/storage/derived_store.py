from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.state.sessions import SessionSegment
from personal_predictive_ai.transitions.models import Transition


class RunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    source_high_water: int = Field(ge=0)
    schema_version: str = "ppa.b1-derived/v1"


class DerivedStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        migration = Path(__file__).with_name("migrations") / "002_b1_derived.sql"
        self._conn.executescript(migration.read_text(encoding="utf-8"))
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def replace_run(
        self,
        run_id: str,
        source_high_water: int,
        snapshots: Iterable[StateSnapshot],
        actions: Iterable[NormalizedAction],
        sessions: Iterable[SessionSegment],
        transitions: Iterable[Transition],
    ) -> None:
        metadata = RunMetadata(run_id=run_id, source_high_water=source_high_water)
        snapshot_rows = [
            (run_id, item.state_id, item.monotonic_seq, self._encode(item))
            for item in snapshots
        ]
        action_rows = [
            (run_id, item.action_id, item.monotonic_seq, self._encode(item))
            for item in actions
        ]
        session_rows = [
            (run_id, item.session_id, item.start_ns, self._encode(item))
            for item in sessions
        ]
        transition_rows = [
            (run_id, item.transition_id, item.start_seq, self._encode(item))
            for item in transitions
        ]

        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._conn.execute("DELETE FROM derived_runs WHERE run_id = ?", (run_id,))
                self._conn.execute(
                    """
                    INSERT INTO derived_runs(run_id, source_high_water, schema_version)
                    VALUES (?, ?, ?)
                    """,
                    (metadata.run_id, metadata.source_high_water, metadata.schema_version),
                )
                self._conn.executemany(
                    """
                    INSERT INTO b1_state_snapshots(run_id, state_id, monotonic_seq, data_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    snapshot_rows,
                )
                self._conn.executemany(
                    """
                    INSERT INTO b1_actions(run_id, action_id, monotonic_seq, data_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    action_rows,
                )
                self._conn.executemany(
                    """
                    INSERT INTO b1_sessions(run_id, session_id, start_ns, data_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    session_rows,
                )
                self._conn.executemany(
                    """
                    INSERT INTO b1_transitions(run_id, transition_id, start_seq, data_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    transition_rows,
                )
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise

    def delete_run(self, run_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM derived_runs WHERE run_id = ?", (run_id,))

    def get_run(self, run_id: str) -> RunMetadata | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT run_id, source_high_water, schema_version
                FROM derived_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return RunMetadata(
            run_id=str(row["run_id"]),
            source_high_water=int(row["source_high_water"]),
            schema_version=str(row["schema_version"]),
        )

    def iter_snapshots(self, run_id: str) -> Iterator[StateSnapshot]:
        yield from self._iter_model(
            "b1_state_snapshots", "monotonic_seq", run_id, StateSnapshot
        )

    def iter_actions(self, run_id: str) -> Iterator[NormalizedAction]:
        yield from self._iter_model("b1_actions", "monotonic_seq", run_id, NormalizedAction)

    def iter_sessions(self, run_id: str) -> Iterator[SessionSegment]:
        yield from self._iter_model("b1_sessions", "rowid", run_id, SessionSegment)

    def iter_transitions(self, run_id: str) -> Iterator[Transition]:
        yield from self._iter_model("b1_transitions", "start_seq", run_id, Transition)

    def integrity_check(self) -> str:
        with self._lock:
            row = self._conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0])

    def _iter_model(self, table: str, order_by: str, run_id: str, model_type):
        allowed = {
            "b1_state_snapshots": "monotonic_seq",
            "b1_actions": "monotonic_seq",
            "b1_sessions": "rowid",
            "b1_transitions": "start_seq",
        }
        if allowed.get(table) != order_by:
            raise ValueError("unsupported derived table/order")
        with self._lock:
            rows = self._conn.execute(
                f"SELECT data_json FROM {table} WHERE run_id = ? ORDER BY {order_by} ASC",
                (run_id,),
            ).fetchall()
        for row in rows:
            yield model_type.model_validate(json.loads(row["data_json"]))

    @staticmethod
    def _encode(model: BaseModel) -> str:
        return json.dumps(
            model.model_dump(mode="json"),
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

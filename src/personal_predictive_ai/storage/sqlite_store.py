from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from pathlib import Path

from personal_predictive_ai.events.models import CanonicalEvent


class EventStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        migration = Path(__file__).with_name("migrations") / "001_initial.sql"
        self._conn.executescript(migration.read_text(encoding="utf-8"))
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def append(self, event: CanonicalEvent) -> None:
        self.append_many([event])

    def append_many(self, events: Iterable[CanonicalEvent]) -> None:
        rows = [self._row(event) for event in events]
        with self._lock, self._conn:
            self._conn.executemany(
                """
                INSERT INTO canonical_events(event_id, timestamp_ns, monotonic_seq, data_json)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )

    def get(self, event_id: str) -> CanonicalEvent | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data_json FROM canonical_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        if row is None:
            return None
        return CanonicalEvent.model_validate(json.loads(row["data_json"]))

    def iter_events(
        self,
        *,
        start_ns: int | None = None,
        end_ns: int | None = None,
        limit: int | None = None,
    ) -> Iterator[CanonicalEvent]:
        conditions: list[str] = []
        params: list[int] = []
        if start_ns is not None:
            conditions.append("timestamp_ns >= ?")
            params.append(start_ns)
        if end_ns is not None:
            conditions.append("timestamp_ns <= ?")
            params.append(end_ns)

        query = "SELECT data_json FROM canonical_events"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY timestamp_ns ASC, monotonic_seq ASC"
        if limit is not None:
            if limit < 0:
                raise ValueError("limit must be non-negative")
            query += " LIMIT ?"
            params.append(limit)

        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        for row in rows:
            yield CanonicalEvent.model_validate(json.loads(row["data_json"]))

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM canonical_events").fetchone()
        return int(row["n"])

    def integrity_check(self) -> str:
        with self._lock:
            row = self._conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0])

    @staticmethod
    def _row(event: CanonicalEvent) -> tuple[str, int, int, str]:
        data = event.model_dump(mode="json")
        encoded = json.dumps(data, allow_nan=False, sort_keys=True, separators=(",", ":"))
        return event.event_id, event.timestamp_ns, event.monotonic_seq, encoded

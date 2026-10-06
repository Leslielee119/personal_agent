from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from pathlib import Path

from personal_predictive_ai.events.models import CanonicalEvent, RetentionClass

_SEQUENCE_HIGH_WATER_KEY = "monotonic_seq_high_water"


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
        materialized = list(events)
        rows = [self._row(event) for event in materialized]
        high_water = max((event.monotonic_seq for event in materialized), default=0)
        with self._lock, self._conn:
            self._conn.executemany(
                """
                INSERT INTO canonical_events(event_id, timestamp_ns, monotonic_seq, data_json)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )
            if high_water > 0:
                row = self._conn.execute(
                    "SELECT value FROM runtime_metadata WHERE key = ?",
                    (_SEQUENCE_HIGH_WATER_KEY,),
                ).fetchone()
                if row is None:
                    self._conn.execute(
                        "INSERT INTO runtime_metadata(key, value) VALUES (?, ?)",
                        (_SEQUENCE_HIGH_WATER_KEY, high_water),
                    )
                elif high_water > int(row["value"]):
                    self._conn.execute(
                        "UPDATE runtime_metadata SET value = ? WHERE key = ?",
                        (high_water, _SEQUENCE_HIGH_WATER_KEY),
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

    def sequence_high_water(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM runtime_metadata WHERE key = ?",
                (_SEQUENCE_HIGH_WATER_KEY,),
            ).fetchone()
            if row is not None:
                return int(row["value"])
            legacy = self._conn.execute(
                "SELECT COALESCE(MAX(monotonic_seq), 0) AS n FROM canonical_events"
            ).fetchone()
        return int(legacy["n"])

    def expire_structured_short(self, *, now_ns: int, ttl_seconds: int) -> int:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")
        cutoff_ns = now_ns - ttl_seconds * 1_000_000_000
        if cutoff_ns < 0:
            return 0

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT event_id, data_json
                FROM canonical_events
                WHERE timestamp_ns <= ?
                ORDER BY timestamp_ns ASC, monotonic_seq ASC
                """,
                (cutoff_ns,),
            ).fetchall()
            expired_ids: list[str] = []
            for row in rows:
                try:
                    event = CanonicalEvent.model_validate(json.loads(row["data_json"]))
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
                if event.retention_class is RetentionClass.STRUCTURED_SHORT:
                    expired_ids.append(str(row["event_id"]))

            if not expired_ids:
                return 0
            with self._conn:
                self._conn.executemany(
                    "DELETE FROM canonical_events WHERE event_id = ?",
                    [(event_id,) for event_id in expired_ids],
                )
            return len(expired_ids)

    def integrity_check(self) -> str:
        with self._lock:
            row = self._conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0])

    @staticmethod
    def _row(event: CanonicalEvent) -> tuple[str, int, int, str]:
        data = event.model_dump(mode="json")
        encoded = json.dumps(data, allow_nan=False, sort_keys=True, separators=(",", ":"))
        return event.event_id, event.timestamp_ns, event.monotonic_seq, encoded

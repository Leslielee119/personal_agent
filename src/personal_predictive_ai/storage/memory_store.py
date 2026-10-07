from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

from personal_predictive_ai.memory.models import (
    MemoryAuditEvent,
    MemoryDependency,
    MemoryEvidenceLink,
    MemoryRecord,
    SupersessionEdge,
)


class MemoryRunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    source_b1_run_id: str = Field(min_length=1)
    source_high_water: int = Field(ge=0)
    extractor_version: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    schema_version: str = "ppa.memory-run/v1"


_ModelT = TypeVar("_ModelT", bound=BaseModel)


class MemoryStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        migration = Path(__file__).with_name("migrations") / "003_b2_memory.sql"
        self._conn.executescript(migration.read_text(encoding="utf-8"))
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def replace_run(
        self,
        metadata: MemoryRunMetadata,
        records: Iterable[MemoryRecord],
        evidence_links: Iterable[MemoryEvidenceLink],
        dependencies: Iterable[MemoryDependency],
        supersessions: Iterable[SupersessionEdge],
        audit_events: Iterable[MemoryAuditEvent],
    ) -> None:
        record_rows = [
            (metadata.run_id, item.memory_id, item.created_seq, self._encode(item))
            for item in records
        ]
        evidence_rows = [
            (
                metadata.run_id,
                item.memory_id,
                item.evidence_type,
                item.evidence_id,
                item.role.value,
                self._encode(item),
            )
            for item in evidence_links
        ]
        dependency_rows = [
            (metadata.run_id, item.dependency_id, item.created_seq, self._encode(item))
            for item in dependencies
        ]
        supersession_rows = [
            (metadata.run_id, item.supersession_id, item.created_seq, self._encode(item))
            for item in supersessions
        ]
        audit_rows = [
            (metadata.run_id, item.audit_id, item.source_seq, self._encode(item))
            for item in audit_events
        ]

        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._conn.execute("DELETE FROM memory_runs WHERE run_id = ?", (metadata.run_id,))
                self._conn.execute(
                    """
                    INSERT INTO memory_runs(
                        run_id, source_b1_run_id, source_high_water,
                        extractor_version, config_version, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        metadata.run_id,
                        metadata.source_b1_run_id,
                        metadata.source_high_water,
                        metadata.extractor_version,
                        metadata.config_version,
                        metadata.schema_version,
                    ),
                )
                self._conn.executemany(
                    """
                    INSERT INTO memory_records(run_id, memory_id, created_seq, data_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    record_rows,
                )
                self._conn.executemany(
                    """
                    INSERT INTO memory_evidence_links(
                        run_id, memory_id, evidence_type, evidence_id, role, data_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    evidence_rows,
                )
                self._conn.executemany(
                    """
                    INSERT INTO memory_dependencies(run_id, dependency_id, created_seq, data_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    dependency_rows,
                )
                self._conn.executemany(
                    """
                    INSERT INTO memory_supersessions(
                        run_id, supersession_id, created_seq, data_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    supersession_rows,
                )
                self._conn.executemany(
                    """
                    INSERT INTO memory_audit_events(run_id, audit_id, source_seq, data_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    audit_rows,
                )
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise

    def delete_run(self, run_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM memory_runs WHERE run_id = ?", (run_id,))

    def get_run(self, run_id: str) -> MemoryRunMetadata | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT run_id, source_b1_run_id, source_high_water,
                       extractor_version, config_version, schema_version
                FROM memory_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return MemoryRunMetadata(
            run_id=str(row["run_id"]),
            source_b1_run_id=str(row["source_b1_run_id"]),
            source_high_water=int(row["source_high_water"]),
            extractor_version=str(row["extractor_version"]),
            config_version=str(row["config_version"]),
            schema_version=str(row["schema_version"]),
        )

    def iter_records(self, run_id: str) -> Iterator[MemoryRecord]:
        yield from self._iter_models(
            "memory_records", "created_seq ASC, memory_id ASC", run_id, MemoryRecord
        )

    def iter_evidence_links(self, run_id: str) -> Iterator[MemoryEvidenceLink]:
        yield from self._iter_models(
            "memory_evidence_links",
            "memory_id ASC, evidence_type ASC, evidence_id ASC, role ASC",
            run_id,
            MemoryEvidenceLink,
        )

    def iter_dependencies(self, run_id: str) -> Iterator[MemoryDependency]:
        yield from self._iter_models(
            "memory_dependencies",
            "created_seq ASC, dependency_id ASC",
            run_id,
            MemoryDependency,
        )

    def iter_supersessions(self, run_id: str) -> Iterator[SupersessionEdge]:
        yield from self._iter_models(
            "memory_supersessions",
            "created_seq ASC, supersession_id ASC",
            run_id,
            SupersessionEdge,
        )

    def iter_audit_events(self, run_id: str) -> Iterator[MemoryAuditEvent]:
        yield from self._iter_models(
            "memory_audit_events",
            "source_seq ASC, audit_id ASC",
            run_id,
            MemoryAuditEvent,
        )

    def integrity_check(self) -> str:
        with self._lock:
            row = self._conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0])

    def _iter_models(
        self,
        table: str,
        order_by: str,
        run_id: str,
        model_type: type[_ModelT],
    ) -> Iterator[_ModelT]:
        allowed = {
            "memory_records": "created_seq ASC, memory_id ASC",
            "memory_evidence_links": (
                "memory_id ASC, evidence_type ASC, evidence_id ASC, role ASC"
            ),
            "memory_dependencies": "created_seq ASC, dependency_id ASC",
            "memory_supersessions": "created_seq ASC, supersession_id ASC",
            "memory_audit_events": "source_seq ASC, audit_id ASC",
        }
        if allowed.get(table) != order_by:
            raise ValueError("unsupported memory table/order")
        with self._lock:
            rows = self._conn.execute(
                f"SELECT data_json FROM {table} WHERE run_id = ? ORDER BY {order_by}",
                (run_id,),
            ).fetchall()
        for row in rows:
            yield model_type.model_validate(json.loads(row["data_json"]))

    @staticmethod
    def _encode(model: BaseModel) -> str:
        return json.dumps(
            model.model_dump(mode="json"),
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

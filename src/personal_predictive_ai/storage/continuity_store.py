from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from personal_predictive_ai.continuity.models import (
    DeletionTombstoneRecord,
    EvidenceRecord,
    ProjectRecord,
    ResumeBriefRecord,
    TaskRecord,
    TaskSnapshot,
    TaskStateFieldVersion,
    VerifiedResultRecord,
    WorkCopyRecord,
)

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class ContinuityStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        migration = Path(__file__).with_name("migrations") / "005_task_continuity.sql"
        self._conn.executescript(migration.read_text(encoding="utf-8"))
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def _encode(model: BaseModel) -> str:
        return json.dumps(model.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)

    @staticmethod
    def _decode(payload: str, model_type: type[_ModelT]) -> _ModelT:
        return model_type.model_validate_json(payload)

    def _insert(self, sql: str, params: tuple[object, ...]) -> None:
        with self._lock, self._conn:
            self._conn.execute(sql, params)

    def add_project(self, item: ProjectRecord) -> None:
        self._insert(
            "INSERT INTO continuity_projects(project_id, created_at_ns, data_json) "
            "VALUES (?, ?, ?)",
            (item.project_id, item.created_at_ns, self._encode(item)),
        )

    def add_workcopy(self, item: WorkCopyRecord) -> None:
        self._insert(
            "INSERT INTO continuity_workcopies(workcopy_id, project_id, created_at_ns, data_json) "
            "VALUES (?, ?, ?, ?)",
            (item.workcopy_id, item.project_id, item.created_at_ns, self._encode(item)),
        )

    def add_task(self, item: TaskRecord) -> None:
        self._insert(
            "INSERT INTO continuity_tasks("
            + "task_id, project_id, workcopy_id, created_at_ns, data_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                item.task_id,
                item.project_id,
                item.workcopy_id,
                item.created_at_ns,
                self._encode(item),
            ),
        )

    def add_evidence(self, item: EvidenceRecord) -> None:
        self._insert(
            "INSERT INTO continuity_evidence("
            "evidence_id, project_id, workcopy_id, task_id, available_at_ns, data_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                item.evidence_id,
                item.project_id,
                item.workcopy_id,
                item.task_id,
                item.available_at_ns,
                self._encode(item),
            ),
        )

    def add_field_version(self, item: TaskStateFieldVersion) -> None:
        self._insert(
            "INSERT INTO continuity_field_versions("
            "field_version_id, task_id, field_name, created_at_ns, data_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                item.field_version_id,
                item.task_id,
                item.field_name,
                item.created_at_ns,
                self._encode(item),
            ),
        )

    def add_verified_result(self, item: VerifiedResultRecord) -> None:
        self._insert(
            "INSERT INTO continuity_verified_results("
            "result_id, workcopy_id, task_id, observed_at_ns, data_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                item.result_id,
                item.workcopy_id,
                item.task_id,
                item.observed_at_ns,
                self._encode(item),
            ),
        )

    def add_snapshot(self, item: TaskSnapshot) -> None:
        self._insert(
            "INSERT OR IGNORE INTO continuity_snapshots("
            "snapshot_id, task_id, captured_at_ns, data_json) VALUES (?, ?, ?, ?)",
            (item.snapshot_id, item.task_id, item.captured_at_ns, self._encode(item)),
        )

    def add_brief(self, item: ResumeBriefRecord) -> None:
        self._insert(
            "INSERT INTO continuity_briefs(brief_id, task_id, created_at_ns, data_json) "
            "VALUES (?, ?, ?, ?)",
            (item.brief_id, item.task_id, item.created_at_ns, self._encode(item)),
        )

    def add_tombstone(self, item: DeletionTombstoneRecord) -> None:
        self._insert(
            "INSERT INTO continuity_deletions(deletion_id, deleted_at_ns, data_json) "
            "VALUES (?, ?, ?)",
            (item.deletion_id, item.deleted_at_ns, self._encode(item)),
        )

    def _get(self, table: str, key_col: str, key: str, model_type: type[_ModelT]) -> _ModelT | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT data_json FROM {table} WHERE {key_col} = ?", (key,)
            ).fetchone()
        return None if row is None else self._decode(str(row["data_json"]), model_type)

    def get_project(self, project_id: str) -> ProjectRecord | None:
        return self._get("continuity_projects", "project_id", project_id, ProjectRecord)

    def get_workcopy(self, workcopy_id: str) -> WorkCopyRecord | None:
        return self._get("continuity_workcopies", "workcopy_id", workcopy_id, WorkCopyRecord)

    def get_task(self, task_id: str) -> TaskRecord | None:
        return self._get("continuity_tasks", "task_id", task_id, TaskRecord)

    def get_snapshot(self, snapshot_id: str) -> TaskSnapshot | None:
        return self._get("continuity_snapshots", "snapshot_id", snapshot_id, TaskSnapshot)

    def iter_evidence(
        self,
        project_id: str,
        *,
        workcopy_id: str | None = None,
        task_id: str | None = None,
        as_of_ns: int | None = None,
    ) -> Iterator[EvidenceRecord]:
        clauses = ["project_id = ?"]
        params: list[object] = [project_id]
        if workcopy_id is not None:
            clauses.append("workcopy_id = ?")
            params.append(workcopy_id)
        if task_id is not None:
            clauses.append("task_id = ?")
            params.append(task_id)
        if as_of_ns is not None:
            clauses.append("available_at_ns <= ?")
            params.append(as_of_ns)
        sql = (
            "SELECT data_json FROM continuity_evidence WHERE "
            + " AND ".join(clauses)
            + " ORDER BY available_at_ns ASC, evidence_id ASC"
        )
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        for row in rows:
            yield self._decode(str(row["data_json"]), EvidenceRecord)

    def iter_field_versions(
        self, task_id: str, *, field_name: str | None = None, as_of_ns: int | None = None
    ) -> Iterator[TaskStateFieldVersion]:
        clauses = ["task_id = ?"]
        params: list[object] = [task_id]
        if field_name is not None:
            clauses.append("field_name = ?")
            params.append(field_name)
        if as_of_ns is not None:
            clauses.append("created_at_ns <= ?")
            params.append(as_of_ns)
        sql = (
            "SELECT data_json FROM continuity_field_versions WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at_ns ASC, field_version_id ASC"
        )
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        for row in rows:
            yield self._decode(str(row["data_json"]), TaskStateFieldVersion)

    def integrity_check(self) -> str:
        with self._lock:
            row = self._conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0])

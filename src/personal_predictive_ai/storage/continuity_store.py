from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from personal_predictive_ai.continuity.ids import deletion_id_for
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
        self._conn.execute("PRAGMA secure_delete=ON")
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
            "INSERT OR IGNORE INTO continuity_evidence("
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

    def replace_field_version(self, item: TaskStateFieldVersion) -> None:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE continuity_field_versions SET data_json = ? "
                "WHERE field_version_id = ?",
                (self._encode(item), item.field_version_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(item.field_version_id)

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

    def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        return self._get("continuity_evidence", "evidence_id", evidence_id, EvidenceRecord)

    def get_snapshot(self, snapshot_id: str) -> TaskSnapshot | None:
        return self._get("continuity_snapshots", "snapshot_id", snapshot_id, TaskSnapshot)

    def get_verified_result(self, result_id: str) -> VerifiedResultRecord | None:
        return self._get(
            "continuity_verified_results", "result_id", result_id, VerifiedResultRecord
        )

    def iter_verified_results(
        self, task_id: str, *, as_of_ns: int | None = None
    ) -> Iterator[VerifiedResultRecord]:
        clauses = ["task_id = ?"]
        params: list[object] = [task_id]
        if as_of_ns is not None:
            clauses.append("observed_at_ns <= ?")
            params.append(as_of_ns)
        sql = (
            "SELECT data_json FROM continuity_verified_results WHERE "
            + " AND ".join(clauses)
            + " ORDER BY observed_at_ns ASC, result_id ASC"
        )
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        for row in rows:
            yield self._decode(str(row["data_json"]), VerifiedResultRecord)

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

    def iter_snapshots(self, task_id: str) -> Iterator[TaskSnapshot]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data_json FROM continuity_snapshots WHERE task_id = ? "
                "ORDER BY captured_at_ns ASC, snapshot_id ASC",
                (task_id,),
            ).fetchall()
        for row in rows:
            yield self._decode(str(row["data_json"]), TaskSnapshot)

    def iter_briefs(self, task_id: str) -> Iterator[ResumeBriefRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data_json FROM continuity_briefs WHERE task_id = ? "
                "ORDER BY created_at_ns ASC, brief_id ASC",
                (task_id,),
            ).fetchall()
        for row in rows:
            yield self._decode(str(row["data_json"]), ResumeBriefRecord)

    def iter_tombstones(self) -> Iterator[DeletionTombstoneRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data_json FROM continuity_deletions "
                "ORDER BY deleted_at_ns ASC, deletion_id ASC"
            ).fetchall()
        for row in rows:
            yield self._decode(str(row["data_json"]), DeletionTombstoneRecord)

    def delete_evidence(
        self, evidence_id: str, *, now_ns: int
    ) -> DeletionTombstoneRecord:
        evidence = self.get_evidence(evidence_id)
        if evidence is None:
            raise KeyError(evidence_id)
        tombstone = self._new_tombstone("evidence", evidence_id, now_ns)
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                if evidence.task_id is not None:
                    field_rows = self._conn.execute(
                        "SELECT field_version_id, data_json FROM continuity_field_versions "
                        "WHERE task_id = ?",
                        (evidence.task_id,),
                    ).fetchall()
                    for row in field_rows:
                        record = self._decode(
                            str(row["data_json"]), TaskStateFieldVersion
                        )
                        if evidence_id in record.evidence_ids:
                            self._conn.execute(
                                "DELETE FROM continuity_field_versions "
                                "WHERE field_version_id = ?",
                                (record.field_version_id,),
                            )
                    result_rows = self._conn.execute(
                        "SELECT result_id, data_json FROM continuity_verified_results "
                        "WHERE task_id = ?",
                        (evidence.task_id,),
                    ).fetchall()
                    for row in result_rows:
                        result = self._decode(
                            str(row["data_json"]), VerifiedResultRecord
                        )
                        if evidence_id in result.evidence_ids:
                            self._conn.execute(
                                "DELETE FROM continuity_verified_results WHERE result_id = ?",
                                (result.result_id,),
                            )
                    self._conn.execute(
                        "DELETE FROM continuity_snapshots WHERE task_id = ?",
                        (evidence.task_id,),
                    )
                    self._conn.execute(
                        "DELETE FROM continuity_briefs WHERE task_id = ?",
                        (evidence.task_id,),
                    )
                self._conn.execute(
                    "DELETE FROM continuity_evidence WHERE evidence_id = ?",
                    (evidence_id,),
                )
                self._insert_tombstone(tombstone)
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
        self._purge_free_pages()
        return tombstone

    def delete_task(self, task_id: str, *, now_ns: int) -> DeletionTombstoneRecord:
        if self.get_task(task_id) is None:
            raise KeyError(task_id)
        return self._delete_scope("continuity_tasks", "task_id", "task", task_id, now_ns)

    def delete_workcopy(
        self, workcopy_id: str, *, now_ns: int
    ) -> DeletionTombstoneRecord:
        if self.get_workcopy(workcopy_id) is None:
            raise KeyError(workcopy_id)
        return self._delete_scope(
            "continuity_workcopies", "workcopy_id", "workcopy", workcopy_id, now_ns
        )

    def delete_project(
        self, project_id: str, *, now_ns: int
    ) -> DeletionTombstoneRecord:
        if self.get_project(project_id) is None:
            raise KeyError(project_id)
        return self._delete_scope(
            "continuity_projects", "project_id", "project", project_id, now_ns
        )

    def _delete_scope(
        self,
        table: str,
        key_column: str,
        scope_type: str,
        scope_id: str,
        now_ns: int,
    ) -> DeletionTombstoneRecord:
        tombstone = self._new_tombstone(scope_type, scope_id, now_ns)
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._conn.execute(
                    f"DELETE FROM {table} WHERE {key_column} = ?", (scope_id,)
                )
                self._insert_tombstone(tombstone)
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
        self._purge_free_pages()
        return tombstone

    @staticmethod
    def _new_tombstone(
        scope_type: str, scope_id: str, now_ns: int
    ) -> DeletionTombstoneRecord:
        scope_hash = hashlib.sha256(
            f"{scope_type}\x00{scope_id}".encode("utf-8")
        ).hexdigest()
        return DeletionTombstoneRecord(
            deletion_id=deletion_id_for(scope_type, scope_id, now_ns),
            scope_type=scope_type,
            scope_hash=scope_hash,
            deleted_at_ns=now_ns,
        )

    def _insert_tombstone(self, item: DeletionTombstoneRecord) -> None:
        self._conn.execute(
            "INSERT INTO continuity_deletions(deletion_id, deleted_at_ns, data_json) "
            "VALUES (?, ?, ?)",
            (item.deletion_id, item.deleted_at_ns, self._encode(item)),
        )

    def _purge_free_pages(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._conn.execute("VACUUM")
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def integrity_check(self) -> str:
        with self._lock:
            row = self._conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0])

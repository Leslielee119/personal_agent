from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from personal_predictive_ai.knowledge.models import KnowledgeRecord
from personal_predictive_ai.skills.models import (
    SkillAuditEvent,
    SkillMutationProposal,
    SkillPackageManifest,
    SkillProjectionManifest,
    SkillRecord,
)

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class KnowledgeSkillStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        migration = Path(__file__).with_name("migrations") / "004_e_knowledge_skill.sql"
        self._conn.executescript(migration.read_text(encoding="utf-8"))
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def put_knowledge(self, record: KnowledgeRecord) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO knowledge_records(knowledge_id, status, data_json)
                VALUES (?, ?, ?)
                ON CONFLICT(knowledge_id) DO UPDATE SET
                    status=excluded.status,
                    data_json=excluded.data_json
                """,
                (record.knowledge_id, record.status.value, self._encode(record)),
            )

    def get_knowledge(self, knowledge_id: str) -> KnowledgeRecord | None:
        return self._get_model(
            "knowledge_records", "knowledge_id", knowledge_id, KnowledgeRecord
        )

    def iter_knowledge(self) -> Iterator[KnowledgeRecord]:
        yield from self._iter_models("knowledge_records", "knowledge_id ASC", KnowledgeRecord)

    def stage_proposal(self, proposal: SkillMutationProposal) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO skill_mutation_proposals(
                    proposal_id, target_skill_id, base_version, approval_status, data_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    proposal.proposal_id,
                    proposal.target_skill_id,
                    proposal.base_version,
                    proposal.approval_status.value,
                    self._encode(proposal),
                ),
            )

    def get_proposal(self, proposal_id: str) -> SkillMutationProposal | None:
        return self._get_model(
            "skill_mutation_proposals", "proposal_id", proposal_id, SkillMutationProposal
        )

    def replace_proposal(self, proposal: SkillMutationProposal) -> None:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """
                UPDATE skill_mutation_proposals
                SET target_skill_id=?, base_version=?, approval_status=?, data_json=?
                WHERE proposal_id=?
                """,
                (
                    proposal.target_skill_id,
                    proposal.base_version,
                    proposal.approval_status.value,
                    self._encode(proposal),
                    proposal.proposal_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(proposal.proposal_id)

    def append_skill_version(self, record: SkillRecord) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO skill_records(skill_id, version, status, risk_class, data_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.skill_id,
                    record.version,
                    record.status.value,
                    record.risk_class.value,
                    self._encode(record),
                ),
            )

    def get_skill(self, skill_id: str, version: int | None = None) -> SkillRecord | None:
        with self._lock:
            if version is None:
                row = self._conn.execute(
                    """
                    SELECT data_json FROM skill_records
                    WHERE skill_id=? ORDER BY version DESC LIMIT 1
                    """,
                    (skill_id,),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT data_json FROM skill_records WHERE skill_id=? AND version=?",
                    (skill_id, version),
                ).fetchone()
        if row is None:
            return None
        return SkillRecord.model_validate(json.loads(row["data_json"]))

    def iter_skill_versions(self, skill_id: str) -> Iterator[SkillRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT data_json FROM skill_records
                WHERE skill_id=? ORDER BY version ASC
                """,
                (skill_id,),
            ).fetchall()
        for row in rows:
            yield SkillRecord.model_validate(json.loads(row["data_json"]))

    def put_package_manifest(self, manifest: SkillPackageManifest) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO skill_package_manifests(package_id, trust_state, source_type, data_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(package_id) DO UPDATE SET
                    trust_state=excluded.trust_state,
                    source_type=excluded.source_type,
                    data_json=excluded.data_json
                """,
                (
                    manifest.package_id,
                    manifest.trust_state.value,
                    manifest.source_type.value,
                    self._encode(manifest),
                ),
            )

    def get_package_manifest(self, package_id: str) -> SkillPackageManifest | None:
        return self._get_model(
            "skill_package_manifests", "package_id", package_id, SkillPackageManifest
        )

    def append_audit_event(self, event: SkillAuditEvent) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO skill_audit_events(
                    audit_id, skill_id, event_type, occurred_at, data_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.audit_id,
                    event.skill_id,
                    event.event_type,
                    event.occurred_at,
                    self._encode(event),
                ),
            )

    def iter_audit_events(self, skill_id: str | None = None) -> Iterator[SkillAuditEvent]:
        with self._lock:
            if skill_id is None:
                rows = self._conn.execute(
                    "SELECT data_json FROM skill_audit_events ORDER BY occurred_at, audit_id"
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT data_json FROM skill_audit_events
                    WHERE skill_id=? ORDER BY occurred_at, audit_id
                    """,
                    (skill_id,),
                ).fetchall()
        for row in rows:
            yield SkillAuditEvent.model_validate(json.loads(row["data_json"]))

    def put_projection_manifest(self, manifest: SkillProjectionManifest) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO skill_projection_manifests(projection_id, skill_id, version, data_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(projection_id) DO UPDATE SET data_json=excluded.data_json
                """,
                (
                    manifest.projection_id,
                    manifest.skill_id,
                    manifest.version,
                    self._encode(manifest),
                ),
            )

    def get_projection_manifest(self, projection_id: str) -> SkillProjectionManifest | None:
        return self._get_model(
            "skill_projection_manifests",
            "projection_id",
            projection_id,
            SkillProjectionManifest,
        )

    def commit_approved_skill(
        self,
        proposal: SkillMutationProposal,
        record: SkillRecord,
        audit_event: SkillAuditEvent,
        *,
        expected_base_version: int | None,
    ) -> None:
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                current = self._conn.execute(
                    "SELECT MAX(version) FROM skill_records WHERE skill_id=?",
                    (record.skill_id,),
                ).fetchone()[0]
                current_version = None if current is None else int(current)
                if current_version != expected_base_version:
                    raise ValueError(
                        "base version mismatch: "
                        f"expected {expected_base_version}, got {current_version}"
                    )
                self._conn.execute(
                    """
                    INSERT INTO skill_records(skill_id, version, status, risk_class, data_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        record.skill_id,
                        record.version,
                        record.status.value,
                        record.risk_class.value,
                        self._encode(record),
                    ),
                )
                cursor = self._conn.execute(
                    """
                    UPDATE skill_mutation_proposals
                    SET target_skill_id=?, base_version=?, approval_status=?, data_json=?
                    WHERE proposal_id=?
                    """,
                    (
                        proposal.target_skill_id,
                        proposal.base_version,
                        proposal.approval_status.value,
                        self._encode(proposal),
                        proposal.proposal_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise KeyError(proposal.proposal_id)
                self._conn.execute(
                    """
                    INSERT INTO skill_audit_events(
                        audit_id, skill_id, event_type, occurred_at, data_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        audit_event.audit_id,
                        audit_event.skill_id,
                        audit_event.event_type,
                        audit_event.occurred_at,
                        self._encode(audit_event),
                    ),
                )
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise

    def integrity_check(self) -> str:
        with self._lock:
            row = self._conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0])

    def _get_model(
        self,
        table: str,
        key_column: str,
        key: str,
        model_type: type[_ModelT],
    ) -> _ModelT | None:
        allowed = {
            ("knowledge_records", "knowledge_id"),
            ("skill_mutation_proposals", "proposal_id"),
            ("skill_package_manifests", "package_id"),
            ("skill_projection_manifests", "projection_id"),
        }
        if (table, key_column) not in allowed:
            raise ValueError("unsupported registry lookup")
        with self._lock:
            row = self._conn.execute(
                f"SELECT data_json FROM {table} WHERE {key_column}=?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return model_type.model_validate(json.loads(row["data_json"]))

    def _iter_models(
        self,
        table: str,
        order_by: str,
        model_type: type[_ModelT],
    ) -> Iterator[_ModelT]:
        allowed = {("knowledge_records", "knowledge_id ASC")}
        if (table, order_by) not in allowed:
            raise ValueError("unsupported registry iteration")
        with self._lock:
            rows = self._conn.execute(
                f"SELECT data_json FROM {table} ORDER BY {order_by}"
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

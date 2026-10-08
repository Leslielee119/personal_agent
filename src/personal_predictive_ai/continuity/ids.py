from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    return value


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    for value in payload.values():
        if isinstance(value, str) and not value:
            raise ValueError("identity inputs must be non-empty")
    encoded = json.dumps(
        {key: _jsonable(value) for key, value in payload.items()},
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()}"


def project_id_for(project_key: str) -> str:
    return _stable_id("project", {"project_key": project_key})


def workcopy_id_for(project_id: str, canonical_root: str) -> str:
    return _stable_id("workcopy", {"project_id": project_id, "canonical_root": canonical_root})


def task_id_for(project_id: str, workcopy_id: str, created_at_ns: int, initial_title: str) -> str:
    return _stable_id(
        "task",
        {
            "project_id": project_id,
            "workcopy_id": workcopy_id,
            "created_at_ns": created_at_ns,
            "initial_title": initial_title,
        },
    )


def evidence_id_for(
    project_id: str,
    workcopy_id: str | None,
    task_id: str | None,
    kind: str,
    source_ref: str,
    observed_at_ns: int,
    content: Any,
) -> str:
    return _stable_id(
        "evidence",
        {
            "project_id": project_id,
            "workcopy_id": workcopy_id,
            "task_id": task_id,
            "kind": kind,
            "source_ref": source_ref,
            "observed_at_ns": observed_at_ns,
            "content": content,
        },
    )


def field_version_id_for(
    task_id: str, field_name: str, value: Any, created_at_ns: int, evidence_ids: list[str]
) -> str:
    return _stable_id(
        "field",
        {
            "task_id": task_id,
            "field_name": field_name,
            "value": value,
            "created_at_ns": created_at_ns,
            "evidence_ids": evidence_ids,
        },
    )


def snapshot_id_for(task_id: str, captured_at_ns: int, field_version_ids: list[str]) -> str:
    return _stable_id(
        "snapshot",
        {
            "task_id": task_id,
            "captured_at_ns": captured_at_ns,
            "field_version_ids": field_version_ids,
        },
    )


def brief_id_for(snapshot_id: str, created_at_ns: int) -> str:
    return _stable_id("brief", {"snapshot_id": snapshot_id, "created_at_ns": created_at_ns})


def verified_result_id_for(
    workcopy_id: str, check_kind: str, code_state_fingerprint: str, observed_at_ns: int
) -> str:
    return _stable_id(
        "verified",
        {
            "workcopy_id": workcopy_id,
            "check_kind": check_kind,
            "code_state_fingerprint": code_state_fingerprint,
            "observed_at_ns": observed_at_ns,
        },
    )


def deletion_id_for(scope_type: str, scope_id: str, deleted_at_ns: int) -> str:
    return _stable_id(
        "deletion", {"scope_type": scope_type, "scope_id": scope_id, "deleted_at_ns": deleted_at_ns}
    )

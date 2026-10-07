from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel

from personal_predictive_ai.memory.models import DependencyRelation, MemoryKind, MemoryScope


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    return value


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {key: _jsonable(value) for key, value in payload.items()},
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()}"


def memory_id_for(
    kind: MemoryKind,
    scope: MemoryScope,
    key: str,
    value: Any,
    extractor_id: str,
) -> str:
    return _stable_id(
        "mem",
        {
            "kind": kind,
            "scope": scope,
            "key": key,
            "value": value,
            "extractor_id": extractor_id,
        },
    )


def dependency_id_for(
    parent_memory_id: str,
    child_memory_id: str,
    relation: DependencyRelation,
    created_seq: int,
) -> str:
    return _stable_id(
        "dep",
        {
            "parent_memory_id": parent_memory_id,
            "child_memory_id": child_memory_id,
            "relation": relation,
            "created_seq": created_seq,
        },
    )


def supersession_id_for(new_memory_id: str, old_memory_id: str, source_seq: int) -> str:
    return _stable_id(
        "sup",
        {
            "new_memory_id": new_memory_id,
            "old_memory_id": old_memory_id,
            "source_seq": source_seq,
        },
    )


def audit_id_for(
    memory_id: str,
    event_type: str,
    source_seq: int,
    reason_code: str,
    *,
    ordinal: int = 0,
) -> str:
    return _stable_id(
        "audit",
        {
            "memory_id": memory_id,
            "event_type": event_type,
            "source_seq": source_seq,
            "reason_code": reason_code,
            "ordinal": ordinal,
        },
    )

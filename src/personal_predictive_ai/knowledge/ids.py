from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel

from personal_predictive_ai.knowledge.models import KnowledgeScope, KnowledgeSourceClass


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


def knowledge_id_for(
    scope: KnowledgeScope,
    key: str,
    value: Any,
    source_class: KnowledgeSourceClass,
) -> str:
    return _stable_id(
        "kn",
        {
            "scope": scope,
            "key": key,
            "value": value,
            "source_class": source_class,
        },
    )

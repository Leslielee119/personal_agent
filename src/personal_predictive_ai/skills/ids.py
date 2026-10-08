from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel

from personal_predictive_ai.skills.models import MutationKind, SkillKind, SkillScope


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


def skill_id_for(kind: SkillKind, canonical_name: str, scope: SkillScope) -> str:
    return _stable_id("skill", {"kind": kind, "canonical_name": canonical_name, "scope": scope})


def proposal_id_for(
    target_skill_id: str,
    base_version: int | None,
    mutation_kind: MutationKind,
    proposed_patch: dict[str, Any],
    proposed_by: str,
) -> str:
    return _stable_id(
        "proposal",
        {
            "target_skill_id": target_skill_id,
            "base_version": base_version,
            "mutation_kind": mutation_kind,
            "proposed_patch": proposed_patch,
            "proposed_by": proposed_by,
        },
    )


def package_id_for(
    source_type: str,
    source_uri: str,
    source_revision: str,
    content_hash: str,
) -> str:
    return _stable_id(
        "pkg",
        {
            "source_type": source_type,
            "source_uri": source_uri,
            "source_revision": source_revision,
            "content_hash": content_hash,
        },
    )

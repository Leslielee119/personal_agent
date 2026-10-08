from __future__ import annotations

import json
import re
from typing import Any

from personal_predictive_ai.skills.models import RiskClass

_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|password|secret)\b\s*[:=]"
)
_RISK_RANK = {
    RiskClass.READ_ONLY: 0,
    RiskClass.WRITE_LOCAL: 1,
    RiskClass.ACT_LOCAL: 2,
    RiskClass.EXTERNAL_EFFECT: 3,
    RiskClass.UNKNOWN: 4,
}


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _walk_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_strings(item)


def validate_safe_structured_text(value: object) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("structured value must be strict JSON-safe data") from exc
    for text in _walk_strings(value):
        if _SENSITIVE_ASSIGNMENT.search(text):
            raise ValueError("sensitive credential-like content is not allowed")


def risk_rank(risk: RiskClass) -> int:
    return _RISK_RANK[risk]

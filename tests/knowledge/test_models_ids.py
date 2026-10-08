import pytest
from pydantic import ValidationError

from personal_predictive_ai.knowledge.ids import knowledge_id_for
from personal_predictive_ai.knowledge.models import (
    KnowledgeRecord,
    KnowledgeScope,
    KnowledgeSourceClass,
    KnowledgeStatus,
)


def _record(**overrides) -> KnowledgeRecord:
    data = {
        "knowledge_id": "kn:1",
        "kind": "preference",
        "key": "editor.theme",
        "value": "dark",
        "scope": KnowledgeScope(scope_type="global", scope_id="user"),
        "source_class": KnowledgeSourceClass.HUMAN_DECLARED,
        "provenance": {"author": "human"},
        "created_at": "2026-10-08T09:00:00+08:00",
        "created_seq": 1,
        "valid_from": 1,
        "valid_to": None,
        "evidence_refs": ["note:1"],
        "confidence": 1.0,
        "status": KnowledgeStatus.ACTIVE,
    }
    data.update(overrides)
    return KnowledgeRecord(**data)


def test_knowledge_enums_and_schema_are_exact() -> None:
    assert [item.value for item in KnowledgeSourceClass] == [
        "human_declared",
        "human_approved_import",
        "derived_from_b2",
        "ai_proposed",
        "system",
        "external",
        "unknown",
    ]
    assert [item.value for item in KnowledgeStatus] == [
        "draft",
        "active",
        "superseded",
        "invalid",
    ]
    record = _record()
    assert record.schema_version == "ppa.knowledge/v1"
    with pytest.raises(ValidationError):
        KnowledgeRecord(**{**record.model_dump(), "unexpected": True})


def test_knowledge_validation_and_id_are_deterministic() -> None:
    scope = KnowledgeScope(scope_type="project", scope_id="alpha")
    first = knowledge_id_for(scope, "editor.theme", "dark", KnowledgeSourceClass.HUMAN_DECLARED)
    second = knowledge_id_for(scope, "editor.theme", "dark", KnowledgeSourceClass.HUMAN_DECLARED)
    assert first == second
    assert first.startswith("kn:")
    assert first != knowledge_id_for(
        scope,
        "editor.theme",
        "light",
        KnowledgeSourceClass.HUMAN_DECLARED,
    )

    with pytest.raises(ValidationError):
        _record(value={"bad": {1, 2}})
    with pytest.raises(ValidationError):
        _record(valid_from=5, valid_to=4)
    with pytest.raises(ValidationError):
        _record(confidence=1.1)

import pytest
from pydantic import ValidationError

from personal_predictive_ai.memory.ids import (
    audit_id_for,
    dependency_id_for,
    memory_id_for,
    supersession_id_for,
)
from personal_predictive_ai.memory.models import (
    ConsolidationConfigV1,
    DependencyRelation,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    ProvenanceSummary,
)


def _record(**overrides) -> MemoryRecord:
    data = {
        "memory_id": "mem-1",
        "kind": MemoryKind.FACT,
        "key": "foreground_application.primary",
        "value": "Code.exe",
        "scope": MemoryScope(scope_type="global", scope_id="user"),
        "observed_from": 10,
        "valid_from": 10,
        "valid_to": None,
        "created_seq": 1,
        "last_supported_seq": 3,
        "evidence_ids": ["evt-1", "evt-2", "evt-3"],
        "provenance_summary": ProvenanceSummary(system_support=3),
        "support_count": 3,
        "contradiction_count": 0,
        "session_ids": ["s1", "s2"],
        "confidence": 1.0,
        "status": MemoryStatus.ACTIVE,
        "extractor_id": "fact.foreground_application/v1",
        "config_version": "ppa.memory-config/v1",
    }
    data.update(overrides)
    return MemoryRecord(**data)


def test_enum_values_and_frozen_config_are_exact() -> None:
    assert [item.value for item in MemoryKind] == ["fact", "habit", "procedure", "style"]
    assert [item.value for item in MemoryStatus] == [
        "candidate",
        "active",
        "superseded",
        "invalid",
        "needs_revalidation",
    ]
    assert [item.value for item in DependencyRelation] == [
        "derived_from",
        "supports",
        "constrains",
    ]

    config = ConsolidationConfigV1()
    assert config.schema_version == "ppa.memory-config/v1"
    assert config.fact_min_support == 3
    assert config.fact_min_sessions == 2
    assert config.fact_min_ratio == 0.80
    assert config.habit_min_support == 5
    assert config.habit_min_sessions == 3
    assert config.habit_min_ratio == 0.70


def test_memory_record_requires_json_safe_value_and_valid_bounds() -> None:
    with pytest.raises(ValidationError):
        _record(value={"bad": {1, 2, 3}})
    with pytest.raises(ValidationError):
        _record(confidence=1.01)
    with pytest.raises(ValidationError):
        _record(support_count=-1)
    with pytest.raises(ValidationError):
        _record(valid_from=20, valid_to=19)


def test_provenance_summary_has_nonnegative_seven_counters() -> None:
    summary = ProvenanceSummary(
        human_physical_support=1,
        ai_suggested_accepted_support=2,
        ai_suggested_modified_support=3,
        ai_executed_support=4,
        system_support=5,
        external_support=6,
        unknown_support=7,
    )
    assert sum(summary.model_dump().values()) == 28
    with pytest.raises(ValidationError):
        ProvenanceSummary(unknown_support=-1)


def test_memory_id_is_claim_stable_and_not_evidence_or_wall_clock_dependent() -> None:
    scope = MemoryScope(scope_type="application", scope_id="Code.exe")
    first = memory_id_for(
        MemoryKind.HABIT,
        scope,
        "habit.next_operation:Code.exe:save",
        "run_tests",
        "habit.next_operation/v1",
    )
    second = memory_id_for(
        MemoryKind.HABIT,
        MemoryScope(scope_type="application", scope_id="Code.exe"),
        "habit.next_operation:Code.exe:save",
        "run_tests",
        "habit.next_operation/v1",
    )
    changed = memory_id_for(
        MemoryKind.HABIT,
        scope,
        "habit.next_operation:Code.exe:save",
        "open_browser",
        "habit.next_operation/v1",
    )
    assert first == second
    assert first != changed
    assert first.startswith("mem:")


def test_other_ids_are_deterministic_from_semantic_fields() -> None:
    dep1 = dependency_id_for("m1", "m2", DependencyRelation.DERIVED_FROM, 11)
    dep2 = dependency_id_for("m1", "m2", DependencyRelation.DERIVED_FROM, 11)
    sup1 = supersession_id_for("m-new", "m-old", 12)
    sup2 = supersession_id_for("m-new", "m-old", 12)
    audit1 = audit_id_for("m1", "memory.created", 13, "extractor", ordinal=0)
    audit2 = audit_id_for("m1", "memory.created", 13, "extractor", ordinal=0)
    assert dep1 == dep2
    assert sup1 == sup2
    assert audit1 == audit2
    assert len({dep1, sup1, audit1}) == 3

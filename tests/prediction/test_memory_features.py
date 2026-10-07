from __future__ import annotations

from personal_predictive_ai.events.models import EventProvenance
from personal_predictive_ai.memory.models import (
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    ProvenanceSummary,
)
from personal_predictive_ai.prediction.config import PredictionConfigV1
from personal_predictive_ai.prediction.models import (
    PredictionExample,
    StructuredContext,
    TargetSpace,
)


def _load_api():
    from personal_predictive_ai.prediction.memory_features import (
        ExampleMemoryFeatures,
        audit_memory_exposure,
        memory_features_for_example,
    )

    return ExampleMemoryFeatures, audit_memory_exposure, memory_features_for_example


def _record(
    memory_id: str,
    *,
    status: MemoryStatus = MemoryStatus.ACTIVE,
    created_seq: int = 1,
    last_supported_seq: int = 2,
    valid_from: int = 1,
    valid_to: int | None = None,
    kind: MemoryKind = MemoryKind.HABIT,
    scope: MemoryScope | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        kind=kind,
        key=f"habit.test:{memory_id}",
        value="run_tests",
        scope=scope or MemoryScope(scope_type="global", scope_id="user"),
        observed_from=valid_from,
        valid_from=valid_from,
        valid_to=valid_to,
        created_seq=created_seq,
        last_supported_seq=last_supported_seq,
        evidence_ids=[f"evt-{memory_id}"],
        provenance_summary=ProvenanceSummary(human_physical_support=3),
        support_count=3,
        contradiction_count=0,
        session_ids=["s1", "s2"],
        confidence=1.0,
        extractor_id="fixture/v1",
        status=status,
        eligible_support_count=3,
        eligible_human_support_count=3,
    )


def _snapshot(*records: MemoryRecord):
    from personal_predictive_ai.memory.reconstruction import B2Snapshot

    return B2Snapshot(
        source_b1_run_id="b1",
        source_high_water=100,
        source_event_count=100,
        v1_count=0,
        v2_count=100,
        fact_candidates=sum(item.kind is MemoryKind.FACT for item in records),
        habit_candidates=sum(item.kind is MemoryKind.HABIT for item in records),
        records=tuple(records),
        evidence_links=(),
        dependencies=(),
        supersessions=(),
        audit_events=(),
        extractor_version="b2-deterministic/v1",
        config_version="ppa.memory-config/v1",
    )


def _example(sample_id: str, session_id: str, seq: int, ts: int) -> PredictionExample:
    return PredictionExample(
        sample_id=sample_id,
        target_space=TargetSpace.OPERATION,
        session_id=session_id,
        cutoff_seq=seq,
        target_timestamp_ns=ts,
        target_action_id=f"act-{sample_id}",
        target_label="run_tests",
        history_labels=("save",),
        joint_history=("Code.exe::save",),
        context=StructuredContext(
            foreground_application="Code.exe",
            previous_operation="save",
            recent_joint_actions=("Code.exe::save",),
            active_process_names=("Code.exe",),
        ),
    )


def test_only_active_or_historically_valid_records_with_past_evidence_are_exposed() -> None:
    _, _, memory_features_for_example = _load_api()
    example = _example("q", "s1", 50, 5_000)
    snapshot = _snapshot(
        _record("active", created_seq=10, last_supported_seq=20, valid_from=1_000),
        _record("candidate", status=MemoryStatus.CANDIDATE, created_seq=10, last_supported_seq=20),
        _record(
            "needs",
            status=MemoryStatus.NEEDS_REVALIDATION,
            created_seq=10,
            last_supported_seq=20,
        ),
        _record("future-evidence", created_seq=10, last_supported_seq=60, valid_from=1_000),
        _record("future-validity", created_seq=10, last_supported_seq=20, valid_from=6_000),
    )

    features = memory_features_for_example(
        example,
        snapshot,
        allowed_provenance={EventProvenance.HUMAN_PHYSICAL},
        limit=10,
    )

    assert [item.memory_id for item in features] == ["active"]
    encoded = "".join(item.model_dump_json() for item in features)
    assert "evt-active" not in encoded
    assert "evidence" not in encoded


def test_superseded_record_is_available_only_inside_its_historical_interval() -> None:
    _, _, memory_features_for_example = _load_api()
    record = _record(
        "old",
        status=MemoryStatus.SUPERSEDED,
        created_seq=5,
        last_supported_seq=10,
        valid_from=1_000,
        valid_to=4_000,
    )
    snapshot = _snapshot(record)

    inside = memory_features_for_example(
        _example("inside", "s1", 20, 3_000),
        snapshot,
        allowed_provenance={EventProvenance.HUMAN_PHYSICAL},
        limit=10,
    )
    outside = memory_features_for_example(
        _example("outside", "s1", 20, 5_000),
        snapshot,
        allowed_provenance={EventProvenance.HUMAN_PHYSICAL},
        limit=10,
    )

    assert [item.memory_id for item in inside] == ["old"]
    assert outside == ()


def test_zero_and_low_memory_exposure_are_ineligible() -> None:
    ExampleMemoryFeatures, audit_memory_exposure, _ = _load_api()
    config = PredictionConfigV1()
    empty = [
        ExampleMemoryFeatures(sample_id=f"s-{index}", session_id="s1", features=())
        for index in range(50)
    ]
    report = audit_memory_exposure(empty, config)
    assert report.status == "INSUFFICIENT_MEMORY_EXPOSURE"
    assert report.eligible is False
    assert report.memory_available_samples == 0

    one_session = [
        ExampleMemoryFeatures(
            sample_id=f"e-{index}",
            session_id="s1",
            features=(() if index >= 40 else (_feature("m1"), _feature("m2"))),
        )
        for index in range(50)
    ]
    report = audit_memory_exposure(one_session, config)
    assert report.memory_coverage >= 0.20
    assert report.memory_exposed_test_sessions == 1
    assert report.status == "INSUFFICIENT_MEMORY_EXPOSURE"


def _feature(memory_id: str):
    from personal_predictive_ai.prediction.memory_features import MemoryFeature

    return MemoryFeature(
        memory_id=memory_id,
        kind=MemoryKind.HABIT,
        key=f"habit.test:{memory_id}",
        value="run_tests",
        confidence=1.0,
        scope_rank=1,
    )


def test_exposure_gate_passes_only_when_all_frozen_thresholds_are_met() -> None:
    ExampleMemoryFeatures, audit_memory_exposure, _ = _load_api()
    rows = []
    for index in range(50):
        session_id = "s1" if index < 25 else "s2"
        features = (_feature("m1"), _feature("m2")) if index < 40 else ()
        rows.append(
            ExampleMemoryFeatures(
                sample_id=f"sample-{index}",
                session_id=session_id,
                features=features,
            )
        )

    report = audit_memory_exposure(rows, PredictionConfigV1())

    assert report.memory_available_samples == 40
    assert report.memory_coverage == 0.8
    assert report.memory_exposed_test_sessions == 2
    assert report.distinct_active_memory_ids == 2
    assert report.status == "PASS"
    assert report.eligible is True


def test_memory_augmented_retrieval_changes_only_neighbor_similarity() -> None:
    assert PredictionConfigV1().memory_similarity_weight == 1.0
    from personal_predictive_ai.prediction.memory_features import (
        MemoryAugmentedRetrievalPredictor,
    )
    from personal_predictive_ai.prediction.metrics import build_vocabulary
    from personal_predictive_ai.prediction.retrieval import StructuredRetrievalPredictor

    first = _example("train-a", "train", 10, 10_000).model_copy(
        update={"target_label": "a", "target_action_id": "act-a"}
    )
    second = _example("train-b", "train", 20, 20_000).model_copy(
        update={"target_label": "b", "target_action_id": "act-b"}
    )
    query = _example("query", "test", 30, 30_000).model_copy(
        update={"target_label": "b", "target_action_id": "act-q"}
    )
    train = [first, second]
    vocabulary = build_vocabulary(train)
    features = {
        first.sample_id: (_feature("m1"),),
        second.sample_id: (_feature("m2"),),
        query.sample_id: (_feature("m2"),),
    }

    base = StructuredRetrievalPredictor().fit(train, vocabulary).predict(query)
    augmented = (
        MemoryAugmentedRetrievalPredictor(memory_features_by_sample_id=features)
        .fit(train, vocabulary)
        .predict(query)
    )

    assert base.probabilities["a"] == base.probabilities["b"]
    assert augmented.probabilities["b"] > augmented.probabilities["a"]
    assert augmented.target_space is base.target_space
    assert set(augmented.probabilities) == set(base.probabilities)

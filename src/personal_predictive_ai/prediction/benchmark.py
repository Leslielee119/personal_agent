from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from personal_predictive_ai.events.models import EventProvenance
from personal_predictive_ai.memory.models import MemoryStatus
from personal_predictive_ai.memory.reconstruction import build_b2_snapshot
from personal_predictive_ai.prediction.artifacts import write_benchmark_artifacts
from personal_predictive_ai.prediction.baselines import (
    BigramPredictor,
    ContextualFrequencyPredictor,
    GlobalFrequencyPredictor,
    PersistencePredictor,
    TrigramBackoffPredictor,
    select_action_only_baseline,
)
from personal_predictive_ai.prediction.config import PredictionConfigV1
from personal_predictive_ai.prediction.dataset import build_prediction_examples
from personal_predictive_ai.prediction.decision import evaluate_gate
from personal_predictive_ai.prediction.memory_features import (
    ExampleMemoryFeatures,
    MemoryAugmentedRetrievalPredictor,
    MemoryFeature,
    audit_memory_exposure,
    memory_features_for_example,
)
from personal_predictive_ai.prediction.metrics import (
    build_vocabulary,
    score_predictions,
    transition_only_slice,
)
from personal_predictive_ai.prediction.models import (
    MetricReport,
    PredictionDistribution,
    PredictionExample,
    PredictionFold,
    TargetSpace,
)
from personal_predictive_ai.prediction.retrieval import StructuredRetrievalPredictor
from personal_predictive_ai.prediction.splits import build_session_forward_folds
from personal_predictive_ai.prediction.validity import audit_validity
from personal_predictive_ai.storage.derived_store import DerivedStore
from personal_predictive_ai.storage.memory_store import MemoryStore

PREDICTOR_VERSION = "ppa.predictors/v1"
METRIC_VERSION = "ppa.metrics/v1"


class BenchmarkSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ppa.milestone-c-summary/v1"] = "ppa.milestone-c-summary/v1"
    run_id: str = Field(min_length=1)
    source_b1_run_id: str = Field(min_length=1)
    source_b2_run_id: str | None = None
    source_high_water: int = Field(ge=0)
    target_space_statuses: dict[str, str]
    artifact_dir: str = Field(min_length=1)


def _examples_for_ids(
    ids: tuple[str, ...],
    by_id: dict[str, PredictionExample],
) -> list[PredictionExample]:
    return [by_id[sample_id] for sample_id in ids]


def _predict_all(predictor, examples: Iterable[PredictionExample]) -> list[PredictionDistribution]:
    return [predictor.predict(example) for example in examples]


def _metric_dict(report: MetricReport, *, split: str) -> dict[str, object]:
    payload = report.model_dump(mode="json")
    payload["split"] = split
    payload["predictor_version"] = PREDICTOR_VERSION
    payload["metric_version"] = METRIC_VERSION
    return payload


def _prediction_rows(
    distributions: Iterable[PredictionDistribution],
    examples: Iterable[PredictionExample],
    *,
    fold_id: str,
    split: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for example, distribution in zip(examples, distributions, strict=True):
        rows.append(
            {
                "schema_version": "ppa.baseline-prediction/v1",
                "fold_id": fold_id,
                "split": split,
                "sample_id": example.sample_id,
                "session_id": example.session_id,
                "target_space": example.target_space.value,
                "target_label": example.target_label,
                "predictor_id": distribution.predictor_id,
                "predictor_version": PREDICTOR_VERSION,
                "probabilities": distribution.probabilities,
            }
        )
    return rows


def _append_transition_metric(
    metric_rows: list[dict[str, object]],
    predictor,
    test: list[PredictionExample],
    vocabulary,
    *,
    fold_id: str,
) -> None:
    switches = transition_only_slice(test)
    if not switches:
        return
    distributions = _predict_all(predictor, switches)
    report = score_predictions(
        switches,
        distributions,
        vocabulary,
        fold_id=fold_id,
        slice_name="transition_only",
    )
    metric_rows.append(_metric_dict(report, split="test"))


def _total_variation_distance(
    train_values: Iterable[str],
    test_values: Iterable[str],
) -> float:
    train_counts = Counter(train_values)
    test_counts = Counter(test_values)
    train_total = sum(train_counts.values())
    test_total = sum(test_counts.values())
    if train_total == 0 or test_total == 0:
        return 0.0
    labels = set(train_counts) | set(test_counts)
    return 0.5 * sum(
        abs((train_counts[label] / train_total) - (test_counts[label] / test_total))
        for label in labels
    )


def _fold_drift_diagnostic(
    *,
    fold_id: str,
    train: list[PredictionExample],
    test: list[PredictionExample],
    retrieval: StructuredRetrievalPredictor,
    active_memory_ids: set[str] | None,
    previous_active_memory_ids: set[str] | None,
) -> dict[str, object]:
    train_prefixes = {tuple(item.joint_history) for item in train}
    unseen_prefix_rate = (
        sum(tuple(item.joint_history) not in train_prefixes for item in test) / len(test)
        if test
        else 0.0
    )
    max_similarity = sum(retrieval.weights.values())
    neighbor_scores: list[float] = []
    for example in test:
        neighbors = retrieval._neighbors(example)
        raw = neighbors[0][0] if neighbors else 0.0
        neighbor_scores.append((raw / max_similarity) if max_similarity > 0.0 else 0.0)
    neighbor_mean = sum(neighbor_scores) / len(neighbor_scores) if neighbor_scores else 0.0

    if active_memory_ids is None:
        memory_count: int | None = None
        memory_change_count: int | None = None
    else:
        memory_count = len(active_memory_ids)
        memory_change_count = (
            0
            if previous_active_memory_ids is None
            else len(active_memory_ids.symmetric_difference(previous_active_memory_ids))
        )

    return {
        "fold_id": fold_id,
        "target_distribution_tv": _total_variation_distance(
            (item.target_label for item in train),
            (item.target_label for item in test),
        ),
        "application_distribution_tv": _total_variation_distance(
            (item.context.foreground_application or "__NONE__" for item in train),
            (item.context.foreground_application or "__NONE__" for item in test),
        ),
        "ngram_unseen_prefix_rate": unseen_prefix_rate,
        "retrieval_neighbor_similarity_mean": neighbor_mean,
        "active_memory_count": memory_count,
        "active_memory_change_count": memory_change_count,
    }


def _gate_status(decision, *, fail_status: str) -> str:
    if decision.passed:
        return "PASS"
    if decision.status == "INSUFFICIENT_EVALUATION_FOLDS":
        return decision.status
    return fail_status


def _validate_source_b2(
    db_path: Path,
    *,
    source_b1_run_id: str,
    source_b2_run_id: str | None,
) -> None:
    if source_b2_run_id is None:
        return
    store = MemoryStore(db_path)
    try:
        metadata = store.get_run(source_b2_run_id)
    finally:
        store.close()
    if metadata is None:
        raise ValueError(f"B2 run not found: {source_b2_run_id}")
    if metadata.source_b1_run_id != source_b1_run_id:
        raise ValueError("B2 run does not derive from the requested B1 run")


def _formal_pipeline_for_target(
    *,
    db_path: Path,
    source_b1_run_id: str,
    source_b2_run_id: str | None,
    examples: list[PredictionExample],
    folds: list[PredictionFold],
    config: PredictionConfigV1,
    prediction_rows: list[dict[str, object]],
    metric_rows: list[dict[str, object]],
) -> tuple[dict[str, object], str]:
    by_id = {example.sample_id: example for example in examples}
    gate1_candidates: list[MetricReport] = []
    gate1_references: list[MetricReport] = []
    gate2_candidates: list[MetricReport] = []
    gate2_references: list[MetricReport] = []
    memory_exposure_rows: list[ExampleMemoryFeatures] = []
    memory_fold_inputs: list[
        tuple[
            str,
            list[PredictionExample],
            list[PredictionExample],
            object,
            dict[str, tuple[MemoryFeature, ...]],
            MetricReport,
        ]
    ] = []
    drift_rows: list[dict[str, object]] = []
    independent_test_sessions: set[str] = set()
    frozen_selected_id: str | None = None
    previous_active_memory_ids: set[str] | None = None

    baseline_types = (
        GlobalFrequencyPredictor,
        PersistencePredictor,
        ContextualFrequencyPredictor,
        BigramPredictor,
        TrigramBackoffPredictor,
    )
    action_only_ids = {
        PersistencePredictor.predictor_id,
        ContextualFrequencyPredictor.predictor_id,
        BigramPredictor.predictor_id,
        TrigramBackoffPredictor.predictor_id,
    }

    for fold in folds:
        train = _examples_for_ids(fold.train_sample_ids, by_id)
        validation = _examples_for_ids(fold.validation_sample_ids, by_id)
        test = _examples_for_ids(fold.test_sample_ids, by_id)
        independent_test_sessions.update(fold.test_session_ids)
        vocabulary = build_vocabulary(train, unseen_token=config.unseen_token)

        fitted = [
            predictor_type(config).fit(train, vocabulary) for predictor_type in baseline_types
        ]
        validation_reports: list[MetricReport] = []
        for predictor in fitted:
            distributions = _predict_all(predictor, validation)
            report = score_predictions(
                validation,
                distributions,
                vocabulary,
                fold_id=fold.fold_id,
            )
            validation_reports.append(report)
            metric_rows.append(_metric_dict(report, split="validation"))

        if frozen_selected_id is None:
            frozen_selected_id = select_action_only_baseline(
                report for report in validation_reports if report.predictor_id in action_only_ids
            )

        fold_selected_report: MetricReport | None = None
        global_report: MetricReport | None = None
        for predictor in fitted:
            distributions = _predict_all(predictor, test)
            report = score_predictions(
                test,
                distributions,
                vocabulary,
                fold_id=fold.fold_id,
            )
            metric_rows.append(_metric_dict(report, split="test"))
            prediction_rows.extend(
                _prediction_rows(distributions, test, fold_id=fold.fold_id, split="test")
            )
            _append_transition_metric(
                metric_rows, predictor, test, vocabulary, fold_id=fold.fold_id
            )
            if predictor.predictor_id == frozen_selected_id:
                fold_selected_report = report
            if predictor.predictor_id == GlobalFrequencyPredictor.predictor_id:
                global_report = report

        if fold_selected_report is None or global_report is None:
            raise RuntimeError("frozen action-only/global baseline missing from fitted predictors")
        gate1_candidates.append(fold_selected_report)
        gate1_references.append(global_report)

        retrieval = StructuredRetrievalPredictor(config=config).fit(train, vocabulary)
        retrieval_validation = _predict_all(retrieval, validation)
        retrieval_validation_report = score_predictions(
            validation,
            retrieval_validation,
            vocabulary,
            fold_id=fold.fold_id,
        )
        metric_rows.append(_metric_dict(retrieval_validation_report, split="validation"))
        retrieval_test = _predict_all(retrieval, test)
        retrieval_test_report = score_predictions(
            test,
            retrieval_test,
            vocabulary,
            fold_id=fold.fold_id,
        )
        metric_rows.append(_metric_dict(retrieval_test_report, split="test"))
        prediction_rows.extend(
            _prediction_rows(retrieval_test, test, fold_id=fold.fold_id, split="test")
        )
        _append_transition_metric(metric_rows, retrieval, test, vocabulary, fold_id=fold.fold_id)
        gate2_candidates.append(retrieval_test_report)
        gate2_references.append(fold_selected_report)

        active_memory_ids: set[str] | None = None
        if source_b2_run_id is not None:
            snapshot = build_b2_snapshot(
                db_path,
                source_b1_run_id=source_b1_run_id,
                source_high_water=fold.train_high_water,
            )
            active_memory_ids = {
                record.memory_id
                for record in snapshot.records
                if record.status is MemoryStatus.ACTIVE
            }
            allowed_provenance = {
                EventProvenance.HUMAN_PHYSICAL,
                EventProvenance.SYSTEM,
            }
            feature_map: dict[str, tuple[MemoryFeature, ...]] = {}
            for example in [*train, *test]:
                feature_map[example.sample_id] = memory_features_for_example(
                    example,
                    snapshot,
                    allowed_provenance=allowed_provenance,
                    limit=32,
                )
            memory_exposure_rows.extend(
                ExampleMemoryFeatures(
                    sample_id=example.sample_id,
                    session_id=example.session_id,
                    features=feature_map[example.sample_id],
                )
                for example in test
            )
            memory_fold_inputs.append(
                (
                    fold.fold_id,
                    train,
                    test,
                    vocabulary,
                    feature_map,
                    retrieval_test_report,
                )
            )

        drift_rows.append(
            _fold_drift_diagnostic(
                fold_id=fold.fold_id,
                train=train,
                test=test,
                retrieval=retrieval,
                active_memory_ids=active_memory_ids,
                previous_active_memory_ids=previous_active_memory_ids,
            )
        )
        if active_memory_ids is not None:
            previous_active_memory_ids = active_memory_ids

    gate1 = evaluate_gate(
        gate1_candidates,
        gate1_references,
        independent_test_sessions=len(independent_test_sessions),
        gate_name="Gate1_SequentialPredictability",
    )
    gate2 = evaluate_gate(
        gate2_candidates,
        gate2_references,
        independent_test_sessions=len(independent_test_sessions),
        gate_name="Gate2_StateValue",
    )
    gate1_status = _gate_status(gate1, fail_status="NO_STABLE_SEQUENCE_SIGNAL")
    gate2_status = _gate_status(gate2, fail_status="NO_NONREDUNDANT_STATE_GAIN")

    result: dict[str, object] = {
        "selected_action_only_baseline": frozen_selected_id,
        "drift_diagnostics": drift_rows,
        "gate1_status": gate1_status,
        "gate1": gate1.model_dump(mode="json"),
        "gate2_status": gate2_status,
        "gate2": gate2.model_dump(mode="json"),
    }
    final_status = gate1_status if gate1_status != "PASS" else gate2_status

    if source_b2_run_id is None:
        result["gate3_status"] = "MEMORY_ABLATION_NOT_REQUESTED"
        return result, final_status

    exposure = audit_memory_exposure(memory_exposure_rows, config)
    result["memory_exposure"] = exposure.model_dump(mode="json")
    if not exposure.eligible:
        result["gate3_status"] = "INSUFFICIENT_MEMORY_EXPOSURE"
        if final_status == "PASS":
            final_status = "INSUFFICIENT_MEMORY_EXPOSURE"
        return result, final_status

    gate3_candidates: list[MetricReport] = []
    gate3_references: list[MetricReport] = []
    for fold_id, train, test, vocabulary, feature_map, retrieval_test_report in memory_fold_inputs:
        memory_predictor = MemoryAugmentedRetrievalPredictor(
            memory_features_by_sample_id=feature_map,
            config=config,
        ).fit(train, vocabulary)
        memory_test = _predict_all(memory_predictor, test)
        memory_report = score_predictions(
            test,
            memory_test,
            vocabulary,
            fold_id=fold_id,
        )
        metric_rows.append(_metric_dict(memory_report, split="test"))
        prediction_rows.extend(_prediction_rows(memory_test, test, fold_id=fold_id, split="test"))
        _append_transition_metric(metric_rows, memory_predictor, test, vocabulary, fold_id=fold_id)
        gate3_candidates.append(memory_report)
        gate3_references.append(retrieval_test_report)

    gate3 = evaluate_gate(
        gate3_candidates,
        gate3_references,
        independent_test_sessions=len(independent_test_sessions),
        gate_name="Gate3_MemoryValue",
    )
    gate3_status = _gate_status(gate3, fail_status="NO_NONREDUNDANT_MEMORY_GAIN")
    result["gate3_status"] = gate3_status
    result["gate3"] = gate3.model_dump(mode="json")
    if final_status == "PASS":
        final_status = gate3_status
    return result, final_status


def run_milestone_c(
    db_path: str | Path,
    *,
    source_b1_run_id: str,
    source_b2_run_id: str | None,
    run_id: str,
    output_root: str | Path,
    config: PredictionConfigV1 | None = None,
) -> BenchmarkSummary:
    path = Path(db_path)
    cfg = config or PredictionConfigV1()
    derived = DerivedStore(path)
    try:
        b1_run = derived.get_run(source_b1_run_id)
        if b1_run is None:
            raise ValueError(f"B1 run not found: {source_b1_run_id}")
        actions = list(derived.iter_actions(source_b1_run_id))
        snapshots = list(derived.iter_snapshots(source_b1_run_id))
        sessions = list(derived.iter_sessions(source_b1_run_id))
    finally:
        derived.close()
    _validate_source_b2(
        path,
        source_b1_run_id=source_b1_run_id,
        source_b2_run_id=source_b2_run_id,
    )

    target_spaces_manifest: dict[str, object] = {}
    validity_payload: dict[str, object] = {}
    split_payload: dict[str, object] = {}
    ablation_targets: dict[str, object] = {}
    prediction_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    target_statuses: dict[str, str] = {}

    for target_space in TargetSpace:
        examples = build_prediction_examples(
            actions,
            snapshots,
            sessions,
            target_space=target_space,
        )
        examples = [
            example.model_copy(update={"source_b1_run_id": source_b1_run_id})
            for example in examples
        ]
        folds = build_session_forward_folds(examples)
        validity = audit_validity(examples, folds, cfg)
        key = target_space.value
        target_spaces_manifest[key] = {
            "example_count": len(examples),
            "session_count": len({item.session_id for item in examples}),
            "formal_target_provenance": EventProvenance.HUMAN_PHYSICAL.value,
        }
        validity_payload[key] = validity.model_dump(mode="json")
        split_payload[key] = [fold.model_dump(mode="json") for fold in folds]

        if not validity.decision.eligible_for_formal_comparison:
            status = validity.decision.status
            target_statuses[key] = status
            ablation_targets[key] = {
                "c0_status": status,
                "model_comparison": "BLOCKED_BY_C0",
            }
            continue

        target_ablation, status = _formal_pipeline_for_target(
            db_path=path,
            source_b1_run_id=source_b1_run_id,
            source_b2_run_id=source_b2_run_id,
            examples=examples,
            folds=folds,
            config=cfg,
            prediction_rows=prediction_rows,
            metric_rows=metric_rows,
        )
        target_statuses[key] = status
        ablation_targets[key] = {
            "c0_status": "PASS",
            **target_ablation,
        }

    run_metadata = {
        "run_id": run_id,
        "source_b1_run_id": source_b1_run_id,
        "source_b2_run_id": source_b2_run_id,
        "source_high_water": b1_run.source_high_water,
        "config_version": cfg.schema_version,
        "predictor_version": PREDICTOR_VERSION,
        "metric_version": METRIC_VERSION,
    }
    dataset_manifest = {
        "schema_version": "ppa.prediction-dataset-manifest/v1",
        **run_metadata,
        "target_spaces": target_spaces_manifest,
    }
    validity_artifact = {
        "schema_version": "ppa.validity-audit-artifact/v1",
        **run_metadata,
        "targets": validity_payload,
    }
    split_manifest = {
        "schema_version": "ppa.split-manifest/v1",
        **run_metadata,
        "targets": split_payload,
    }
    ablation = {
        "schema_version": "ppa.ablation-report/v1",
        **run_metadata,
        "targets": ablation_targets,
    }
    prediction_rows.sort(
        key=lambda row: (
            str(row["target_space"]),
            str(row["fold_id"]),
            str(row["predictor_id"]),
            str(row["sample_id"]),
        )
    )
    metric_rows.sort(
        key=lambda row: (
            str(row["target_space"]),
            str(row["fold_id"]),
            str(row["split"]),
            str(row["predictor_id"]),
        )
    )
    artifact_root = write_benchmark_artifacts(
        output_root,
        run_id=run_id,
        dataset_manifest=dataset_manifest,
        validity_audit=validity_artifact,
        split_manifest=split_manifest,
        baseline_predictions=prediction_rows,
        metrics=metric_rows,
        ablation=ablation,
    )
    return BenchmarkSummary(
        run_id=run_id,
        source_b1_run_id=source_b1_run_id,
        source_b2_run_id=source_b2_run_id,
        source_high_water=b1_run.source_high_water,
        target_space_statuses=target_statuses,
        artifact_dir=str(artifact_root),
    )

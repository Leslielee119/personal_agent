from __future__ import annotations

from personal_predictive_ai.memory.ids import audit_id_for
from personal_predictive_ai.memory.models import (
    ConsolidationConfigV1,
    MemoryAuditEvent,
    MemoryCandidate,
    MemoryKind,
    MemoryRecord,
    MemoryStatus,
)
from personal_predictive_ai.memory.temporal import activate, mark_needs_revalidation


def _ratio(candidate: MemoryCandidate) -> float:
    total = candidate.support_count + candidate.contradiction_count
    return candidate.support_count / total if total else 0.0


def _failed_gates(
    candidate: MemoryCandidate,
    config: ConsolidationConfigV1,
) -> list[str]:
    failed: list[str] = []
    ratio = _ratio(candidate)
    session_count = len(set(candidate.session_ids))
    if candidate.kind is MemoryKind.FACT:
        if candidate.support_count < config.fact_min_support:
            failed.append("fact_min_support")
        if session_count < config.fact_min_sessions:
            failed.append("fact_min_sessions")
        if ratio < config.fact_min_ratio:
            failed.append("fact_min_ratio")
        return failed
    if candidate.kind is MemoryKind.HABIT:
        if candidate.support_count < config.habit_min_support:
            failed.append("habit_min_support")
        if candidate.eligible_support_count < config.habit_min_support:
            failed.append("habit_min_eligible_support")
        if session_count < config.habit_min_sessions:
            failed.append("habit_min_sessions")
        if ratio < config.habit_min_ratio:
            failed.append("habit_min_ratio")
        if candidate.eligible_human_support_count < 1:
            failed.append("habit_human_support")
        return failed
    return ["extractor_not_supported_v1"]


def _record_from_candidate(
    candidate: MemoryCandidate,
    *,
    status: MemoryStatus,
) -> MemoryRecord:
    payload = candidate.model_dump(exclude={"schema_version"})
    payload["confidence"] = _ratio(candidate)
    payload["status"] = status
    return MemoryRecord.model_validate(payload)


def _audit(
    memory_id: str,
    event_type: str,
    source_seq: int,
    reason_code: str,
    details: dict[str, object] | None = None,
) -> MemoryAuditEvent:
    return MemoryAuditEvent(
        audit_id=audit_id_for(memory_id, event_type, source_seq, reason_code),
        memory_id=memory_id,
        event_type=event_type,
        source_seq=source_seq,
        reason_code=reason_code,
        details=details or {},
    )


def consolidate(
    candidate: MemoryCandidate,
    *,
    config: ConsolidationConfigV1,
) -> tuple[MemoryRecord, list[MemoryAuditEvent]]:
    failed = _failed_gates(candidate, config)
    record = _record_from_candidate(candidate, status=MemoryStatus.CANDIDATE)
    created = _audit(
        record.memory_id,
        "memory.created",
        record.created_seq,
        "deterministic_extractor",
        {"extractor_id": record.extractor_id},
    )
    if failed:
        retained = _audit(
            record.memory_id,
            "memory.candidate_retained",
            record.last_supported_seq,
            "gates_failed",
            {"failed_gates": failed},
        )
        return record, [created, retained]

    reason = "fact_gates_passed" if record.kind is MemoryKind.FACT else "habit_gates_passed"
    active, activated = activate(
        record,
        source_seq=record.last_supported_seq,
        reason_code=reason,
    )
    return active, [created, activated]


def reassess_active(
    memory: MemoryRecord,
    candidate: MemoryCandidate,
    *,
    config: ConsolidationConfigV1,
) -> tuple[MemoryRecord, list[MemoryAuditEvent]]:
    if memory.status is not MemoryStatus.ACTIVE:
        raise ValueError("only active memory can be reassessed")
    if (
        memory.memory_id != candidate.memory_id
        or memory.kind is not candidate.kind
        or memory.scope != candidate.scope
        or memory.key != candidate.key
        or memory.value != candidate.value
    ):
        raise ValueError("candidate does not describe the active memory claim")

    refreshed = _record_from_candidate(candidate, status=MemoryStatus.ACTIVE)
    failed = _failed_gates(candidate, config)
    if not failed:
        audit = _audit(
            refreshed.memory_id,
            "memory.reassessed",
            refreshed.last_supported_seq,
            "gates_still_passed",
        )
        return refreshed, [audit]

    pending, audit = mark_needs_revalidation(
        refreshed,
        source_seq=refreshed.last_supported_seq,
        reason_code="consolidation_gates_failed",
    )
    return pending, [audit]

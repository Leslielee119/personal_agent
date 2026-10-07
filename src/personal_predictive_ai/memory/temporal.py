from __future__ import annotations

from personal_predictive_ai.memory.ids import audit_id_for, supersession_id_for
from personal_predictive_ai.memory.models import (
    MemoryAuditEvent,
    MemoryKind,
    MemoryRecord,
    MemoryStatus,
    SupersessionEdge,
)


def _audit(
    memory_id: str,
    event_type: str,
    source_seq: int,
    reason_code: str,
    *,
    ordinal: int = 0,
    details: dict[str, object] | None = None,
) -> MemoryAuditEvent:
    return MemoryAuditEvent(
        audit_id=audit_id_for(
            memory_id,
            event_type,
            source_seq,
            reason_code,
            ordinal=ordinal,
        ),
        memory_id=memory_id,
        event_type=event_type,
        source_seq=source_seq,
        reason_code=reason_code,
        details=details or {},
    )


def activate(
    memory: MemoryRecord,
    *,
    source_seq: int,
    reason_code: str,
) -> tuple[MemoryRecord, MemoryAuditEvent]:
    if memory.status is not MemoryStatus.CANDIDATE:
        raise ValueError("only candidate memory can be activated")
    updated = memory.model_copy(update={"status": MemoryStatus.ACTIVE})
    return updated, _audit(
        memory.memory_id,
        "memory.consolidated",
        source_seq,
        reason_code,
    )


def mark_needs_revalidation(
    memory: MemoryRecord,
    *,
    source_seq: int,
    reason_code: str,
) -> tuple[MemoryRecord, MemoryAuditEvent]:
    if memory.status is not MemoryStatus.ACTIVE:
        raise ValueError("only active memory can require revalidation")
    updated = memory.model_copy(update={"status": MemoryStatus.NEEDS_REVALIDATION})
    return updated, _audit(
        memory.memory_id,
        "memory.revalidation_required",
        source_seq,
        reason_code,
    )


def revalidate(
    memory: MemoryRecord,
    *,
    source_seq: int,
    reason_code: str,
) -> tuple[MemoryRecord, MemoryAuditEvent]:
    if memory.status is not MemoryStatus.NEEDS_REVALIDATION:
        raise ValueError("only memory awaiting revalidation can be revalidated")
    updated = memory.model_copy(update={"status": MemoryStatus.ACTIVE})
    return updated, _audit(
        memory.memory_id,
        "memory.revalidated",
        source_seq,
        reason_code,
    )


def invalidate(
    memory: MemoryRecord,
    *,
    source_seq: int,
    reason_code: str,
) -> tuple[MemoryRecord, MemoryAuditEvent]:
    if memory.status not in {
        MemoryStatus.CANDIDATE,
        MemoryStatus.ACTIVE,
        MemoryStatus.NEEDS_REVALIDATION,
    }:
        raise ValueError("memory status cannot transition to invalid")
    updated = memory.model_copy(update={"status": MemoryStatus.INVALID})
    return updated, _audit(
        memory.memory_id,
        "memory.invalidated",
        source_seq,
        reason_code,
    )


def supersede(
    old: MemoryRecord,
    new: MemoryRecord,
    *,
    source_seq: int,
) -> tuple[MemoryRecord, MemoryRecord, SupersessionEdge, list[MemoryAuditEvent]]:
    if old.kind is not MemoryKind.FACT or new.kind is not MemoryKind.FACT:
        raise ValueError("supersession is defined only for facts")
    if old.status is not MemoryStatus.ACTIVE or new.status is not MemoryStatus.ACTIVE:
        raise ValueError("supersession requires active old and new facts")
    if old.scope != new.scope or old.key != new.key:
        raise ValueError("supersession requires the same scope and key")
    if old.value == new.value:
        raise ValueError("supersession requires a different fact value")
    if new.valid_from < old.valid_from:
        raise ValueError("new fact validity cannot precede old fact validity")

    old_after = old.model_copy(
        update={
            "status": MemoryStatus.SUPERSEDED,
            "valid_to": new.valid_from,
        }
    )
    edge = SupersessionEdge(
        supersession_id=supersession_id_for(new.memory_id, old.memory_id, source_seq),
        new_memory_id=new.memory_id,
        old_memory_id=old.memory_id,
        created_seq=source_seq,
    )
    audits = [
        _audit(
            old.memory_id,
            "memory.superseded",
            source_seq,
            "newer_fact",
            details={"new_memory_id": new.memory_id, "supersession_id": edge.supersession_id},
        ),
        _audit(
            new.memory_id,
            "memory.supersedes",
            source_seq,
            "newer_fact",
            details={"old_memory_id": old.memory_id, "supersession_id": edge.supersession_id},
        ),
    ]
    return old_after, new, edge, audits

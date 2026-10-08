from __future__ import annotations

from personal_predictive_ai.continuity.ids import brief_id_for
from personal_predictive_ai.continuity.models import (
    ApplicabilityStatus,
    ResumeBriefRecord,
    TaskSnapshot,
)
from personal_predictive_ai.storage.continuity_store import ContinuityStore


class ResumeBriefService:
    def __init__(self, store: ContinuityStore) -> None:
        self.store = store

    def render(self, snapshot: TaskSnapshot, *, generated_at_ns: int) -> ResumeBriefRecord:
        task = self.store.get_task(snapshot.task_id)
        if task is None:
            raise KeyError(snapshot.task_id)
        attention = list(snapshot.blockers + snapshot.pending_items + snapshot.constraints)
        sections: dict[str, object] = {"current_task": snapshot.current_goal or task.title}
        if snapshot.last_position:
            sections["last_position"] = snapshot.last_position
        if snapshot.verified_result_ids:
            result_id = snapshot.verified_result_ids[-1]
            result = self.store.get_verified_result(result_id)
            if result is not None:
                applicability = snapshot.verification_applicability.get(
                    result_id, result.applicability
                )
                sections["verification"] = {
                    "check_kind": result.check_kind,
                    "outcome": result.outcome,
                    "applicability": applicability.value,
                }
                if (
                    result.outcome.lower() == "pass"
                    and applicability != ApplicabilityStatus.CURRENT
                ):
                    attention.append("上次通过，当前状态尚未复验")
        if attention:
            sections["attention"] = attention
        if snapshot.candidate_next_step:
            sections["next_step"] = snapshot.candidate_next_step
        brief = ResumeBriefRecord(
            brief_id=brief_id_for(snapshot.snapshot_id, generated_at_ns),
            snapshot_id=snapshot.snapshot_id,
            project_id=snapshot.project_id,
            workcopy_id=snapshot.workcopy_id,
            task_id=snapshot.task_id,
            created_at_ns=generated_at_ns,
            sections=sections,
            evidence_ids=snapshot.evidence_ids,
        )
        self.store.add_brief(brief)
        return brief

    def render_text(self, brief: ResumeBriefRecord) -> str:
        lines: list[str] = []
        sections = brief.sections
        if value := sections.get("current_task"):
            lines.extend(["当前任务", str(value)])
        if value := sections.get("last_position"):
            lines.extend(["", "上次停在哪里", str(value)])
        if value := sections.get("attention"):
            lines.extend(["", "需要注意"])
            lines.extend(f"• {item}" for item in value if isinstance(value, list))
        if value := sections.get("next_step"):
            lines.extend(["", "建议继续", str(value)])
        return "\n".join(lines).strip()

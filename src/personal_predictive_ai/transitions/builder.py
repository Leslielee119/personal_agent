from __future__ import annotations

from dataclasses import dataclass, field

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.events.models import CanonicalEvent, EventOrigin
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.transitions.models import Transition


@dataclass
class _PendingTransition:
    session_id: str | None
    pre_state_id: str
    action: NormalizedAction
    exogenous_event_ids: list[str] = field(default_factory=list)
    post_state_id: str | None = None
    end_seq: int = 1


class TransitionBuilder:
    def __init__(self) -> None:
        self._pending: _PendingTransition | None = None

    def observe(
        self,
        event: CanonicalEvent,
        action: NormalizedAction | None,
        pre_state: StateSnapshot,
        post_state: StateSnapshot | None,
    ) -> list[Transition]:
        emitted: list[Transition] = []
        current_session = pre_state.session_id or (post_state.session_id if post_state else None)

        if (
            self._pending is not None
            and current_session is not None
            and self._pending.session_id is not None
            and current_session != self._pending.session_id
        ):
            emitted.append(self._finalize())

        if action is not None:
            if self._pending is not None:
                self._pending.post_state_id = pre_state.state_id
                self._pending.end_seq = pre_state.monotonic_seq
                emitted.append(self._finalize())

            self._pending = _PendingTransition(
                session_id=current_session,
                pre_state_id=pre_state.state_id,
                action=action,
                post_state_id=post_state.state_id if post_state is not None else None,
                end_seq=post_state.monotonic_seq
                if post_state is not None
                else action.monotonic_seq,
            )
            return emitted

        if self._pending is not None:
            if event.origin is EventOrigin.EXOGENOUS:
                self._pending.exogenous_event_ids.append(event.event_id)
            if post_state is not None:
                self._pending.post_state_id = post_state.state_id
                self._pending.end_seq = post_state.monotonic_seq
        return emitted

    def flush(self) -> list[Transition]:
        if self._pending is None:
            return []
        return [self._finalize()]

    def _finalize(self) -> Transition:
        pending = self._pending
        assert pending is not None
        transition = Transition(
            transition_id=f"transition:{pending.action.action_id}",
            session_id=pending.session_id,
            pre_state_id=pending.pre_state_id,
            action_id=pending.action.action_id,
            exogenous_event_ids=list(pending.exogenous_event_ids),
            post_state_id=pending.post_state_id,
            actor=pending.action.actor,
            provenance=pending.action.provenance,
            start_seq=pending.action.monotonic_seq,
            end_seq=pending.end_seq,
        )
        self._pending = None
        return transition

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import TypeVar

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.events.models import EventProvenance
from personal_predictive_ai.prediction.models import (
    PredictionExample,
    StructuredContext,
    TargetSpace,
)
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.state.sessions import SessionSegment

T = TypeVar("T", NormalizedAction, StateSnapshot)


def target_label(action: NormalizedAction, target_space: TargetSpace) -> str | None:
    if target_space is TargetSpace.APPLICATION:
        return action.application
    if target_space is TargetSpace.OPERATION:
        return action.operation
    if action.application is None:
        return None
    return f"{action.application}::{action.operation}"


def _joint_label(action: NormalizedAction) -> str | None:
    if action.application is None:
        return None
    return f"{action.application}::{action.operation}"


def _unique_session_membership(
    items: Iterable[T],
    sessions: Iterable[SessionSegment],
    *,
    identity,
) -> dict[str, str]:
    ordered_items = sorted(items, key=lambda item: (item.timestamp_ns, item.monotonic_seq))
    ordered_sessions = sorted(
        sessions, key=lambda item: (item.start_ns, item.end_ns, item.session_id)
    )
    active: list[SessionSegment] = []
    session_index = 0
    result: dict[str, str] = {}

    for item in ordered_items:
        timestamp_ns = item.timestamp_ns
        while (
            session_index < len(ordered_sessions)
            and ordered_sessions[session_index].start_ns <= timestamp_ns
        ):
            active.append(ordered_sessions[session_index])
            session_index += 1
        active = [session for session in active if session.end_ns >= timestamp_ns]
        matching = [
            session for session in active if session.start_ns <= timestamp_ns <= session.end_ns
        ]
        if len(matching) == 1:
            result[identity(item)] = matching[0].session_id
    return result


def _safe_foreground_application(snapshot: StateSnapshot | None) -> str | None:
    if snapshot is None or not isinstance(snapshot.foreground_app, dict):
        return None
    name = snapshot.foreground_app.get("name")
    if isinstance(name, str) and name.strip():
        return name
    return None


def _safe_process_names(snapshot: StateSnapshot | None) -> tuple[str, ...]:
    if snapshot is None:
        return ()
    names = {
        str(process["name"])
        for process in snapshot.active_processes.values()
        if isinstance(process, dict)
        and isinstance(process.get("name"), str)
        and str(process["name"]).strip()
    }
    return tuple(sorted(names, key=str.casefold))


def _idle_bucket(snapshot: StateSnapshot | None) -> str | None:
    if snapshot is None or snapshot.idle_ns is None:
        return None
    seconds = snapshot.idle_ns / 1_000_000_000
    if seconds < 10:
        return "lt_10s"
    if seconds < 60:
        return "10s_to_60s"
    if seconds < 300:
        return "1m_to_5m"
    return "ge_5m"


def build_prediction_examples(
    actions: Iterable[NormalizedAction],
    snapshots: Iterable[StateSnapshot],
    sessions: Iterable[SessionSegment],
    *,
    target_space: TargetSpace,
) -> list[PredictionExample]:
    ordered_actions = sorted(actions, key=lambda item: item.monotonic_seq)
    session_list = list(sessions)
    action_session = _unique_session_membership(
        ordered_actions,
        session_list,
        identity=lambda item: item.action_id,
    )

    snapshot_list = list(snapshots)
    snapshot_session = _unique_session_membership(
        snapshot_list,
        session_list,
        identity=lambda item: item.state_id,
    )
    snapshots_by_session: dict[str, list[StateSnapshot]] = defaultdict(list)
    for snapshot in snapshot_list:
        session_id = snapshot_session.get(snapshot.state_id)
        if session_id is not None:
            snapshots_by_session[session_id].append(snapshot)
    for session_snapshots in snapshots_by_session.values():
        session_snapshots.sort(key=lambda item: item.monotonic_seq)

    history_by_session: dict[str, list[NormalizedAction]] = defaultdict(list)
    snapshot_position: dict[str, int] = defaultdict(int)
    latest_snapshot: dict[str, StateSnapshot | None] = {}
    examples: list[PredictionExample] = []

    for action in ordered_actions:
        session_id = action_session.get(action.action_id)
        if session_id is None:
            continue

        session_snapshots = snapshots_by_session.get(session_id, [])
        position = snapshot_position[session_id]
        current_snapshot = latest_snapshot.get(session_id)
        while (
            position < len(session_snapshots)
            and session_snapshots[position].monotonic_seq < action.monotonic_seq
        ):
            current_snapshot = session_snapshots[position]
            position += 1
        snapshot_position[session_id] = position
        latest_snapshot[session_id] = current_snapshot

        if action.provenance is not EventProvenance.HUMAN_PHYSICAL:
            continue

        prior_actions = history_by_session[session_id]
        label = target_label(action, target_space)
        if label is not None:
            history_labels = tuple(
                prior_label
                for prior in prior_actions
                if (prior_label := target_label(prior, target_space)) is not None
            )
            joint_history = tuple(
                joint for prior in prior_actions if (joint := _joint_label(prior)) is not None
            )
            context = StructuredContext(
                foreground_application=_safe_foreground_application(current_snapshot),
                previous_operation=(prior_actions[-1].operation if prior_actions else None),
                recent_joint_actions=joint_history[-3:],
                active_process_names=_safe_process_names(current_snapshot),
                recent_exogenous_event_types=(),
                exogenous_event_type_availability="UNAVAILABLE_FROM_B1_V1",
                idle_bucket=_idle_bucket(current_snapshot),
                time_of_day_bucket=None,
            )
            examples.append(
                PredictionExample(
                    sample_id=f"prediction:{target_space.value}:{action.action_id}",
                    source_b1_run_id=None,
                    target_space=target_space,
                    session_id=session_id,
                    cutoff_seq=action.monotonic_seq,
                    target_timestamp_ns=action.timestamp_ns,
                    target_action_id=action.action_id,
                    target_label=label,
                    history_labels=history_labels,
                    joint_history=joint_history,
                    pre_state_id=(
                        current_snapshot.state_id if current_snapshot is not None else None
                    ),
                    context=context,
                    eligible_memory_ids=(),
                )
            )

        prior_actions.append(action)

    return examples

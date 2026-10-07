from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from personal_predictive_ai.actions.normalize import normalize_action
from personal_predictive_ai.events.models import EventProvenance
from personal_predictive_ai.state.estimator import ExplicitStateEstimator
from personal_predictive_ai.state.sessions import SessionSegmenter
from personal_predictive_ai.storage.derived_store import DerivedStore
from personal_predictive_ai.storage.sqlite_store import EventStore
from personal_predictive_ai.transitions.builder import TransitionBuilder


def _source_version_counts(db_path: Path) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT data_json FROM canonical_events").fetchall()
    finally:
        conn.close()
    v1 = 0
    v2 = 0
    for (encoded,) in rows:
        data = json.loads(encoded)
        if data.get("schema_version", "ppa.event/v1") == "ppa.event/v1":
            v1 += 1
        else:
            v2 += 1
    return v1, v2


def derive_b1(db_path: str | Path, *, run_id: str) -> dict[str, object]:
    path = Path(db_path)
    event_store = EventStore(path)
    derived_store = DerivedStore(path)
    try:
        events = list(event_store.iter_events_by_sequence())
        source_high_water = event_store.sequence_high_water()
        v1_count, v2_count = _source_version_counts(path)

        estimator = ExplicitStateEstimator()
        segmenter = SessionSegmenter()
        builder = TransitionBuilder()

        snapshots = []
        actions = []
        sessions = []
        transitions = []
        current_state = None
        unknown_provenance_count = 0
        dropped_non_action_events = 0

        for event in events:
            if event.provenance is EventProvenance.UNKNOWN:
                unknown_provenance_count += 1

            action = normalize_action(event)
            if action is None:
                dropped_non_action_events += 1
            else:
                actions.append(action)

            pre_state = current_state
            raw_post_state = estimator.apply(event, action)
            boundary = segmenter.observe(event, raw_post_state)
            current_session_id = segmenter.current_session_id
            post_state = raw_post_state.model_copy(
                update={"session_id": current_session_id}
            )
            snapshots.append(post_state)

            if boundary is not None and boundary.closed_segment is not None:
                sessions.append(boundary.closed_segment)
                transitions.extend(builder.flush())

            if pre_state is not None:
                same_session = pre_state.session_id == current_session_id
                if action is None:
                    transitions.extend(
                        builder.observe(event, None, pre_state, post_state)
                    )
                elif boundary is None and same_session:
                    transitions.extend(
                        builder.observe(event, action, pre_state, post_state)
                    )

            current_state = post_state

        final_session = segmenter.flush()
        if final_session is not None:
            sessions.append(final_session)
        transitions.extend(builder.flush())

        derived_store.replace_run(
            run_id,
            source_high_water,
            snapshots,
            actions,
            sessions,
            transitions,
        )
        integrity = derived_store.integrity_check()
        return {
            "run_id": run_id,
            "source_event_count": len(events),
            "source_high_water": source_high_water,
            "v1_count": v1_count,
            "v2_count": v2_count,
            "unknown_provenance_count": unknown_provenance_count,
            "snapshots": len(snapshots),
            "actions": len(actions),
            "sessions": len(sessions),
            "transitions": len(transitions),
            "dropped_non_action_events": dropped_non_action_events,
            "integrity": integrity,
        }
    finally:
        derived_store.close()
        event_store.close()


def iter_b1_replay_lines(
    store: DerivedStore,
    run_id: str,
    *,
    limit: int | None = None,
) -> Iterator[str]:
    actions = {action.action_id: action for action in store.iter_actions(run_id)}
    count = 0
    for transition in store.iter_transitions(run_id):
        if limit is not None and count >= limit:
            return
        action = actions.get(transition.action_id)
        operation = action.operation if action is not None else "unknown_action"
        actor = transition.actor.name
        provenance = transition.provenance.name
        exogenous = ",".join(transition.exogenous_event_ids) or "-"
        post_state = transition.post_state_id or "?"
        session = transition.session_id or "?"
        yield (
            f"{session} | {transition.pre_state_id} -> {operation} "
            f"[{actor}/{provenance}] -> X=[{exogenous}] -> {post_state}"
        )
        count += 1

from __future__ import annotations

import importlib.util

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.events.models import EventActor, EventProvenance
from personal_predictive_ai.prediction.models import TargetSpace
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.state.sessions import SessionSegment


def _load_dataset_api():
    module_spec = importlib.util.find_spec("personal_predictive_ai.prediction.dataset")
    assert module_spec is not None, "prediction dataset module must exist"
    from personal_predictive_ai.prediction.dataset import (
        build_prediction_examples,
        target_label,
    )

    return build_prediction_examples, target_label


def _action(
    seq: int,
    ts: int,
    *,
    app: str | None = "Code.exe",
    operation: str = "key_input",
    provenance: EventProvenance = EventProvenance.HUMAN_PHYSICAL,
) -> NormalizedAction:
    actor = EventActor.HUMAN if provenance is EventProvenance.HUMAN_PHYSICAL else EventActor.AI
    return NormalizedAction(
        action_id=f"act-{seq}",
        source_event_id=f"evt-{seq}",
        timestamp_ns=ts,
        monotonic_seq=seq,
        actor=actor,
        provenance=provenance,
        application=app,
        operation=operation,
        concrete="SECRET_KEY_CONTENT",
        fine={"exact": "SECRET_KEY_CONTENT"},
        context={"window_title": "SECRET_WINDOW_TITLE"},
    )


def _snapshot(
    seq: int,
    ts: int,
    *,
    app: str = "Code.exe",
    session_id: str | None = None,
) -> StateSnapshot:
    return StateSnapshot(
        state_id=f"state-{seq}",
        source_event_id=f"state-event-{seq}",
        timestamp_ns=ts,
        monotonic_seq=seq,
        foreground_app={"name": app},
        foreground_process={"name": app, "pid": 123},
        foreground_window={"title": "SECRET_WINDOW_TITLE"},
        focused_ui_summary={"name": "SECRET_UI_TEXT", "role": "edit"},
        recent_action_ids=["raw-id"],
        active_processes={
            "123:1": {"name": app, "pid": 123},
            "456:1": {"name": "python.exe", "pid": 456},
        },
        active_exogenous_event_ids=["external-secret-id"],
        recent_visual_event_ids=["screenshot-secret-id"],
        last_activity_ns=max(0, ts - 5_000_000_000),
        idle_ns=5_000_000_000,
        session_id=session_id,
    )


def _session(name: str, start: int, end: int) -> SessionSegment:
    return SessionSegment(
        session_id=name,
        start_event_id=f"{name}-start",
        start_ns=start,
        end_event_id=f"{name}-end",
        end_ns=end,
        reason="fixture",
    )


def test_target_label_contract_is_hierarchical_and_joint_is_deterministic() -> None:
    _, target_label = _load_dataset_api()
    action = _action(2, 20, app="Code.exe", operation="save")

    assert target_label(action, TargetSpace.APPLICATION) == "Code.exe"
    assert target_label(action, TargetSpace.OPERATION) == "save"
    assert target_label(action, TargetSpace.JOINT) == "Code.exe::save"
    assert target_label(_action(3, 30, app=None), TargetSpace.APPLICATION) is None
    assert target_label(_action(3, 30, app=None), TargetSpace.JOINT) is None


def test_builder_uses_only_strictly_pre_target_state_and_strips_free_text() -> None:
    build_prediction_examples, _ = _load_dataset_api()
    actions = [_action(10, 100, app="Code.exe", operation="save")]
    snapshots = [
        _snapshot(9, 90, app="Code.exe", session_id="s1"),
        _snapshot(10, 100, app="FutureSameSeq.exe", session_id="s1"),
        _snapshot(11, 110, app="Future.exe", session_id="s1"),
    ]

    examples = build_prediction_examples(
        actions,
        snapshots,
        [_session("s1", 0, 200)],
        target_space=TargetSpace.JOINT,
    )

    assert len(examples) == 1
    example = examples[0]
    assert example.pre_state_id == "state-9"
    assert example.context.foreground_application == "Code.exe"
    assert example.context.active_process_names == ("Code.exe", "python.exe")
    assert example.context.recent_exogenous_event_types == ()
    assert example.context.exogenous_event_type_availability == "UNAVAILABLE_FROM_B1_V1"

    encoded = example.model_dump_json()
    for sentinel in (
        "SECRET_KEY_CONTENT",
        "SECRET_WINDOW_TITLE",
        "SECRET_UI_TEXT",
        "screenshot-secret-id",
        "external-secret-id",
    ):
        assert sentinel not in encoded


def test_builder_excludes_ai_executed_targets() -> None:
    build_prediction_examples, _ = _load_dataset_api()
    actions = [
        _action(2, 20, operation="save"),
        _action(3, 30, operation="run", provenance=EventProvenance.AI_EXECUTED),
    ]
    examples = build_prediction_examples(
        actions,
        [_snapshot(1, 10, session_id="s1")],
        [_session("s1", 0, 100)],
        target_space=TargetSpace.OPERATION,
    )

    assert [item.target_action_id for item in examples] == ["act-2"]


def test_first_action_in_new_session_does_not_inherit_prior_history() -> None:
    build_prediction_examples, _ = _load_dataset_api()
    actions = [
        _action(2, 20, app="Code.exe", operation="save"),
        _action(10, 220, app="chrome.exe", operation="key_input"),
    ]
    snapshots = [
        _snapshot(1, 10, app="Code.exe", session_id="s1"),
        _snapshot(9, 210, app="chrome.exe", session_id="s2"),
    ]
    sessions = [_session("s1", 0, 100), _session("s2", 200, 300)]

    examples = build_prediction_examples(
        actions,
        snapshots,
        sessions,
        target_space=TargetSpace.OPERATION,
    )

    by_action = {item.target_action_id: item for item in examples}
    second = by_action["act-10"]
    assert second.session_id == "s2"
    assert second.history_labels == ()
    assert second.joint_history == ()
    assert second.context.previous_operation is None
    assert second.context.recent_joint_actions == ()

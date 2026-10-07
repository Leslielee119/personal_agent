from pathlib import Path

from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.diagnostics.state_replay import iter_b1_replay_lines
from personal_predictive_ai.events.models import EventActor, EventProvenance
from personal_predictive_ai.state.models import StateSnapshot
from personal_predictive_ai.storage.derived_store import DerivedStore
from personal_predictive_ai.transitions.models import Transition


def test_state_replay_uses_ids_and_operation_not_sensitive_payload(tmp_path: Path) -> None:
    store = DerivedStore(tmp_path / "events.db")
    snapshots = [
        StateSnapshot(
            state_id="state-1",
            source_event_id="evt-1",
            timestamp_ns=1,
            monotonic_seq=1,
            session_id="s1",
        ),
        StateSnapshot(
            state_id="state-2",
            source_event_id="evt-2",
            timestamp_ns=2,
            monotonic_seq=2,
            session_id="s1",
        ),
    ]
    action = NormalizedAction(
        action_id="action-2",
        source_event_id="evt-2",
        timestamp_ns=2,
        monotonic_seq=2,
        actor=EventActor.HUMAN,
        provenance=EventProvenance.HUMAN_PHYSICAL,
        operation="key_input",
        concrete="secret-text",
        fine={"canonical_key_char": "secret-text"},
    )
    transition = Transition(
        transition_id="transition-2",
        session_id="s1",
        pre_state_id="state-1",
        action_id="action-2",
        exogenous_event_ids=["evt-9"],
        post_state_id="state-2",
        actor=EventActor.HUMAN,
        provenance=EventProvenance.HUMAN_PHYSICAL,
        start_seq=2,
        end_seq=2,
    )
    store.replace_run("run-1", 9, snapshots, [action], [], [transition])

    line = next(iter_b1_replay_lines(store, "run-1"))

    assert "state-1" in line
    assert "key_input" in line
    assert "HUMAN_PHYSICAL" in line
    assert "evt-9" in line
    assert "state-2" in line
    assert "secret-text" not in line
    assert "canonical_key_char" not in line
    store.close()

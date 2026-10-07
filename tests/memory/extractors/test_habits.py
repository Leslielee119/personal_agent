from personal_predictive_ai.actions.models import NormalizedAction
from personal_predictive_ai.events.models import EventActor, EventProvenance
from personal_predictive_ai.memory.extractors.habits import extract_next_operation_habits
from personal_predictive_ai.memory.models import ConsolidationConfigV1, MemoryKind
from personal_predictive_ai.state.sessions import SessionSegment


def _action(
    action_id: str,
    seq: int,
    operation: str,
    *,
    application: str | None = "Code.exe",
    provenance: EventProvenance = EventProvenance.HUMAN_PHYSICAL,
    concrete: str | None = None,
    fine: dict | None = None,
) -> NormalizedAction:
    actor = EventActor.AI if provenance is EventProvenance.AI_EXECUTED else EventActor.HUMAN
    if provenance is EventProvenance.UNKNOWN:
        actor = EventActor.UNKNOWN
    return NormalizedAction(
        action_id=action_id,
        source_event_id=f"evt-{action_id}",
        timestamp_ns=seq,
        monotonic_seq=seq,
        actor=actor,
        provenance=provenance,
        application=application,
        operation=operation,
        concrete=concrete,
        fine=fine,
    )


def _session(session_id: str, index: int) -> SessionSegment:
    return SessionSegment(
        session_id=session_id,
        start_event_id=f"start-{index}",
        start_ns=index * 100,
        end_event_id=f"end-{index}",
        end_ns=index * 100 + 99,
        reason="end_of_stream",
    )


def _mapping(actions: list[NormalizedAction], session_id: str) -> dict[str, str]:
    return {action.source_event_id: session_id for action in actions}


def test_extracts_repeated_bigrams_with_competing_next_operation() -> None:
    sessions = [_session("s1", 1), _session("s2", 2), _session("s3", 3)]
    groups = [
        [_action("a1", 1, "save"), _action("a2", 2, "run_tests")],
        [_action("a3", 3, "save"), _action("a4", 4, "run_tests")],
        [_action("a5", 5, "save"), _action("a6", 6, "open_browser")],
    ]
    actions = [item for group in groups for item in group]
    mapping = {}
    for session, group in zip(sessions, groups, strict=True):
        mapping.update(_mapping(group, session.session_id))

    candidates = extract_next_operation_habits(
        actions,
        sessions,
        config=ConsolidationConfigV1(),
        session_id_by_event_id=mapping,
    )
    by_value = {candidate.value: candidate for candidate in candidates}
    run_tests = by_value["run_tests"]
    assert run_tests.kind is MemoryKind.HABIT
    assert run_tests.key == "habit.next_operation:Code.exe:save"
    assert run_tests.scope.scope_type == "application"
    assert run_tests.scope.scope_id == "Code.exe"
    assert run_tests.support_count == 2
    assert run_tests.contradiction_count == 1
    assert run_tests.session_ids == ["s1", "s2"]
    assert run_tests.provenance_summary.human_physical_support == 2
    assert run_tests.eligible_support_count == 2
    assert run_tests.eligible_human_support_count == 2
    assert by_value["open_browser"].support_count == 1
    assert by_value["open_browser"].contradiction_count == 2


def test_missing_application_uses_global_scope_and_never_crosses_sessions() -> None:
    sessions = [_session("s1", 1), _session("s2", 2)]
    first = [_action("a1", 1, "save", application=None)]
    second = [
        _action("a2", 2, "run_tests", application=None),
        _action("a3", 3, "edit", application=None),
    ]
    actions = first + second
    mapping = {**_mapping(first, "s1"), **_mapping(second, "s2")}

    candidates = extract_next_operation_habits(
        actions,
        sessions,
        config=ConsolidationConfigV1(),
        session_id_by_event_id=mapping,
    )
    assert len(candidates) == 1
    assert candidates[0].key == "habit.next_operation:*:run_tests"
    assert candidates[0].value == "edit"
    assert candidates[0].scope.scope_type == "global"


def test_single_occurrence_stays_a_low_support_candidate() -> None:
    session = _session("s1", 1)
    actions = [_action("a1", 1, "save"), _action("a2", 2, "run_tests")]
    candidate = extract_next_operation_habits(
        actions,
        [session],
        config=ConsolidationConfigV1(),
        session_id_by_event_id=_mapping(actions, "s1"),
    )[0]
    assert candidate.support_count == 1
    assert candidate.session_ids == ["s1"]


def test_ai_executed_and_unknown_targets_do_not_increment_eligible_support() -> None:
    for provenance, field in (
        (EventProvenance.AI_EXECUTED, "ai_executed_support"),
        (EventProvenance.UNKNOWN, "unknown_support"),
    ):
        sessions = []
        actions = []
        mapping = {}
        seq = 1
        for index in range(100):
            session_id = f"s{index}"
            sessions.append(_session(session_id, index + 1))
            pair = [
                _action(f"c-{index}-{provenance.value}", seq, "save"),
                _action(
                    f"t-{index}-{provenance.value}",
                    seq + 1,
                    "run_tests",
                    provenance=provenance,
                ),
            ]
            seq += 2
            actions.extend(pair)
            mapping.update(_mapping(pair, session_id))
        candidate = extract_next_operation_habits(
            actions,
            sessions,
            config=ConsolidationConfigV1(),
            session_id_by_event_id=mapping,
        )[0]
        assert candidate.support_count == 0
        assert candidate.eligible_support_count == 0
        assert candidate.eligible_human_support_count == 0
        assert getattr(candidate.provenance_summary, field) == 100


def test_exact_key_content_is_never_copied_into_habit_claim() -> None:
    sentinel = "DO_NOT_PERSIST_EXACT_KEY_TEXT"
    session = _session("s1", 1)
    actions = [
        _action("a1", 1, "key_input", concrete=sentinel, fine={"canonical_key_char": sentinel}),
        _action("a2", 2, "save"),
    ]
    candidate = extract_next_operation_habits(
        actions,
        [session],
        config=ConsolidationConfigV1(),
        session_id_by_event_id=_mapping(actions, "s1"),
    )[0]
    encoded = candidate.model_dump_json()
    assert sentinel not in encoded
    assert candidate.key == "habit.next_operation:Code.exe:key_input"
    assert candidate.value == "save"

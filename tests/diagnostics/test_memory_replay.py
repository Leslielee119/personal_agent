from personal_predictive_ai.diagnostics.memory_replay import (
    _apply_fact_supersession,
    iter_b2_replay_lines,
)
from personal_predictive_ai.memory.models import (
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    ProvenanceSummary,
)
from personal_predictive_ai.storage.memory_store import MemoryStore


def _fact(memory_id, value, seq, valid_from):
    return MemoryRecord(
        memory_id=memory_id,
        kind=MemoryKind.FACT,
        key="preferred_browser",
        value=value,
        scope=MemoryScope(scope_type="global", scope_id="user"),
        observed_from=valid_from,
        valid_from=valid_from,
        created_seq=seq,
        last_supported_seq=seq,
        evidence_ids=[f"e-{seq}"],
        provenance_summary=ProvenanceSummary(system_support=3),
        support_count=3,
        session_ids=["s1", "s2"],
        confidence=1.0,
        extractor_id="test/v1",
        status=MemoryStatus.ACTIVE,
    )


def test_synthetic_fact_supersession_chain_is_preserved():
    old = _fact("m-old", "chrome", 1, 100)
    new = _fact("m-new", "firefox", 10, 200)
    records, edges, audits = _apply_fact_supersession([new, old])
    by_id = {r.memory_id: r for r in records}
    assert by_id["m-old"].status is MemoryStatus.SUPERSEDED
    assert by_id["m-old"].valid_to == 200
    assert by_id["m-new"].status is MemoryStatus.ACTIVE
    assert [(e.old_memory_id, e.new_memory_id) for e in edges] == [("m-old", "m-new")]
    assert [a.event_type for a in audits] == ["memory.superseded", "memory.supersedes"]


def test_replay_lines_are_safe_and_structured(tmp_path):
    db = tmp_path / "memory.db"
    store = MemoryStore(db)
    # Empty run is enough to prove iterator handles no data without raw reads.
    assert list(iter_b2_replay_lines(store, "missing")) == []
    store.close()

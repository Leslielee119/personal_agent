# Milestone B2 — Temporal Provenance Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic long-term personal memory layer on top of B1 evidence that preserves temporal validity, provenance, dependency, supersession, invalidation, historical retrieval, and auditability without introducing LLM/vector retrieval or predictive models.

**Architecture:** B2 treats Memory as a versioned derived assertion, never as raw history or a vector chunk. Canonical/B1 evidence remains immutable; deterministic extractors emit FACT/HABIT candidates, a rule-based consolidation engine promotes eligible candidates, a graph engine maintains dependency/supersession state, and a gated retrieval interface is the only supported path into future Policy/Generator context.

**Tech Stack:** Python 3.12; Pydantic 2.x; stdlib `sqlite3`, `hashlib`, `json`; existing B1 `EventStore`/`DerivedStore`; pytest; ruff. No new ML, embedding, vector-database, LLM, or cloud dependency.

**Spec:** `docs/superpowers/specs/2026-10-07-temporal-memory-provenance-design.md`

## Global Constraints

- Runtime and reconstruction remain fully local/offline.
- B2 never modifies canonical events or B1 state/action/session/transition artifacts.
- Memory is a derived assertion with evidence links; model output alone cannot become Memory truth.
- B2 implements `FACT`, `HABIT`, `PROCEDURE`, `STYLE` schema support, but V1 extractors are required only for FACT and HABIT; PROCEDURE/STYLE extraction is deferred.
- B2 does not add embeddings, vector search, RAG, LLM summarization, GRU/Transformer/SSM, action prediction, generation, or autonomous execution.
- `AI_EXECUTED` has zero default user-habit learning eligibility.
- `UNKNOWN` cannot be promoted to high-confidence user HABIT/STYLE evidence.
- `SYSTEM` may support environment FACTs but cannot alone establish user preference.
- `STRUCTURED_SHORT` exact keyboard content, secure/password values, and raw screenshot bytes must never be copied into long-lived Memory values.
- Reconstruction ordering is source-sequence based; wall-clock `now()` must not affect IDs, status, supersession, dependency propagation, or audit order.
- Derived Memory runs are replaceable/versioned and deletable without changing canonical/B1 evidence.

## Frozen V1 Consolidation Thresholds

These values are pre-registered for `ppa.memory-config/v1`. Changing them requires a new config version and reconstruction run; they are not tuned inside a run.

- FACT activation: `support_count >= 3`, evidence from at least `2 distinct B1 sessions`, support ratio `support/(support+contradiction) >= 0.80`, and no unresolved contradiction at equal/latest validity time.
- HABIT activation: `support_count >= 5`, at least `3 distinct B1 sessions`, support ratio `>= 0.70`, and at least one eligible human-origin support item.
- HABIT support eligibility: target action provenance in `{HUMAN_PHYSICAL, AI_SUGGESTED_ACCEPTED, AI_SUGGESTED_MODIFIED}`. `AI_EXECUTED`, `SYSTEM`, `EXTERNAL`, and `UNKNOWN` do not increment eligible user-habit support.
- FACT environment evidence may use `SYSTEM`; user-preference FACTs, if added later, require explicit human evidence and are not inferred in B2 V1.
- `NEEDS_REVALIDATION`, `SUPERSEDED`, and `INVALID` have zero default retrieval eligibility for current Policy/Generator context.
- A candidate that misses any gate remains `CANDIDATE`; no fallback heuristic promotes it.

## Review Focus

1. **Legacy/unknown provenance:** repeated `UNKNOWN` actions must remain diagnosable but never become an ACTIVE user HABIT.
2. **Retention bypass:** a short-lived key character present in historical B1 evidence must not appear in a persisted Memory value/audit payload.
3. **Clock regression:** backward/equal wall-clock timestamps must not reorder Memory creation, supersession, audit events, or historical reconstruction.
4. **Dependency cycle:** invalidation over a cyclic graph must terminate deterministically and visit each reachable Memory once.
5. **Historical retrieval:** a superseded FACT must be excluded from current retrieval but retrievable for an `as_of` time inside its former valid interval.

---

## Planned File Structure

```text
src/personal_predictive_ai/
  memory/
    __init__.py
    models.py              MemoryRecord, status/kind/scope, provenance summary
    ids.py                 deterministic claim/dependency/audit IDs
    eligibility.py         provenance summary + learning eligibility
    temporal.py            state transitions + validity/supersession helpers
    graph.py               dependency + cascading invalidation/revalidation
    consolidation.py       V1 gates and contradiction handling
    retrieval.py           temporal/provenance/status/scope gated retrieval
    extractors/
      __init__.py
      facts.py             deterministic foreground-application FACT candidates
      habits.py            deterministic action-operation HABIT candidates
  storage/
    migrations/003_b2_memory.sql
    memory_store.py        transactional derived-run persistence
  diagnostics/
    memory_replay.py       reconstruction, audit summary, safe replay
  cli.py                   derive-b2 / replay-b2 commands

tests/
  memory/test_models.py
  memory/test_eligibility.py
  memory/test_temporal.py
  memory/test_graph.py
  memory/test_consolidation.py
  memory/test_retrieval.py
  memory/extractors/test_facts.py
  memory/extractors/test_habits.py
  storage/test_memory_store.py
  diagnostics/test_memory_replay.py
  integration/test_b2_reconstruction.py
```

### Task 1: Memory schema, deterministic IDs, and versioned consolidation config

**Files:**
- Create: `src/personal_predictive_ai/memory/__init__.py`
- Create: `src/personal_predictive_ai/memory/models.py`
- Create: `src/personal_predictive_ai/memory/ids.py`
- Test: `tests/memory/test_models.py`

**Interfaces:**
- Produces `MemoryKind = FACT | HABIT | PROCEDURE | STYLE`.
- Produces `MemoryStatus = CANDIDATE | ACTIVE | SUPERSEDED | INVALID | NEEDS_REVALIDATION`.
- Produces `DependencyRelation = DERIVED_FROM | SUPPORTS | CONSTRAINS`.
- Produces immutable `MemoryScope(scope_type: str, scope_id: str)`.
- Produces immutable `ProvenanceSummary` with the seven counters from the spec.
- Produces immutable `MemoryCandidate` with claim identity, evidence IDs/roles, provenance summary, support/contradiction counts, distinct session IDs, confidence inputs, extractor ID, and proposed temporal fields; it has no persisted ACTIVE status yet.
- Produces immutable `MemoryRecord` fields from spec section 5 plus `session_ids: list[str]` and `config_version`.
- Produces immutable `MemoryEvidenceLink(memory_id, evidence_type, evidence_id, role)` with role `SUPPORT | CONTRADICTION`.
- Produces immutable `MemoryDependency`, `SupersessionEdge`, and `MemoryAuditEvent`.
- Produces `ConsolidationConfigV1` with the frozen thresholds above and schema/version string `ppa.memory-config/v1`.
- Produces `memory_id_for(kind, scope, key, value, extractor_id) -> str`; ID is SHA-256 over canonical JSON of claim identity only, not support-count/evidence ordering.
- Produces deterministic dependency/supersession/audit ID helpers using canonical JSON and source sequence/reason fields.

- [ ] **Step 1: Write failing model tests** for enum values, strict JSON-safe `value`, nonnegative counts/confidence bounds, valid interval (`valid_to is None or valid_to >= valid_from`), and exact frozen V1 thresholds.
- [ ] **Step 2: Write deterministic-ID tests** proving claim IDs are stable across evidence-order changes, different claim values have different IDs, and IDs do not depend on wall clock.
- [ ] **Step 3: Run** `python -m pytest tests/memory/test_models.py -v`; expect FAIL because `memory` package does not exist.
- [ ] **Step 4: Implement** the schema/config/ID interfaces only; no storage or graph behavior yet.
- [ ] **Step 5: Run** focused tests and `python -m ruff check src tests`; expect PASS.
- [ ] **Step 6: Commit** `feat: define deterministic temporal memory schema`.

### Task 2: Transactional MemoryStore and derived-run boundary

**Files:**
- Create: `src/personal_predictive_ai/storage/migrations/003_b2_memory.sql`
- Create: `src/personal_predictive_ai/storage/memory_store.py`
- Test: `tests/storage/test_memory_store.py`

**Interfaces:**
- Produces `MemoryRunMetadata(run_id, source_b1_run_id, source_high_water, extractor_version, config_version, schema_version="ppa.memory-run/v1")`.
- Produces `MemoryStore.replace_run(run_metadata, records, evidence_links, dependencies, supersessions, audit_events) -> None` in one transaction.
- Produces iterators/getters for records, evidence links, dependencies, supersessions, audit events and `delete_run(run_id)`.
- Evidence links store `evidence_type` + `evidence_id` + `role in {SUPPORT, CONTRADICTION}`; they do not use cascading FKs into canonical/B1 tables.
- Deleting a Memory run cascades only inside B2 tables.

- [ ] **Step 1: Write failing storage tests** for full round-trip, restart persistence, idempotent replace-by-run, duplicate-row rollback, SQLite integrity, and delete-run isolation.
- [ ] **Step 2: Add immutability test**: snapshot canonical event JSON and B1 derived row JSON before `replace_run/delete_run`; assert byte equality afterward.
- [ ] **Step 3: Add Review Focus privacy test** asserting a supplied sensitive fixture string never appears in any B2 table unless explicitly present in an allowed Memory value fixture.
- [ ] **Step 4: Run** `python -m pytest tests/storage/test_memory_store.py -v`; expect FAIL.
- [ ] **Step 5: Implement** migration/store with explicit table allowlists and transaction rollback.
- [ ] **Step 6: Run** focused tests, storage/B1 integration tests, SQLite integrity, and ruff; expect PASS.
- [ ] **Step 7: Commit** `feat: persist versioned temporal memory runs`.

### Task 3: Evidence provenance summary and learning eligibility

**Files:**
- Create: `src/personal_predictive_ai/memory/eligibility.py`
- Test: `tests/memory/test_eligibility.py`

**Interfaces:**
- Produces `summarize_provenance(items: Iterable[EventProvenance]) -> ProvenanceSummary`.
- Produces `habit_support_eligible(provenance: EventProvenance) -> bool` using the frozen V1 set.
- Produces `learning_eligibility(memory: MemoryRecord, target: Literal["world_state", "personal_policy", "generator_style"]) -> bool`.
- `SYSTEM FACT` may be eligible for `world_state`; `HUMAN_PHYSICAL HABIT` may be eligible for `personal_policy`; `AI_EXECUTED`/`UNKNOWN` do not make a user HABIT eligible.

- [ ] **Step 1: Write failing provenance-count tests** for all seven provenance classes and mixed evidence.
- [ ] **Step 2: Add Review Focus negative controls**: 100 `AI_EXECUTED` and 100 `UNKNOWN` repetitions still return false for personal-policy habit support.
- [ ] **Step 3: Write learning-eligibility tests** distinguishing SYSTEM FACT, HUMAN HABIT, AI_EXECUTED HABIT, UNKNOWN HABIT, and EXTERNAL FACT.
- [ ] **Step 4: Run** `python -m pytest tests/memory/test_eligibility.py -v`; expect FAIL.
- [ ] **Step 5: Implement** pure functions only; no database queries.
- [ ] **Step 6: Run** focused tests and ruff; expect PASS.
- [ ] **Step 7: Commit** `feat: enforce memory provenance eligibility`.

### Task 4: Temporal status machine and supersession semantics

**Files:**
- Create: `src/personal_predictive_ai/memory/temporal.py`
- Test: `tests/memory/test_temporal.py`

**Interfaces:**
- Produces `activate(memory, *, source_seq, reason_code) -> tuple[MemoryRecord, MemoryAuditEvent]`.
- Produces `mark_needs_revalidation(...)`, `invalidate(...)`, and `revalidate(...)` with explicit allowed source-status transitions.
- Produces `supersede(old, new, *, source_seq) -> tuple[MemoryRecord, MemoryRecord, SupersessionEdge, list[MemoryAuditEvent]]`.
- Supersession requires same `kind=FACT`, same scope/key, different value, new claim meeting ACTIVE eligibility, and sets `old.valid_to = new.valid_from`.
- Invalid transitions raise `ValueError`; no physical deletion.

- [ ] **Step 1: Write failing state-machine tests** for candidate→active, active→needs-revalidation, needs-revalidation→active/invalid, and forbidden invalid→active without explicit revalidation.
- [ ] **Step 2: Write supersession tests** proving old FACT remains stored, becomes SUPERSEDED, receives `valid_to`, new is ACTIVE, and edge/audit IDs are deterministic.
- [ ] **Step 3: Add Review Focus clock-regression test**: source sequence controls audit order even when new FACT timestamp is lower than old wall-clock timestamp.
- [ ] **Step 4: Run** `python -m pytest tests/memory/test_temporal.py -v`; expect FAIL.
- [ ] **Step 5: Implement** pure immutable transformations.
- [ ] **Step 6: Run** focused tests and ruff; expect PASS.
- [ ] **Step 7: Commit** `feat: add temporal memory state and supersession`.

### Task 5: Dependency graph and cascading invalidation/revalidation

**Files:**
- Create: `src/personal_predictive_ai/memory/graph.py`
- Test: `tests/memory/test_graph.py`

**Interfaces:**
- Produces `MemoryGraph(records, dependencies)` with deterministic lookup by ID.
- Produces `propagate_parent_change(parent_id, *, source_seq, reason_code) -> GraphUpdate` containing updated records and audit events without mutating input models.
- `DERIVED_FROM`: ACTIVE child → NEEDS_REVALIDATION.
- `SUPPORTS`: child is returned in `recompute_support_ids`; graph layer does not invent support counts.
- `CONSTRAINS`: child is returned in `scope_recheck_ids`.
- Traversal is sorted by `(created_seq, memory_id)` and uses a visited set.

- [ ] **Step 1: Write failing tests** for one-level and three-level DERIVED_FROM propagation.
- [ ] **Step 2: Write relation-specific tests** for SUPPORTS and CONSTRAINS outputs.
- [ ] **Step 3: Add Review Focus cycle test** `A→B→C→A`; assert termination, deterministic event order, and each child updated at most once.
- [ ] **Step 4: Run** `python -m pytest tests/memory/test_graph.py -v`; expect FAIL.
- [ ] **Step 5: Implement** deterministic graph traversal; dependency edges are derivation relationships only, never labeled causal.
- [ ] **Step 6: Run** focused tests and ruff; expect PASS.
- [ ] **Step 7: Commit** `feat: propagate temporal memory invalidation`.

### Task 6: Deterministic foreground-application FACT extractor

**Files:**
- Create: `src/personal_predictive_ai/memory/extractors/__init__.py`
- Create: `src/personal_predictive_ai/memory/extractors/facts.py`
- Test: `tests/memory/extractors/test_facts.py`

**Interfaces:**
- Produces `extract_foreground_application_facts(events, snapshots, *, config) -> list[MemoryCandidate]`.
- V1 extractor ID: `fact.foreground_application/v1`.
- Considers only canonical `window.foreground.current` and `window.foreground.changed` events with a nonempty `app.name`, joined to B1 snapshot/session by `source_event_id`.
- Emits global-scope claim `key="foreground_application.primary"`, `value=<app name>` for each observed value with support/contradiction/session counts; evidence links point to foreground event IDs.
- SYSTEM provenance is allowed because this is an environment-usage FACT, not a declared user preference.
- Tie-breaking is deterministic: support count descending, then first source sequence ascending, then normalized app name.

- [ ] **Step 1: Write failing extraction tests** with two sessions, repeated foreground changes, ties, missing app names, and unrelated process events.
- [ ] **Step 2: Assert** support/contradiction/session counts and deterministic candidate IDs are stable under wall-clock regression but increasing source sequence.
- [ ] **Step 3: Add privacy test** ensuring window title/secure payload/raw_ref are not copied into Memory value.
- [ ] **Step 4: Run** `python -m pytest tests/memory/extractors/test_facts.py -v`; expect FAIL.
- [ ] **Step 5: Implement** the extractor as a pure reduction over ordered evidence.
- [ ] **Step 6: Run** focused tests and ruff; expect PASS.
- [ ] **Step 7: Commit** `feat: extract deterministic application facts`.

### Task 7: Deterministic action-operation HABIT extractor

**Files:**
- Create: `src/personal_predictive_ai/memory/extractors/habits.py`
- Test: `tests/memory/extractors/test_habits.py`

**Interfaces:**
- Produces `extract_next_operation_habits(actions, sessions, *, config) -> list[MemoryCandidate]`.
- V1 extractor ID: `habit.next_operation/v1`.
- Within each session, actions are ordered by `monotonic_seq`; each adjacent pair forms condition `(application-or-"*", current.operation)` and observed next operation.
- Emits claim `key="habit.next_operation:<application>:<current_operation>"`, `value=<next_operation>`, scope application when known otherwise global.
- Support count is eligible occurrences of candidate next operation; contradiction count is eligible occurrences of other next operations for the same condition.
- `AI_EXECUTED`, SYSTEM, EXTERNAL and UNKNOWN target actions never increment eligible support. They may increment diagnostic provenance summary but cannot activate a user HABIT.

- [ ] **Step 1: Write failing tests** for repeated operation bigrams across sessions, competing next operations, missing application, and session boundaries.
- [ ] **Step 2: Add negative controls**: one occurrence remains CANDIDATE; 100 AI_EXECUTED pairs do not produce eligible support; legacy UNKNOWN pairs do not produce eligible support.
- [ ] **Step 3: Add retention test** using a `key_input` action whose `concrete/fine` contain a sentinel; assert Memory key/value never contain that sentinel because extractor uses only application/operation metadata.
- [ ] **Step 4: Run** `python -m pytest tests/memory/extractors/test_habits.py -v`; expect FAIL.
- [ ] **Step 5: Implement** pure sequence aggregation with deterministic ordering and canonical claim identity.
- [ ] **Step 6: Run** focused tests and ruff; expect PASS.
- [ ] **Step 7: Commit** `feat: extract provenance-aware action habits`.

### Task 8: Consolidation, contradiction handling, and candidate activation

**Files:**
- Create: `src/personal_predictive_ai/memory/consolidation.py`
- Test: `tests/memory/test_consolidation.py`

**Interfaces:**
- Consumes `MemoryCandidate` from Task 1; extractors in Tasks 6/7 populate this shared model.
- Produces `consolidate(candidate, *, config) -> tuple[MemoryRecord, list[MemoryAuditEvent]]`.
- FACT uses V1 thresholds `3 support / 2 sessions / ratio>=0.80`.
- HABIT uses V1 thresholds `5 eligible support / 3 sessions / ratio>=0.70 / at least one eligible human support`.
- `contradiction_count` participates in ratio denominator and cannot be ignored.
- Candidates missing any criterion remain CANDIDATE with an audit reason code naming failed gates.

- [ ] **Step 1: Write failing boundary tests** immediately below/at/above every FACT and HABIT threshold.
- [ ] **Step 2: Write contradiction tests** where support count is sufficient but ratio fails, and where an ACTIVE record receives enough contradiction to require revalidation.
- [ ] **Step 3: Add provenance tests** proving AI_EXECUTED/UNKNOWN cannot satisfy the human-support gate.
- [ ] **Step 4: Run** `python -m pytest tests/memory/test_consolidation.py -v`; expect FAIL.
- [ ] **Step 5: Implement** explicit rule evaluation returning structured reason codes; no learned score.
- [ ] **Step 6: Run** focused extractor/consolidation tests and ruff; expect PASS.
- [ ] **Step 7: Commit** `feat: consolidate deterministic temporal memories`.

### Task 9: Gated retrieval, historical as-of query, and learning-use filters

**Files:**
- Create: `src/personal_predictive_ai/memory/retrieval.py`
- Test: `tests/memory/test_retrieval.py`

**Interfaces:**
- Produces `MemoryQuery(scope, as_of_ns, allowed_provenance, kinds, limit, include_historical=False)`.
- Produces `retrieve_memories(records, dependencies, query) -> list[MemoryRecord]`.
- Processing order: candidate selection → scope → temporal → status/validity → provenance → dependency consistency → deterministic rank.
- Current/default query returns ACTIVE only.
- Historical query may return SUPERSEDED when `as_of_ns` lies in its `[valid_from, valid_to)` interval.
- `NEEDS_REVALIDATION`/INVALID never enter default Policy/Generator context.
- Deterministic rank V1: exact scope before global fallback, then confidence descending, `last_supported_seq` descending, `memory_id` ascending.

- [ ] **Step 1: Write failing tests** for scope compatibility, valid interval boundaries, status filtering, provenance allowlist, kind filter, rank, and limit.
- [ ] **Step 2: Add Review Focus historical supersession test**: old FACT absent now, returned for historical as-of; new FACT not returned before its valid_from.
- [ ] **Step 3: Write dependency-consistency test** excluding ACTIVE child whose active DERIVED_FROM parent is no longer retrieval-valid.
- [ ] **Step 4: Run** `python -m pytest tests/memory/test_retrieval.py -v`; expect FAIL.
- [ ] **Step 5: Implement** pure gated retrieval; no semantic/vector candidate selection.
- [ ] **Step 6: Run** focused tests and ruff; expect PASS.
- [ ] **Step 7: Commit** `feat: add gated temporal memory retrieval`.

### Task 10: B2 reconstruction orchestration, supersession pass, and audit persistence

**Files:**
- Create: `src/personal_predictive_ai/diagnostics/memory_replay.py`
- Modify: `src/personal_predictive_ai/cli.py`
- Test: `tests/diagnostics/test_memory_replay.py`
- Test: `tests/integration/test_b2_reconstruction.py`

**Interfaces:**
- Produces `derive_b2(db_path, *, source_b1_run_id, run_id, config=ConsolidationConfigV1()) -> dict[str, object]`.
- Pipeline order: load canonical+B1 evidence by sequence → FACT/HABIT extraction → consolidate → deterministic same-key FACT supersession pass → dependency/invalidation pass → persist complete run atomically.
- Produces `iter_b2_replay_lines(store, run_id, *, limit=None)` showing memory ID/kind/key/status/support/contradiction/provenance counts and audit reason codes, never raw/sensitive payloads.
- CLI adds `ppa derive-b2 --source-b1-run-id <id> --run-id <id>` and `ppa replay-b2 --run-id <id> [--limit N]`.
- Summary includes source high-water, source B1 run, FACT/HABIT candidate/active counts, statuses, dependencies, supersessions, audit events, unknown/AI-executed support counts, config/extractor versions, and SQLite integrity.

- [ ] **Step 1: Write failing mixed integration fixture** with two+ sessions, FACT evidence, an activatable HABIT, AI_EXECUTED/UNKNOWN negative controls, equal/backward timestamps, expired raw refs, and a synthetic supersession chain.
- [ ] **Step 2: Assert byte-level canonical/B1 immutability** before/after two identical B2 derivations.
- [ ] **Step 3: Assert deterministic equality** of records/dependencies/supersession/audit sequence across repeated runs with same IDs/config.
- [ ] **Step 4: Assert privacy**: sentinel short-lived key text/raw path/secure string never appears in any persisted B2 JSON or replay line.
- [ ] **Step 5: Run** `python -m pytest tests/integration/test_b2_reconstruction.py tests/diagnostics/test_memory_replay.py -v`; expect FAIL.
- [ ] **Step 6: Implement** orchestration/CLI and safe replay using Tasks 1–9 only.
- [ ] **Step 7: Run** full pytest, ruff, `git diff --check`, and SQLite integrity; expect PASS.
- [ ] **Step 8: Commit** `test: qualify deterministic b2 memory reconstruction`.

### Task 11: Real-session qualification and project-status documentation

**Files:**
- Modify: `docs/PROJECT_VISION_AND_PROGRESS_CN.md`
- Create: `docs/milestones/MILESTONE_B2_ACCEPTANCE.md`
- Test: existing full suite plus real copied session database; no product-code files unless a failing qualification test requires a separately TDD-verified fix.

**Interfaces:**
- Qualification uses a copy of a real B1-derived database; never modifies the original capture evidence.
- Reports candidate/ACTIVE Memory examples with evidence IDs and provenance counts, not sensitive values.
- Explicitly reports when real history lacks enough session diversity to activate FACT/HABIT under frozen gates; this is a valid result, not a reason to weaken thresholds.

- [ ] **Step 1: Run B2 derivation** on a copied real B1 session DB using `ppa derive-b2`.
- [ ] **Step 2: Manually audit** at least 5 representative Memory candidates/ACTIVE records where available, tracing each to evidence IDs and status/audit reasons.
- [ ] **Step 3: Run negative diagnostics** confirming AI_EXECUTED/UNKNOWN are not mislabeled as human support and no short-lived exact input appears in B2 tables.
- [ ] **Step 4: Record measured results** in `MILESTONE_B2_ACCEPTANCE.md`; do not claim activation if the real dataset does not meet thresholds.
- [ ] **Step 5: Update project overview** with implemented B2 capabilities, open limitations, and the next Milestone C boundary.
- [ ] **Step 6: Run fresh** `python -m pytest -v`, `python -m ruff check src tests scripts`, `git diff --check`, and SQLite integrity.
- [ ] **Step 7: Commit** `docs: record milestone b2 qualification`.

## Milestone B2 Definition of Done

B2 is complete only when:

1. MemoryRecord, evidence-link, dependency, supersession, audit, and run schemas are versioned and persisted transactionally.
2. FACT and HABIT deterministic extractors work under frozen V1 gates.
3. Candidate→ACTIVE consolidation is deterministic and audit-replayable.
4. Same-key FACT supersession preserves old records and valid intervals.
5. Multi-level cascading invalidation terminates on cycles and produces deterministic state/audit updates.
6. Current and historical `as_of` retrieval obey status, time, scope, provenance, and dependency gates.
7. Learning eligibility is separate from Memory existence and blocks AI_EXECUTED/UNKNOWN from personal-policy habit use.
8. Repeated reconstruction with identical evidence/config produces identical Memory IDs, statuses, edges, and audit ordering.
9. B2 writes do not change canonical/B1 evidence byte-for-byte.
10. Privacy tests prove exact short-lived input, secure content, and raw bytes/paths are not copied into long-term Memory.
11. A copied real B1 session can be reconstructed and audited honestly, including the possibility that frozen gates leave candidates inactive due insufficient diversity.
12. Full pytest, Ruff, `git diff --check`, and SQLite integrity all pass.
13. No vector DB, embedding, LLM summarization, predictive model, generator, or autonomous executor has been introduced.

## Execution Order

Execute Tasks 1–11 sequentially. Tasks 1–5 define semantics consumed by extractors and consolidation; Tasks 6–8 create eligible candidates; Task 9 freezes the only supported retrieval gate; Task 10 integrates the complete deterministic reconstruction; Task 11 qualifies against real evidence and updates the project record. Do not parallelize the semantic core (Tasks 1–9) because later interfaces depend directly on earlier models and reason codes.

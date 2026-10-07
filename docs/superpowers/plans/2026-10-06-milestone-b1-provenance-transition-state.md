# Milestone B1 — Provenance, Transition, and State Reconstruction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the capture evidence into provenance-aware, replayable state transitions `(S_t, A_t, X_t, S_t+1, provenance)` without adding any learned predictor, generator, LLM, or autonomous action execution.

**Architecture:** Preserve Milestone A raw/canonical events as immutable evidence, extend new events to schema v2 with explicit actor/provenance/device/injected evidence, reconstruct explicit state incrementally, segment sessions deterministically, normalize human actions, and derive transitions into separate SQLite tables. Existing v1 rows remain readable through a conservative migration layer and are never silently relabeled as human physical input.

**Tech Stack:** Python 3.12; Pydantic 2.x; stdlib `sqlite3`; existing Milestone A EventStore/EventBus/collectors; pytest; ruff. No new ML dependency is introduced in B1.

**Spec:** `docs/superpowers/specs/2026-10-06-personal-predictive-generative-system-design.md`

## Global Constraints

- Do not begin B1 product-code changes until Milestone A's real physical mouse qualification and formal 8-hour soak are both recorded as PASS in `docs/milestones/MILESTONE_A_ACCEPTANCE.md`.
- Runtime remains fully offline; no cloud inference, telemetry, downloads, or remote logging.
- Raw capture evidence remains immutable; state, actions, sessions, and transitions are derived artifacts and may be recomputed.
- AI-generated/executed events must never be silently relabeled as human behavior.
- Existing `ppa.event/v1` rows must remain readable; uncertain legacy provenance maps to `UNKNOWN`, not `HUMAN_PHYSICAL`.
- `EventOrigin` remains for coarse endogenous/exogenous compatibility; actor/provenance becomes the authoritative learning label.
- No State neural network, GRU, Transformer/SSM, generator, verifier, suggestion UI, or action executor is added in B1.
- Exact keyboard content remains subject to Milestone A privacy/retention policy; B1 must not extend its retention lifetime.

## Review Focus

1. **Legacy v1 rows:** loading old data must upgrade in memory with `actor=UNKNOWN`, `provenance=UNKNOWN`, never infer physical-human ground truth from `origin=endogenous` alone.
2. **Injected/synthetic input:** injected evidence must never become `HUMAN_PHYSICAL`; ambiguous source is `UNKNOWN` and receives zero default learning eligibility.
3. **Simultaneous system events around a human action:** transition construction must associate bounded exogenous events deterministically without pretending they are caused by the action.
4. **Restart/session boundaries:** state/session IDs and transition ordering must remain deterministic when the runtime restarts or wall clock moves backward; monotonic sequence remains the tie-breaker.
5. **Missing context:** a human input with no UIA/window/screen evidence must still produce a valid action/transition with nullable context rather than being dropped or fabricated.

---

## Planned File Structure

```text
src/personal_predictive_ai/
  events/
    models.py                 event v2 actor/provenance/device fields
    migration.py              v1 -> v2 conservative in-memory upgrade
    ids.py                    v2 factory defaults
  collector/
    openadapt.py              HUMAN_PHYSICAL mapping for accepted native input
    process.py                SYSTEM provenance
    filesystem.py             SYSTEM provenance
    screen.py                 SYSTEM provenance
    windows_foreground.py     SYSTEM provenance
    windows_notifications.py  SYSTEM/EXTERNAL mapping only when evidence exists
  state/
    models.py                 StateSnapshot, normalized context models
    estimator.py              incremental explicit state estimator
    sessions.py               deterministic session segmentation
  actions/
    models.py                 NormalizedAction + hierarchy fields
    normalize.py              CanonicalEvent -> NormalizedAction | None
  transitions/
    models.py                 Transition record
    builder.py                streaming transition derivation
  storage/
    migrations/002_b1_derived.sql
    derived_store.py          snapshots/actions/sessions/transitions
  diagnostics/
    state_replay.py           derived-state/transition trace
  cli.py                      derive-b1 / replay-b1 commands

tests/
  events/test_provenance.py
  collector/test_provenance_mapping.py
  state/test_estimator.py
  state/test_sessions.py
  actions/test_normalize.py
  transitions/test_builder.py
  storage/test_derived_store.py
  diagnostics/test_state_replay.py
  integration/test_b1_reconstruction.py
```

## Pre-Implementation Gate: Close Milestone A qualification

- [ ] **Gate 1: Physical mouse qualification.** Run a bounded real desktop capture while the user performs at least one physical click or scroll; require a persisted `modality="mouse"` event from OpenAdapt and explicit native/UIA capability status. Injected input does not count.
- [ ] **Gate 2: Formal 8-hour soak.** Run `scripts/soak_capture.ps1` for 8 hours with whole-process-tree network/resource monitoring and record measured results in `docs/milestones/MILESTONE_A_ACCEPTANCE.md`.
- [ ] **Gate 3: Re-run Milestone A verification.** Run `python -m pytest -v`, `python -m ruff check src tests scripts`, `git diff --check`, and OS-level offline audit; all must pass before Task 1 starts.
- [ ] **Gate 4: Commit qualification-only evidence** separately from B1 product code, e.g. `test: close milestone A qualification`.

### Task 1: Canonical event v2 with conservative provenance migration

**Files:**
- Modify: `src/personal_predictive_ai/events/models.py`
- Create: `src/personal_predictive_ai/events/migration.py`
- Modify: `src/personal_predictive_ai/events/ids.py`
- Modify: `src/personal_predictive_ai/storage/sqlite_store.py`
- Test: `tests/events/test_provenance.py`

**Interfaces:**
- Produces `EventActor = HUMAN | AI | SYSTEM | EXTERNAL | UNKNOWN`.
- Produces `EventProvenance = HUMAN_PHYSICAL | AI_SUGGESTED_ACCEPTED | AI_SUGGESTED_MODIFIED | AI_EXECUTED | SYSTEM | EXTERNAL | UNKNOWN`.
- `CanonicalEvent` defaults to `schema_version="ppa.event/v2"` and adds `actor`, `provenance`, `device: dict[str, Any] | None`, and `injected: bool | None`.
- Produces `parse_canonical_event(data: Mapping[str, Any]) -> CanonicalEvent`; v1 data is upgraded in memory with `UNKNOWN/UNKNOWN`, leaving persisted JSON unchanged.
- `EventFactory.next(...)` accepts the new fields explicitly; it must not guess human provenance.

- [ ] **Step 1: Write failing tests** proving v2 round-trip, JSON safety for `device`, enum validation, and that a v1 endogenous row upgrades to `UNKNOWN/UNKNOWN` rather than `HUMAN_PHYSICAL`.
- [ ] **Step 2: Add Review Focus tests** for `injected=True + provenance=HUMAN_PHYSICAL` rejection and `AI_EXECUTED + actor=HUMAN` rejection.
- [ ] **Step 3: Run** `python -m pytest tests/events/test_provenance.py -v`; expect FAIL on missing v2 contract/parser.
- [ ] **Step 4: Implement** enums, v2 fields, cross-field validation, conservative v1 migration, and replace direct `CanonicalEvent.model_validate(json.loads(...))` calls in `EventStore` with `parse_canonical_event(...)`.
- [ ] **Step 5: Run** focused tests plus existing event/storage/privacy suites and ruff; expect PASS with existing Milestone A DB fixtures still readable.
- [ ] **Step 6: Commit** `feat: add provenance-aware event v2`.

### Task 2: Provenance mapping at collector boundaries

**Files:**
- Modify: `src/personal_predictive_ai/collector/openadapt.py`
- Modify: `src/personal_predictive_ai/collector/process.py`
- Modify: `src/personal_predictive_ai/collector/filesystem.py`
- Modify: `src/personal_predictive_ai/collector/screen.py`
- Modify: `src/personal_predictive_ai/collector/windows_foreground.py`
- Modify: `src/personal_predictive_ai/collector/windows_notifications.py`
- Test: `tests/collector/test_provenance_mapping.py`

**Interfaces:**
- OpenAdapt native keyboard/mouse events accepted after its injected-input filter map to `actor=HUMAN`, `provenance=HUMAN_PHYSICAL`, `injected=False`; `device` remains `None` unless the upstream API supplies real device identity.
- Screen/window/process/filesystem observations map to `actor=SYSTEM`, `provenance=SYSTEM`.
- Notification backend maps to `EXTERNAL` only when backend evidence identifies an external source; otherwise use `SYSTEM`/`UNKNOWN` conservatively.

- [ ] **Step 1: Write failing mapping tests** for physical key/mouse, screen snapshot, foreground change, process exit, filesystem change, and notification-with/without source evidence.
- [ ] **Step 2: Add Review Focus test** that a synthetic fixture marked injected cannot be emitted as `HUMAN_PHYSICAL`; translator must return `UNKNOWN` or reject according to upstream evidence.
- [ ] **Step 3: Run** `python -m pytest tests/collector/test_provenance_mapping.py -v`; expect FAIL.
- [ ] **Step 4: Implement** explicit provenance arguments at every collector `EventFactory.next(...)` call; do not infer actor later in the state layer.
- [ ] **Step 5: Run** all collector/privacy/runtime tests and ruff; expect PASS.
- [ ] **Step 6: Commit** `feat: preserve event actor provenance at capture boundary`.

### Task 3: Deterministic normalized action layer

**Files:**
- Create: `src/personal_predictive_ai/actions/__init__.py`
- Create: `src/personal_predictive_ai/actions/models.py`
- Create: `src/personal_predictive_ai/actions/normalize.py`
- Test: `tests/actions/test_normalize.py`

**Interfaces:**
- Produces `ActionLevel` hierarchy labels and immutable `NormalizedAction` with `action_id`, `source_event_id`, `timestamp_ns`, `monotonic_seq`, `actor`, `provenance`, `intent`, `application`, `operation`, `concrete`, `fine`, and nullable context references.
- Produces `normalize_action(event: CanonicalEvent) -> NormalizedAction | None`.
- Only human/AI action-bearing events normalize into actions; pure system observations such as `process.started` or `screen.snapshot` return `None`.

- [ ] **Step 1: Write failing tests** for keyboard, mouse click/scroll, window/application switch, and a system process event that must return `None`.
- [ ] **Step 2: Add Review Focus tests** for human input with missing UIA/window context and `UNKNOWN` provenance; action must remain valid with nullable context and preserve `UNKNOWN` rather than fabricating semantics.
- [ ] **Step 3: Run** `python -m pytest tests/actions/test_normalize.py -v`; expect FAIL.
- [ ] **Step 4: Implement** deterministic rule-based normalization only; B1 does not use an LLM or learned classifier for intent/action labeling.
- [ ] **Step 5: Run** focused tests and ruff; expect PASS.
- [ ] **Step 6: Commit** `feat: derive normalized actions from evidence`.

### Task 4: Incremental explicit state estimator

**Files:**
- Create: `src/personal_predictive_ai/state/__init__.py`
- Create: `src/personal_predictive_ai/state/models.py`
- Create: `src/personal_predictive_ai/state/estimator.py`
- Test: `tests/state/test_estimator.py`

**Interfaces:**
- Produces immutable `StateSnapshot` with `state_id`, `timestamp_ns`, `monotonic_seq`, foreground app/process/window, focused UI summary, recent action IDs, active process/job summary, active exogenous event IDs, recent raw visual references (IDs only), idle/activity fields, and `session_id`.
- Produces `ExplicitStateEstimator.apply(event: CanonicalEvent, action: NormalizedAction | None) -> StateSnapshot` and `current() -> StateSnapshot | None`.
- State uses IDs/reduced summaries, never embeds raw screenshot bytes or expired raw artifacts.

- [ ] **Step 1: Write failing tests** for foreground changes, process start/exit, keyboard activity, screen-reference update, and preservation of missing context as `None`.
- [ ] **Step 2: Add Review Focus test** for equal timestamps/backward wall clock where increasing `monotonic_seq` must still yield deterministic state progression.
- [ ] **Step 3: Run** `python -m pytest tests/state/test_estimator.py -v`; expect FAIL.
- [ ] **Step 4: Implement** pure incremental state updates with bounded recent-ID windows; no neural hidden state in B1.
- [ ] **Step 5: Run** focused tests plus event/action suites and ruff; expect PASS.
- [ ] **Step 6: Commit** `feat: reconstruct explicit personal computer state`.

### Task 5: Deterministic session segmentation

**Files:**
- Create: `src/personal_predictive_ai/state/sessions.py`
- Test: `tests/state/test_sessions.py`

**Interfaces:**
- Produces `SessionSegment(session_id, start_event_id, start_ns, end_event_id, end_ns, reason)`.
- Produces `SessionSegmenter.observe(event, state) -> SessionBoundary | None`.
- Initial deterministic rules: new session on first event, runtime restart marker when supplied by replay, or inactivity gap >= 30 minutes; wall-clock regressions alone do not create a new session.

- [ ] **Step 1: Write failing tests** for first session, 29-minute gap staying in-session, 30-minute gap creating a new session, restart marker, and backward wall clock with increasing sequence.
- [ ] **Step 2: Run** `python -m pytest tests/state/test_sessions.py -v`; expect FAIL.
- [ ] **Step 3: Implement** deterministic segmenter using event sequence for ordering and timestamp only for inactivity duration when non-negative.
- [ ] **Step 4: Run** focused tests and ruff; expect PASS.
- [ ] **Step 5: Commit** `feat: segment personal activity sessions`.

### Task 6: Transition builder `(S_t, A_t, X_t, S_t+1, provenance)`

**Files:**
- Create: `src/personal_predictive_ai/transitions/__init__.py`
- Create: `src/personal_predictive_ai/transitions/models.py`
- Create: `src/personal_predictive_ai/transitions/builder.py`
- Test: `tests/transitions/test_builder.py`

**Interfaces:**
- Produces immutable `Transition` with `transition_id`, `session_id`, `pre_state_id`, `action_id`, `exogenous_event_ids`, `post_state_id`, `actor`, `provenance`, `start_seq`, and `end_seq`.
- Produces `TransitionBuilder.observe(event, action, pre_state, post_state) -> list[Transition]` and `flush() -> list[Transition]`.
- A transition is anchored on an action-bearing event; system/exogenous events between one human action and the next are attached as `X_t` evidence, not labeled as caused by that action.

- [ ] **Step 1: Write failing tests** for `state -> human action -> process result -> next human action`, verifying the process event is attached as exogenous evidence and a transition is emitted deterministically.
- [ ] **Step 2: Add Review Focus tests** for multiple exogenous events with equal timestamps, missing post-context, session boundary flush, and AI_EXECUTED action preserving its zero-learning provenance.
- [ ] **Step 3: Run** `python -m pytest tests/transitions/test_builder.py -v`; expect FAIL.
- [ ] **Step 4: Implement** sequence-driven buffering; do not claim causal direction beyond the explicit `exogenous_event_ids` association window.
- [ ] **Step 5: Run** focused tests plus state/action suites and ruff; expect PASS.
- [ ] **Step 6: Commit** `feat: build provenance-aware state transitions`.

### Task 7: Derived artifact storage and idempotent reconstruction

**Files:**
- Create: `src/personal_predictive_ai/storage/migrations/002_b1_derived.sql`
- Create: `src/personal_predictive_ai/storage/derived_store.py`
- Test: `tests/storage/test_derived_store.py`

**Interfaces:**
- Produces `DerivedStore` with `replace_run(run_id, source_high_water, snapshots, actions, sessions, transitions)`, iterators for each artifact type, and `delete_run(run_id)`.
- Derived rows link to canonical event IDs but never rewrite/delete canonical evidence.
- Reconstruction is idempotent for a fixed `run_id + source_high_water`; a new algorithm/schema version uses a new run ID.

- [ ] **Step 1: Write failing tests** for snapshot/action/session/transition round-trip, restart persistence, duplicate reconstruction idempotence, and canonical-event immutability.
- [ ] **Step 2: Add Review Focus test** that expired/missing raw refs do not prevent reconstruction from structured evidence.
- [ ] **Step 3: Run** `python -m pytest tests/storage/test_derived_store.py -v`; expect FAIL.
- [ ] **Step 4: Implement** append/replace-by-run derived tables with explicit schema/run metadata and transaction rollback on malformed batches.
- [ ] **Step 5: Run** focused tests plus SQLite integrity check and ruff; expect PASS.
- [ ] **Step 6: Commit** `feat: persist recomputable b1 derived artifacts`.

### Task 8: Offline reconstruction pipeline, CLI, and diagnostics

**Files:**
- Create: `src/personal_predictive_ai/diagnostics/state_replay.py`
- Modify: `src/personal_predictive_ai/cli.py`
- Test: `tests/diagnostics/test_state_replay.py`
- Test: `tests/integration/test_b1_reconstruction.py`

**Interfaces:**
- Adds CLI `ppa derive-b1 --data-dir <path> --run-id <id>` that reads canonical events in deterministic order and writes derived artifacts without starting collectors.
- Adds CLI `ppa replay-b1 --data-dir <path> --run-id <id> [--limit N]` printing safe compact lines `state -> action -> exogenous -> state` with actor/provenance labels.
- Produces a machine-readable reconstruction summary: source event count/high-water, v1/v2 counts, unknown-provenance count, actions, sessions, transitions, dropped/non-action events, and integrity status.

- [ ] **Step 1: Write failing integration fixture** containing v1 legacy rows, v2 human keyboard/mouse actions, system window/process events, equal timestamps, a 30-minute session gap, unknown provenance, and an expired raw reference.
- [ ] **Step 2: Assert** canonical rows remain byte-equivalent before/after derivation, v1 rows stay `UNKNOWN`, state/session/transition counts are deterministic across two runs, and replay contains no raw bytes or secure text.
- [ ] **Step 3: Run** `python -m pytest tests/integration/test_b1_reconstruction.py tests/diagnostics/test_state_replay.py -v`; expect FAIL.
- [ ] **Step 4: Implement** reconstruction orchestration and safe replay CLI using Tasks 3–7 interfaces.
- [ ] **Step 5: Run** full automated suite and ruff; expect PASS.
- [ ] **Step 6: Run** B1 derivation against a copy of a real Milestone A session DB; inspect replay manually for coherent `S_t -> A_t -> X_t -> S_t+1` trajectories and no fabricated human labels.
- [ ] **Step 7: Commit** `test: qualify milestone b1 state reconstruction`.

## Milestone B1 Definition of Done

B1 is complete only when:

1. Milestone A physical-mouse and 8-hour soak gates are already PASS.
2. All new canonical events carry explicit actor/provenance semantics and existing v1 rows remain conservatively readable.
3. Physical-human, AI, system, external, and unknown evidence cannot silently collapse into one label.
4. Explicit state reconstruction is deterministic and replayable without raw screenshot bytes.
5. Session segmentation is deterministic under inactivity, restart, equal timestamps, and backward wall clock.
6. Every derived transition links `pre-state + normalized action + associated exogenous evidence + post-state + provenance`.
7. Derived artifacts are recomputable and never mutate canonical evidence.
8. Real-session replay is coherent enough to explain both user actions and environmental responses.
9. `python -m pytest -v`, `python -m ruff check src tests scripts`, `git diff --check`, and SQLite integrity checks pass.
10. No learned predictor, GRU, generator, LLM, verifier, suggestion UI, or autonomous executor has been added prematurely.

## Execution Order

Close Milestone A qualification first. Then execute Tasks 1–8 sequentially: event semantics are consumed by collector mapping; action normalization consumes provenance; state consumes events/actions; sessions and transitions consume state; storage consumes all derived models; reconstruction/diagnostics integrate the complete B1 pipeline. Do not parallelize Tasks 1–6 because their interfaces are intentionally coupled.

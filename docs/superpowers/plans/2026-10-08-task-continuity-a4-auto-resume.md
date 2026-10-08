# Task Continuity A4 Automatic Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add natural WorkEpisode tracking and a fail-closed automatic Resume Trigger so PersonalAgent can notice when the user returns to a registered task after a meaningful break.

**Architecture:** A4 reads the existing canonical `events.db` incrementally and writes only derived episode/trigger state to `continuity.db`. A deterministic activity resolver maps grounded desktop evidence to registered WorkCopy/Task identities; a WorkEpisode state machine separates natural work segments from capture sessions; a trigger policy decides whether re-entry warrants a Resume Brief. UI remains out of scope until A6.

**Tech Stack:** Python 3.12, Pydantic, SQLite, existing CanonicalEvent/EventStore, existing ContinuityStore and TaskSnapshot services.

**Spec:** `docs/superpowers/specs/2026-10-08-task-continuity-mvp-design.md`

## Global Constraints

- `runtime.restart` / technical `session_id` never defines a WorkEpisode boundary.
- A4 is read-only with respect to registered project files and external services.
- A4 may write only PersonalAgent-owned state in `continuity.db`.
- Automatic task resolution must fail closed on ambiguous WorkCopy/Task identity.
- Formal targets/provenance semantics remain unchanged; A4 does not reclassify AI-generated behavior as natural behavior.
- Default inactivity boundary is 30 minutes; default automatic resume gap is 120 minutes; both are configurable.
- Background filesystem activity without nearby HUMAN_PHYSICAL input cannot start/re-enter an episode.
- A4 does not add LLM interpretation, arbitrary command execution, or desktop UI.

## Review Focus

1. Two registered workcopies whose names/path hints overlap must resolve as ambiguous rather than cross-contaminate state.
2. Background build/git/filesystem churn without HUMAN_PHYSICAL activity must not create an episode or trigger.
3. `runtime.restart` during active work must continue the same natural episode.
4. Monitor restart/replay must be idempotent: persisted event high-water prevents duplicate episodes/triggers.
5. A task switch followed by return before/after the resume-gap threshold must respectively suppress/create a trigger exactly once.
6. Multiple active tasks bound to one workcopy must not be guessed; explicit selection or a unique active task is required.

---
### Task 1: WorkEpisode and ResumeTrigger persistence

**Files:**
- Modify: `src/personal_predictive_ai/continuity/models.py`
- Modify: `src/personal_predictive_ai/continuity/ids.py`
- Modify: `src/personal_predictive_ai/storage/continuity_store.py`
- Create: `src/personal_predictive_ai/storage/migrations/006_task_continuity_a4.sql`
- Create: `tests/continuity/test_episode_store.py`

**Interfaces:**
- Produces `WorkEpisodeRecord`, `ResumeTriggerRecord`, `ContinuityMonitorCursor`, and `WorkCopyTaskSelectionRecord`.
- Produces store methods for append/get/list episodes, triggers, current task selection, and the monitor event high-water cursor.

- [ ] **Step 1: Write failing persistence tests**

Assert episode/trigger/task-selection round-trip, one current selection per workcopy, project/workcopy/task foreign-key scope, cursor persistence across store reopen, and migration from an existing A1-A3 `continuity.db`.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `pytest -q tests/continuity/test_episode_store.py`
Expected: FAIL because A4 models/tables do not exist.

- [ ] **Step 3: Implement models, stable IDs, migration, and store APIs**

`WorkEpisodeRecord` includes `episode_id`, project/workcopy/task IDs, start/end/last-activity timestamps, evidence sequence range, `continuation_of`, `boundary_reason`, and confidence.

`ResumeTriggerRecord` includes trigger ID, episode/task identity, reason, created time, status (`pending/opened/dismissed`), and source episode IDs.

`WorkCopyTaskSelectionRecord` stores the user-selected current task for a workcopy with selection time; it is identity state, not inferred preference.

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Commit**

Commit: `feat: add continuity work episode persistence`
### Task 2: Deterministic registered-workcopy activity resolver

**Files:**
- Create: `src/personal_predictive_ai/continuity/activity.py`
- Modify: `src/personal_predictive_ai/storage/continuity_store.py`
- Create: `tests/continuity/test_activity_resolver.py`

**Interfaces:**
- Consumes ordered `CanonicalEvent` values and registered `WorkCopyRecord`/`TaskRecord` values.
- Produces `TaskActivityObservation | None` with task/workcopy identity, timestamp, event sequence/evidence IDs, resolution reason, and confidence.

- [ ] **Step 1: Write failing resolver tests**

Cover: filesystem event under exactly one registered root + HUMAN_PHYSICAL input within 10 seconds resolves; background filesystem-only activity does not; unique exact workcopy path/window-title hint may support resolution; overlapping/ambiguous workcopies return no observation; multiple tasks on one workcopy require explicit selection unless exactly one active task exists.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `pytest -q tests/continuity/test_activity_resolver.py`
Expected: FAIL because resolver is absent.

- [ ] **Step 3: Implement `TaskActivityResolver`**

Use canonical paths and event provenance only. Keep recent human activity as transient resolver state. Do not inspect project file contents or invoke Git/LLM. Title heuristics are supporting evidence only and must resolve to exactly one registered workcopy.

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Commit**

Commit: `feat: resolve grounded continuity task activity`

### Task 3: WorkEpisode state machine

**Files:**
- Create: `src/personal_predictive_ai/continuity/episodes.py`
- Create: `tests/continuity/test_work_episodes.py`

**Interfaces:**
- Consumes `TaskActivityObservation` in timestamp/sequence order.
- Produces persisted episode start/update/close transitions.

- [ ] **Step 1: Write failing episode-boundary tests**

Assert: same task within 30 minutes stays one episode; task/workcopy switch closes previous episode; inactivity >=30 minutes creates a new episode with `continuation_of`; technical `runtime.restart` has no direct boundary effect; builder recreation resumes the persisted open episode; explicit user end closes the active episode.

- [ ] **Step 2: Run focused tests and verify RED**

- [ ] **Step 3: Implement `WorkEpisodeBuilder.update(...)` and `end(...)`**

Episode boundary reasons are explicit enums: `first_activity`, `task_switch`, `inactivity`, `user_end`. Persist last activity and evidence sequence range on every accepted observation.

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Commit**

Commit: `feat: derive natural continuity work episodes`
### Task 4: Resume Trigger policy

**Files:**
- Create: `src/personal_predictive_ai/continuity/triggers.py`
- Create: `tests/continuity/test_resume_triggers.py`

**Interfaces:**
- Consumes newly started WorkEpisodes plus prior episode/task state.
- Produces zero or one pending `ResumeTriggerRecord` per qualifying re-entry.

- [ ] **Step 1: Write failing trigger-policy tests**

Cover: first-ever episode does not trigger; same-task re-entry after <120 minutes does not trigger; >=120 minutes does; task switch and later return uses the same rule; duplicate processing does not create duplicate trigger; missing useful task state suppresses auto-trigger.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `pytest -q tests/continuity/test_resume_triggers.py`
Expected: FAIL because policy is absent.

- [ ] **Step 3: Implement `ResumeTriggerPolicy.evaluate(...)`**

Default `resume_gap_seconds=7200` and trigger cooldown `3600` seconds. Trigger creation must be deterministic from task + current/prior episode identity, so replay is idempotent.

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Commit**

Commit: `feat: add continuity automatic resume trigger policy`
### Task 5: Incremental ContinuityMonitor over canonical events

**Files:**
- Create: `src/personal_predictive_ai/continuity/monitor.py`
- Modify: `src/personal_predictive_ai/storage/sqlite_store.py`
- Create: `tests/continuity/test_monitor.py`

**Interfaces:**
- Consumes `EventStore.iter_events_after_sequence(...)` and the persisted continuity monitor cursor.
- Composes `TaskActivityResolver`, `WorkEpisodeBuilder`, and `ResumeTriggerPolicy`.
- Produces persisted episodes/triggers and advances cursor only after successful processing.

- [ ] **Step 1: Write failing replay/idempotency tests**

Assert ordered incremental processing, crash-before-cursor-update replay safety, monitor restart without duplicate trigger, and `runtime.restart` events being ignored as natural boundaries.

- [ ] **Step 2: Run focused tests and verify RED**

- [ ] **Step 3: Add sequence-after query and implement `ContinuityMonitor.run_once()`**

Do not copy canonical events into `continuity.db`; store only IDs/sequence ranges needed as evidence references.

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Commit**

Commit: `feat: monitor canonical events for task continuity`
### Task 6: A4 CLI and trigger lifecycle

**Files:**
- Modify: `src/personal_predictive_ai/cli.py`
- Create: `tests/integration/test_continuity_a4_cli.py`

**Interfaces:**
- Adds `continuity-monitor --once|--duration`.
- Adds `continuity-select-task --task-id ID` to bind the current task for its registered workcopy.
- Adds `continuity-triggers --status pending|opened|dismissed`.
- Adds `continuity-trigger-open --trigger-id ID` and `continuity-trigger-dismiss --trigger-id ID`.
- Adds `continuity-end-task --task-id ID` for explicit WorkEpisode end.

- [ ] **Step 1: Write failing CLI tests**

Verify monitor output includes processed event high-water and new trigger count; selecting a task replaces only that workcopy's current selection; listing is task/workcopy scoped; open/dismiss transitions are valid and idempotent; explicit end closes only the selected task episode.

- [ ] **Step 2: Run focused tests and verify RED**

- [ ] **Step 3: Implement thin CLI adapters over A4 services**

No CLI command may write registered project files, run tests/builds, access network, or infer task state with an LLM.

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Commit**

Commit: `feat: expose continuity automatic resume lifecycle`
### Task 7: Frozen A4 dogfood acceptance

**Files:**
- Create: `tests/integration/test_task_continuity_a4_acceptance.py`
- Create: `docs/milestones/TASK_CONTINUITY_A4_ACCEPTANCE.md`

**Interfaces:**
- Exercises two registered workcopies/tasks against a real `events.db` + `continuity.db` pair.
- Produces the product contract A6 will consume: pending Resume Trigger -> current evidence-grounded Resume Brief.

- [ ] **Step 1: Write the frozen end-to-end acceptance test**

Create natural-looking HUMAN_PHYSICAL/window/filesystem events. Assert one workcopy starts an episode, technical restart does not split it, background-only changes do not count, task switch closes it, and return after 120 minutes creates exactly one pending trigger for the correct task.

- [ ] **Step 2: Add restart/replay and ambiguity acceptance cases**

Restart the monitor from persisted cursor and assert no duplicate trigger. Create overlapping workcopy title hints and assert no automatic resolution until unambiguous evidence appears.

- [ ] **Step 3: Write dogfood documentation**

Document how to run the monitor alongside capture, inspect pending triggers, manually open/dismiss them, tune inactivity/resume-gap thresholds, and report false-positive/false-negative trigger cases.

- [ ] **Step 4: Run full verification**

Run: `pytest -q`
Expected: all non-environmental tests pass.

Run: `ruff check .`
Expected: PASS.

Run: `git diff --check`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: qualify task continuity automatic resume trigger`

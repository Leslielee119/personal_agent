# Task Continuity A1–A3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first dogfoodable Task Continuity slice: bind a project/workcopy/task, record a first-use task note, recover a compact evidence-grounded Resume Brief, track verification applicability, correct state, inspect evidence, and perform privacy-first scoped deletion without cross-worktree contamination.

**Architecture:** Add a new `continuity` domain above the existing event/B1/B2 layers, with Pydantic domain models and deterministic IDs, a dedicated local `continuity.db` for product state, fixed read-only observation adapters, and thin CLI entry points. Canonical desktop events remain in `events.db` and are referenced rather than duplicated. A1 works entirely from explicit user declarations; A2 adds deterministic Git/workcopy evidence and materialized TaskSnapshot state; A3 adds supersession, evidence inspection, and destructive scoped deletion with non-content tombstones.

**Tech Stack:** Python 3.12, Pydantic 2, SQLite/WAL, argparse CLI, subprocess only inside fixed Git observation adapter, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-10-08-task-continuity-mvp-design.md`

## Global Constraints

- Phase A may read only registered project/workcopy state and may write only PersonalAgent-owned state, correction records, caches, and tombstones.
- Model output must never reach arbitrary command execution, project-file mutation, test/build execution, UI control, or external-service access.
- `Project / WorkCopy / Task` are separate identities; Git branch names are hints, never permanent task identity.
- `provenance`, `validity/applicability`, and `evidence scope` are separate concepts.
- A1–A3 must not require WorkEpisode or any LLM.
- Every `as_of` query may use only evidence already available at that time.
- User deletion overrides append-only history retention and must remove deleted content from derived state, historical briefs, indexes, and caches.
- Existing A/B1/B2/privacy behavior must not regress.
- Continuity-owned task text, snapshots, briefs and Git evidence live in `continuity.db`; raw canonical events remain in `events.db` and are referenced rather than copied wholesale.

## Review Focus

- Same Git repository, different worktrees/tasks: state, blockers, pending items, and verification results must remain isolated; Task 10 pins this end-to-end.
- Dirty workcopy after a historical PASS: the result must become `NEEDS_REVALIDATION`, never remain “currently passing”; Task 7 pins this.
- Ambiguous or mismatched project/workcopy/task identity: fail closed and require explicit selection instead of merging; Task 3 pins this.
- User-declared state conflicts with observed state: preserve both provenance trails and surface conflict; never silently overwrite by provenance rank; Task 7 pins this.
- Scoped deletion: deleted text must disappear from evidence, snapshots, historical briefs, and lookup results while only a content-free tombstone remains; Task 9 pins this.

## File Structure

Create `src/personal_predictive_ai/continuity/` as the product-domain package. Keep persistence in `storage/` to match existing B1/B2/E conventions and keep `cli.py` as a thin dispatcher.

- `continuity/models.py` — immutable domain models/enums for identity, evidence, field versions, snapshots, briefs, verification and deletion.
- `continuity/ids.py` — deterministic stable IDs for all continuity records.
- `continuity/registry.py` — project/workcopy/task binding and identity validation.
- `continuity/brief.py` — compact Resume Brief projection from current task state.
- `continuity/git_observer.py` — fixed read-only Git workcopy observation and code-state fingerprinting.
- `continuity/verification.py` — verified-result recording and current applicability evaluation.
- `continuity/state.py` — evidence assembly, conflict preservation and TaskSnapshot materialization.
- `continuity/corrections.py` — first-use notes, field corrections, supersession and scoped delete orchestration.
- `storage/continuity_store.py` + `storage/migrations/005_task_continuity.sql` — canonical Task Continuity persistence in `continuity.db`; canonical desktop events stay in `events.db`.
- `cli.py` — new continuity commands only; no business logic.

---
### Task 1: Continuity Domain Models and Stable IDs

**Files:**
- Create: `src/personal_predictive_ai/continuity/__init__.py`
- Create: `src/personal_predictive_ai/continuity/models.py`
- Create: `src/personal_predictive_ai/continuity/ids.py`
- Create: `tests/continuity/test_models_ids.py`

**Interfaces:**
- Produces enums `FieldProvenance={OBSERVED,USER_DECLARED,DERIVED,INFERRED,UNKNOWN}`, `ApplicabilityStatus={CURRENT,STALE,NEEDS_REVALIDATION,UNSUPPORTED}`, `EvidenceAvailability={AVAILABLE,EXPIRED_BY_TTL,USER_DELETED,INTEGRITY_INVALID}`, and `ContinuityRecordStatus={ACTIVE,SUPERSEDED,INVALID}`.
- Produces immutable models `ProjectRecord`, `WorkCopyRecord`, `TaskRecord`, `EvidenceRecord`, `TaskStateFieldVersion`, `VerifiedResultRecord`, `TaskSnapshot`, `ResumeBriefRecord`, `DeletionTombstoneRecord`.
- Produces ID functions `project_id_for(project_key)`, `workcopy_id_for(project_id, canonical_root)`, `task_id_for(project_id, workcopy_id, created_at_ns, initial_title)`, `evidence_id_for(...)`, `field_version_id_for(...)`, `snapshot_id_for(...)`, `brief_id_for(...)`, `verified_result_id_for(...)`, `deletion_id_for(...)`.

- [ ] **Step 1: Write failing model/ID tests**

Assert Pydantic `extra="forbid"`/frozen behavior, enum JSON values, strict non-empty IDs, stable IDs for identical inputs, different workcopy IDs for two roots under one project, and task IDs that do not depend on Git branch name.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `pytest tests/continuity/test_models_ids.py -q`
Expected: FAIL because `personal_predictive_ai.continuity` does not exist.

- [ ] **Step 3: Implement the exact models and ID signatures**

Use the existing SHA-256 sorted-JSON ID convention from `memory/ids.py`; use schema versions prefixed `ppa.continuity-*/v1`. `EvidenceRecord` must carry `observed_at_ns`, `available_at_ns`, `project_id`, optional `workcopy_id`/`task_id`, `scope`, `provenance`, `availability`, and JSON-safe `content`.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/continuity/test_models_ids.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

`git add src/personal_predictive_ai/continuity tests/continuity/test_models_ids.py && git commit -m "feat: add task continuity domain models"`

### Task 2: Canonical Continuity Store and Migration

**Files:**
- Create: `src/personal_predictive_ai/storage/migrations/005_task_continuity.sql`
- Create: `src/personal_predictive_ai/storage/continuity_store.py`
- Create: `tests/storage/test_continuity_store.py`

**Interfaces:**
- Consumes all models from Task 1.
- Produces `ContinuityStore(db_path)` with `add/get/iter` methods for project, workcopy, task, evidence, field version, verified result, snapshot, brief and tombstone records.
- Produces scope-aware lookups `iter_field_versions(task_id, field_name=None, as_of_ns=None)` and `iter_evidence(project_id, workcopy_id=None, task_id=None, as_of_ns=None)`.

- [ ] **Step 1: Write failing persistence tests**

Test round-trip serialization, foreign-key rejection for unknown project/workcopy/task, ordering by creation time then ID, `as_of_ns` filtering on `available_at_ns`, WAL/integrity check, and reopening the same `continuity.db` without data loss.

- [ ] **Step 2: Verify RED**

Run: `pytest tests/storage/test_continuity_store.py -q`
Expected: FAIL because migration/store do not exist.

- [ ] **Step 3: Implement migration and `ContinuityStore`**

Follow `MemoryStore`: `sqlite3.Row`, `PRAGMA foreign_keys=ON`, `journal_mode=WAL`, one migration executed in constructor, JSON model payloads plus indexed identity/scope columns. The store path is the dedicated `continuity.db`; do not copy raw canonical event payloads from `events.db` into this database.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/storage/test_continuity_store.py -q`
Expected: PASS and `integrity_check() == "ok"`.

- [ ] **Step 5: Commit**

`git add src/personal_predictive_ai/storage tests/storage/test_continuity_store.py && git commit -m "feat: persist task continuity state"`

### Task 3: A1 Project / WorkCopy / Task Registry

**Files:**
- Create: `src/personal_predictive_ai/continuity/registry.py`
- Create: `tests/continuity/test_registry.py`

**Interfaces:**
- Consumes `ContinuityStore` and Task 1 ID/model APIs.
- Produces `TaskBinding(project: ProjectRecord, workcopy: WorkCopyRecord, task: TaskRecord)`.
- Produces `ContinuityRegistry.bind(project_key: str, workcopy_root: Path, task_title: str, *, now_ns: int) -> TaskBinding`.
- Produces `ContinuityRegistry.resolve_task(task_id: str, *, expected_workcopy_root: Path | None = None) -> TaskBinding`.

- [ ] **Step 1: Write failing registry tests**

Cover: same `project_key` + two roots creates one project/two workcopies; same root can contain two different tasks; branch-like strings never become task IDs; a requested `task_id` bound to another root raises `WorkCopyMismatchError`; unknown/ambiguous selection fails closed rather than merging.

- [ ] **Step 2: Verify RED**

Run: `pytest tests/continuity/test_registry.py -q`
Expected: FAIL because registry APIs are absent.

- [ ] **Step 3: Implement registry**

Normalize roots with `Path.resolve(strict=True)` and Windows case normalization before `workcopy_id_for`. `project_key` is explicit A1 user identity, so it is the stable input to `project_id_for`; no Git remote/branch inference in A1.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/continuity/test_registry.py -q`
Expected: PASS, including the Review Focus ambiguous/mismatched identity test.

- [ ] **Step 5: Commit**

`git add src/personal_predictive_ai/continuity/registry.py tests/continuity/test_registry.py && git commit -m "feat: bind continuity project workcopy and task"`

### Task 4: A1 First-Use Task State and Compact Resume Brief

**Files:**
- Create: `src/personal_predictive_ai/continuity/state.py`
- Create: `src/personal_predictive_ai/continuity/brief.py`
- Create: `tests/continuity/test_a1_resume.py`

**Interfaces:**
- Produces `TaskStateService(store).initialize(task_id, *, current_goal: str, last_position: str, next_step: str, now_ns: int) -> TaskSnapshot`.
- Produces `TaskStateService.build(task_id: str, *, as_of_ns: int) -> TaskSnapshot`.
- Produces `ResumeBriefService(store).render(snapshot: TaskSnapshot, *, generated_at_ns: int) -> ResumeBriefRecord` and `render_text(brief) -> str`.
- Canonical field names for A1: `current_goal`, `last_position`, `candidate_next_step`; `TaskSnapshot` carries these explicitly in addition to list-valued blocker/pending/constraint fields.

- [ ] **Step 1: Write failing A1 recovery tests**

Initialize “goal / reached position / next step”, rebuild at the same `as_of`, and assert the compact brief contains exactly the available four-section vocabulary (`当前任务`, `上次停在哪里`, `需要注意`, `建议继续`) while omitting empty “需要注意”; assert every displayed statement references USER_DECLARED evidence.

- [ ] **Step 2: Add an `as_of` regression test**

Create an initial note at `t1`, a newer note at `t2`, build at `t1`, and assert no `t2` value appears. Run the file and confirm RED.

- [ ] **Step 3: Implement minimal A1 state/brief services**

Initialization writes one USER_DECLARED `EvidenceRecord` and one `TaskStateFieldVersion` per non-empty field, then materializes/persists a snapshot and brief. `build()` selects the latest non-superseded field version available by `as_of_ns`; no LLM and no WorkEpisode.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/continuity/test_a1_resume.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

`git add src/personal_predictive_ai/continuity/state.py src/personal_predictive_ai/continuity/brief.py tests/continuity/test_a1_resume.py && git commit -m "feat: add manual task resume brief"`

### Task 5: A1 CLI for Binding, First-Use Note, and Manual Resume

**Files:**
- Modify: `src/personal_predictive_ai/cli.py`
- Create: `tests/integration/test_continuity_a1_cli.py`

**Interfaces:**
- Adds `continuity-init` with required `--project-key`, `--workcopy-root`, `--task-title`; optional `--goal`, `--last-position`, `--next-step`.
- Adds `continuity-resume --task-id <id> [--format text|json]`, default `text` for dogfood use.
- Uses `ContinuityStore(settings.data_dir / "continuity.db")`; CLI never constructs canonical records directly.

- [ ] **Step 1: Write failing CLI integration tests**

Call `main()` to initialize a task in a temporary data dir; assert JSON init output returns `project_id`, `workcopy_id`, `task_id`. Resume in text mode and assert concise human-readable content; resume in JSON mode and assert evidence IDs/snapshot ID are present.

- [ ] **Step 2: Verify RED**

Run: `pytest tests/integration/test_continuity_a1_cli.py -q`
Expected: parser rejects unknown continuity commands.

- [ ] **Step 3: Add parser entries and thin dispatch functions**

Follow existing flat-command argparse style. Add `_CONTINUITY_COMMANDS` and `_run_continuity_command(args, settings)` analogous to E1 dispatch; always close the store in `finally`.

- [ ] **Step 4: Verify A1 end-to-end**

Run: `pytest tests/continuity/test_a1_resume.py tests/integration/test_continuity_a1_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

`git add src/personal_predictive_ai/cli.py tests/integration/test_continuity_a1_cli.py && git commit -m "feat: expose task continuity a1 cli"`

### Task 6: A2 Fixed Git Observation Adapter and Code-State Fingerprint

**Files:**
- Create: `src/personal_predictive_ai/continuity/git_observer.py`
- Create: `tests/continuity/test_git_observer.py`

**Interfaces:**
- Produces immutable `GitWorkCopyState` in `models.py` with `workcopy_id`, `head_commit`, `branch_hint`, `is_dirty`, `tracked_diff_digest`, `untracked_digest`, `code_state_fingerprint`, `observed_at_ns`.
- Produces `GitObserver.observe(workcopy: WorkCopyRecord, *, now_ns: int) -> GitWorkCopyState`.
- Adapter may invoke only fixed Git argv templates; no caller/model-provided subcommands.

- [ ] **Step 1: Write failing clean/dirty repository tests**

Create temporary Git repositories/worktrees, commit one file, observe clean state, then modify a tracked file and add an untracked file. Assert fingerprint changes for each relevant content change and branch hint does not affect stable workcopy/task IDs.

- [ ] **Step 2: Write the safety test**

Monkeypatch `subprocess.run` and assert every invocation starts with the fixed executable/`-C <root>` and belongs to the allowlist: `rev-parse HEAD`, `rev-parse --abbrev-ref HEAD`, `status --porcelain=v1 -z --untracked-files=all`, `diff --no-ext-diff --no-textconv --binary HEAD --`.

- [ ] **Step 3: Verify RED, then implement `GitObserver`**

For untracked entries, hash file bytes directly under the registered root in sorted relative-path order; reject paths escaping the workcopy. Compute `code_state_fingerprint` from HEAD + tracked diff digest + untracked digest.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/continuity/test_git_observer.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

`git add src/personal_predictive_ai/continuity/git_observer.py src/personal_predictive_ai/continuity/models.py tests/continuity/test_git_observer.py && git commit -m "feat: observe continuity git workcopy state"`

### Task 7: A2 Verification Applicability and Evidence-Grounded Snapshot

**Files:**
- Create: `src/personal_predictive_ai/continuity/verification.py`
- Modify: `src/personal_predictive_ai/continuity/state.py`
- Modify: `src/personal_predictive_ai/continuity/models.py`
- Create: `tests/continuity/test_a2_state.py`

**Interfaces:**
- Produces `VerificationService.record_user_declared(task_id, *, check_kind: str, outcome: str, command_or_adapter_scope: str, git_state: GitWorkCopyState, now_ns: int) -> VerifiedResultRecord`.
- Produces `VerificationService.evaluate(result: VerifiedResultRecord, current_git_state: GitWorkCopyState) -> ApplicabilityStatus`.
- Extends `TaskStateService.build(..., git_state: GitWorkCopyState | None = None)` to include current observation evidence, latest verification plus applicability, and explicit `FieldConflict` records rather than provenance-based silent overwrite.

- [ ] **Step 1: Write failing applicability tests**

Record a PASS against a clean fingerprint and assert `CURRENT`; mutate the tracked file and assert `NEEDS_REVALIDATION`; restore exact bytes and assert applicability returns to `CURRENT` only when the complete fingerprint matches.

- [ ] **Step 2: Write provenance-conflict test**

Insert overlapping USER_DECLARED and OBSERVED field versions with different values for the same singleton field. Assert both evidence references survive and the snapshot exposes a `FieldConflict`; it must not silently prefer OBSERVED or USER_DECLARED.

- [ ] **Step 3: Implement verification and A2 state integration**

Recording a user result never runs the check. Persist `command_or_adapter_scope`, outcome and evidence provenance. Define `environment_fingerprint` as stable SHA-256 over `{platform.system(), platform.release(), platform.machine(), platform.python_version()}` and bind `code_state_fingerprint` from the current `GitWorkCopyState`. Snapshot rendering may say “上次通过，当前状态尚未复验” when applicability is not current.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/continuity/test_git_observer.py tests/continuity/test_a2_state.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

`git add src/personal_predictive_ai/continuity tests/continuity/test_a2_state.py && git commit -m "feat: track continuity verification applicability"`

### Task 8: A3 Correction, Supersession, and Evidence Inspection

**Files:**
- Create: `src/personal_predictive_ai/continuity/corrections.py`
- Modify: `src/personal_predictive_ai/cli.py`
- Create: `tests/continuity/test_corrections.py`
- Create: `tests/integration/test_continuity_a3_cli.py`

**Interfaces:**
- Produces `CorrectionService.correct_scalar(task_id, field_name, value, *, now_ns) -> TaskSnapshot` for `current_goal`, `last_position`, `candidate_next_step`.
- Produces `CorrectionService.add_item(task_id, field_name, value, *, now_ns) -> TaskSnapshot` and `resolve_item(...)` for `blockers`, `pending_items`, `constraints`.
- Produces `EvidenceViewService.list_for_task(task_id, *, field_name: str | None = None, as_of_ns: int | None = None) -> list[EvidenceRecord]`.
- Adds CLI `continuity-correct` and `continuity-evidence`.

- [ ] **Step 1: Write failing correction/supersession tests**

Correct an existing goal and assert old field version remains stored but is superseded/inactive; rebuild the brief and assert only the new value is current. Add and resolve a blocker and assert it disappears from compact “需要注意” while its historical evidence remains inspectable.

- [ ] **Step 2: Write failing evidence-view tests**

Assert task evidence cannot return records from a sibling task/workcopy, `as_of` hides future evidence, and every correction has USER_DECLARED provenance.

- [ ] **Step 3: Implement services and thin CLI commands**

CLI forms: `continuity-correct --task-id ID --field FIELD --value TEXT [--action set|add|resolve]`; `continuity-evidence --task-id ID [--field FIELD]`. Reject invalid action/field combinations before writing.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/continuity/test_corrections.py tests/integration/test_continuity_a3_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

`git add src/personal_predictive_ai/continuity/corrections.py src/personal_predictive_ai/cli.py tests/continuity/test_corrections.py tests/integration/test_continuity_a3_cli.py && git commit -m "feat: add continuity correction loop"`

### Task 9: A3 Privacy-First Scoped Deletion

**Files:**
- Modify: `src/personal_predictive_ai/storage/continuity_store.py`
- Modify: `src/personal_predictive_ai/continuity/corrections.py`
- Modify: `src/personal_predictive_ai/cli.py`
- Create: `tests/continuity/test_deletion.py`
- Modify: `tests/integration/test_continuity_a3_cli.py`

**Interfaces:**
- Produces transactional store operations `delete_evidence(evidence_id, *, now_ns)`, `delete_task(task_id, *, now_ns)`, `delete_workcopy(workcopy_id, *, now_ns)`, `delete_project(project_id, *, now_ns)` returning a `DeletionTombstoneRecord` that contains no deleted user content.
- Produces `CorrectionService.forget(scope_type: Literal["evidence","task","workcopy","project"], scope_id: str, *, now_ns: int) -> DeletionTombstoneRecord`.
- Adds `continuity-forget --scope ... --id ...`.

- [ ] **Step 1: Write failing privacy deletion tests with a unique sentinel**

Persist sentinel text into evidence, a derived field, snapshot and historical brief. Delete its scope; assert all canonical/query APIs return no sentinel and only a content-free tombstone remains.

- [ ] **Step 2: Pin SQLite physical-remanence behavior**

After deletion, close the store, checkpoint/truncate WAL and inspect `continuity.db`, `continuity.db-wal` if present, and `continuity.db-shm` if present. Assert sentinel UTF-8 bytes are absent. This test owns the spec requirement that deletion beats audit retention.

- [ ] **Step 3: Implement secure deletion**

Enable `PRAGMA secure_delete=ON` for ContinuityStore; delete dependent continuity rows in one transaction, write a tombstone containing only deletion ID/scope type/time/non-content scope hash, then perform `PRAGMA wal_checkpoint(TRUNCATE)` and `VACUUM` after commit. This operation touches only `continuity.db`; canonical `events.db` retention/deletion remains governed by the existing event/privacy plane.

- [ ] **Step 4: Verify scope isolation and CLI**

Run: `pytest tests/continuity/test_deletion.py tests/integration/test_continuity_a3_cli.py -q`
Expected: PASS for evidence/task/workcopy/project scopes.

- [ ] **Step 5: Commit**

`git add src/personal_predictive_ai/storage/continuity_store.py src/personal_predictive_ai/continuity/corrections.py src/personal_predictive_ai/cli.py tests/continuity/test_deletion.py tests/integration/test_continuity_a3_cli.py && git commit -m "feat: add scoped continuity deletion"`

### Task 10: Product Integration and Frozen Cross-Worktree Acceptance Scenario

**Files:**
- Modify: `src/personal_predictive_ai/cli.py`
- Modify: `src/personal_predictive_ai/continuity/state.py`
- Create: `tests/integration/test_task_continuity_acceptance.py`
- Create: `docs/milestones/TASK_CONTINUITY_A1_A3_ACCEPTANCE.md`

**Interfaces:**
- Adds `continuity-record-result --task-id ID --check-kind KIND --outcome OUTCOME --scope TEXT`; this records a USER_DECLARED result and fingerprints current registered workcopy state without running the check.
- Upgrades `continuity-resume` to run the fixed `GitObserver`, append observation evidence, evaluate any historical VerifiedResult, rebuild the snapshot, and then render the brief.
- No command in this task may modify the registered workcopy.

- [ ] **Step 1: Write the frozen end-to-end acceptance test**

Create one Git repository with two worktrees A/B; bind both under one `project_key` to different tasks. Give A goal/blocker/result and B different values. Resume A and assert only A state appears. Resume B and assert no A goal/blocker/result appears.

- [ ] **Step 2: Extend the acceptance test for applicability and correction**

Record PASS for A, modify A without re-recording result, resume and assert “上次通过，当前状态尚未复验”/`NEEDS_REVALIDATION`. Correct A goal and assert the new brief changes immediately while B remains unchanged.

- [ ] **Step 3: Extend the acceptance test for deletion**

Add a unique sensitive note to A, generate a brief, forget the evidence scope containing that note, and assert the sentinel is absent from current/historical continuity views and storage bytes while B remains intact.

- [ ] **Step 4: Implement CLI integration and acceptance documentation**

Document exact dogfood commands, the read-only security boundary, evidence/applicability language, and the frozen acceptance scenario. Do not claim automatic resume triggering (A4) or LLM interpretation (A5).

- [ ] **Step 5: Run full verification**

Run: `pytest -q`
Expected: all non-environmental tests pass; only already-declared native-input/symlink environment skips are acceptable.
Run: `ruff check .`
Expected: PASS.
Run: `git diff --check`
Expected: PASS.

- [ ] **Step 6: Commit**

`git add src/personal_predictive_ai/cli.py src/personal_predictive_ai/continuity/state.py tests/integration/test_task_continuity_acceptance.py docs/milestones/TASK_CONTINUITY_A1_A3_ACCEPTANCE.md && git commit -m "feat: complete task continuity a1 a3 dogfood slice"`

# Milestone B2 ? Temporal Provenance Memory Acceptance

Date: 2026-10-07
Branch: `feature/milestone-b2-temporal-memory`
Scope: deterministic long-term temporal Memory over B1 evidence. No vector DB, embedding, LLM summarization, learned policy, generator, or autonomous execution.

## Overall status

**IMPLEMENTATION COMPLETE / REAL-SESSION QUALIFICATION PENDING.**

The B2 semantic/storage/reconstruction stack is implemented and passes automated deterministic/privacy qualification. The final real-user-session gate is still open because no preserved real B1-derived `events.db` exists outside deleted/temporary worktrees on this machine. Test fixture databases are explicitly not accepted as substitutes for this gate.

## Implemented capabilities

B2 now provides:

- versioned `MemoryRecord`, `MemoryCandidate`, evidence-link, dependency, supersession, audit and run schemas;
- deterministic SHA-256 claim/dependency/audit identifiers;
- frozen `ppa.memory-config/v1` consolidation thresholds;
- transactional B2 SQLite run replacement/deletion isolated from canonical/B1 evidence;
- provenance summaries and separate learning-eligibility rules;
- immutable temporal status transitions and FACT supersession;
- derivation dependency graph plus deterministic cascading revalidation with cycle protection;
- deterministic foreground-application FACT extraction;
- deterministic next-operation HABIT extraction;
- explicit contradiction evidence IDs, not only contradiction counts;
- rule-based candidate consolidation and active-memory reassessment;
- scope/time/status/provenance/dependency-gated retrieval with historical `as_of`;
- deterministic `derive-b2` and privacy-safe `replay-b2` CLI paths;
- repeatable B2 reconstruction that leaves canonical/B1 rows byte-identical.

## Frozen V1 gates

FACT becomes ACTIVE only when all hold:

- `support_count >= 3`;
- at least 2 distinct B1 sessions;
- `support / (support + contradiction) >= 0.80`;
- no failed V1 deterministic gate.

HABIT becomes ACTIVE only when all hold:

- eligible support count >= 5;
- at least 3 distinct B1 sessions;
- eligible support ratio >= 0.70;
- at least one eligible human-origin support item.

`AI_EXECUTED`, `SYSTEM`, `EXTERNAL`, and `UNKNOWN` do not increment user-habit eligible support. The gates were pre-registered before implementation and were not weakened to make qualification pass.

## Automated qualification

Latest Task 10 full-suite evidence before this document update:

- pytest: **171 passed, 1 skipped**;
- Ruff: PASS;
- `git diff --check`: PASS;
- B2 reconstruction integration: PASS;
- SQLite integrity in reconstruction fixture: `ok`;
- repeated same-run derivation produced identical persisted B2 rows;
- source canonical/B1 tables remained byte-identical;
- synthetic FACT supersession preserved the old record and closed its validity interval;
- active HABIT fixture contained 5 eligible HUMAN_PHYSICAL supports while extra AI_EXECUTED/UNKNOWN repetitions remained non-eligible;
- short-lived exact-key sentinel and raw-artifact path sentinel were absent from B2 persisted JSON and replay output.

The one skip remains the existing native physical-input smoke when no physical input occurs during its observation window; it is not a B2 test failure.

## Important execution rulings

1. **Session membership for HABIT extraction is source-linked, not wall-clock inferred.** B1 `NormalizedAction` has no session ID and wall-clock can regress, so B2 consumes `source_event_id -> session_id` from B1 snapshots.
2. **Contradictions retain evidence IDs.** A count alone could not satisfy the audit requirement to explain which evidence opposed a Memory.
3. **No dependency edges are invented in V1 reconstruction.** Graph semantics/storage exist, but no deterministic dependency extractor has been approved yet.
4. **Ambiguous FACT temporal order is not fabricated.** Supersession only closes a valid interval when the newer claim's validity start does not precede the prior claim's validity start.

## Real-session qualification

Status: **PENDING ? NO PRESERVED REAL B1 DATABASE AVAILABLE.**

A search under `E:\Experiment` excluding `.pytest-tmp` and `.worktrees` found no real `events.db`. The earlier five-minute pre-soak database was stored under the old Milestone A worktree and was removed when that worktree was cleaned after merge. Only pytest fixture databases remain.

Therefore this milestone does **not** claim that the frozen FACT/HABIT gates already produce useful ACTIVE memories on actual longitudinal user behavior. That question remains empirical.

To close the gate, collect/preserve a real B1 database in a persistent path outside Git worktrees, for example:

`E:\Experiment\personal-predictive-ai-runtime\captures\<date>\events.db`

Then, on a copy of that database:

1. ensure a B1 derived run exists;
2. run `ppa derive-b2 --source-b1-run-id <id> --run-id <id>`;
3. audit at least five representative Memory records/candidates where available;
4. trace their support/contradiction evidence IDs and provenance summaries;
5. verify no AI_EXECUTED/UNKNOWN support is mislabeled as natural user support;
6. verify no short-lived exact input appears in B2 tables;
7. record whether frozen gates yield ACTIVE FACT/HABIT records without changing thresholds.

Insufficient real session diversity is an acceptable qualification result; it is not a reason to weaken the gates.

## Relationship to Milestone A

Milestone A still has its independent physical-mouse and formal 8-hour-soak qualification gates open. B2 implementation does not retroactively close them.

## Decision

B2 code is suitable for whole-branch review as an **implementation-complete, qualification-pending** feature. Milestone C policy experiments should not treat B2 real-world usefulness as established until the real-session gate above is closed.

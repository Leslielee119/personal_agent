# Milestone B2 ? Temporal Provenance Memory Acceptance

Date: 2026-10-07
Branch: `feature/milestone-b2-temporal-memory`
Scope: deterministic long-term temporal Memory over B1 evidence. No vector DB, embedding, LLM summarization, learned policy, generator, or autonomous execution.

## Overall status

**QUALIFIED FOR B2 V1 SEMANTICS ? REAL-SESSION RECONSTRUCTION PASS; LONGITUDINAL UTILITY NOT YET ESTABLISHED.**

The B2 semantic/storage/reconstruction stack passes both automated deterministic/privacy qualification and a new persistent real-session reconstruction. The real session produced only one B1 session, so the frozen multi-session gates correctly left all Memory records as CANDIDATE. This qualifies the B2 V1 semantics and conservative gating behavior; it does not establish long-horizon personalization quality.

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

- pytest after final review fixes: **173 passed, 1 skipped**;
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

## Known V1 limitations

- The V1 foreground-application FACT extractor is a full-run frequency aggregate. It does **not** yet infer temporal change points such as ?Chrome was primary, then Firefox became primary.? The supersession state machine and persistence path are implemented and covered by synthetic deterministic tests, but automatic real-world preference migration detection is not yet implemented.
- The V1 reconstruction creates no Memory dependency edges because no deterministic dependency extractor has been approved. Dependency storage, propagation, cycle handling, and retrieval consistency are implemented for future extractors.
- B2 therefore establishes temporal/provenance semantics and safe gates; it does not yet prove that every temporal transition can be discovered automatically from user history.

## Real-session qualification

Status: **PASS for reconstruction/provenance/privacy semantics.**

A fresh real local capture was written outside Git worktrees to the persistent path:

`E:\Experiment\personal-predictive-ai-runtime\captures\2026-10-07-b2-qualification\events.db`

The capture was bounded to 60 seconds and processed fully offline by the project runtime. Measured canonical evidence:

- canonical events: **391**;
- schema: **391 v2 / 0 v1**;
- provenance: **364 HUMAN_PHYSICAL / 27 SYSTEM / 0 UNKNOWN**;
- modalities: **364 keyboard / 16 process / 10 screen / 1 window / 0 mouse**;
- structured-short events: **374**;
- SQLite integrity: **ok**.

B1 reconstruction on this real database (`real-b1-20261007`) produced:

- snapshots: **391**;
- actions: **182**;
- transitions: **182**;
- sessions: **1**;
- unknown provenance: **0**.

B2 reconstruction (`real-b2-20261007`) produced:

- FACT candidates: **1**, ACTIVE: **0**;
- HABIT candidates: **1**, ACTIVE: **0**;
- status counts: **2 CANDIDATE**;
- dependencies: **0**;
- supersessions: **0**;
- audit events: **4**;
- AI_EXECUTED support: **0**;
- UNKNOWN support: **0**;
- SQLite integrity: **ok**.

The available real Memory candidates were audited:

1. `foreground_application.primary = chrome.exe`
   - support: **1** SYSTEM foreground event;
   - sessions: **1**;
   - remained CANDIDATE because `fact_min_support` and `fact_min_sessions` failed.
2. `habit.next_operation:chrome.exe:key_input -> key_input`
   - eligible HUMAN_PHYSICAL support: **181**;
   - contradiction count: **0**;
   - sessions: **1**;
   - remained CANDIDATE solely because `habit_min_sessions` failed.

This second result is an important positive control for the frozen gate: even 181 repeated actions do not become a long-term habit when they come from only one session. Thresholds were not changed. It also exposes a modeling boundary: B1's current keyboard action normalization is coarse, so the real candidate is the low-level pattern `key_input -> key_input`, not yet a semantically rich workflow habit.

Privacy checks on the real B2 tables showed:

- no `canonical_key_char` field in persisted B2 JSON;
- no `raw_ref` / `raw/` path in persisted B2 JSON;
- replay contains only Memory IDs, structured keys/status/counts/provenance and reason codes;
- exact short-lived keyboard content was not promoted into Memory value.

Repeated reconstruction of the same real B2 run produced identical hashes:

- source canonical+B1 SHA-256 before/after: `82b4eed9936f108722e08f1cdf2e6132ea1b85a03f2288cfab654fb4fb6f6623`;
- B2 derived SHA-256 before/after: `0023e5c1b63c06c1e4a01f918b4b721489c13b420f36238959eec1f7a88dd1fc`.

Therefore real-session reconstruction is deterministic and source-immutable. The lack of ACTIVE Memory is an expected data-diversity result, not a qualification failure.

## Relationship to Milestone A

Milestone A still has its independent physical-mouse and formal 8-hour-soak qualification gates open. B2 implementation does not retroactively close them.

## Decision

B2 V1 is **qualified for deterministic temporal/provenance Memory semantics and real-session reconstruction**. Milestone C may begin simple policy baselines, but must not claim that useful long-horizon personalization is established: this real capture contained only one session and produced no ACTIVE memories under the frozen gates.

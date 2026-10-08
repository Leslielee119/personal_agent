# Milestone A — Capture Data Plane Acceptance

Date: 2026-10-06
Branch: `feature/milestone-a-capture-data-plane`
Scope: local observation/capture data plane only. No State Estimator, predictor, LLM, or action executor.

## Overall status

**QUALIFICATION PENDING — implementation complete, 5-minute pre-soak strong partial PASS, physical-mouse qualification PASS, one final gate remains open.**

Open gate:
1. the required real 8-hour soak has not yet been run.

Historical gate at the start of qualification: Milestone B was originally blocked until both were closed.

Execution ruling (2026-10-07): the user explicitly approved B1 implementation proceeding in parallel with the then-open physical-mouse and 8-hour-soak qualification work after the native mouse hook and injected-input rejection path were independently validated. The physical-mouse gate was closed by real native evidence on 2026-10-08; only the 8-hour soak remains mandatory before Milestone A may be called **fully qualified**.

## Frozen acceptance gates

Milestone A is complete only when all gates below are satisfied on the real Windows desktop:

1. automated tests and Ruff pass;
2. native OpenAdapt keyboard/mouse/UIA capture is available or records an explicit OS capability block;
3. runtime shows zero non-loopback outbound connections across the whole runtime process tree;
4. source-time privacy tests prove credential/secure-field values do not persist;
5. SQLite `PRAGMA integrity_check` returns `ok`;
6. event insertion ordering consistency is >= 99.99%;
7. replay reconstructs both endogenous user actions and exogenous environment events without reading raw artifact bytes;
8. raw artifacts obey configured TTL with zero `ttl_violations` at report time;
9. `structured_short` rows have real GC, while sequence high-water never regresses or reuses IDs after GC/restart;
10. no crash or unbounded RSS growth in the 8-hour soak;
11. idle CPU target < 2%; sustained active CPU target < 5–8% on this machine.

## Implemented data plane

The V0 data plane includes:

- canonical event schema with persisted monotonic sequence high-water across process restarts;
- deterministic source-time privacy policy and recursive sanitizer;
- fail-closed keyboard privacy: unverified keyboard text is redacted, secure UIA context redacts sibling key fields, and KeyUp never retains character content;
- exact verified keyboard evidence marked `SENSITIVE + STRUCTURED_SHORT`;
- SQLite structured event store with WAL, integrity checking, short-retention GC, and immutable long-term rows;
- TTL/size-bounded raw artifact ring;
- fault-isolated event bus;
- OpenAdapt keyboard/mouse/UIA adapter;
- event-driven screen snapshots stored only in the raw ring;
- Windows foreground-window collector;
- Windows process start/exit collector;
- filesystem watcher for explicitly configured roots with cache/build exclusions;
- Windows notification capability interface; native notification ingestion is not yet implemented and reports explicit unavailability;
- zero-network runtime guard covering TCP connect/connect_ex, UDP sendto, and explicit DNS resolver calls;
- OS-level whole-process-tree TCP audit;
- safe replay diagnostics;
- machine-readable soak health reporting and whole-process-tree CPU/RSS/network sampling.

## Fresh automated verification

Latest fresh verification on the implementation used for qualification:

- `pytest`: **75 passed, 0 failed** before the final CLI GC regression was added; the added focused CLI GC test also passes;
- `ruff check src tests scripts`: **PASS**;
- `git diff --check`: **PASS**;
- dedicated offline-guard tests cover TCP, UDP, DNS and reversibility;
- native OpenAdapt smoke can explicitly skip when no physical input occurs; injected Windows input is intentionally filtered by upstream OpenAdapt.

A final full-suite verification is required again immediately before commit.

## Whole-process-tree offline audit

Latest full-stack audit:

- result: `OFFLINE_AUDIT_OK`;
- non-loopback established TCP connections: **0**;
- audited process tree: **2 processes** (venv launcher + real Python worker);
- runtime self-report: `offline_mode=true`;
- provider errors: **0**.

This audit corrected an earlier measurement bug where only the venv launcher PID was inspected.

## Accepted 5-minute pre-soak evidence

Data directory: `data/pre-soak-5min-accepted-candidate/`

Measured results:

- duration: ~304.6 s;
- structured events: **370**;
- endogenous events: **82**;
- exogenous events: **288**;
- process events: **254**;
- keyboard events: **82**;
- window events: **29**;
- screen snapshots: **5**;
- filesystem events during this window: **0**;
- native mouse events during this window: **0**;
- ordering comparisons: **369**;
- ordering violations: **0**;
- ordering consistency: **1.0**;
- privacy violations: **0**;
- forbidden fixture string hits: **0**;
- SQLite integrity: **ok**;
- external-network samples: **47**;
- samples with external established connection: **0**;
- raw artifacts at report: **2 / 674,376 bytes**;
- raw TTL: **60 s**;
- oldest remaining raw age: **47.23 s**;
- raw TTL violations: **0**;
- malformed raw metadata: **0**;
- CPU samples: **46**;
- average CPU across logical CPUs: **~0.098%**;
- maximum sampled CPU: **~1.176%**;
- RSS samples: **47**;
- RSS start: **47.7 MB**;
- RSS peak: **160.9 MB**;
- RSS end: **152.6 MB**;
- bus errors: **0**;
- provider errors: **0**.

The replay trace is coherent and includes user typing, foreground-window transitions, process start/exit evidence, and expiring screen snapshots. Expired screenshots appear only as `raw=expired`; replay never loads image bytes.

### Real-data privacy spot check

During the pre-soak:

- all keyboard rows were classified as `structured_short`;
- all observed KeyUp character/key-code fields were redacted;
- verified non-secure KeyDown characters remained available for short-term modeling;
- dedicated unit/integration fixtures verify PasswordBox/secure context also redacts sibling key fields before persistence.

## Mouse qualification

Status: **PASS — REAL PHYSICAL MOUSE EVIDENCE RECORDED (2026-10-08)**.

Dedicated native qualification directory:
`E:\Experiment\personal-predictive-ai-runtime\qualification\mouse-native-20261008-1132`

Observed persisted `HUMAN_PHYSICAL` evidence:

- physical events: **2**;
- mouse events: **2**;
- `mouse.down`: **1**;
- `mouse.up`: **1**;
- keyboard events: **0**.

The run used the real OpenAdapt native hook. No injected input was synthesized; upstream injected-input filtering therefore remains intact as an independent negative control. Temporary raw screen artifacts were deleted immediately after the structured event summary was generated.

Evidence hashes:

- `mouse_qualification_summary.json` SHA-256: `A9C89F49DAD5FDFD760EED7A2554D2D75D4BB7DF5E735C4B5518C323F616C56F`;
- `events.db` SHA-256: `A3D829CEF714BC3E89FB0DF7064536A4456351B9DA1530EAB9DD01B71A131602`.

This closes the physical-mouse qualification gate. It does not substitute for the formal 8-hour soak.

## Structured-short retention and restart safety

The implementation now enforces rather than merely labels short retention:

- exact verified keyboard evidence is `STRUCTURED_SHORT`;
- `CaptureService.expire_structured_short()` deletes only expired short rows;
- the CLI runs short-row GC periodically and on clean shutdown;
- long-term structured rows are not affected;
- SQLite stores `monotonic_seq_high_water` separately from event rows;
- deleting the latest short row does not decrease the sequence floor;
- process restart continues from the persisted sequence high-water, preventing duplicate/reused `monotonic_seq` values.

## 8-hour soak

Status: **NOT YET RUN**.

This is the final stability gate. It must use the frozen code after the final commit candidate and record:

- crash/exit status;
- full process-tree CPU/RSS samples;
- network samples;
- raw TTL violations;
- SQLite integrity;
- ordering consistency;
- provider/bus errors;
- replay coherence;
- evidence that RSS does not grow without bound.

The 5-minute pre-soak is not a substitute for this gate.

## Known capability boundary

`WindowsNotificationCollector` currently reports explicit unavailability because no native Windows notification backend is implemented. No notification evidence is fabricated. This remains a declared provider capability gap rather than a hidden success.

## Decision

Current decision: **Milestone A remains qualification-pending solely because the formal 8-hour soak has not yet been completed.**

The capture/data-plane implementation is functionally complete; the measured short qualification is healthy; and real native physical-mouse evidence is now recorded. Higher-level B1/B2/C/E work may continue under the prior ruling, but Milestone A must not be called fully qualified until the required 8-hour soak also passes.

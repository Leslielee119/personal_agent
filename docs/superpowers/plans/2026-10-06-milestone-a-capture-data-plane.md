# Personal Predictive AI Milestone A 鈥?Capture/Data Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows-first, fully local capture/data plane that converts broad desktop observations into versioned canonical events, suppresses sensitive content before persistence, and stores ordered structured events plus bounded raw artifacts.

**Architecture:** OpenAdapt Capture 1.3.x is isolated behind a collector adapter for native keyboard/mouse/screen/UIA observations. All upstream events are translated into our own Pydantic canonical contracts, passed through source-time privacy policy, then written through a local event bus to SQLite and a TTL-bounded raw-artifact ring. Exogenous providers are independent producers on the same bus.

**Tech Stack:** Python 3.12; Pydantic 2.x; pydantic-settings 2.x; SQLite via stdlib `sqlite3`; `psutil`; `watchdog`; optional local `openadapt-capture==1.3.x`; pytest; pytest-asyncio; ruff.

**Spec:** `docs/superpowers/specs/2026-10-06-personal-predictive-ai-v0-design.md`

## Global Constraints

- Runtime normal operation must have no outbound network capability.
- V0 captures broadly across the desktop but never equates broad observation with permanent raw retention.
- Credential/secure-field values must be removed before any disk write.
- V0 predicts/records only; it never executes desktop actions.
- Canonical event contracts are owned by this repository, not by OpenAdapt Capture.
- Event ordering is deterministic by `(timestamp_ns, monotonic_seq)`.
- Raw events are immutable evidence; normalization/labels remain separate derived records.
- Windows is the reference platform for Milestone A; interfaces must leave macOS/Linux adapters possible.
- OpenAdapt Capture is pinned to `>=1.3,<1.4` and used only through `collector/openadapt.py`.
- No Screenpipe code is copied into this repository.

## Review Focus

1. Secure text arrives inside nested UIA/event payloads: privacy sanitizer must recursively remove it before storage and preserve only non-secret metadata.
2. Wall clock moves backward or two events share a timestamp: `monotonic_seq` must still produce deterministic total ordering.
3. Raw artifact expires before a structured event is read: event retrieval must remain valid with a missing `raw_ref` target.
4. A collector/provider crashes or emits malformed data: bus/storage must reject that event without corrupting prior committed events or stopping unrelated providers.
5. Network code is accidentally invoked by a dependency: offline runtime guard must deny non-loopback sockets and the audit must observe zero established external connections.

---

## Planned File Structure

```text
pyproject.toml
src/personal_predictive_ai/
  __init__.py
  config.py
  events/
    models.py
    bus.py
    ids.py
  privacy/
    policy.py
    sanitizer.py
  storage/
    sqlite_store.py
    raw_ring.py
    migrations/001_initial.sql
  collector/
    base.py
    openadapt.py
    process.py
    filesystem.py
    windows_notifications.py
  runtime/
    offline_guard.py
    service.py
  cli.py
tests/
  events/
  privacy/
  storage/
  collector/
  runtime/
scripts/
  install_local_capture.ps1
  offline_audit.ps1
  soak_capture.ps1
```

### Task 1: Project scaffold and deterministic configuration

**Files:**
- Create: `pyproject.toml`
- Create: `src/personal_predictive_ai/__init__.py`
- Create: `src/personal_predictive_ai/config.py`
- Create: `tests/test_config.py`
- Create: `.gitignore`

**Interfaces:**
- Produces: `Settings(data_dir: Path, raw_ttl_seconds: int, structured_retention_days: int, offline_mode: bool)` and `load_settings() -> Settings`.

- [ ] **Step 1: Write failing tests** for defaults: local `data/`, `raw_ttl_seconds=900`, `structured_retention_days=30`, `offline_mode=True`; environment overrides must parse without network access.
- [ ] **Step 2: Run** `python -m pytest tests/test_config.py -v`; expect import/definition failure.
- [ ] **Step 3: Create the isolated environment** with `python -m venv .venv`, then implement package metadata for Python `>=3.12`, dependencies `pydantic>=2,<3`, `pydantic-settings>=2,<3`, `psutil>=5,<8`, `watchdog>=4,<7`, and dev dependencies `pytest`, `pytest-asyncio`, `ruff`; install with `.\.venv\Scripts\python -m pip install -e ".[dev]"` and implement `Settings` in `config.py`.
- [ ] **Step 4: Run** `python -m pytest tests/test_config.py -v` and `python -m ruff check src tests`; expect PASS.
- [ ] **Step 5: Commit** `chore: scaffold local capture data plane`.

### Task 2: Canonical event schema and monotonic ordering

**Files:**
- Create: `src/personal_predictive_ai/events/models.py`
- Create: `src/personal_predictive_ai/events/ids.py`
- Create: `tests/events/test_models.py`

**Interfaces:**
- Produces: `EventOrigin`, `PrivacyTier`, `RetentionClass`, `CanonicalEvent`, `EventFactory.next(...) -> CanonicalEvent`.
- `CanonicalEvent` fields must match spec section 6, with `schema_version="ppa.event/v1"`, nanosecond timestamp, positive `monotonic_seq`, JSON-safe payload, optional `raw_ref` and `causal_parent_ids`.

- [ ] **Step 1: Write failing tests** for schema validation, equal timestamps receiving increasing sequence numbers, backward wall-clock timestamps still ordering by sequence, and invalid negative sequence rejection.
- [ ] **Step 2: Run** `python -m pytest tests/events/test_models.py -v`; expect FAIL.
- [ ] **Step 3: Implement** the enums/models plus thread-safe `EventFactory` using an internal sequence counter; event IDs use UUIDv7 if available, otherwise UUID4 plus sequence without adding a new runtime dependency.
- [ ] **Step 4: Run** the focused tests and `ruff`; expect PASS.
- [ ] **Step 5: Commit** `feat: add canonical event contract`.

### Task 3: Source-time privacy policy and recursive sanitizer

**Files:**
- Create: `src/personal_predictive_ai/privacy/policy.py`
- Create: `src/personal_predictive_ai/privacy/sanitizer.py`
- Create: `tests/privacy/test_sanitizer.py`

**Interfaces:**
- Consumes: `CanonicalEvent` from Task 2.
- Produces: `PrivacyDecision`, `PrivacyPolicy.classify(...)`, `sanitize_event(event, policy) -> CanonicalEvent | None`.

- [ ] **Step 1: Write failing tests** for password/UIA secure-field payloads, nested credential-like values, clipboard/text tiers, excluded app/window rules, and a non-sensitive event that must remain byte-for-byte equivalent except policy metadata.
- [ ] **Step 2: Add the Review Focus test**: nested secure text such as `payload.structural.value` must never survive sanitization; safe metadata like app/window/event type may remain.
- [ ] **Step 3: Run** `python -m pytest tests/privacy/test_sanitizer.py -v`; expect FAIL.
- [ ] **Step 4: Implement** recursive sanitization with explicit sensitive-key/secure-role handling, `never_store` drop semantics, and configurable app/window exclusions; do not use remote classifiers or LLMs.
- [ ] **Step 5: Re-run focused tests plus** `python -m ruff check src tests`; expect PASS.
- [ ] **Step 6: Commit** `feat: enforce source-time privacy policy`.

### Task 4: Structured SQLite store and expiring raw-artifact ring

**Files:**
- Create: `src/personal_predictive_ai/storage/migrations/001_initial.sql`
- Create: `src/personal_predictive_ai/storage/sqlite_store.py`
- Create: `src/personal_predictive_ai/storage/raw_ring.py`
- Create: `tests/storage/test_sqlite_store.py`
- Create: `tests/storage/test_raw_ring.py`

**Interfaces:**
- Consumes: sanitized `CanonicalEvent`.
- Produces: `EventStore.append(event)`, `EventStore.iter_events(...)`, `EventStore.get(event_id)`, `RawRing.put(bytes, suffix) -> str`, `RawRing.resolve(raw_ref) -> Path | None`, `RawRing.expire(now_ns) -> int`.

- [ ] **Step 1: Write failing SQLite tests** for append/read round-trip, ordering by `(timestamp_ns, monotonic_seq)`, transaction rollback after malformed insert, and restart persistence.
- [ ] **Step 2: Write failing raw-ring tests** for TTL expiry, bounded total bytes, safe deletion, and retrieval after expiry returning `None` rather than invalidating the structured event.
- [ ] **Step 3: Run** `python -m pytest tests/storage -v`; expect FAIL.
- [ ] **Step 4: Implement** WAL-mode SQLite schema with immutable canonical event rows and JSON payload; use foreign-key-free `raw_ref` strings so artifact expiry cannot corrupt structured history.
- [ ] **Step 5: Implement** filesystem ring with metadata sidecars/index sufficient for deterministic TTL/size eviction; atomic temp-file-to-final rename for writes.
- [ ] **Step 6: Run focused tests, `PRAGMA integrity_check`, and ruff; expect PASS/`ok`.**
- [ ] **Step 7: Commit** `feat: add local structured and raw storage`.

### Task 5: In-process event bus with fault isolation

**Files:**
- Create: `src/personal_predictive_ai/events/bus.py`
- Create: `tests/events/test_bus.py`

**Interfaces:**
- Consumes: producer callbacks yielding unsanitized `CanonicalEvent` objects.
- Produces: `EventBus.publish(event) -> PublishResult`, `EventBus.subscribe(handler)`, and storage sink composition with privacy sanitizer before persistence.

- [ ] **Step 1: Write failing tests** for ordered publish, multiple subscribers, one failing subscriber not stopping the bus, sanitizer drop behavior, and a malformed event returning a rejected result without touching storage.
- [ ] **Step 2: Add the Review Focus failure-isolation test**: one collector handler raises while a second provider continues publishing and prior rows remain queryable.
- [ ] **Step 3: Run** `python -m pytest tests/events/test_bus.py -v`; expect FAIL.
- [ ] **Step 4: Implement** a synchronous bounded hot-path bus first; keep subscriber errors in a local error record/counter and never retry malformed evidence implicitly.
- [ ] **Step 5: Run focused tests and full unit suite; expect PASS.**
- [ ] **Step 6: Commit** `feat: add fault-isolated canonical event bus`.

### Task 6: OpenAdapt Capture adapter for endogenous desktop events

**Files:**
- Create: `src/personal_predictive_ai/collector/base.py`
- Create: `src/personal_predictive_ai/collector/openadapt.py`
- Create: `tests/collector/test_openadapt_adapter.py`
- Create: `scripts/install_local_capture.ps1`

**Interfaces:**
- Produces: `Collector` protocol with `start(publish)`, `stop()`, `health()`; `OpenAdaptCollector` translates OpenAdapt 1.3.x events into canonical endogenous events.
- Adapter must not expose OpenAdapt event classes outside `collector/openadapt.py`.

- [ ] **Step 1: Write failing mapping tests** using synthetic OpenAdapt `KeyDownEvent`, `KeyTypeEvent`, `MouseClickEvent`, `MouseScrollEvent`, `ScreenFrameEvent`, and structural observation fixtures; assert canonical source/modality/origin/event type and payload mapping.
- [ ] **Step 2: Write secure-field adapter test** proving OpenAdapt structural secure/password values are marked so Task 3 sanitizer drops them before store.
- [ ] **Step 3: Run** `python -m pytest tests/collector/test_openadapt_adapter.py -v`; expect FAIL.
- [ ] **Step 4: Implement** translation only; do not import OpenAdapt in core modules. Add a local install script that runs `python -m pip install -e E:\Experiment\personal-predictive-ai-sources\openadapt-capture` and verifies version `>=1.3,<1.4`.
- [ ] **Step 5: Add a Windows native smoke test** marked `@pytest.mark.slow` that starts capture for a bounded interval, records at least one keyboard/mouse event and one screen/UIA observation where permission allows, then stops cleanly.
- [ ] **Step 6: Run unit mapping tests; run slow smoke manually on the reference desktop; expect PASS or an explicit permission/capability skip, never silent degradation.**
- [ ] **Step 7: Commit** `feat: adapt OpenAdapt desktop capture`.

### Task 7: Exogenous Windows providers

**Files:**
- Create: `src/personal_predictive_ai/collector/process.py`
- Create: `src/personal_predictive_ai/collector/filesystem.py`
- Create: `src/personal_predictive_ai/collector/windows_notifications.py`
- Create: `tests/collector/test_process_provider.py`
- Create: `tests/collector/test_filesystem_provider.py`
- Create: `tests/collector/test_windows_notifications.py`

**Interfaces:**
- Consumes: `Collector` protocol and `EventFactory`.
- Produces: canonical exogenous events for process start/exit, configured filesystem changes, and Windows notification availability/events; unavailable OS capabilities emit health/capability state rather than fabricated observations.

- [ ] **Step 1: Write failing process tests** using injected `psutil` snapshots; assert start/exit events are `origin=exogenous`, stable process identity includes PID plus create time, and exits can represent job completion evidence.
- [ ] **Step 2: Write failing filesystem tests** using a temporary watched directory; assert create/modify/delete/move normalization, debounce duplicate bursts, and project exclusions.
- [ ] **Step 3: Write failing notification tests** around an injectable Windows notification backend: permission unavailable must produce `health().available=False`; a supplied notification fixture maps metadata without forcing message-body persistence.
- [ ] **Step 4: Implement** `ProcessCollector` with snapshot diffing and bounded poll cadence; implement `FilesystemCollector` with watchdog; implement `WindowsNotificationCollector` behind a backend protocol so Windows Runtime/UIA integration can be swapped without changing the canonical contract.
- [ ] **Step 5: Run** `python -m pytest tests/collector/test_process_provider.py tests/collector/test_filesystem_provider.py tests/collector/test_windows_notifications.py -v`; expect PASS.
- [ ] **Step 6: Commit** `feat: capture exogenous desktop events`.

### Task 8: Offline guard, runtime composition, and CLI

**Files:**
- Create: `src/personal_predictive_ai/runtime/offline_guard.py`
- Create: `src/personal_predictive_ai/runtime/service.py`
- Create: `src/personal_predictive_ai/cli.py`
- Create: `tests/runtime/test_offline_guard.py`
- Create: `tests/runtime/test_service.py`
- Create: `scripts/offline_audit.ps1`

**Interfaces:**
- Produces: `OfflineNetworkGuard` denying non-loopback IPv4/IPv6 socket connects; `CaptureService.start()/stop()/status()` composing settings, store, ring, privacy, bus, and collectors; CLI commands `ppa capture`, `ppa status`, `ppa expire-raw`.

- [ ] **Step 1: Write failing guard tests**: loopback socket allowed, `8.8.8.8:53`/public test endpoint denied before connect, guard is reversible in tests, and offline mode defaults on.
- [ ] **Step 2: Write failing service tests** with fake collectors for clean startup/shutdown, provider crash isolation, raw expiry, and deterministic event persistence.
- [ ] **Step 3: Run** `python -m pytest tests/runtime -v`; expect FAIL.
- [ ] **Step 4: Implement** process-level socket guard before importing/starting optional collectors; do not patch local IPC/loopback.
- [ ] **Step 5: Implement** service/CLI lifecycle and local status reporting; no telemetry, update check, remote logging, or package download is permitted from runtime commands.
- [ ] **Step 6: Add** `offline_audit.ps1` to launch the service, inspect its PID's established TCP connections, and fail if any non-loopback remote address is observed.
- [ ] **Step 7: Run runtime tests and the audit on Windows; expect zero external established connections.**
- [ ] **Step 8: Commit** `feat: add offline capture runtime`.

### Task 9: Milestone A integration, replay diagnostics, and soak harness

**Files:**
- Create: `tests/integration/test_capture_pipeline.py`
- Create: `scripts/soak_capture.ps1`
- Create: `scripts/report_capture_health.py`
- Create: `docs/milestones/MILESTONE_A_ACCEPTANCE.md`

**Interfaces:**
- Consumes: all Task 1鈥? public interfaces.
- Produces: an end-to-end local session database/raw ring plus a machine-readable health report with event counts, ordering violations, privacy violations, raw bytes, CPU/RAM samples, provider errors, and external network connections.

- [ ] **Step 1: Write failing integration test** with fake endogenous/exogenous producers that sends interleaved equal/backward timestamps, an expiring raw artifact, a nested secure payload, and one provider exception; assert ordered safe persistence and continued service.
- [ ] **Step 2: Add a replay diagnostic** that prints a chronological compact trace `time | origin | app | event_type | safe payload summary` without exposing `never_store` or expired raw content.
- [ ] **Step 3: Implement** `soak_capture.ps1` for configurable duration (default 8 hours), periodic process CPU/RSS/disk/network sampling, clean Ctrl-C shutdown, and final `report_capture_health.py` generation.
- [ ] **Step 4: Run** `python -m pytest -v` and `python -m ruff check src tests scripts`; expect all automated tests PASS.
- [ ] **Step 5: Run a 5-minute pre-soak** on the real desktop and inspect the replay trace manually; require keyboard/mouse/window plus at least one exogenous event and no stored credential test fixture.
- [ ] **Step 6: Run the 8-hour soak acceptance**. Gate: no crash/unbounded RSS, zero outbound connections, zero secure-field values persisted, ordering consistency >=99.99%, idle CPU target <2%, active sustained CPU target <5鈥?%, bounded raw growth under TTL.
- [ ] **Step 7: Record actual measured results** in `docs/milestones/MILESTONE_A_ACCEPTANCE.md`; any failed gate remains explicit and blocks Milestone B.
- [ ] **Step 8: Commit** `test: qualify milestone A capture data plane`.

## Milestone A Definition of Done

Milestone A is complete only when:

1. `python -m pytest -v` passes.
2. `python -m ruff check src tests scripts` passes.
3. OpenAdapt adapter native smoke either passes or reports an explicit OS-permission capability block.
4. A real 8-hour Windows soak has a written acceptance report.
5. Offline audit shows zero non-loopback established outbound connections for the runtime process.
6. Dedicated secret fixtures prove credential/secure-field values never reach SQLite or raw-artifact storage.
7. SQLite `PRAGMA integrity_check` returns `ok` after soak.
8. The replay diagnostic reconstructs a coherent sequence containing both user/endogenous and environment/exogenous events.
9. No State Estimator, predictor, LLM, or action executor has been added prematurely.

## Execution Order

Implement Tasks 1鈫? sequentially because each task locks interfaces consumed by the next. Do not parallelize Tasks 2鈥?: schema/privacy/storage/bus/adapter boundaries are coupled. Task 7 provider implementations may be developed independently after Task 5, but integration waits for Task 8.



# Milestone E0/E1 Trusted Knowledge & Skill Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the local canonical Knowledge/Skill registry and human-authored E1 workflow with immutable Skill versions, staged approval, package quarantine/provenance, progressive disclosure, and Markdown projection, without enabling autonomous behavior mining or side-effect execution.

**Architecture:** Add separate `knowledge` and `skills` domain packages backed by one SQLite registry store and migration. All Skill semantic changes pass through `SkillMutationProposal`; external packages remain quarantined until explicit review; retrieval exposes L0/L1/L2 separately; Markdown is a projection, never machine truth.

**Tech Stack:** Python 3.12, Pydantic v2, SQLite, argparse CLI, pytest, Ruff, PyYAML 6.x for deterministic Markdown frontmatter.

**Spec:** `docs/superpowers/specs/2026-10-07-milestone-e-personal-knowledge-skill-plane-design.md`

## Global Constraints

- Keep `Memory != Knowledge != Skill != Prediction != Authorization` as separate domains.
- E0/E1 must not implement behavior-to-Skill mining, autonomous Skill self-improvement, MXC execution, desktop execution, or cloud routing.
- `READ_ONLY` may be auto-allowed; `WRITE_LOCAL`, `ACT_LOCAL`, `EXTERNAL_EFFECT`, and `UNKNOWN` require explicit human approval.
- `VERIFIED != AUTHORIZED_TO_EXECUTE`; `ACTIVE` only means retrievable/proposable.
- External Skill content must be quarantined, hashed, scanned, and reviewed before canonical activation.- External package source revision, content hash, scanner version, and findings are provenance and must survive canonicalization.
- Historical Skill versions are immutable; update/retire/supersede/invalidate operations create a new version after approval.
- Markdown/Obsidian is projection only; edited projection creates a proposal, never a silent registry write.
- Tests must not execute `WRITE_LOCAL`, `ACT_LOCAL`, or `EXTERNAL_EFFECT` Skill procedures.
- Keep all state local under the configured data directory; no network access is needed for E0/E1 runtime behavior.
- Python remains `>=3.12,<3.13`; use existing Pydantic `extra="forbid"`, frozen models, strict JSON-safe serialization, and SQLite WAL conventions.

## Review Focus

1. A stale `base_version` proposal approved after a newer version exists must fail closed; Task 3 adds the concurrency/stale-base test.
2. Package path traversal, absolute references, or symlink escape outside the import root must be rejected; Task 4 pins these cases.
3. A proposed risk downgrade must require an explicit `allow_risk_downgrade=True` approval flag; Task 3 tests silent downgrade rejection.
4. Corrupt/unknown Markdown projection fields must fail parsing and leave canonical state unchanged; Task 6 tests fail-closed round-trip behavior.
5. L0/L1 retrieval and L2 reference reads must never execute scripts or expose references from unapproved packages; Task 5 tests this boundary.

---

## File Structure

- `src/personal_predictive_ai/knowledge/models.py` — explicit Knowledge schema/provenance.
- `src/personal_predictive_ai/knowledge/ids.py` — deterministic Knowledge IDs.
- `src/personal_predictive_ai/skills/models.py` — Skill, version, verification, proposal, package, and retrieval view models.
- `src/personal_predictive_ai/skills/ids.py` — deterministic Skill/proposal/package IDs.
- `src/personal_predictive_ai/skills/safety.py` — JSON-safety, secret-pattern, path, and risk-order helpers.- `src/personal_predictive_ai/storage/migrations/004_e_knowledge_skill.sql` — canonical E0/E1 SQLite tables/indexes.
- `src/personal_predictive_ai/storage/knowledge_skill_store.py` — persistence primitives only; no implicit approval.
- `src/personal_predictive_ai/skills/registry.py` — proposal staging, approval, immutable version creation, and Knowledge import service.
- `src/personal_predictive_ai/skills/packages.py` — local package quarantine, hash, scan, and manifest creation.
- `src/personal_predictive_ai/skills/retrieval.py` — L0/L1/L2 read-only retrieval.
- `src/personal_predictive_ai/skills/projection.py` — deterministic Markdown render/parse/diff-to-proposal.
- `src/personal_predictive_ai/cli.py` — explicit human E1 commands.
- `pyproject.toml` — add `pyyaml>=6,<7` for frontmatter parsing/writing.
- Tests mirror each responsibility under `tests/knowledge`, `tests/skills`, `tests/storage`, and `tests/integration`.

### Task 1: E0 Canonical Schemas, Safety Rules, and Deterministic IDs

**Files:**
- Create: `src/personal_predictive_ai/knowledge/__init__.py`
- Create: `src/personal_predictive_ai/knowledge/models.py`
- Create: `src/personal_predictive_ai/knowledge/ids.py`
- Create: `src/personal_predictive_ai/skills/__init__.py`
- Create: `src/personal_predictive_ai/skills/models.py`
- Create: `src/personal_predictive_ai/skills/ids.py`
- Create: `src/personal_predictive_ai/skills/safety.py`
- Test: `tests/knowledge/test_models_ids.py`
- Test: `tests/skills/test_models_ids.py`

**Interfaces:**
- Produces `KnowledgeRecord`, `KnowledgeSourceClass`, `SkillDraft`, `SkillRecord`, `VerificationSpec`, `SkillMutationProposal`, `SkillPackageManifest`, `SkillAuditEvent`, `SkillProjectionManifest`, `RiskClass`, `SkillStatus`, `PackageTrustState`, and deterministic ID helpers used by all later tasks.
- `knowledge_id_for(scope, key, value, source_class) -> str`; `skill_id_for(kind, canonical_name, scope) -> str`; `proposal_id_for(...) -> str`; `package_id_for(...) -> str` must use sorted strict JSON + SHA-256 with stable prefixes.
- `SkillRecord.version` is `>=1`; updates preserve `skill_id` and increment version; a rename that changes canonical identity is represented as `SUPERSEDE`, not in-place rename.
- `RiskClass` order is `READ_ONLY < WRITE_LOCAL < ACT_LOCAL < EXTERNAL_EFFECT < UNKNOWN` only for detecting downgrades; `UNKNOWN` is never auto-allowed.

- [ ] **Step 1: Write failing schema/ID tests** asserting exact enums, `extra="forbid"`, frozen models, strict JSON-safe payloads, valid intervals, deterministic IDs, and rejection of embedded credential/token sentinel values.
- [ ] **Step 2: Run** `pytest tests/knowledge/test_models_ids.py tests/skills/test_models_ids.py -v`; expected FAIL because the modules do not exist.
- [ ] **Step 3: Implement the domain models and ID helpers** with schema versions `ppa.knowledge/v1`, `ppa.skill/v1`, `ppa.skill-verification/v1`, `ppa.skill-mutation/v1`, `ppa.skill-package/v1`, `ppa.skill-audit/v1`, and `ppa.skill-projection/v1`; `SkillDraft`/`SkillRecord` include optional `source_package_id` so an approved external package can be linked without auto-translating its semantics.
- [ ] **Step 4: Implement `validate_safe_structured_text(value: object) -> None` and `risk_rank(risk: RiskClass) -> int`** in `skills/safety.py`; keep scanning deterministic and local.
- [ ] **Step 5: Run** the two test files again; expected PASS.
- [ ] **Step 6: Run** `ruff check src/personal_predictive_ai/knowledge src/personal_predictive_ai/skills tests/knowledge tests/skills`; expected PASS.
- [ ] **Step 7: Commit** `git commit -m "feat: add trusted knowledge and skill schemas"`.

### Task 2: SQLite Canonical Registry and Migration

**Files:**
- Create: `src/personal_predictive_ai/storage/migrations/004_e_knowledge_skill.sql`
- Create: `src/personal_predictive_ai/storage/knowledge_skill_store.py`
- Test: `tests/storage/test_knowledge_skill_store.py`

**Interfaces:**
- Consumes Task 1 models.
- Produces `KnowledgeSkillStore` with explicit persistence primitives; callers cannot obtain an approval side effect by merely inserting a proposal.

Required methods:

```python
put_knowledge(record: KnowledgeRecord) -> None
get_knowledge(knowledge_id: str) -> KnowledgeRecord | None
iter_knowledge() -> Iterator[KnowledgeRecord]
stage_proposal(proposal: SkillMutationProposal) -> None
get_proposal(proposal_id: str) -> SkillMutationProposal | None
replace_proposal(proposal: SkillMutationProposal) -> None
append_skill_version(record: SkillRecord) -> None
get_skill(skill_id: str, version: int | None = None) -> SkillRecord | None
iter_skill_versions(skill_id: str) -> Iterator[SkillRecord]
put_package_manifest(manifest: SkillPackageManifest) -> None
get_package_manifest(package_id: str) -> SkillPackageManifest | None
append_audit_event(event: SkillAuditEvent) -> None
iter_audit_events(skill_id: str | None = None) -> Iterator[SkillAuditEvent]
put_projection_manifest(manifest: SkillProjectionManifest) -> None
get_projection_manifest(projection_id: str) -> SkillProjectionManifest | None
commit_approved_skill(
    proposal: SkillMutationProposal,
    record: SkillRecord,
    audit_event: SkillAuditEvent,
    *,
    expected_base_version: int | None,
) -> None
```

- [ ] **Step 1: Write the failing store test** covering restart persistence, deterministic ordering, immutable `(skill_id, version)` primary key, proposal/package/audit/projection-manifest round-trip, atomic `commit_approved_skill`, and SQLite rollback on duplicate/conflicting writes.
- [ ] **Step 2: Add a regression test** proving E-store writes never modify canonical event, B1, or B2 tables.
- [ ] **Step 3: Run** `pytest tests/storage/test_knowledge_skill_store.py -v`; expected FAIL because migration/store are absent.
- [ ] **Step 4: Implement migration 004** with tables `knowledge_records`, `skill_records`, `skill_mutation_proposals`, `skill_package_manifests`, `skill_audit_events`, and `skill_projection_manifests`; store `data_json` plus indexed identity/status/version fields only.
- [ ] **Step 5: Implement `KnowledgeSkillStore`** using the existing `MemoryStore` locking/WAL/strict sorted-JSON pattern; do not expose `UPDATE skill_records`.
- [ ] **Step 6: Run** the storage test; expected PASS and `integrity_check() == "ok"`.
- [ ] **Step 7: Commit** `git commit -m "feat: add knowledge and skill registry storage"`.

### Task 3: Proposal Approval and Immutable Skill Lifecycle

**Files:**
- Create: `src/personal_predictive_ai/skills/registry.py`
- Test: `tests/skills/test_registry.py`

**Interfaces:**
- Consumes Task 1 IDs/models and Task 2 store.
- Produces `TrustedRegistryService` as the only E1 write orchestration API.

Required methods:

```python
import_human_knowledge(record: KnowledgeRecord) -> KnowledgeRecord
stage_skill_create(draft: SkillDraft, *, proposed_by: str) -> SkillMutationProposal  # if draft.source_package_id is set, manifest must be APPROVED
stage_skill_update(skill_id: str, patch: dict[str, object], *, proposed_by: str) -> SkillMutationProposal
approve_proposal(proposal_id: str, *, approver: str, allow_risk_downgrade: bool = False) -> SkillRecord
reject_proposal(proposal_id: str, *, approver: str, reason: str) -> SkillMutationProposal
```

- [ ] **Step 1: Write failing lifecycle tests** proving CREATE approval always yields `DRAFT`, UPDATE increments version without bypassing status gates, `PENDING`/`REJECTED` proposals create no Skill rows, and E1 rejects attempts to promote a Skill directly to `VERIFIED` or `ACTIVE` (`UnsupportedE1TransitionError`).
- [ ] **Step 2: Add concurrency tests**: stage update at version 1, approve another update to version 2, then approving the stale proposal must raise `StaleSkillVersionError` with no version 3 write; two concurrent CREATE proposals for the same deterministic `skill_id` must allow only the first canonical version 1.
- [ ] **Step 3: Add the risk/package tests**: `ACT_LOCAL -> READ_ONLY` approval fails unless `allow_risk_downgrade=True`; a `SkillDraft.source_package_id` referencing anything except an `APPROVED` package is rejected before proposal staging.
- [ ] **Step 4: Run** `pytest tests/skills/test_registry.py -v`; expected FAIL because service is absent.
- [ ] **Step 5: Implement `TrustedRegistryService`** and make approval call `KnowledgeSkillStore.commit_approved_skill(...)`; that store method re-checks `expected_base_version`, appends the new Skill version, replaces the proposal with its approved form, and appends the audit event in one SQLite transaction. E1 CREATE always materializes `DRAFT`; direct promotion to `VERIFIED`/`ACTIVE` is rejected until E3 exists.
- [ ] **Step 6: Ensure audit metadata is canonical**: stage/approve/reject operations emit `SkillAuditEvent`; approved proposals record `approved_by`, `approved_at`, and `resulting_version`; never mutate historical Skill JSON.
- [ ] **Step 7: Run** registry tests and `tests/storage/test_knowledge_skill_store.py`; expected PASS.
- [ ] **Step 8: Commit** `git commit -m "feat: gate skill mutations through approval"`.

### Task 4: External Skill Package Quarantine and Provenance

**Files:**
- Create: `src/personal_predictive_ai/skills/packages.py`
- Test: `tests/skills/test_packages.py`

**Interfaces:**
- Consumes `SkillPackageManifest`, package IDs, safety scanner, and store.
- Produces `quarantine_local_package(root: Path, *, source_uri: str, source_revision: str, quarantine_root: Path) -> SkillPackageManifest`, `scan_package(package_id: str) -> SkillPackageManifest`, and `approve_package(package_id: str, *, reviewer: str) -> SkillPackageManifest`.

Quarantine format is `data_dir/skill-packages/quarantine/<package_id>/`; copy only regular files reachable beneath the import root, preserve relative paths, and compute one package hash over sorted `(relative_path, sha256)` pairs.

- [ ] **Step 1: Write failing package tests** for content-hash stability, source/revision retention, scanner findings, and `QUARANTINED -> SCANNED -> APPROVED` transitions.
- [ ] **Step 2: Add path-safety tests** for `../` traversal, absolute referenced paths, and symlink/junction escape; all must fail before copying content outside quarantine.
- [ ] **Step 3: Add a secret/invisible-Unicode fixture** and assert the manifest records findings and cannot become `APPROVED` while blocking findings remain.
- [ ] **Step 4: Run** `pytest tests/skills/test_packages.py -v`; expected FAIL because package functions are absent.
- [ ] **Step 5: Implement `quarantine_local_package`** with no URL fetching and no automatic canonical Skill creation; it copies validated regular files, computes the manifest/hash, persists `QUARANTINED`, and returns.
- [ ] **Step 6: Implement `scan_package` and `approve_package`**: scanner version `ppa.skill-package-scan/v1` uses deterministic checks from `skills/safety.py`; scanning persists `SCANNED` plus structured findings, and approval fails if blocking findings remain.
- [ ] **Step 7: Run** package tests; expected PASS.
- [ ] **Step 8: Commit** `git commit -m "feat: quarantine imported skill packages"`.

### Task 5: Progressive Disclosure Retrieval

**Files:**
- Create: `src/personal_predictive_ai/skills/retrieval.py`
- Test: `tests/skills/test_retrieval.py`

**Interfaces:**
- Produces `SkillIndexEntry` (L0), `SkillCoreView` (L1), and `SkillReferenceView` (L2).

Required functions:

```python
list_skill_index(store: KnowledgeSkillStore, *, statuses: set[SkillStatus] | None = None) -> list[SkillIndexEntry]
get_skill_core(store: KnowledgeSkillStore, skill_id: str, *, version: int | None = None) -> SkillCoreView
get_skill_reference(store: KnowledgeSkillStore, package_root: Path, skill_id: str, reference_path: str, *, version: int | None = None) -> SkillReferenceView
```

- [ ] **Step 1: Write failing L0/L1/L2 tests** proving L0 omits procedure/reference content, L1 contains only canonical core fields, and L2 returns one requested reference only.
- [ ] **Step 2: Add authorization-boundary tests** proving retrieval never invokes scripts and rejects L2 reads for missing, quarantined, scanned-only, or rejected package manifests.
- [ ] **Step 3: Add reference-path safety tests** rejecting absolute paths, traversal, and references not listed in the approved manifest.
- [ ] **Step 4: Run** `pytest tests/skills/test_retrieval.py -v`; expected FAIL because retrieval module is absent.
- [ ] **Step 5: Implement L0/L1 as pure model projections** over canonical Skill records and implement L2 as validated text-file read from an APPROVED package only.
- [ ] **Step 6: Run** retrieval tests; expected PASS.
- [ ] **Step 7: Commit** `git commit -m "feat: add progressive skill disclosure"`.

### Task 6: Deterministic Markdown Projection and Edit-to-Proposal

**Files:**
- Modify: `pyproject.toml`
- Create: `src/personal_predictive_ai/skills/projection.py`
- Test: `tests/skills/test_projection.py`

**Interfaces:**
- Consumes `SkillRecord`, `SkillDraft`, proposal staging service, and safety validation.
- Produces `render_skill_markdown(record: SkillRecord) -> str`, `parse_skill_markdown(text: str) -> SkillDraft`, `projection_manifest_for(record: SkillRecord, *, output_path: Path, content: str) -> SkillProjectionManifest`, and `proposal_from_projection_edit(base: SkillRecord, text: str, *, proposed_by: str) -> SkillMutationProposal | None`.

Projection contract:
- YAML frontmatter contains only stable machine fields needed for round-trip (`skill_id`, `version`, `kind`, `status`, `risk_class`, `scope`, optional `source_package_id`, schema marker). `status` is machine-controlled in E1; editing it in Markdown fails closed instead of staging a promotion.
- Human-facing sections are `Purpose`, `Initiation`, `Preconditions`, `Procedure`, `Termination`, `Success`, `Verification`, and `Evidence Summary`.
- `yaml.safe_load` only; no custom YAML object construction.

- [ ] **Step 1: Add `pyyaml>=6,<7` to core dependencies** and write the failing unedited round-trip test: canonical -> Markdown -> draft must be semantically equivalent for editable fields.
- [ ] **Step 2: Add edited-projection test** asserting a semantic change returns a `SkillMutationProposal` while byte-identical/semantic-identical projection returns `None`.
- [ ] **Step 3: Add fail-closed tests** for unknown frontmatter fields, malformed YAML, mismatched `skill_id`/version, edited machine-controlled `status`, unsafe secret sentinel, and unsupported schema marker; store state must remain byte-for-byte unchanged.
- [ ] **Step 4: Run** `pytest tests/skills/test_projection.py -v`; expected FAIL because projection module is absent.
- [ ] **Step 5: Implement deterministic rendering/parsing and `projection_manifest_for`** with sorted frontmatter keys, stable section order, and SHA-256 content hash; parsing returns data only and never writes storage.
- [ ] **Step 6: Implement `proposal_from_projection_edit`** by comparing normalized editable fields and calling the Task 3 staging path only when there is a semantic difference.
- [ ] **Step 7: Run** projection tests plus registry tests; expected PASS.
- [ ] **Step 8: Commit** `git commit -m "feat: add auditable skill markdown projection"`.

### Task 7: Explicit Human CLI and E1 End-to-End Qualification

**Files:**
- Modify: `src/personal_predictive_ai/cli.py`
- Create: `tests/integration/test_e1_trusted_registry_cli.py`
- Create: `docs/milestones/MILESTONE_E0_E1_ACCEPTANCE.md`

**Interfaces:**
- Consumes Tasks 1-6.
- Adds explicit human commands; none executes a Skill procedure.

CLI commands:

```text
ppa knowledge-import --file <json>
ppa skill-stage --file <json> --proposed-by <name> [--package-id <approved-package-id>]
ppa skill-approve --proposal-id <id> --approver <name> [--allow-risk-downgrade]
ppa skill-list [--status <status>]
ppa skill-show --skill-id <id> --level index|core [--version N]
ppa skill-export --skill-id <id> --output <path> [--version N]
ppa skill-package-import --path <dir> --source-uri <uri> --source-revision <rev>
ppa skill-package-scan --package-id <id>
ppa skill-package-approve --package-id <id> --reviewer <name>
```

Every command that persists registry/package/projection state (`knowledge-import`, `skill-stage`, `skill-approve`, `skill-export`, `skill-package-import`, `skill-package-scan`, `skill-package-approve`) is an explicit human-triggered WRITE_LOCAL operation; the CLI must not imply that a model may call it without host approval. `skill-list` and `skill-show` remain read-only.

- [ ] **Step 1: Write failing CLI integration tests** that create a temp `data_dir`, import one Knowledge record, stage one Skill, prove `skill-list` is empty before approval, approve it, then verify L0/L1 JSON output and immutable version history.
- [ ] **Step 2: Add package integration coverage**: import -> QUARANTINED, scan -> SCANNED, approve -> APPROVED; L2 is blocked before approval, and `skill-stage --package-id <approved-id>` creates only a proposal whose eventual SkillRecord preserves `source_package_id`.
- [ ] **Step 3: Add export integration coverage** proving `skill-export` writes deterministic Markdown only after explicit CLI invocation, persists a `SkillProjectionManifest` with output path/content hash, and never mutates canonical Skill state.
- [ ] **Step 4: Run** `pytest tests/integration/test_e1_trusted_registry_cli.py -v`; expected FAIL because CLI commands are absent.
- [ ] **Step 5: Add parsers/handlers to `cli.py`** using the existing JSON-printing convention; commands must close stores in `finally` blocks and return non-zero on validation/approval failures.
- [ ] **Step 6: Run the full E0/E1 focused suite**: `pytest tests/knowledge tests/skills tests/storage/test_knowledge_skill_store.py tests/integration/test_e1_trusted_registry_cli.py -v`; expected PASS.
- [ ] **Step 7: Write `MILESTONE_E0_E1_ACCEPTANCE.md`** recording implemented scope, explicit non-goals, Gate E0/E1 evidence, and the fact that E2/F remain closed.
- [ ] **Step 8: Run full project verification**: `pytest -q`, `ruff check .`, and `git diff --check`; expected zero failures/errors.
- [ ] **Step 9: Commit** `git commit -m "feat: qualify trusted knowledge and skill registry"`.

## Final Qualification Checklist

- [ ] Gate E0: deterministic IDs/versioning and strict Pydantic schemas pass.
- [ ] Gate E0: historical Skill records are immutable and stale-base approval fails closed.
- [ ] Gate E0: package provenance/hash/scanner findings survive persistence.
- [ ] Gate E0: QUARANTINED/REJECTED packages never become ACTIVE Skills implicitly.
- [ ] Gate E1: canonical -> Markdown -> parse-back is semantically equivalent when unedited.
- [ ] Gate E1: edited Markdown creates a proposal only; corrupt/unknown projection fails closed.
- [ ] Gate E1: L0/L1/L2 disclosure boundaries are independently tested.
- [ ] Gate E1: `VERIFIED`/`ACTIVE` never bypass risk approval.
- [ ] Privacy: secret/token sentinels do not persist into Skill/package/projection artifacts.
- [ ] Side-effect boundary: no test executes a Skill procedure or external action.
- [ ] Existing A/B/C tests still pass unchanged.

## Explicitly Deferred

- E2 Behavior-to-Skill discovery and cross-session mining, including `SkillEvidenceLink` and `SkillDependency` population from behavioral evidence.
- E3 verification/lifecycle promotion into `VERIFIED` / `ACTIVE` / `NEEDS_REVALIDATION`, plus experimental `SkillValidationRun`; E1 only materializes and edits `DRAFT` canonical Skills.
- Automated Skill self-improvement or background mutation.
- Planner/Executor retrieval benchmark beyond the L0/L1/L2 E1 substrate.
- MXC or any execution backend integration.
- `BackendCapabilityProfile` and `TrustedCompletionReport` implementation; their semantics remain reserved for Milestone F.
# Milestone C Validity-first Predictive Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个可重放、无未来信息泄漏、先验证数据有效性再比较模型的个人下一动作预测基准，并严格隔离 sequence、structured state 与 B2 Memory 的独立增量价值。

**Architecture:** 新增 `personal_predictive_ai.prediction` 子系统。B1 `DerivedStore` 与 B2 `MemoryStore` 仍是唯一事实来源；C 层只构造隐私裁剪后的 prediction examples、chronological/session-forward splits、可解释 baseline/retrieval/memory ablation，并把确定性 JSON/JSONL 工件写到独立 prediction run 目录，不修改 canonical/B1/B2 数据。所有 gate 先由冻结 config 与 validation 决定，再一次性评估 test。

**Tech Stack:** Python 3.12, Pydantic 2, stdlib `math/statistics/random/hashlib/json`, pytest, Ruff。V1 不新增 NumPy/Pandas/scikit-learn/ML/embedding/LLM 依赖。

**Spec:** `docs/superpowers/specs/2026-10-07-predictive-baselines-design.md`

## Global Constraints

- C V1 不训练 GRU/LSTM/Transformer/SSM，不使用 embedding/vector retrieval，不使用 LLM。
- 正式 target 仅允许 `HUMAN_PHYSICAL`；其他 provenance 只做单独诊断或排除。
- 所有 predictor 输入必须满足 `source_seq < target_action.monotonic_seq`；禁止 post-state、target-triggered UIA/screenshot/process evidence。
- 正式 split 必须 chronological/session-forward；单 session 仅允许 `NON_GENERALIZATION_DIAGNOSTIC`。
- Operation/Joint C0 Gate：sessions >= 4、targets >= 200、classes >= 3、dominant <= 0.90、normalized entropy >= 0.25、test classes >= 2、test samples >= 40。
- Primary metric 固定为 NLL；`tau_NLL = max(0.01 nats, 0.01 * NLL_reference)`；secondary metrics 不能救回 primary gate。
- `best action-only baseline` 只能按 validation NLL 选择；test 不允许重新选模型/参数。
- Prediction vocabulary = train labels + reserved `__UNSEEN__`；unseen concrete label 在 ranking 指标中永远算 miss。
- C3 只有在 `memory_available_samples >= 40`、coverage >= 0.20、exposed test sessions >= 2、distinct ACTIVE memories >= 2 时才可判定 Memory value。
- 禁止普通 action-row bootstrap；独立 test sessions < 5 时 inferential status 固定为 `DESCRIPTIVE_ONLY`。
- Prediction artifacts 禁止保存 exact key content、raw screenshot、clipboard exact content、secure UI text、credential fields。
- 当前真实 182-action/1-session qualification capture 必须得到 `INSUFFICIENT_PREDICTIVE_DIVERSITY`，不得得到 prediction PASS。

## Review Focus

- **No-future boundary:** target 同一 seq 或之后生成的 state/event/memory 不得进入 example；Task 2 加边界测试。
- **Session/action linking:** B1 action 本身无 session_id，必须用 source event/session/state 边界确定归属；Task 2 加跨 session fixture。
- **Unseen target probability:** NLL 有有限概率，但 Top-1/HR@3/MRR 不得把 `__UNSEEN__` 当作精确命中；Task 4 加专门测试。
- **Persistence inflation:** Chrome→Chrome 等 self-transition 不得被解释为 sequence understanding；Task 5 加 transition-only/app-switch diagnostics。
- **Memory non-identifiability:** ACTIVE Memory 为 0 或 exposure 不足时必须返回 `INSUFFICIENT_MEMORY_EXPOSURE`；Task 7 加 0-memory 与低覆盖测试。

---

### Task 1: Prediction Domain Models and Frozen Config

**Files:**
- Create: `src/personal_predictive_ai/prediction/__init__.py`
- Create: `src/personal_predictive_ai/prediction/models.py`
- Create: `src/personal_predictive_ai/prediction/config.py`
- Test: `tests/prediction/test_models_config.py`

**Interfaces:**
- Produces `TargetSpace(str, Enum)` with `APPLICATION`, `OPERATION`, `JOINT`.
- Produces frozen Pydantic models: `StructuredContext`, `PredictionExample`, `PredictionVocabulary`, `PredictionDistribution`, `PredictionFold`, `ValidityDecision`, `MetricReport`, `GateDecision`.
- Produces `PredictionConfigV1` with exact C0 thresholds, suffix ks `(1,2,3,5)`, unseen token `"__UNSEEN__"`, primary metric `"nll"`, NLL floor/effect rule, and C3 exposure thresholds from the spec.
- `StructuredContext` stores only structured allowlisted fields: foreground application, previous operation, last 3 joint labels, sorted active process names, sorted recent exogenous event types, idle bucket, optional time-of-day bucket. No free-text window/UI fields.

- [ ] **Step 1: Write failing schema/config tests**
  - Assert models reject unknown fields (`extra="forbid"`) and are frozen.
  - Assert `PredictionConfigV1()` exposes the exact frozen thresholds from the spec.
  - Assert `StructuredContext` has no field for exact key text, window title, screenshot, clipboard, UI text.

- [ ] **Step 2: Run targeted tests and verify failure**
  - Run: `pytest tests/prediction/test_models_config.py -v`
  - Expected: FAIL because prediction package/models do not exist.

- [ ] **Step 3: Implement minimal models/config**
  - Keep schemas strict JSON-safe and deterministic.
  - Do not add persistence or evaluation logic yet.

- [ ] **Step 4: Run targeted tests and Ruff**
  - Run: `pytest tests/prediction/test_models_config.py -v && ruff check src/personal_predictive_ai/prediction tests/prediction/test_models_config.py`
  - Expected: PASS.

- [ ] **Step 5: Commit**
  - `git add src/personal_predictive_ai/prediction tests/prediction/test_models_config.py && git commit -m "feat: add milestone c prediction contracts"`.

### Task 2: Leakage-safe Dataset Builder

**Files:**
- Create: `src/personal_predictive_ai/prediction/dataset.py`
- Test: `tests/prediction/test_dataset.py`

**Interfaces:**
- Consumes `DerivedStore.iter_actions`, `iter_snapshots`, `iter_sessions` and frozen models from Task 1.
- Produces `build_prediction_examples(actions, snapshots, sessions, *, target_space: TargetSpace) -> list[PredictionExample]`.
- Produces `target_label(action, target_space) -> str | None` and deterministic joint encoding `application + "::" + operation`.
- Each example uses the latest snapshot with `snapshot.monotonic_seq < target.monotonic_seq`; never `<=`.
- Session membership is determined from `SessionSegment.start_ns <= action.timestamp_ns <= end_ns`; ambiguous/missing membership is excluded with a reason count, never guessed.
- Only `HUMAN_PHYSICAL` actions enter the formal dataset.
- Recent history includes only prior eligible actions from the same session.
- `recent_exogenous_event_types` remains empty with availability=`UNAVAILABLE_FROM_B1_V1` unless a future versioned B1 schema exposes safe event types; Task 2 must not resolve canonical/raw payloads.

- [ ] **Step 1: Write failing tests for provenance/session/future boundaries**
  - Target at seq 10 must not see snapshot seq 10 or 11.
  - An `AI_EXECUTED` target is excluded.
  - First action of a new session must not inherit recent actions from prior session.
  - Free-text state fields never appear in serialized `PredictionExample`.

- [ ] **Step 2: Verify RED**
  - Run: `pytest tests/prediction/test_dataset.py -v`
  - Expected: FAIL because builder is missing.

- [ ] **Step 3: Implement minimal dataset construction**
  - Use sorted-by-seq scans; no quadratic full-log lookahead.
  - Keep exclusion counters available for manifest generation.

- [ ] **Step 4: Verify GREEN**
  - Run: `pytest tests/prediction/test_dataset.py -v`
  - Expected: PASS.

- [ ] **Step 5: Commit**
  - `git add src/personal_predictive_ai/prediction/dataset.py tests/prediction/test_dataset.py && git commit -m "feat: build leakage-safe prediction examples"`.

### Task 3: Chronological Splits and C0 Validity Audit

**Files:**
- Create: `src/personal_predictive_ai/prediction/splits.py`
- Create: `src/personal_predictive_ai/prediction/validity.py`
- Test: `tests/prediction/test_splits_validity.py`

**Interfaces:**
- Produces `build_session_forward_folds(examples, *, min_train_sessions=2) -> list[PredictionFold]`.
- Produces `audit_validity(examples, folds, config) -> ValidityAuditReport`.
- C0 report includes sessions, eligible targets, class count, dominant ratio, Shannon entropy, normalized entropy, effective classes, full-prefix duplicate/unseen rates, suffix-k duplicate/unseen rates for k=1/2/3/5, conditional entropy, deterministic-prefix fraction, multi-continuation fraction, diagnostic test-oracle ceiling.
- Single-session data returns `NON_GENERALIZATION_DIAGNOSTIC`; a target space failing frozen diversity thresholds returns `INSUFFICIENT_PREDICTIVE_DIVERSITY` and prevents model comparison.

- [ ] **Step 1: Write failing split and validity tests**
  - Sessions must never be split across train/test.
  - Folds must advance only forward in time.
  - Construct 182 identical one-session labels and assert `INSUFFICIENT_PREDICTIVE_DIVERSITY`.
  - Construct a valid 4-session, 3-class fixture and assert C0 PASS.
  - Assert full-prefix and suffix-k leakage are reported separately.

- [ ] **Step 2: Verify RED**
  - Run: `pytest tests/prediction/test_splits_validity.py -v`

- [ ] **Step 3: Implement split/audit logic**
  - Test-oracle ceiling must be marked diagnostic-only and never exposed as a predictor candidate.

- [ ] **Step 4: Verify GREEN**
  - Run: `pytest tests/prediction/test_splits_validity.py -v`

- [ ] **Step 5: Commit**
  - `git add src/personal_predictive_ai/prediction tests/prediction/test_splits_validity.py && git commit -m "feat: add predictive validity audit"`.

### Task 4: Probability Vocabulary, Metrics, and Decision Protocol

**Files:**
- Create: `src/personal_predictive_ai/prediction/metrics.py`
- Create: `src/personal_predictive_ai/prediction/decision.py`
- Test: `tests/prediction/test_metrics_decision.py`

**Interfaces:**
- Produces `build_vocabulary(train_examples) -> PredictionVocabulary`.
- Produces `score_predictions(examples, distributions, vocabulary) -> MetricReport` with Top-1, HitRate@3, MRR, NLL, Macro-F1, coverage, unseen-target rate.
- Produces `transition_only_slice(examples) -> list[PredictionExample]`.
- Produces `nll_effect_threshold(reference_nll: float) -> float` using `max(0.01, 0.01 * reference_nll)`.
- Produces `evaluate_gate(candidate_reports, reference_reports, *, independent_test_sessions: int) -> GateDecision` implementing fold direction consistency, median Delta_NLL threshold, and `DESCRIPTIVE_ONLY` when independent test sessions < 5.

- [ ] **Step 1: Write failing metric/gate tests**
  - Unseen concrete target consumes `__UNSEEN__` probability for finite NLL but is a miss for Top-1/HR@3/MRR.
  - Two folds require positive Delta_NLL in both.
  - Three folds require positive Delta_NLL in at least two and median >= tau.
  - Secondary metric improvements cannot turn an NLL failure into PASS.
  - Four independent sessions => inferential status `DESCRIPTIVE_ONLY`.

- [ ] **Step 2: Verify RED**
  - Run: `pytest tests/prediction/test_metrics_decision.py -v`

- [ ] **Step 3: Implement deterministic metric and gate functions**
  - Use epsilon/frozen unseen mass only from training-side predictor output; metrics must not inspect test frequency.

- [ ] **Step 4: Verify GREEN**
  - Run: `pytest tests/prediction/test_metrics_decision.py -v`

- [ ] **Step 5: Commit**
  - `git add src/personal_predictive_ai/prediction tests/prediction/test_metrics_decision.py && git commit -m "feat: add prediction metrics and frozen gates"`.

### Task 5: C1 Strong Non-neural Baselines

**Files:**
- Create: `src/personal_predictive_ai/prediction/baselines.py`
- Test: `tests/prediction/test_baselines.py`

**Interfaces:**
- Define protocol `Predictor.fit(train_examples, vocabulary)` and `predict(example) -> PredictionDistribution`.
- Implement `GlobalFrequencyPredictor`, `PersistencePredictor`, `ContextualFrequencyPredictor`, `BigramPredictor`, `TrigramBackoffPredictor`.
- Trigram uses deterministic absolute-discount/backoff behavior with all smoothing constants frozen in `PredictionConfigV1`; no test tuning.
- Produces `select_action_only_baseline(validation_reports) -> str` using validation NLL only with deterministic lexical tie-break.

- [ ] **Step 1: Write failing baseline tests**
  - Global distribution sums to 1.
  - Persistence predicts prior label but safely backs off when unavailable/unseen.
  - Bigram/trigram never read future/test counts.
  - Trigram unseen context backs off deterministically.
  - Selection chooses validation-lowest NLL even when another model has better test/secondary metrics.
  - Transition-only diagnostic exposes a persistence-heavy fixture that looks strong on all-sample accuracy but weak on switches.

- [ ] **Step 2: Verify RED**
  - Run: `pytest tests/prediction/test_baselines.py -v`

- [ ] **Step 3: Implement minimal predictors**
  - No learned libraries or random state.

- [ ] **Step 4: Verify GREEN**
  - Run: `pytest tests/prediction/test_baselines.py -v`

- [ ] **Step 5: Commit**
  - `git add src/personal_predictive_ai/prediction/baselines.py tests/prediction/test_baselines.py && git commit -m "feat: add strong non-neural prediction baselines"`.

### Task 6: C2 Structured Retrieval

**Files:**
- Create: `src/personal_predictive_ai/prediction/retrieval.py`
- Test: `tests/prediction/test_retrieval.py`

**Interfaces:**
- Produces `structured_similarity(query: StructuredContext, candidate: StructuredContext, config) -> float`.
- Produces `StructuredRetrievalPredictor(top_k, weights, config)` implementing fit/predict.
- Similarity components are exact categorical match + Jaccard(set fields) + suffix action sequence match; weights are frozen in config/validation and never test-tuned.
- Retrieval pool contains train examples only for each fold.
- Weighted next-target vote returns a full distribution with deterministic backoff to Global Frequency when no usable neighbor exists.

- [ ] **Step 1: Write failing retrieval tests**
  - Test example cannot retrieve itself or any validation/test future example.
  - Similarity is deterministic and ignores disallowed text fields.
  - Empty-neighbor case backs off to Global Frequency.
  - Same train set/order permutations produce identical predictions.

- [ ] **Step 2: Verify RED**
  - Run: `pytest tests/prediction/test_retrieval.py -v`

- [ ] **Step 3: Implement retrieval predictor**

- [ ] **Step 4: Verify GREEN**
  - Run: `pytest tests/prediction/test_retrieval.py -v`

- [ ] **Step 5: Commit**
  - `git add src/personal_predictive_ai/prediction/retrieval.py tests/prediction/test_retrieval.py && git commit -m "feat: add structured retrieval predictor"`.

### Task 7: C3 B2 Memory Features and Exposure Gate

**Files:**
- Create: `src/personal_predictive_ai/memory/reconstruction.py`
- Modify: `src/personal_predictive_ai/diagnostics/memory_replay.py`
- Create: `src/personal_predictive_ai/prediction/memory_features.py`
- Test: `tests/memory/test_reconstruction.py`
- Test: `tests/prediction/test_memory_features.py`

**Interfaces:**
- Adds a pure B2 prefix reconstruction primitive `build_b2_snapshot(db_path, *, source_b1_run_id, source_high_water, config) -> B2Snapshot`; refactor existing `derive_b2` to call the same primitive so full-run B2 behavior stays byte/semantic compatible.
- C3 builds one in-memory B2 snapshot per evaluation fold using only the fold training high-water; it never queries a full-log B2 run across the test cutoff.
- Consumes `MemoryQuery`/`retrieve_memories` only over that prefix-safe snapshot.
- Produces `memory_features_for_example(example, snapshot, *, allowed_provenance, limit) -> tuple[MemoryFeature, ...]` with historical/as-of query semantics; CANDIDATE/NEEDS_REVALIDATION remain excluded.
- Produces `audit_memory_exposure(examples_with_features, config) -> MemoryExposureReport`.
- Produces `MemoryAugmentedRetrievalPredictor` that is identical to frozen Structured Retrieval except for added structured Memory similarity/features.
- Persisted prediction artifacts may store memory IDs, kind/key, confidence, scope rank, but not raw evidence payload/audit text.

- [ ] **Step 1: Write failing memory tests**
  - CANDIDATE/NEEDS_REVALIDATION memories never appear.
  - Full-log B2 evidence beyond the fold train high-water never enters the fold snapshot.
  - Memory valid only after target timestamp never appears.
  - Zero ACTIVE memories => `INSUFFICIENT_MEMORY_EXPOSURE`, not `NO_NONREDUNDANT_MEMORY_GAIN`.
  - Low coverage or one exposed session also => `INSUFFICIENT_MEMORY_EXPOSURE`.
  - Exposure threshold fixture with 40+ samples, >=20% coverage, >=2 sessions, >=2 IDs passes eligibility.

- [ ] **Step 2: Verify RED**
  - Run: `pytest tests/memory/test_reconstruction.py tests/prediction/test_memory_features.py -v`

- [ ] **Step 3: Implement prefix-safe B2 reconstruction, then as-of gated Memory feature extraction/exposure audit**
  - Full-run `derive_b2` must delegate to the same reconstruction primitive to prevent semantic drift between production B2 and benchmark B2.

- [ ] **Step 4: Verify GREEN and B2 compatibility**
  - Run: `pytest tests/memory/test_reconstruction.py tests/prediction/test_memory_features.py tests/integration/test_b2_reconstruction.py -v`

- [ ] **Step 5: Commit**
  - `git add src/personal_predictive_ai/memory/reconstruction.py src/personal_predictive_ai/diagnostics/memory_replay.py src/personal_predictive_ai/prediction/memory_features.py tests/memory/test_reconstruction.py tests/prediction/test_memory_features.py && git commit -m "feat: add gated memory prediction ablation"`.

### Task 8: Benchmark Orchestrator, Deterministic Artifacts, and CLI

**Files:**
- Create: `src/personal_predictive_ai/prediction/artifacts.py`
- Create: `src/personal_predictive_ai/prediction/benchmark.py`
- Modify: `src/personal_predictive_ai/cli.py`
- Test: `tests/prediction/test_artifacts_benchmark.py`
- Test: `tests/integration/test_c_cli.py`

**Interfaces:**
- Produces `run_milestone_c(db_path, *, source_b1_run_id, source_b2_run_id: str | None, run_id, output_root) -> BenchmarkSummary`.
- Artifact directory: `<data_dir>/prediction_runs/<run_id>/`.
- Writes deterministic UTF-8 sorted JSON/JSONL: `dataset_manifest.json`, `validity_audit.json`, `split_manifest.json`, `baseline_predictions.jsonl`, `metrics.json`, `ablation.json`.
- Every run records source B1/B2 IDs, source high-water, split boundaries, config/schema/predictor/metric versions.
- CLI command: `ppa benchmark-c --source-b1-run-id ... --run-id ... [--source-b2-run-id ...]`.
- C0 failure must short-circuit C1/C2/C3 formal comparison while still writing audit/manifest artifacts.

- [ ] **Step 1: Write failing artifact/CLI tests**
  - Same source/config/run inputs produce byte-identical artifacts across rerun.
  - C0 fail writes validity report and no fake model PASS.
  - Artifact JSON does not contain key sentinel/window-title/screenshot/raw path sentinel.
  - CLI returns JSON summary with explicit target-space statuses.

- [ ] **Step 2: Verify RED**
  - Run: `pytest tests/prediction/test_artifacts_benchmark.py tests/integration/test_c_cli.py -v`

- [ ] **Step 3: Implement orchestrator/artifact writer/CLI path**
  - Do not mutate canonical/B1/B2 tables.

- [ ] **Step 4: Verify GREEN**
  - Run: `pytest tests/prediction/test_artifacts_benchmark.py tests/integration/test_c_cli.py -v`

- [ ] **Step 5: Commit**
  - `git add src/personal_predictive_ai/prediction src/personal_predictive_ai/cli.py tests/prediction/test_artifacts_benchmark.py tests/integration/test_c_cli.py && git commit -m "feat: add milestone c benchmark runner"`.

### Task 9: Real Qualification Regression and Full Verification

**Files:**
- Create: `tests/integration/test_c_real_shape_regression.py`
- Create: `docs/milestones/MILESTONE_C_ACCEPTANCE.md` only after implementation evidence exists.
- Modify: `docs/PROJECT_VISION_AND_PROGRESS_CN.md` only after verification.

**Interfaces:**
- Regression fixture mirrors the known real qualification shape: 182 eligible actions, 1 session, all `chrome.exe/key_input`.
- Expected decision for Application/Operation/Joint: C0 audit completes, formal comparison blocked, status includes `INSUFFICIENT_PREDICTIVE_DIVERSITY` / `NON_GENERALIZATION_DIAGNOSTIC` as applicable.
- Final verification must prove deterministic rerun, source immutability, privacy sentinels absent, and existing B1/B2 suite unaffected.

- [ ] **Step 1: Write the real-shape regression test**
  - Assert the degenerate 182/182 fixture cannot produce prediction PASS.

- [ ] **Step 2: Run new Milestone C suite**
  - Run: `pytest tests/prediction tests/integration/test_c_cli.py tests/integration/test_c_real_shape_regression.py -v`
  - Expected: PASS.

- [ ] **Step 3: Run complete regression suite**
  - Run: `pytest -q`
  - Expected: all existing tests plus C tests pass; only the pre-existing native physical-input skip is acceptable unless environment supplies physical input.

- [ ] **Step 4: Run static/repository checks**
  - Run: `ruff check src tests`
  - Run: `git diff --check`
  - Expected: PASS.

- [ ] **Step 5: Native real-data qualification**
  - Run against `E:\Experiment\personal-predictive-ai-runtime\captures\2026-10-07-b2-qualification\events.db` using the frozen real B1/B2 run IDs.
  - Expected: C0 audit completes; no target space claims formal predictive success; source canonical/B1/B2 hashes unchanged before/after.
  - If the path/run IDs are absent on the executing machine, mark this single step `ENVIRONMENT_BLOCKED` and do not replace it with synthetic evidence.

- [ ] **Step 6: Write acceptance evidence only from observed outputs**
  - Record exact test counts, C0 statuses, deterministic artifact hashes, source hashes, privacy checks, and any blocked native qualification.
  - Do not pre-write success language.

- [ ] **Step 7: Commit**
  - `git add tests/integration/test_c_real_shape_regression.py docs/milestones/MILESTONE_C_ACCEPTANCE.md docs/PROJECT_VISION_AND_PROGRESS_CN.md && git commit -m "test: qualify milestone c predictive benchmark"`.

## Plan Self-review Result

- **Spec coverage:** C0 validity, chronological split, C1 B0–B4, unseen probability contract, metrics, NLL gate, C2 retrieval, C3 Memory exposure/value, drift-compatible fold artifacts, privacy/provenance, current-real-data negative control all have owning tasks.
- **Type consistency:** Dataset → folds/validity → vocabulary/metrics → predictors → retrieval → Memory → benchmark uses one `PredictionExample`/`PredictionDistribution` contract.
- **Selection leakage:** Explicitly prevented by validation-only baseline/config selection and train-only retrieval pools.
- **Statistical discipline:** Engineering gate and inferential status are separate; no row-i.i.d. bootstrap path is planned.
- **YAGNI:** No learned model, vector DB, new database migration, autonomous execution, concrete text/mouse-coordinate prediction, or online adaptation in Milestone C V1.

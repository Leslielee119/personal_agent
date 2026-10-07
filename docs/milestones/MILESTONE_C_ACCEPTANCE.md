# Milestone C — Validity-first Predictive Benchmark Acceptance

Date: 2026-10-07
Branch: `feat/milestone-c-predictive-benchmark`
Scope: leakage-safe next-action validity audit, non-neural baselines, structured retrieval, prefix-safe B2 Memory ablation, deterministic benchmark artifacts and CLI. No GRU/LSTM/Transformer/SSM, embedding/vector retrieval, LLM prediction, concrete text generation, mouse-coordinate prediction, or autonomous execution.

## Overall status

**IMPLEMENTATION QUALIFIED — REAL QUALIFICATION DATA IS INSUFFICIENT FOR FORMAL PREDICTIVE COMPARISON.**

Milestone C V1 now provides a deterministic, replayable benchmark that first asks whether the available personal-behavior data is valid for prediction before comparing models. The implementation passes automated regression/static checks and a native replay on the frozen B2 qualification database. The real capture is intentionally rejected at C0 because it contains only one session, 182 eligible actions, and one effective class in every target space.

This is a benchmark qualification success, not a predictive-model success claim. The current data cannot establish either presence or absence of stable sequence, structured-state, or B2 Memory gain.

## Implemented benchmark stack

C now provides:

- strict/frozen prediction schemas and `ppa.prediction-config/v1`;
- Application / Operation / Joint target spaces;
- HUMAN_PHYSICAL-only formal targets;
- strict pre-target state boundary (`source_seq < target_seq`);
- same-session history only;
- no canonical/raw-event fallback for unavailable B1 exogenous event types;
- chronological/session-forward rolling folds;
- C0 diversity, leakage, ambiguity and empirical-ceiling audit;
- training-only vocabulary plus reserved `__UNSEEN__` probability mass;
- Top-1, HitRate@3, MRR, NLL, Macro-F1, coverage and unseen-target metrics;
- NLL-only primary decision protocol with frozen minimum effect threshold;
- Global Frequency, Persistence, Contextual Frequency, Bigram and Trigram-backoff baselines;
- transition-only persistence diagnostic;
- one validation-selected action-only baseline family frozen across all rolling test folds per target space;
- interpretable structured retrieval with frozen similarity weights;
- per-fold target/application distribution drift, unseen-prefix, retrieval-neighbor-similarity and B2 ACTIVE-Memory-change diagnostics;
- prefix-safe B2 reconstruction per fold;
- historical/as-of Memory feature gating;
- explicit Memory exposure eligibility gate evaluated before any Memory-augmented predictor is scored;
- Memory-augmented retrieval whose only additional signal is Memory similarity;
- deterministic JSON/JSONL artifacts carrying explicit config/predictor/metric versions;
- `ppa benchmark-c` CLI path.

## Frozen V1 validity gates

Operation/Joint formal model comparison requires all of:

- eligible sessions >= 4;
- eligible target actions >= 200;
- target classes >= 3;
- dominant-class ratio <= 0.90;
- normalized entropy >= 0.25;
- chronological test classes >= 2;
- chronological test samples >= 40.

Application is auxiliary and must have at least two classes before any application-prediction success claim.

Gate 1–3 use per-sample NLL as the primary decision metric. Candidate improvement is:

`Delta_NLL = NLL_reference - NLL_candidate`.

The minimum engineering effect is frozen as:

`tau_NLL = max(0.01 nats, 0.01 * NLL_reference)`.

Secondary metrics cannot rescue a failed NLL gate. Baseline/config selection uses validation only; test is not reused for model selection or tuning.

C3 Memory value is identifiable only if all hold:

- memory-available samples >= 40;
- memory coverage >= 0.20;
- exposed test sessions >= 2;
- distinct ACTIVE Memory IDs >= 2.

Otherwise C3 reports `INSUFFICIENT_MEMORY_EXPOSURE`, not `NO_NONREDUNDANT_MEMORY_GAIN`.

## Important validity rulings

1. **No same-seq or future state.** A target at sequence `t` can consume only state/evidence with sequence `< t`.
2. **Session boundaries are hard boundaries.** The first action of a new session cannot inherit action history from a previous session.
3. **`__UNSEEN__` is probability accounting, not a correct class prediction.** It can provide finite NLL mass but never counts as an exact Top-1/HitRate/MRR hit for a concrete unseen label.
4. **Persistence is an explicit baseline.** Repeated Chrome/key-input behavior cannot be interpreted as sequence understanding without transition-only diagnostics.
5. **No full-log Memory back-prediction.** C3 reconstructs B2 from each fold's training high-water and then performs historical/as-of retrieval.
6. **B2 production and benchmark reconstruction share one primitive.** Existing `derive-b2` delegates to the same reconstruction path used by C3, preventing semantic drift.
7. **Unavailable B1 fields remain unavailable.** C does not bypass B1 to recover raw/canonical exogenous payloads.
8. **Engineering gate and statistical claim are separate.** Fewer than five independent test sessions remain `DESCRIPTIVE_ONLY`; no action-row iid bootstrap is used.

## Automated qualification

Fresh verification before this acceptance update:

- Milestone C focused suite: **43 passed**;
- complete repository suite: **218 passed, 1 skipped**;
- Ruff: **PASS**;
- `git diff --check`: **PASS**.

The complete suite includes existing B1/B2 reconstruction and storage tests; no B1/B2 regression was observed. The one skip is the existing native physical-input smoke when no physical input occurs during its observation window.

## Real-data qualification

Source database:

`E:\Experiment\personal-predictive-ai-runtime\captures\2026-10-07-b2-qualification\events.db`

Frozen source runs:

- B1: `real-b1-20261007`, source high-water **391**;
- B2: `real-b2-20261007`, source high-water **391**.

C run:

- run ID: `real-c-20261007`;
- artifacts were written only to the isolated worktree qualification directory, not to the capture directory.

The formal C dataset contains, for each of Application / Operation / Joint:

- eligible HUMAN_PHYSICAL examples: **182**;
- sessions: **1**;
- classes: **1**;
- dominant-class ratio: **1.0**;
- normalized entropy: **0.0**;
- rolling folds: **0**;
- generalization status: `NON_GENERALIZATION_DIAGNOSTIC`.

All three target spaces therefore returned:

`INSUFFICIENT_PREDICTIVE_DIVERSITY`.

C1/C2/C3 formal comparison was correctly blocked by C0. No predictor PASS, `NO_STABLE_SEQUENCE_SIGNAL`, `NO_NONREDUNDANT_STATE_GAIN`, or `NO_NONREDUNDANT_MEMORY_GAIN` conclusion is permitted from this capture because the prerequisite data-validity gate did not pass.

## Deterministic artifact evidence

The same real C run was executed twice with identical source/config/run ID. All six artifacts were byte-identical across reruns:

- `ablation.json`: `f226621955134169b3955c625652d66d7029273618b1cb3f87153cc51ae5950a`;
- `baseline_predictions.jsonl`: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
- `dataset_manifest.json`: `dd9f9fc840cce1904dfdf53317f37240ba44b71a6a3915612cb053b0a0aa7b89`;
- `metrics.json`: `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`;
- `split_manifest.json`: `951c085a06777b315e95bdf272e183400fc05d2b4caf03016617174d418168a6`;
- `validity_audit.json`: `b2b262c91f6d8396b7b8a52f3a8ab48284162406512519358e544937afd22567`.

`baseline_predictions.jsonl` is intentionally empty because C0 blocked model comparison.

## Source immutability evidence

The database file SHA-256 was identical before and after both benchmark runs:

`0961ec1eadf1c2402f27fafda3f3cba9e6f835ad778d72eb5b5df42b161b78df`.

Relevant source table hashes also remained identical before/after:

- `canonical_events`: `29b828efbecfac36ecdbdeea21814918dccdea8b762645522df7a271bb399fc7`;
- `derived_runs`: `9c626926719ce877efbf7b35aaef504bec6333f0dd7f072304a308b14d069a1a`;
- `b1_state_snapshots`: `bd7af90f844cefe74aa82b59a3e38cbf713648db0b57d8449b7fdc8bd6245ce2`;
- `b1_actions`: `c231232a0a471795bff88aad83cd075f7e671a20c8f9290eda57114c2b3652a7`;
- `b1_sessions`: `65c82784471191d72cd36de70df76e5fc78dcd1738396563a3ef240d88000422`;
- `b1_transitions`: `12915a137f7539f112d9c1cedba3f81d4a6660df5b7e48b28febc211a42433da`;
- `memory_runs`: `d075483b18f73fd8b55018c455db65753a6c15b69b7dd1d7505fe74ca5836039`;
- `memory_records`: `e9753e6e3885d7c4cbb9097508391eddcb18ccaddb593d469553749cd5631ca6`;
- `memory_evidence_links`: `c5ebada46c4eefa4da1bd0f9657066febfcc02f365f3cb593c8cfcc2bd36e043`;
- `memory_audit_events`: `9bd57387f75a853a55872e1fd08c61481d55e9300d9c24064f8be0e42134fafa`;
- empty `memory_dependencies` and `memory_supersessions`: SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

## Privacy evidence

A scan of all six real prediction artifacts found no occurrences of the forbidden artifact tokens used by the qualification check:

- `canonical_key_char`;
- `window_title`;
- `clipboard`;
- `screenshot`;
- `credential`;
- `password`.

C artifacts therefore contain only the frozen structured prediction representation for this run; exact-key/raw-screen/clipboard/credential material was not promoted into benchmark output.

## Interpretation boundary

The real result must be read as:

> the current capture is too homogeneous and too short longitudinally to support a credible out-of-time prediction experiment.

It must **not** be read as:

- sequence modeling has no value;
- structured state has no value;
- B2 Memory has no value;
- a majority predictor is highly accurate and therefore successful;
- learned GRU/SSM should already be trained.

The next empirical requirement is more diverse, multi-session HUMAN_PHYSICAL data. At minimum the frozen C0 thresholds must become satisfiable before formal C1/C2/C3 conclusions are allowed.

## Relationship to Milestone D and E

Milestone D learned-policy comparison remains gated. It may begin only after C0 passes and Gate 1 demonstrates stable out-of-time sequence signal on at least two rolling test folds, with sufficient independent sessions for the intended claim strength.

Milestone E Personal Knowledge & Verified Skill Plane has a reviewed design, but Behavior-to-Skill discovery should likewise wait for cross-session behavioral evidence; the current one-session `key_input -> key_input` pattern is not sufficient evidence for a reusable personal workflow.

The project's execution safety boundary remains unchanged: read-only analysis can be automatic, while model-initiated local file mutation or computer operation requires human approval.

## Decision

Milestone C V1 is **qualified as a validity-first predictive benchmark implementation**. The current real dataset is **not qualified for formal predictive-model comparison**. No learned-policy or Memory-value claim is made from the current capture.

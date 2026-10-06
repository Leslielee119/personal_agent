# Personal Predictive AI V0 — Architecture Design

Date: 2026-10-06
Status: Design approved in chat; implementation not started
Project root: `E:\Experiment\personal-predictive-ai`

## 1. Product intent

Build a fully local framework that continuously observes a user's personal-computer interaction, learns the user's behavioral dynamics over time, and predicts or completes likely next operations.

The target experience is not "the assistant remembers old conversations." It is: "the system increasingly anticipates what I am about to do."

The framework must support fine-to-coarse prediction across character/token completion, edits, application operations, task-level actions, and eventually workflows.

The framework is model-agnostic. LLMs are optional slow-path semantic interpreters/planners, not the core real-time predictor.

## 2. Hard constraints

1. Runtime is fully offline: no outbound network capability during normal operation.
2. Capture starts broad across the desktop rather than being limited to one application.
3. Broad observation does not imply permanent raw retention.
4. Credential/secure-field content must be suppressed before persistence.
5. V0 predicts and evaluates; it does not autonomously execute desktop actions.
6. Canonical event/state/action contracts belong to this project, not to any third-party collector.
7. Collector, storage, state estimation, prediction, and optional LLM backend must remain replaceable modules.
## 3. Non-goals for V0

V0 will not:
- build a general autonomous desktop agent;
- train a large world model that renders future screen pixels;
- continuously fine-tune a multi-billion-parameter LLM in the hot path;
- permanently store raw screenshots, clipboard contents, or exact keystrokes without policy/TTL controls;
- infer strict causal effects in the Pearl/do-calculus sense;
- optimize for multi-user cloud deployment.

The immediate problem is predictive modeling of one user's local interaction dynamics.

## 4. System model

At time `t`, the system observes computer state and events and predicts a hierarchical next action:

`P(A_{t+1} | S_t, H_t, E_t, U_t)`

Where:
- `S_t`: current structured computer/task state;
- `H_t`: recent interaction history;
- `E_t`: current exogenous/environmental events;
- `U_t`: slowly changing personal habit representation;
- `A_{t+1}`: next user action at one or more hierarchy levels.

State transition is modeled separately as:

`S_{t+1} = F(S_t, A_t, E_{t+1})`

This separation prevents the system from assuming that every next action is caused only by the previous user action.
## 5. Architecture

```text
Windows / Applications
        |
        v
Capture Adapters
(keyboard, mouse, screen, window/UIA, process, filesystem, notifications)
        |
        v
Canonical Event Bus
        |
   +----+------------------+
   |                       |
Raw Ring Buffer      Structured Event Store
(short TTL)               (SQLite)
   |                       |
   +-----------+-----------+
               v
         State Estimator
               |
               v
   Hierarchical Action Predictor
               |
               v
        Prediction Event
               |
               v
     Suggest / Observe Only
               |
               v
        Feedback Event
               |
               v
       Continual Learner
```

A local LLM may be attached beside the predictor as a low-frequency semantic slow path when structured models are uncertain or require interpretation of unseen UI/task states.
## 6. Canonical event contract

Third-party capture schemas are adapters only. The framework stores a versioned canonical event with at least:

```text
CanonicalEvent
- schema_version
- event_id
- timestamp_ns
- monotonic_seq
- source
- modality
- origin: endogenous | exogenous
- event_type
- app/process/window identity
- session_id
- payload
- privacy_tier
- retention_class
- raw_ref (optional)
- causal_parent_ids (optional hypotheses/links, not asserted ground truth)
```

Examples of endogenous events: key input, click, scroll, window switch, file edit, terminal command.

Examples of exogenous events: process completion, notification arrival, externally modified file, build/test result, timer completion, popup/error state.

`causal_parent_ids` records candidate dependency links for later modeling; it must not be interpreted as verified causal truth.

## 7. Capture plane

OpenAdapt Capture is the preferred V0 collection backend candidate because it already provides native input capture, screen frames, Windows UIA structure, timestamps, and MIT-licensed code.

The project adds adapters for process lifecycle, filesystem changes, notifications/system events, and job/timer completion.

Capture is event-driven and multi-rate. Exact input events may be real-time, while screenshots/UI structure are sampled on meaningful triggers such as app switch, click, typing pause, scroll stop, external event, and periodic idle fallback.
## 8. Privacy and retention model

Privacy is enforced before persistence, not only at query time.

Retention classes:
- `ephemeral_raw`: raw screenshots/clipboard/exact-input evidence held in a bounded ring buffer and deleted by TTL;
- `structured_short`: detailed normalized events retained for debugging/model construction for a configurable short period;
- `structured_long`: privacy-reduced action/state events retained for longitudinal learning;
- `never_store`: credential/secure input values and explicitly excluded content.

Rules:
1. Password/secure fields are detected at capture source and their values are discarded before disk write.
2. Authentication events may preserve metadata such as `credential_submit` without preserving credential values.
3. Clipboard contents, exact text input, audio, and screenshots are separate privacy tiers with independent TTLs.
4. User-defined application/window exclusions are evaluated in the capture hot path.
5. All raw references must tolerate the referenced artifact expiring.
6. Structured long-term data must remain useful after raw evidence is deleted.

Zero-network runtime will ultimately be enforced by OS/process policy (for example outbound firewall denial), not merely by application convention.

## 9. Storage model

V0 uses SQLite for structured events and state snapshots, plus a bounded filesystem ring buffer for raw artifacts.

The store is append-oriented. Raw events are immutable once accepted; derived normalized actions, state transitions, labels, predictions, and feedback are separate records linked by IDs.

This preserves the ability to re-run improved normalization/state-estimation logic against historical source events without rewriting evidence.

The database must provide deterministic ordering using `(timestamp_ns, monotonic_seq)` because wall-clock timestamps alone are insufficient during bursts or clock adjustments.
## 10. State estimator

The estimator maintains a compact state `S_t` rather than forcing predictors to replay the complete event log.

V0 state fields include:
- active app/process/window and focus target;
- recent action/event window;
- open/recent files and workspace identity when observable;
- terminal/process state and recent command outcomes when observable;
- UI accessibility summary and optional visual feature references;
- session/task segment identifiers;
- active exogenous events;
- idle/activity level;
- personal habit features accumulated from historical behavior.

State estimation is incremental: `S_t = G(S_{t-1}, event_t)`.

A later recurrent neural state model may augment this representation, but V0 first preserves explicit structured state for debuggability.

## 11. Hierarchical action contract

Actions are represented at multiple levels rather than as one flat vocabulary:

```text
L0 Intent      coding | browsing | file-management | communication | other
L1 Application VSCode | terminal | browser | explorer | ...
L2 Operation   edit | search | open | save | run | switch | copy | navigate | ...
L3 Concrete    command/path/UI element/edit span/shortcut
L4 Fine        next character/token/text span/pointer target
```

A single observed action may have labels at several levels. Predictors may emit distributions at any supported level, with coarse prediction remaining useful when fine-grained confidence is low.

This hierarchy allows code completion, next-edit prediction, application switching, command prediction, and workflow prediction to share one framework without forcing identical representations.
## 12. Predictor strategy for V0

The first implementation deliberately starts with simple baselines before introducing larger neural models:

1. global most-frequent action;
2. per-context frequency model;
3. first-order and higher-order Markov models;
4. retrieval/ranking over similar historical states;
5. GRU/LSTM sequence model;
6. personalized recurrent model with explicit long-term habit features.

Transformer/SSM and local LLM-assisted predictors are deferred until the event/state representation is validated on real data.

The primary comparison is not "small model vs large model". It is whether adding long-term personal history/habit state improves prediction beyond current context and recent history alone.

## 13. Prediction and feedback contract

Every suggestion/prediction is itself an event containing:
- predictor/model version;
- state snapshot reference;
- target action level;
- ranked candidates and confidence;
- latency;
- whether the suggestion was shown to the user.

Feedback records whether the user accepted, partially accepted, ignored, rejected, or performed a different action, plus delay-to-action.

Observed user behavior remains ground truth evidence even when no suggestion was shown. This permits counterfactual-free offline evaluation of the predictor before any UI intervention is introduced.

V0 is suggestion/observation-only: prediction must never automatically synthesize input, click UI elements, or execute shell commands.
## 14. Evaluation

Initial metrics:
- hierarchical Top-1 / Top-k accuracy;
- Mean Reciprocal Rank (MRR);
- negative log-likelihood / calibration where available;
- prediction latency;
- coverage at confidence thresholds;
- per-application and per-action-class performance;
- performance after exogenous interruptions;
- longitudinal gain as personal history accumulates.

Primary hypothesis for the first learning milestone:

`Personal-history model > context/recent-history-only baseline` on held-out chronological segments.

Initial screening gate:
- absolute Top-1 gain of at least 5 percentage points OR MRR gain of at least 0.05 over the strongest non-personal baseline;
- improvement direction consistent across multiple held-out time windows;
- no evaluation leakage from future events into state construction.

These thresholds are engineering screening gates for whether personalization is useful enough to justify more complex models, not claims of statistical causality.

## 15. Engineering acceptance gates

Before training a substantive predictor, the capture/data plane must pass:
- 8 hours continuous collection without crash or unbounded memory growth;
- no outbound network connections during offline runtime validation;
- zero persisted credential/secure-field values in dedicated privacy tests;
- deterministic event ordering and timestamp consistency >= 99.99%;
- idle CPU target < 2%; active capture target < 5-8% sustained on the reference desktop;
- bounded raw-artifact disk growth under configured TTL;
- session reconstruction can explain both user actions and relevant environmental/exogenous events;
- collector failure or raw-artifact expiration cannot corrupt the structured event store.
## 16. Third-party source boundaries

Reference audit location: `E:\Experiment\personal-predictive-ai-sources`.

- OpenAdapt Capture: preferred implementation dependency/candidate for native input/screen/UIA capture; MIT license permits reuse subject to notice requirements.
- Screenpipe: architecture reference only for event-driven capture, privacy filtering, capture throttling, and storage reliability. Current source license restricts commercial/competing-product integration, so no direct code copying into this project.
- ActivityWatch: reference for low-frequency app/window/AFK event concepts and local event storage; MPL-2.0 obligations apply if source is reused.
- NextEditPrediction: Apache-2.0 reference/baseline for edit-history-to-next-edit task construction.
- NeuralOS: research reference for recurrent computer-state modeling. No top-level license was confirmed during audit, so implementation code is not reused unless licensing is clarified.

Third-party objects are translated into the project's canonical contracts at adapter boundaries. Core state/prediction code must not depend directly on third-party event classes.

## 17. Project structure

```text
personal-predictive-ai/
  docs/
  schemas/          canonical versioned contracts
  src/
    collector/      third-party/native capture adapters
    events/         event bus + normalization
    privacy/        source-time suppression + retention policy
    storage/        raw ring + structured SQLite store
    state/          incremental explicit state estimator
    prediction/     baseline and learned predictors
    evaluation/     chronological/offline evaluation
    backends/       optional slow-path models such as local LLMs
  tests/
  experiments/
  data/             runtime data; excluded from source control
```

The initial repository will not vendor upstream source trees; they remain in the separate `personal-predictive-ai-sources` audit directory.
## 18. V0 milestone sequence

Milestone A — Capture/data plane:
- canonical schemas;
- OpenAdapt-based capture adapter;
- endogenous/exogenous event adapters;
- source-time privacy suppression;
- SQLite + raw ring buffer;
- offline/network-denial validation.

Milestone B — State reconstruction:
- incremental structured `S_t`;
- session segmentation;
- state/action replay tools;
- verify that recorded trajectories explain what the user and environment did.

Milestone C — Prediction baselines:
- frequency/Markov/retrieval models;
- chronological splits;
- confidence/calibration and latency metrics.

Milestone D — Personal learning:
- GRU/LSTM baseline;
- slow habit representation;
- compare personal-history vs context-only models;
- continual update strategy only after offline gain is demonstrated.

Milestone E — Suggestion surface:
- passive notification/overlay or application-specific completion surface;
- acceptance/rejection feedback capture;
- still no autonomous execution.

## 19. Risks and fallbacks

- Capture overhead too high: reduce expensive screen/UIA sampling while preserving event observability; never drop the canonical input event stream silently.
- Privacy filters uncertain: default to `never_store`/ephemeral rather than persisting raw content.
- Action taxonomy too brittle: preserve raw events and allow action labels to be recomputed with a new schema version.
- Personal gain is weak: inspect representation/session segmentation before increasing model scale; do not jump directly to an LLM.
- Exogenous event coverage is incomplete: mark unknown environmental transitions explicitly rather than mislabeling them as user-caused.
- Raw data volume is excessive: tighten TTL/dedup/compression without rewriting structured historical events.
- Third-party collector changes: isolate integration in adapters and pin tested versions.

## 20. Frozen V0 decisions

V0 is an event-first, model-agnostic, fully local predictive framework. It observes broadly across the desktop, stores long-term structured behavior rather than unlimited raw surveillance data, explicitly distinguishes endogenous user actions from exogenous environmental events, and predicts rather than acts.

The first proof of value is not a chatbot or agent demo. It is a reliable personal event/state dataset plus measurable next-action prediction gain from accumulated personal history.
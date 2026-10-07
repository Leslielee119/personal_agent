# Personal Predictive Generative System — Architecture Design

Date: 2026-10-06
Status: Design approved in chat; implementation not started
Parent spec: `2026-10-06-personal-predictive-ai-v0-design.md`

## 1. Goal

Extend the local Personal Predictive AI from passive next-action prediction into a system that can both anticipate the user's likely next operation and generate the concrete content needed to complete it. The system remains fully local and model-agnostic. Prediction and generation are deliberately separated so a large generative model is not responsible for deciding every desktop action.

The target behavior is:

`observe -> understand state -> predict intent/action -> generate candidate output -> verify -> suggest -> learn from user response`

The system does not autonomously execute desktop actions in this design stage.

## 2. Core distinction: policy vs generation

The system solves two different problems.

Personal action policy:

`P(A_{t+1} | S_t, H_t, E_t, U_t)`

This answers: what is the user likely to do next, whether the system should suggest anything, what kind of output is needed, and where it applies.

Conditional generation:

`P(Y_t | A_{t+1}, S_t, H_t, R_t, U_t)`

This answers: given the selected action type, what concrete code, text, command, edit, target, or other content should be produced.

`A` is an action proposal. `Y` is the generated content. They must remain separate records and separately evaluable.

## 3. System architecture

```text
Physical Input / OS / Applications
              |
              v
      Canonical Event Plane
              |
              v
       Transition Builder
     (S_t, A_t, X_t, S_t+1)
              |
              v
        State Estimator
              |
      +-------+--------+
      |                |
      v                v
Fast Personal       Slow Personal
Policy State        Habit / Style Memory
      |                |
      +-------+--------+
              v
       Personal Policy
   "what happens next?"
              |
       Action Proposal
              |
      +-------+------------------+
      |          |         |     |
      v          v         v     v
 Code/Text    Command      UI   Other
 Generator    Generator  Target Generator
      |          |         |     |
      +----------+---------+-----+
                 v
         Candidate Outputs
                 |
                 v
             Verifier
                 |
                 v
             Suggestion
                 |
                 v
        User Response / Final Output
                 |
                 v
          Continual Learning
```

A local LLM such as Qwen3.5-4B is a conditional generator/semantic slow path, not the real-time action-policy core.

## 4. Evidence and provenance

Long-term learning must distinguish who caused an event. The canonical event contract should be extended before model training with an explicit actor/provenance field rather than inferring provenance later.

Recommended actor classes:

- `HUMAN_PHYSICAL`: physical keyboard/mouse/touch input attributable to the user;
- `AI_SUGGESTED_ACCEPTED`: user accepted a model suggestion;
- `AI_SUGGESTED_MODIFIED`: user accepted but changed a suggestion;
- `AI_EXECUTED`: future system-generated action, if execution is ever enabled;
- `SYSTEM`: local OS/application event;
- `EXTERNAL`: event caused by a remote or external source when observable;
- `UNKNOWN`: origin cannot be established safely.

The capture layer should preserve device identity/injected flags where available. Exact mouse coordinates, UIA targets, foreground application, screen state, and process state are context attached to input evidence; they are not the definition of the user action itself.

AI-executed actions must never be silently relabeled as human behavior. Default learning weight for `AI_EXECUTED` is zero unless a later feedback protocol explicitly says otherwise.

## 5. Transition as the primary learning unit

The long-term dataset is not merely a list of events. The primary derived example is:

`T_t = (S_t, A_t, X_t, S_{t+1}, provenance)`

where:

- `S_t`: computer/task state before the action;
- `A_t`: user action or action-level label;
- `X_t`: exogenous/system events active during the transition;
- `S_{t+1}`: resulting state;
- `provenance`: who caused the observed action.

Raw events remain immutable evidence. Transition examples are derived artifacts and can be recomputed when state/action labeling improves.

## 6. State model

`S_t` should combine explicit structured state with an optional learned streaming state.

Explicit state includes:

- foreground app/process/window;
- focused UI target when available;
- recent input/action sequence;
- open/recent files and workspace identity;
- process/terminal/job state;
- active exogenous events;
- session/task segment;
- recent visual/UI references;
- elapsed times and idle/activity information.

The first learned streaming state should use a small recurrent model, initially GRU:

`h_t = GRU(h_{t-1}, Enc(event_t))`

GRU is the first neural baseline because the initial dataset is single-user, streaming, comparatively small, and latency-sensitive. SSM/Mamba and small Transformer models are later controlled comparisons, not architecture requirements.

## 7. Personal action policy

The first substantive policy model is:

`P(A_{t+1} | h_t, U_t, E_t)`

where:

- `h_t`: fast recurrent state representing recent seconds/minutes;
- `U_t`: slow personal habit representation;
- `E_t`: explicit exogenous-event features.

The policy should not generate arbitrary text. It emits an `ActionProposal` containing at least:

- target hierarchy level;
- action type;
- target application/context;
- optional semantic intent;
- ranked candidates;
- confidence/calibration information;
- latency;
- generator route, if generation is required.

The first policy experiments must compare:

1. global frequency;
2. contextual frequency;
3. Markov models;
4. retrieval/ranking;
5. GRU without personal habit state;
6. GRU + personal habit state;
7. GRU + personal habit state + exogenous-event features.

Complexity is added only if each component produces measurable incremental value.

## 8. Slow habit and style memory

Personalization is split into behavioral and generative components.

Behavior personalization learns what the user tends to do:

`P(A | S, U_behavior)`

Examples include save -> terminal -> test, or build failure -> inspect traceback.

Generation personalization learns how the user tends to perform an action:

`P(Y | A, S, U_style)`

Examples include preferred command forms, coding style, naming conventions, edit patterns, explanation length, and frequently reused procedural fragments.

The slow memory may initially be a combination of explicit statistics, retrieval indexes, and compact learned embeddings. It should update more slowly than the fast recurrent state and support decay/forgetting for patterns that stop recurring.

## 9. Hierarchical action space

The policy predicts at multiple levels:

```text
L0 Intent       coding | browsing | file-management | communication | other
L1 Application  editor | terminal | browser | explorer | ...
L2 Operation    edit | search | open | save | run | switch | navigate | ...
L3 Concrete     command/path/UI target/edit region/shortcut
L4 Fine         next text span/token/character/pointer target
```

A model may be correct at a coarse level while uncertain at a fine level. Suggestion logic may still use coarse predictions when fine confidence is insufficient.

## 10. Generator layer

Generation is routed by `ActionProposal` rather than invoked for every event.

Initial generator routes:

- `EDIT_TEXT` -> local code/text generator;
- `RUN_COMMAND` -> command generator conditioned on shell/project state;
- `OPEN/NAVIGATE` -> structured target generator/ranker;
- `UI_TARGET` -> UI target ranker using structured UI context;
- unsupported/low-confidence routes -> no suggestion or local LLM slow path.

Qwen3.5-4B is the initial general local generator candidate because it already exists locally and can serve as a code/text/semantic fallback. It is not required on the policy hot path.

Generation context must be task-specific and bounded. The generator should receive the minimum relevant state, retrieval results, and user-style context rather than the entire raw desktop event history.

## 11. Verifier and ranking

Generated output must be treated as a candidate, not truth. A verifier/ranker decides whether to show it.

The verifier can use:

- policy confidence;
- generator likelihood/ranking;
- compatibility with current state and target;
- syntax/parse checks for code/commands where applicable;
- local deterministic safety constraints;
- duplicate/stale-state rejection;
- latency and confidence thresholds.

For V0 suggestion mode, verifier failure means no suggestion. It must not execute a fallback action.

## 12. Feedback and learning records

Every suggestion should record:

- state/transition reference;
- action proposal;
- generated candidate(s);
- whether shown;
- whether accepted, partially accepted, modified, ignored, or rejected;
- final user-produced output when observable;
- delay to final action;
- provenance of all resulting events.

This creates two learning targets:

Behavior target:

`(S_t, H_t, E_t, U_t) -> A_{t+1}`

Generation target:

`(S_t, A_t, Y_suggested) -> Y_user_final`

User actions remain the primary evidence. AI-generated actions do not become positive training labels merely because the system emitted them.

## 13. Evaluation strategy

Policy metrics:

- hierarchical Top-1/Top-k;
- MRR;
- calibration/coverage;
- latency;
- performance around exogenous interruptions;
- chronological personal-history gain.

Generation metrics:

- exact/partial acceptance rate;
- edit distance from suggestion to final output;
- accepted prefix/span length;
- command/code validity where deterministically checkable;
- latency;
- per-generator-route coverage.

System metrics:

- useful suggestion rate;
- false-positive suggestion rate;
- end-to-end latency;
- user interruption cost;
- gain as longitudinal personal data accumulates.

The existing personalization screening gate remains: personal-history models should show at least +5 percentage-point Top-1 or +0.05 MRR over the strongest non-personal baseline before more complex policy models are justified.

## 14. Implementation order

This architecture should be implemented in separate milestones rather than one large model project.

Milestone B1 — provenance + transition foundation:

- extend event contract with actor/provenance/device/injected evidence;
- derive `(S_t, A_t, X_t, S_t+1)` transitions;
- state reconstruction and session segmentation;
- no learned predictor yet.

Milestone C — policy baselines:

- frequency, Markov, retrieval;
- hierarchical labels;
- chronological evaluation.

Milestone D1 — learned personal policy:

- event encoder;
- GRU fast state;
- slow habit features;
- exogenous gate/feature ablation.

Milestone D2 — generation:

- generator routing contract;
- local Qwen3.5-4B code/text/command generation;
- bounded retrieval/style context;
- verifier and candidate ranking.

Milestone E — suggestion + feedback:

- passive suggestion surface;
- acceptance/modification/rejection capture;
- generation-personalization dataset;
- still no autonomous execution.

## 15. Hard boundaries

- No cloud inference or telemetry.
- No autonomous desktop execution in these milestones.
- No training directly from AI-executed actions as if they were human labels.
- No requirement that a single neural model solve state estimation, policy, generation, verification, and memory.
- No raw-history dump into the generator by default.
- No model-scale escalation before simple baselines establish measurable value.

## 16. Relationship to Milestone A

Milestone A remains the evidence/data plane and is not invalidated by this design. Before B1 begins, Milestone A still needs its existing qualification gates: real physical mouse qualification and the formal 8-hour soak. B1 then upgrades the event semantics with provenance and builds transitions/state without changing the principle that raw capture evidence is immutable.

## 17. Frozen direction

The project is now defined as a local **Personal Predictive Generative System**, not merely a memory system or a next-action classifier. The architectural decomposition is:

`State Model + Personal Action Policy + Personal Habit/Style Memory + Conditional Generator + Verifier`

The policy answers what should happen next. The generator creates the concrete output. Personal memory shapes both what the user is likely to do and how the user tends to do it. The verifier decides whether a candidate is suitable to show. Long-term learning is grounded in state transitions and provenance-aware user feedback rather than raw history alone.

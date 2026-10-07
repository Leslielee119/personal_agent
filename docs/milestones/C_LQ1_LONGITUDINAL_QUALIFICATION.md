# C-LQ1 — Longitudinal Qualification Readiness

Milestone C demonstrated that a single short capture is not valid evidence for longitudinal next-action prediction. C-LQ1 therefore measures whether a frozen B1 run contains enough natural, independent sessions to enter screening or confirmatory evaluation. It does not alter any C0 threshold and it does not train a model.

## Data collection rule

Use one persistent local capture directory across normal work sessions. Each independent `ppa capture` start now emits a privacy-safe `runtime.restart` boundary, so repeated captures written to the same `events.db` can become distinct B1 sessions without waiting for the 30-minute inactivity rule.

Do not manufacture actions to satisfy the gate. Browser, IDE, terminal, file, and other normal work should be collected as they naturally occur. A failed readiness gate is evidence about the available behavior abstraction/data, not a prompt to perform scripted behavior.

## Frozen workflow

1. Run a normal capture into the persistent data directory.
2. Stop capture before reconstruction/audit.
3. Rebuild B1 over the accumulated database with a new run ID.
4. Run the read-only readiness command against that frozen B1 run.
5. Only run `benchmark-c` when the target space of interest is ready for the intended evaluation level.

Example:

```powershell
ppa --data-dir E:\Experiment\personal-predictive-ai-runtime\longitudinal capture --duration 1800
ppa --data-dir E:\Experiment\personal-predictive-ai-runtime\longitudinal derive-b1 --run-id longitudinal-b1-v1
ppa --data-dir E:\Experiment\personal-predictive-ai-runtime\longitudinal longitudinal-status --source-b1-run-id longitudinal-b1-v1
```

`longitudinal-status` opens the SQLite database read-only, creates no prediction artifacts, and does not modify C0 thresholds.

## Readiness meanings

For every Application / Operation / Joint target space the report includes: eligible HUMAN_PHYSICAL actions, session count, class count, dominant-class ratio, normalized entropy, C0 status/reasons, rolling test fold count, and independent test session count.

`SCREENING_READY` means that target space has at least 5 sessions and at least 2 rolling test folds. It only means that a minimum longitudinal screening can be attempted; C0 remains a separate validity gate.

`CONFIRMATORY_READY` means that target space has at least 8 sessions, at least 5 independent rolling test sessions, and C0 is PASS. This is the minimum state in which the frozen Milestone C protocol labels inference as confirmatory-eligible.

The aggregate report is ready when at least one target space is ready. It also lists exactly which target spaces satisfy each level.

## What this does not authorize

C-LQ1 does not start GRU/SSM training, does not relax class/diversity thresholds, and does not interpret repeated low-level `key_input -> key_input` behavior as evidence of useful prediction. Learned Milestone D remains blocked until the frozen Milestone C gates establish stable sequence signal on valid longitudinal data.

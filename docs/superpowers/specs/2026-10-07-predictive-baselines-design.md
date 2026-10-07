# Milestone C — Predictive Baselines Design

日期：2026-10-07
状态：Approved for implementation planning after final validity review

## 1. 目标

Milestone C 的目标不是立即追求高准确率，也不是证明某个复杂模型优于简单模型。

目标是建立一个可信、可重放、无未来信息泄漏的个人下一动作预测基准，并回答四个问题：

1. 当前行为表示是否具有足够预测多样性？
2. 仅靠短期动作历史，能否预测下一个动作？
3. 结构化电脑状态是否提供超出 action-only sequence 的增益？
4. B2 provenance-aware temporal Memory 是否提供独立的长期预测增益？

只有这些问题中至少前两层得到可靠正证据后，才值得进入 learned GRU/SSM。

## 2. 非目标

C V1 明确不做：

- GRU/LSTM/Transformer/SSM 训练；
- LLM next-action prediction；
- embedding/vector retrieval；
- concrete text generation；
- mouse-coordinate prediction；
- autonomous execution；
- 为了提高 benchmark 分数而修改 B1 label abstraction。

这些内容都在 C 之后。

## 3. 研究依据

完整调研见：

`docs/research/2026-10-07-predictive-action-research-scan.md`

设计重点吸收四类已有经验：

- Predictive Process Monitoring：prefix leakage、temporal split、accuracy limit、trigram strong baseline；
- Session-based Recommendation：HitRate/MRR/NDCG、rolling/sliding evaluation；
- UI-Vision：桌面 action prediction 应按动作层级/类型分开评估；
- Retrieval-Augmented Next Activity Prediction：retrieval 是合理 baseline，但 concept drift 和 interleaving sensitivity 必须单独考虑。

我们不把 next-activity prediction 本身作为创新点。

## 4. 输入数据合同

C 只能消费已经冻结的 B1/B2 派生数据。

单个预测样本定义为：

```text
PredictionExample
  sample_id
  source_b1_run_id
  session_id
  cutoff_seq
  pre_state
  recent_actions
  eligible_exogenous_context
  eligible_memory_ids
  target_action
```

形式上：

\[
(S_t, H_t, X_t, M_t) \rightarrow A_t
\]

其中所有输入都必须满足 `source_seq < target_action.monotonic_seq`。

### 4.1 Target

C V1 使用三个预测任务：

```text
T1 Application
T2 Operation
T3 Joint(Application, Operation)
```

不使用 `concrete` 或 `fine` 作为目标。

### 4.2 Eligible target provenance

默认只把自然用户行为作为 target：

- `HUMAN_PHYSICAL`：eligible；
- `AI_SUGGESTED_ACCEPTED`：单独报告，不进入 V1 主结果；
- `AI_SUGGESTED_MODIFIED`：单独报告，不进入 V1 主结果；
- `AI_EXECUTED`：禁止作为“用户自然行为”target；
- `SYSTEM/EXTERNAL/UNKNOWN`：禁止作为用户 action target。

这防止未来 Agent 自己制造训练标签。

## 5. 无未来信息原则

这是 C 的最高优先级约束。

对 cutoff `t`：

```text
allowed evidence seq < t
forbidden evidence seq >= t
```

B2 Memory 也必须按预测时点重建或历史查询：

```text
MemoryQuery(as_of = timestamp_before_target)
```

禁止：

1. 先用完整日志构造 Memory，再回头预测早期动作；
2. 用 post-state 预测产生它的 action；
3. 用目标 action 所触发的 screenshot/UIA/process event；
4. 用 test-session 统计构造 train-side context frequency。

## 6. C0 — Predictive Validity Audit

C0 在任何模型评分之前运行。

### 6.1 基础规模

分别统计：

- sessions；
- eligible target actions；
- application classes；
- operation classes；
- joint classes；
- train/validation/test target coverage。

### 6.2 Target diversity

对每个 target space 计算：

- dominant class ratio；
- Shannon entropy；
- normalized entropy；
- effective number of classes `exp(H)`。

如果 dominant class ratio 极高，benchmark 必须明确标记 label collapse。

### 6.3 Prefix leakage

同时报告两类 signature：

```text
full available Joint(Application, Operation) prefix
last-k Joint(Application, Operation) suffix
```

suffix 至少报告 `k = 1, 2, 3, 5`。

full-prefix leakage 更接近 PPM 文献对 duplicate prefix 的定义；suffix leakage 用来诊断局部模式重复和 Markov baseline 的“记忆优势”。两者不能混为同一个指标。

计算：

```text
full-prefix train/test duplicate rate
suffix-k train/test duplicate rate
unseen full-prefix rate
unseen suffix-k rate
```

主评估不允许 random sample split。

### 6.4 Conditional ambiguity

对测试样本的历史-equivalence class，统计同一 prefix 在历史数据中的 next-target 分布。

报告：

- empirical conditional entropy；
- deterministic-prefix fraction；
- multi-continuation fraction。

### 6.5 Empirical ceiling

可以计算一个仅用于诊断、不得作为合法模型的 test-oracle ceiling：

```text
for each test-prefix signature:
    predict most frequent next target in test itself
```

该值只用于说明当前表示下的可预测性上限，绝不进入模型排名。

## 7. 预注册 C0 Gate

V1 采用保守 Gate。以下数值是本项目为防止小样本/标签塌缩而预注册的工程资格阈值，并非文献给出的统一标准；它们必须版本化，且不能根据当前实验结果临时放宽。

Operation / Joint 主任务至少满足：

- eligible sessions >= 4；
- eligible target actions >= 200；
- classes >= 3；
- dominant class ratio <= 0.90；
- normalized entropy >= 0.25；
- test 中至少 2 个 target classes；
- chronological test samples >= 40。

否则判定：

```text
INSUFFICIENT_PREDICTIVE_DIVERSITY
```

并停止该 target space 的模型比较。

Application 可以作为辅助任务单独报告，但若 application class < 2，同样不得声称 prediction success。

Gate 可以在未来版本化修改，但不能根据当前结果临时放宽。

## 8. Chronological Evaluation

### 8.1 Split unit

优先按完整 session 切分，而不是 action row。

最小协议：

```text
earliest sessions -> train
next session(s)    -> validation
latest session(s)  -> test
```

当 session 数足够时使用 rolling-forward：

```text
1..N -> N+1
1..N+1 -> N+2
...
```

### 8.2 Fallback

如果真实数据只有单 session：

- 允许 C0 audit；
- 不允许正式 generalization comparison；
- 可以输出 exploratory within-session metrics，但必须标记 `NON_GENERALIZATION_DIAGNOSTIC`。

## 9. C1 — Strong Non-neural Baselines

所有 baseline 必须输出完整、归一化的 target probability distribution，而不只输出 argmax；这样 Top-k、MRR 与 NLL 才来自同一预测对象。对 unseen context/target 的非零概率处理必须由训练侧固定 backoff/smoothing 决定，不能读取 test 频率。

### 9.1 Prediction vocabulary 与 unseen contract

每个 target space 的概率空间只允许由 training cutoff 之前可见的标签构成，并额外保留一个 `__UNSEEN__` 概率桶：

```text
prediction_vocabulary = sorted(train_labels) + [__UNSEEN__]
```

- validation/test 首次出现的真实新标签在 NLL 中映射到 `__UNSEEN__`；
- `__UNSEEN__` 仅承担概率质量与 coverage 记账，不代表模型猜中了具体新标签；
- 对具体 unseen target，Top-1 / HitRate@3 / MRR 一律按 miss 处理；
- Macro-F1 不把 `__UNSEEN__` 当作普通业务类别冒充精确分类能力；
- `unseen-target rate` 必须单独报告。

### B0 Global Frequency

\[
P(A)
\]

永远预测训练集最常见 action distribution。

### B1 Persistence / Copy-last

\[
\hat A_t=A_{t-1}
\]

这是桌面行为必须显式加入的 persistence baseline。它用于区分“用户长期停留在同一应用/操作”与真正的下一动作预测能力。若上一标签不在当前 vocabulary 中，按 `__UNSEEN__` / Global Frequency 的冻结 backoff 处理。

除全样本指标外，每个 target space 额外报告 transition-only diagnostic：仅在 `A_t != A_{t-1}` 的样本上重新计算指标。Application 任务将该切片记为 `application-switch`。该切片只用于诊断，不替代主 benchmark。

### B2 Contextual Frequency

条件逐步增加：

```text
current application
last operation
current application + last operation
```

需要 deterministic backoff 到 Global Frequency。

### B3 Bigram

\[
P(A_t|A_{t-1})
\]

### B4 Trigram

\[
P(A_t|A_{t-2}, A_{t-1})
\]

使用固定的 deterministic backoff/smoothing；优先采用 absolute discount / Kneser-Ney 风格实现或等价、测试明确的简化版本。

不能在 test 数据上调 smoothing 参数。

## 10. C2 — Structured Retrieval

目的：测试完整结构化 state/context 是否比纯 action n-gram 提供额外信息。

V1 不使用 embedding。

### 10.1 Retrieval key

候选特征只来自 target 前：

```text
foreground application
previous operation
last 3 joint actions
active process-name set
recent exogenous event-type set
idle bucket
time-of-day bucket (optional ablation)
```

若冻结的 B1 schema 只暴露 exogenous event IDs、没有安全的 event-type 派生字段，则 C V1 必须把 `recent exogenous event-type set` 标记为 `UNAVAILABLE_FROM_B1_V1` 并留空；禁止为了补齐该特征直接回读 canonical/raw event payload。后续若 B1 增加安全的 event-type 字段，应通过 schema/version 升级进入 C，而不是在 benchmark 内越过 B1 边界。

禁止：

- window title free text；
- exact key characters；
- raw screenshot content；
- target 后事件。

### 10.2 Similarity

使用可解释加权 similarity：

```text
exact categorical match
+ Jaccard(set features)
+ suffix action-sequence match
```

权重在 config 中冻结，不从 test 调参。

检索历史 top-k examples 后，对其 next target 做加权投票，输出完整概率分布。

## 11. C3 — B2 Memory Ablation

比较：

```text
Structured Retrieval
vs
Structured Retrieval + B2 ACTIVE Memory
```

Memory 必须通过 B2 retrieval gate：

- temporal validity；
- ACTIVE status；
- allowed provenance；
- dependency consistency；
- scope match。

C 不得直接读取 CANDIDATE / NEEDS_REVALIDATION Memory 当作模型上下文。

历史 benchmark 不允许直接拿“完整日志结束后”的 B2 run 回看更早的 test target。每个 fold 的 Memory 必须由该 fold train cutoff 之前的 evidence 做 as-of reconstruction，或使用 `source_high_water < test_start_seq` 的等价 prefix-safe B2 snapshot。若无法建立这样的 prefix-safe Memory snapshot，则 C3 必须停止并报告 Memory source 不具备时间安全性，不能退化为使用 full-log Memory。

### 11.1 Memory feature

V1 只允许结构化 Memory 特征：

```text
active fact keys/values
active habit keys/values
confidence
scope rank
```

不把 audit text、raw evidence payload 或自由文本摘要送进 predictor。

### 11.2 Memory Ablation Eligibility Gate

C3 只有在真实 test exposure 足以形成可识别干预时才允许进入 Memory value 判定。对每个 target space 固定报告：

```text
memory_available_samples
memory_coverage
memory_exposed_test_sessions
distinct_active_memory_ids
```

V1 工程资格阈值预注册为：

- `memory_available_samples >= 40`；
- `memory_coverage >= 0.20`；
- `memory_exposed_test_sessions >= 2`；
- `distinct_active_memory_ids >= 2`。

任一项不满足时，C3 返回：

```text
INSUFFICIENT_MEMORY_EXPOSURE
```

此状态表示“当前数据不足以识别 Memory 增量”，不得改写成 `NO_NONREDUNDANT_MEMORY_GAIN`。只有 exposure gate 通过后，Retrieval + Memory 与 Retrieval-only 的差值才具有 Gate 3 解释资格。

## 12. 指标

每个合法 target space 固定报告：

- Top-1 Accuracy；
- HitRate@3 / Recall@3；
- MRR；
- NLL；
- Macro-F1（classes >= 2）；
- coverage / unseen-target rate。

如果 class 数量 < 3，则 HitRate@3 不作为主要指标。

### 12.1 Relative metrics

重点报告：

```text
Delta_context = Contextual/Markov - GlobalFrequency
Delta_state   = StructuredRetrieval - best action-only baseline
Delta_memory  = Retrieval+Memory - Retrieval
```

绝对 accuracy 不作为唯一结论。

### 12.2 Primary decision metric

Gate 1–3 的主决策指标统一固定为 per-sample NLL，定义候选相对参考方法的改进为：

\[
\Delta_{NLL}=NLL_{reference}-NLL_{candidate}
\]

因此 `Delta_NLL > 0` 表示候选方法更好。Top-1、HitRate@3、MRR、Macro-F1 为 secondary metrics，只用于解释结果，不能在 primary NLL gate 失败时“救回”结论。

最小工程有效增益冻结为：

\[
\tau_{NLL}=\max(0.01\text{ nats},\ 0.01\cdot NLL_{reference})
\]

该阈值是本项目预注册的工程判据，不声称是文献通用标准。

模型/配置选择必须只使用 train/validation。所谓 `best action-only baseline` 是 validation NLL 最优的单一 baseline；test 只能用于一次冻结后的评估，禁止按 test 指标重新选 baseline 或调参数。

## 13. 结果解释 Gate

### 13.1 统一 decision protocol

Gate 1–3 都使用冻结后的 primary NLL protocol：

1. 候选模型/配置仅由 validation NLL 选择；
2. 至少需要 2 个可评估 rolling test folds；
3. 若恰有 2 folds，两者都必须 `Delta_NLL > 0`；若有 3 个及以上 folds，至少 `2/3` folds 必须 `Delta_NLL > 0`；
4. median `Delta_NLL >= tau_NLL`；
5. secondary metrics 只能作为解释，不改变 Gate PASS/FAIL；
6. inferential status 与 engineering gate 分开：独立 test sessions < 5 时只能标记 `DESCRIPTIVE_ONLY`；达到至少 5 个独立 test sessions 后，才运行 session-level bootstrap / paired session test 并允许形成 confirmatory statistical claim。

### Gate 0 — Data validity

C0 PASS 才允许正式模型比较。

### Gate 1 — Sequential predictability

从 B1 Persistence、Contextual Frequency、Bigram、Trigram 中，按 validation NLL 选定 best action-only baseline，再与 Global Frequency 比较。

若不满足统一 decision protocol：

```text
NO_STABLE_SEQUENCE_SIGNAL
```

### Gate 2 — State value

冻结 Structured Retrieval 配置后，与 Gate 1 已在 validation 阶段选定的 best action-only baseline 比较。

若不满足统一 decision protocol：

```text
NO_NONREDUNDANT_STATE_GAIN
```

### Gate 3 — Memory value

先通过 11.2 的 Memory Ablation Eligibility Gate。通过后，保持 Retrieval 配置完全相同，只增加 B2 ACTIVE Memory 特征，并与 Retrieval-only 比较。

若 exposure 不足：

```text
INSUFFICIENT_MEMORY_EXPOSURE
```

若 exposure 足够但不满足统一 decision protocol：

```text
NO_NONREDUNDANT_MEMORY_GAIN
```

不因为 Gate 3 失败而否定 B2 的审计/时间语义价值。

## 14. Statistical discipline

对于有多个 rolling folds 的指标差异：

- 报告每 fold 结果；
- 报告 median / mean delta；
- 主比较单位优先是完整 test session / rolling fold，而不是 action row；
- 禁止把同一 session 内高度相关的 action rows 当作 i.i.d. 样本做普通 row bootstrap；
- 独立 test sessions >= 5 时，使用 session-level paired bootstrap 或 paired session permutation test；
- 单个长 session 的 moving/block bootstrap 只能作为依赖结构诊断，不能替代独立 session 的 confirmatory evidence；
- 不只报单次 pooled accuracy。

独立数据不足时必须明确标记 `DESCRIPTIVE_ONLY`，不能输出具有统计确认含义的结论。

## 15. Concept drift

V1 只做诊断，不实现在线 adaptation。

滚动评估中记录：

- target distribution drift；
- application distribution drift；
- n-gram unseen-prefix rate drift；
- retrieval neighbor similarity drift；
- B2 active Memory changes。

这为后续 online learner / habit decay 提供证据。

## 16. 输出工件

C 应生成：

```text
PredictionDatasetManifest
ValidityAuditReport
SplitManifest
BaselinePredictionRun
MetricReport
AblationReport
```

所有 run 必须包含：

- source B1 run id；
- source B2 run id（如使用）；
- source high-water；
- split boundaries；
- config/schema version；
- predictor version；
- metric version。

## 17. Privacy 与 provenance

C 不新增原始数据权限。

禁止把以下内容复制到 prediction artifacts：

- STRUCTURED_SHORT exact key content；
- raw screenshots；
- clipboard exact content；
- secure UI text；
- password/credential fields。

Prediction artifact 只保存结构化 feature IDs/values 与预测分布。

## 18. 当前真实数据的预期判定

现有 60 秒真实 B2 qualification 数据：

```text
182 actions
1 session
all application = chrome.exe
all operation = key_input
```

因此它应该：

- C0 正常完成；
- Application/Operation/Joint 至少部分 target space 判 `INSUFFICIENT_PREDICTIVE_DIVERSITY`；
- 不进入正式 C1/C2/C3 generalization comparison。

如果实现后这份数据反而得到“prediction PASS”，视为 benchmark bug。

## 19. 后续进入 learned model 的条件

只有满足以下条件后才进入 Milestone D：

1. 至少一个 target space C0 PASS；
2. Gate 1 出现稳定 sequence signal；
3. 至少有两个以上独立 test sessions / rolling folds；
4. baseline artifacts 可完全重放；
5. 无 future leakage。

届时再比较：

```text
GRU
vs
small SSM
vs
small Transformer (optional)
```

而不是现在直接选择复杂 backbone。

## 20. 设计结论

Milestone C 的核心产物不是一个“聪明 predictor”，而是一把可靠的尺子。

如果这把尺子证明当前 B1 action abstraction 不够，下一步应先改 Action Abstraction；如果证明 short-context 有稳定信号，再逐步增加 state、Memory 和 learned model。

这能确保每一层复杂度都有独立、可证伪的增量价值。

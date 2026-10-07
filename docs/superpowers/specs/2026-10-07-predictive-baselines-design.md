# Milestone C — Predictive Baselines Design

日期：2026-10-07
状态：Draft for written-spec review after literature review

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

### B0 Global Frequency

\[
P(A)
\]

永远预测训练集最常见 action distribution。

### B1 Contextual Frequency

条件逐步增加：

```text
current application
last operation
current application + last operation
```

需要 deterministic backoff 到 Global Frequency。

### B2 Bigram

\[
P(A_t|A_{t-1})
\]

### B3 Trigram

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

### 11.1 Memory feature

V1 只允许结构化 Memory 特征：

```text
active fact keys/values
active habit keys/values
confidence
scope rank
```

不把 audit text、raw evidence payload 或自由文本摘要送进 predictor。

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

## 13. 结果解释 Gate

### Gate 0 — Data validity

C0 PASS 才允许正式模型比较。

### Gate 1 — Sequential predictability

要求 best action-only contextual/Markov baseline 在至少两个 rolling test fold 上稳定优于 Global Frequency。

如果没有：

```text
NO_STABLE_SEQUENCE_SIGNAL
```

### Gate 2 — State value

Structured Retrieval 必须稳定优于 best action-only baseline，才可以声称 structured state 有额外预测价值。

否则：

```text
NO_NONREDUNDANT_STATE_GAIN
```

### Gate 3 — Memory value

Retrieval + B2 Memory 必须稳定优于 Retrieval-only，才可以声称长期 Memory 有独立预测价值。

否则：

```text
NO_NONREDUNDANT_MEMORY_GAIN
```

不因为 Gate 3 失败而否定 B2 的审计/时间语义价值。

## 14. Statistical discipline

对于有多个 rolling folds 的指标差异：

- 报告每 fold 结果；
- 报告 median / mean delta；
- 报告 bootstrap CI 或 paired permutation test；
- 不只报单次 pooled accuracy。

数据不足以支持统计检验时明确标记 descriptive-only。

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

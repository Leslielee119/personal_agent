# Milestone B2 — Temporal Memory, Provenance, Dependency, and Invalidation Design

Date: 2026-10-07
Status: Design approved in chat; implementation not started
Parent architecture: `docs/superpowers/specs/2026-10-06-personal-predictive-generative-system-design.md`
B1 foundation: `docs/superpowers/plans/2026-10-06-milestone-b1-provenance-transition-state.md`
Project overview: `docs/PROJECT_VISION_AND_PROGRESS_CN.md`

## 1. 目标

B2 的目标不是增加一个“向量记忆库”，而是在 B1 的可信事件、状态、动作和 transition 之上建立一个**可追溯、具有时间语义、可被替代、可级联失效的长期个人记忆层**。

B2 要回答的是：

> 哪些长期断言值得被系统记住；这些断言由哪些真实证据支持；它们在什么时间范围内有效；当上游事实变化时，哪些下游习惯或程序性记忆必须重新验证；检索到的记忆是否有资格进入预测模型或生成模型。

核心原则：

```text
Observation / Transition
        ↓
      Evidence
        ↓
 Memory Candidate
        ↓
 Consolidation
        ↓
 Active Memory Graph
        ↓
 Retrieval Candidate
        ↓
 Temporal + Provenance + Validity Gate
        ↓
 Policy / Generator Context
```

B2 不引入神经预测模型，不引入 LLM 自动总结，不引入 embedding/vector retrieval，不执行桌面动作。

## 2. 为什么 Memory 不能等于历史文本或向量库

B1 已经提供了不可变 canonical evidence 和可重建 derived state/transition。如果 B2 直接把这些内容转成文本、embedding 后放进向量库，会丢失几个关键语义：

1. 这条信息是谁产生的；
2. 它来自真实用户动作、系统状态、AI 行为还是未知来源；
3. 它什么时候开始成立；
4. 它现在是否仍然成立；
5. 它依赖哪些上游事实；
6. 新证据出现后，它是被加强、被替代还是应该失效；
7. 检索命中以后，它是否有资格进入模型上下文。

因此 B2 的 memory 定义为一种**由 evidence 支撑的派生断言**，而不是存储介质。

形式上：

`M = (claim, kind, temporal scope, evidence, provenance, confidence, dependency, validity)`

Memory 可以存进 SQLite，也可以以后建立 embedding index，但 SQLite/vector index 都只是实现手段，不是 Memory 的语义本身。

## 3. Evidence、Memory 与 Prediction 的边界

三层必须分开。

### 3.1 Evidence

Evidence 是已经发生的事实记录，例如：

- canonical event；
- normalized action；
- explicit state snapshot；
- transition `(S_t, A_t, X_t, S_t+1)`。

Evidence 默认不可被 Memory 层修改。

### 3.2 Memory

Memory 是对多条 evidence 的长期归纳或状态断言，例如：

- “最近主要使用 VS Code”；
- “保存 Python 文件后经常运行 pytest”；
- “测试失败后通常查看 traceback”；
- “某个项目默认使用某条测试命令”。

Memory 必须能够回到 supporting evidence IDs。

### 3.3 Prediction

Prediction 是未来动作概率，例如：

`P(run_tests | recent_python_save, active_habits)`

Prediction 可以使用 Memory，但 Memory 本身不能因为预测模型输出了某个结果就自动变成用户事实。

默认禁止：

`model prediction -> memory truth`

除非未来存在独立用户确认或真实后续证据。

## 4. Memory 类型

B2 初始只支持四类。

### 4.1 FACT

描述随时间变化的状态性事实。

例如：

- 当前主要浏览器是 Firefox；
- 当前项目测试入口为 `pytest`；
- 某工作区当前主要编辑器为 VS Code。

FACT 最需要 temporal validity 和 supersession。

### 4.2 HABIT

描述重复出现的条件行为倾向。

例如：

`Python edit + save -> terminal -> pytest`

HABIT 不是确定规则，必须带支持次数、反例次数和置信度。

### 4.3 PROCEDURE

描述相对稳定的多步 workflow。

例如：

`edit -> save -> run tests -> inspect failure -> edit`

B2 只构造结构化 procedure，不进行自然语言 LLM 总结。

### 4.4 STYLE

描述执行动作时稳定的形式偏好，例如命令形式或代码编辑习惯。

STYLE 在 B2 只定义数据模型和来源规则；复杂的生成风格学习延后到生成阶段。

## 5. MemoryRecord

建议主模型：

```text
MemoryRecord
├── memory_id
├── schema_version
├── kind
├── key
├── value
├── scope
├── observed_from
├── valid_from
├── valid_to
├── created_seq
├── last_supported_seq
├── evidence_ids[]
├── provenance_summary
├── support_count
├── contradiction_count
├── confidence
├── status
└── extractor_id
```

### 5.1 `memory_id`

稳定、不可复用的 Memory 标识。

### 5.2 `key` 与 `value`

Memory 不应一开始全部表示成自由文本。

优先结构化，例如：

```json
{
  "key": "preferred_browser",
  "value": "firefox"
}
```

或：

```json
{
  "key": "habit.after_python_save",
  "value": "run_tests"
}
```

自由文本 Memory 延后到有可靠 semantic extractor 后再增加。

### 5.3 `scope`

Memory 必须说明适用范围，例如：

- global user；
- application；
- workspace/project；
- task/session；
- command family。

避免把某个项目里的局部习惯提升成全局用户习惯。

### 5.4 时间字段

至少区分：

- `observed_from`：首次有证据支持该 Memory 的观察时间；
- `valid_from`：系统认为断言开始有效的时间；
- `valid_to`：有效区间结束，当前有效则为空；
- `created_seq`：Memory 第一次建立时的 source sequence；
- `last_supported_seq`：最近一次支持证据的位置。

关键原则：

`observation time != validity time`

B2 不假设“今天观察到”就意味着“今天才开始成立”。如果不能推断历史有效起点，采用保守值。

## 6. Memory 状态机

状态定义：

```text
CANDIDATE
ACTIVE
SUPERSEDED
INVALID
NEEDS_REVALIDATION
```

### 6.1 CANDIDATE

证据不足以进入长期使用层。

### 6.2 ACTIVE

达到该类型的 deterministic consolidation gate，可以被检索，但仍需 retrieval gate。

### 6.3 SUPERSEDED

同一个互斥事实 key 出现了更新版本。

旧 Memory 不删除，保留 provenance 和历史区间，但退出 active retrieval。

### 6.4 INVALID

其证据被证明错误、其定义不再成立，或 deterministic validator 判定该 Memory 不可继续使用。

### 6.5 NEEDS_REVALIDATION

Memory 本身暂未被直接否定，但其依赖的上游 Memory 已失效或被替代。

默认不允许 `NEEDS_REVALIDATION` 直接进入 Policy/Generator context。

## 7. Provenance 语义

Memory 的 provenance 不是一个简单字符串，而是其 supporting evidence 的来源摘要。

至少统计：

```text
human_physical_support
ai_suggested_accepted_support
ai_suggested_modified_support
ai_executed_support
system_support
external_support
unknown_support
```

B2 默认学习资格：

- `HUMAN_PHYSICAL`：可作为用户行为证据；
- `AI_SUGGESTED_ACCEPTED`：可以作为明确接受行为，但必须单独计数，不能折叠成纯自然行为；
- `AI_SUGGESTED_MODIFIED`：可以作为反馈证据，保留修改语义；
- `AI_EXECUTED`：默认用户习惯学习权重为 0；
- `SYSTEM`：可支持环境事实，但不能单独证明用户偏好；
- `EXTERNAL`：只能支持对应外部事实，不能自动转换为用户偏好；
- `UNKNOWN`：默认不能将候选升级成高可信用户 HABIT/STYLE。

硬边界：

`AI_EXECUTED != HUMAN_PHYSICAL`

`SYSTEM observation != user preference`

`UNKNOWN != inferred human`

## 8. Dependency Graph

B2 在 Memory 之间维护显式依赖边。

```text
MemoryDependency
├── parent_memory_id
├── child_memory_id
├── relation
├── evidence_ids[]
├── created_seq
└── active
```

第一版 relation 只需要：

- `DERIVED_FROM`：child 的成立依赖 parent；
- `SUPPORTS`：parent 增强 child，但 parent 失效不一定直接使 child 失效；
- `CONSTRAINS`：parent 限定 child 的 scope/条件。

不要在 B2 引入完整因果图或 Pearl-style causal inference。

Dependency 表示的是**推导依赖**，不是“现实世界因果关系”。

## 9. Supersession

对于同一 scope 内互斥的 FACT key，新的高可信 Memory 可以替代旧 Memory。

例如：

```text
m1 = preferred_browser: chrome
m3 = preferred_browser: firefox
```

如果 m3 达到 supersession gate：

```text
m1.status = SUPERSEDED
m1.valid_to = m3.valid_from
m3.status = ACTIVE
SupersessionEdge(m3 -> m1)
```

Supersession 必须保留旧值，不允许 SQL update 覆盖历史值后丢失时间链。

## 10. Cascading Invalidation

当 parent Memory 被 `SUPERSEDED` 或 `INVALID`：

1. 找出所有 active dependency edges；
2. 对 `DERIVED_FROM` child 标记 `NEEDS_REVALIDATION`；
3. 对 `SUPPORTS` child 重新计算支持度；
4. 对 `CONSTRAINS` child 重新检查 scope validity；
5. 继续沿依赖图传播，但必须有 visited set 防循环；
6. 不允许直接物理删除 child。

例：

```text
m1: preferred_browser = chrome
       |
       | DERIVED_FROM
       v
m2: open_web -> launch_chrome
```

新证据产生：

```text
m3: preferred_browser = firefox
```

结果：

```text
m3 ACTIVE
m1 SUPERSEDED
m2 NEEDS_REVALIDATION
```

随后只有重新检查原始 transition evidence 后，m2 才能恢复 ACTIVE、被修改，或 INVALID。

## 11. Deterministic Memory Extractors

B2 不允许把 LLM 作为 Memory ground-truth extractor。

第一版只实现少数 deterministic extractors。

### 11.1 Application Usage Fact Extractor

从 foreground/state evidence 中生成：

- 最近主要使用的 editor/browser/terminal；
- application usage frequency；
- workspace-scoped application choice。

### 11.2 Transition Habit Extractor

从同 scope 的 transition 模式统计：

`condition -> next operation`

例如：

`save_python -> run_tests`

必须同时记录支持和反例。

### 11.3 Command Pattern Extractor

只从允许长期保存的结构化 command/action metadata 构造模式。

不得绕过 B1 retention policy，把 `STRUCTURED_SHORT` 原始按键内容重新长期化。

### 11.4 Procedure Extractor

从重复 action-operation chain 构造有限长度 procedure candidate。

第一版使用确定性 N-gram / sequence pattern，不使用 LLM workflow summarization。

## 12. Consolidation

Memory candidate 不能出现一次就直接 ACTIVE。

第一版 consolidation 采用显式规则，而不是学习模型。

规则按 Memory kind 独立配置，例如：

```text
FACT:
  sufficient direct state evidence
  + provenance eligible
  + no unresolved contradiction

HABIT:
  minimum_support_count
  + minimum_support_ratio
  + multiple distinct sessions when possible
  + no dominant AI_EXECUTED support

PROCEDURE:
  repeated chain
  + same scope
  + minimum session diversity

STYLE:
  deferred / stricter support
```

具体阈值属于 implementation plan 阶段预注册，不在设计阶段随意写死。

## 13. Contradiction

Contradiction 与 supersession 不完全相同。

- supersession：新旧事实属于同一 key 的时间替代；
- contradiction：同时期 evidence 对同一断言冲突。

MemoryRecord 保留：

`support_count`

`contradiction_count`

如果 contradiction 超过该 extractor 的 gate：

- CANDIDATE 不升级；
- ACTIVE 可以降为 `NEEDS_REVALIDATION`；
- 不因为一次反例立即物理删除。

## 14. Retrieval Contract

B2 要定义 retrieval 的安全接口，即使第一版还没有 semantic/vector retrieval。

推荐接口概念：

`retrieve_memories(query, scope, as_of, allowed_provenance, kinds, limit)`

处理顺序固定为：

```text
Candidate Selection
    ↓
Scope Filter
    ↓
Temporal Filter
    ↓
Status / Validity Gate
    ↓
Provenance Eligibility Gate
    ↓
Dependency Consistency Gate
    ↓
Rank
    ↓
Return
```

未来即使 Candidate Selection 替换为向量 Top-K，也不能绕过后面的 gates。

检索硬规则：

- `SUPERSEDED` 默认不返回；
- `INVALID` 不返回；
- `NEEDS_REVALIDATION` 不进入 Policy/Generator 默认上下文；
- `valid_from > as_of` 不返回；
- `valid_to <= as_of` 不作为当前事实返回；
- provenance 不满足调用者要求则过滤；
- scope 不兼容则过滤。

## 15. As-of Query

B2 必须支持按历史时间查询，而不只是“现在记得什么”。

例如：

`get(preferred_browser, as_of=2026-09-01)`

应该可以返回当时有效的旧 Memory，即使当前已经 superseded。

这是 temporal truth 的核心，也是以后解释模型决策的重要基础。

## 16. Memory Audit Trace

每条 Memory 必须能回答：

- 为什么存在；
- 哪些 evidence 支持；
- 哪些 evidence 反对；
- 为什么从 CANDIDATE 变成 ACTIVE；
- 为什么被 superseded/invalidated；
- 哪个 parent Memory 变化导致 revalidation；
- 某次 retrieval 为什么返回/过滤了它。

因此 B2 应保存结构化 audit event，例如：

```text
memory.created
memory.support_added
memory.consolidated
memory.contradiction_added
memory.superseded
memory.revalidation_required
memory.invalidated
memory.revalidated
```

Audit 不要求保存自然语言解释；结构化 reason code 即可。

## 17. Storage Boundary

B2 Memory 是 derived artifact，不得修改 canonical evidence。

建议 SQLite 独立表：

```text
memory_runs
memory_records
memory_evidence_links
memory_dependencies
memory_supersessions
memory_audit_events
```

要求：

- 支持 reconstruction run/version；
- 一个新的 extractor/schema 版本可以重建新 run；
- 不允许重建过程删除 canonical events；
- 写入事务失败必须 rollback；
- 历史 superseded Memory 保留；
- 可以删除整个 derived run 而不影响 B1/canonical evidence。

## 18. Rebuild Semantics

给定：

- 相同 canonical/B1 derived evidence；
- 相同 extractor version；
- 相同 consolidation config；

B2 reconstruction 必须得到确定性的：

- memory IDs；
- status；
- dependency edges；
- supersession chain；
- audit reason sequence。

不得让 wall-clock `now()` 参与决定结果；时间只能来自 source evidence 或显式 reconstruction parameter。

## 19. Privacy 与 Retention

B2 不能通过“摘要”绕过 B1 的 retention policy。

特别是：

- `STRUCTURED_SHORT` 的 exact keyboard content 不得复制进长期 Memory value；
- secure/password evidence 不得通过 extractor 重新出现；
- raw screenshot bytes 不进入 Memory；
- Memory 可以保存 event/state/action IDs 和经批准的结构化特征；
- 对敏感 value 的未来 semantic memory 必须有独立 policy，不在 B2 默认开启。

原则：

`derived != exempt from privacy`

## 20. Learning Eligibility

B2 将“Memory 是否存在”和“Memory 是否能训练 Personal Policy”分开。

推荐派生字段/函数：

`learning_eligibility(memory, target)`

例如：

- SYSTEM FACT 可以进入 world/state features；
- HUMAN_PHYSICAL HABIT 可以进入 personal policy；
- AI_EXECUTED HABIT 默认不能作为 user-policy target；
- UNKNOWN memory 可以用于 diagnostics，但默认不能训练个人偏好；
- EXTERNAL FACT 是否进入 context 取决于调用者允许的 source class。

这样避免以后所有 ACTIVE memory 被统一塞进模型。

## 21. B2 与 B1 的关系

B1 输出：

```text
Canonical Evidence
StateSnapshot
NormalizedAction
Session
Transition
Actor / Provenance
```

B2 消费这些数据，但不改变它们。

B2 输出：

```text
Temporal Memory Records
Evidence Links
Dependency Graph
Supersession Chain
Validity State
Audit Trace
```

因此层级为：

```text
A: capture/evidence
        ↓
B1: state/action/transition
        ↓
B2: long-term temporal memory
        ↓
C: frequency/Markov/retrieval policy baselines
        ↓
D: learned policy + generator
```

## 22. B2 不做什么

明确排除：

- 不做向量数据库；
- 不做 embedding；
- 不做 LLM memory summarization；
- 不做 RAG；
- 不做 GRU/Transformer/Mamba；
- 不做 action prediction；
- 不做 code/text generation；
- 不做 autonomous execution；
- 不把 dependency graph 宣称为真实因果图；
- 不根据单次 AI 输出创建“用户事实”。

这些边界是为了先证明长期 Memory 语义本身是可靠的。

## 23. B2 评估维度

B2 不以语言生成质量为指标。

核心指标：

### 23.1 Determinism

相同输入重建结果完全一致。

### 23.2 Provenance Correctness

不允许 UNKNOWN/AI_EXECUTED 被静默升级成 HUMAN_PHYSICAL habit evidence。

### 23.3 Temporal Correctness

历史 `as_of` 查询、valid interval 和 supersession 链必须正确。

### 23.4 Invalidation Correctness

parent Memory 变化后，所有依赖 child 按 relation 规则正确传播状态。

### 23.5 Privacy Preservation

B2 数据库不得出现 B1 已禁止长期保存的 exact input/secure content。

### 23.6 Explainability

任一 ACTIVE/filtered Memory 均能通过 IDs/reason codes解释来源与状态变化。

## 24. 必须包含的负对照

实施阶段至少需要以下负对照：

1. 只有 AI_EXECUTED 重复动作，不应生成高可信 HUMAN HABIT；
2. UNKNOWN legacy v1 行为不能升级成 HUMAN_PHYSICAL habit；
3. 一次偶然 action pattern 不能直接成为 ACTIVE HABIT；
4. superseded FACT 不应被当前时间 retrieval 返回；
5. NEEDS_REVALIDATION child 不应进入默认 Policy context；
6. wall-clock 回退不应改变 reconstruction 顺序；
7. 删除 derived memory run 不应影响 canonical/B1 evidence；
8. expired/removed raw artifact 不应使结构化 Memory reconstruction 崩溃；
9. STRUCTURED_SHORT keyboard content 不应出现在长期 memory DB。

## 25. 初始验收门槛

B2 Definition of Done 至少要求：

1. MemoryRecord、dependency、supersession、audit schema 已实现并版本化；
2. 至少 FACT + HABIT 两个 deterministic extractors 完整工作；
3. candidate -> active consolidation 可重放；
4. supersession 保留历史且更新 valid interval；
5. cascading invalidation 对多层依赖图可重放且防循环；
6. historical `as_of` retrieval 正确；
7. provenance gate 在 retrieval 和 learning eligibility 两处都执行；
8. B1/canonical evidence byte-level 不被 B2 修改；
9. privacy regression tests 证明短期输入不被长期化；
10. real B1 session 副本可以构造合理 Memory graph，并人工审计至少若干典型 Memory provenance chain；
11. full pytest、Ruff、`git diff --check` 和 SQLite integrity 全部通过。

## 26. 与未来 Retrieval/Vector Index 的兼容方式

未来 Milestone C 可以给 ACTIVE Memory 增加 index：

```text
ACTIVE Memory
    ↓
representation / embedding index
    ↓
semantic candidate Top-K
    ↓
B2 retrieval gates
    ↓
policy context
```

关键点：

**vector retrieval 只能替换 candidate selection，不能替换 validity/provenance/temporal gate。**

因此 B2 不会阻碍后续 semantic search，反而给它提供安全语义边界。

## 27. 与 Generator 的兼容方式

未来 Generator 获得的 personal context 应是：

```text
current state
+ recent transitions
+ gated active memories
+ optional style memories
```

而不是：

```text
entire event history
+ top-k arbitrary vector chunks
```

Generator 仍然不能修改 Memory truth。它可以提出 memory candidate，但 candidate 必须经过独立 evidence/consolidation 流程。

## 28. 未来 Delegation / Capability Boundary

B2 只处理 Memory provenance，不实现 Agent 权限系统。

但数据模型应保留未来兼容性：

- HUMAN action；
- AI suggested/accepted；
- AI executed；
- SYSTEM；
- EXTERNAL expert/service。

未来 capability/delegation 层可以基于同一 provenance vocabulary 判断：

- 哪些来源的数据可被记忆；
- 哪些 memory 可用于哪些 action；
- 哪些 external service 有资格接收什么 context。

B2 不提前实现 credential/delegation protocol。

## 29. 实施顺序建议

实施计划应按以下顺序展开：

1. Memory schema + deterministic IDs；
2. temporal interval + status machine；
3. evidence links + provenance summary；
4. dependency graph；
5. supersession；
6. cascading invalidation/revalidation；
7. deterministic FACT extractor；
8. deterministic HABIT extractor；
9. consolidation rules；
10. gated retrieval + historical as-of query；
11. audit/replay diagnostics；
12. real-session reconstruction qualification。

不要并行实现 vector/LLM 路线。

## 30. 冻结方向

B2 将长期个人记忆定义为：

`Memory = Value + Time + Evidence + Provenance + Dependency + Supersession + Validity`

它不是聊天记录，不是向量片段，也不是模型自己说过的话。

系统最终应当能够回答：

> 我为什么认为这是你的习惯？

> 这个判断来自哪些真实行为？

> 它在什么时候成立？

> 后来发生了什么使它失效？

> 为什么这次预测/生成允许使用这条 Memory？

只有当这些问题可以由结构化 evidence 与 audit trace 回答时，这条 Memory 才有资格成为 Personal AI 的长期状态。
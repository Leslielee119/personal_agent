# Personal Predictive AI：项目思想、架构与当前进度

> 更新时间：2026-10-07  
> 仓库：`Leslielee119/personal_agent`  
> 当前主线：本地 Personal Predictive Generative System

## 1. 我们到底想做什么

这个项目的目标不是做一个“带长期聊天记忆的本地 LLM”，也不是单独做一个桌面自动化 Agent。

我们真正想构造的是一个长期运行在个人电脑上的 **Personal Predictive AI**：它持续观察用户与电脑之间的交互，理解当前任务状态，学习用户长期行为规律，预测用户下一步可能要做什么，并在需要时生成具体的代码、文本、命令、导航目标或其他输出。

目标体验不是：

> “它记得我说过什么。”

而是：

> “它越来越知道我接下来准备做什么，以及我通常会怎么做。”

核心预测问题可以写成：

\[
P(A_{t+1}\mid S_t,H_t,E_t,U_t)
\]

其中：

- `S_t`：当前电脑和任务状态；
- `H_t`：近期行为历史；
- `E_t`：系统、应用或外部事件；
- `U_t`：长期、缓慢变化的个人习惯表示；
- `A_{t+1}`：下一步用户动作。

但仅预测动作还不够，所以完整系统还需要生成：

\[
P(Y_t\mid A_{t+1},S_t,H_t,R_t,U_t)
\]

这里 `Y_t` 是真正需要输出的内容，例如代码补全、shell 命令、文本、文件路径或 UI 目标。

因此系统最终是：

\[
\boxed{Prediction + Generation}
\]

而不是一个单独的大模型。

## 2. 为什么不采用“LLM + Vector Memory”作为核心

LLM 很擅长理解和生成内容，但它并不天然适合承担整个 Personal AI 的实时状态机。

我们的数据首先是异构事件流：

- 键盘和鼠标输入；
- 前台窗口变化；
- UIA 结构；
- 进程启动/退出；
- 文件变化；
- 截图；
- 通知；
- 构建、测试和程序完成事件；
- 未来 AI 自己产生的建议和动作。

这些事件具有强时间顺序和来源差异，并且实时路径希望维持在几十毫秒量级。把全部历史不断塞给 LLM 既昂贵，也无法自然解决事件来源、时间状态、行为反馈和长期习惯更新问题。

因此我们把 LLM 定义为 **Conditional Generator / Semantic Slow Path**，而不是整个系统的大脑。

主系统负责：

1. 当前发生了什么；
2. 谁导致了这个事件；
3. 当前处于什么任务状态；
4. 用户下一步大概率做什么；
5. 是否值得产生建议。

生成模型只在需要时回答：

> “如果下一步确实是这个动作，具体应该输出什么？”

## 3. 第一性数据：输入证据，而不是鼠标坐标

我们现在把用户行为的底层证据理解为输入信号，而不是 UI 语义本身。

例如一次点击的第一性事实是：

```text
某个物理输入设备
在时间 t
产生 left mouse down
```

而：

```text
cursor=(812,436)
foreground=VSCode
UI target=editor
```

属于解释这个行为的上下文。

因此数据层需要持续保留：

```text
input evidence + provenance + context
```

而不是简单保存“用户点击了 VSCode”。

这也是为什么当前 Canonical Event 已经加入：

- `actor`
- `provenance`
- `device`
- `injected`

等字段。

## 4. Provenance 是整个系统的核心边界

未来 Personal AI 自己也会产生建议甚至执行动作。如果不区分事件是谁造成的，就会产生严重的自我强化：

```text
AI 预测一个动作
→ AI 执行动作
→ 系统把它记录为用户行为
→ 模型认为用户喜欢这个动作
→ 更倾向再次预测同样行为
```

因此我们从底层区分：

```text
HUMAN_PHYSICAL
AI_SUGGESTED_ACCEPTED
AI_SUGGESTED_MODIFIED
AI_EXECUTED
SYSTEM
EXTERNAL
UNKNOWN
```

其中：

- `HUMAN_PHYSICAL` 是最高质量的用户行为证据；
- `AI_EXECUTED` 默认不能作为用户习惯正样本；
- legacy / 无法确认来源的数据保守标记为 `UNKNOWN`；
- System observation 不会因为和用户动作相邻就被伪装成用户动作。

我们后续的记忆、预测和生成都必须继续继承 provenance，而不能在某一层把它丢掉。

## 5. 真正的长期学习单位：State Transition

长期学习不应该直接针对单个按键、点击或聊天记录，而应该针对状态转移：

\[
\boxed{T_t=(S_t,A_t,X_t,S_{t+1},provenance)}
\]

其中：

- `S_t`：动作前状态；
- `A_t`：规范化动作；
- `X_t`：动作之后到下一动作之前观察到的系统/外部事件；
- `S_{t+1}`：下一动作发生前形成的状态；
- `provenance`：动作是谁造成的。

例如：

```text
S_t:
  VSCode
  trainer.py 已修改

A_t:
  HUMAN_PHYSICAL -> Ctrl+S

X_t:
  filesystem.modified
  pytest process started

S_t+1:
  terminal active
  test process running
```

只有积累大量这类 transition，系统才真正有条件学习：

```text
修改 Python
→ 保存
→ 跑测试
→ 看失败
→ 回到代码
→ 修改
→ 重跑
```

这比“记住用户常按 Ctrl+S”有意义得多。

## 6. 当前完整架构

```text
Physical Input / OS / Applications
              │
              ▼
       Canonical Event Plane
       actor + provenance
              │
              ▼
        Explicit State Model
              │
              ▼
       Transition Builder
   (S_t, A_t, X_t, S_t+1)
              │
              ▼
         Temporal Memory
  fact / habit / procedure / style
              │
      ┌───────┴─────────┐
      ▼                 ▼
Fast Personal       Slow Personal
Policy State        Habit / Style State
      │                 │
      └───────┬─────────┘
              ▼
        Personal Policy
     “下一步要做什么？”
              │
              ▼
        Action Proposal
              │
      ┌───────┼──────────────┐
      ▼       ▼              ▼
 Code/Text  Command        UI/Target
 Generator Generator       Generator
      └───────┼──────────────┘
              ▼
           Verifier
              │
              ▼
          Suggestion
              │
              ▼
       User Feedback
              │
              ▼
        Continual Learning
```

## 7. Memory 的新定义

我们已经不再把长期 Memory 定义为：

```text
text + embedding
```

下一阶段准备采用的是：

\[
\boxed{
Memory = Value + Time + Evidence + Provenance + Dependency + Supersession + Validity
}
\]

一个长期记忆至少需要回答：

- 它是什么；
- 从什么时候开始成立；
- 依据哪些事件/transition 得出；
- 来源是谁；
- 它依赖哪些其他记忆；
- 是否已经被新的事实替代；
- 当前是否仍有效。

例如：

```text
m1: 用户当前主要使用 Chrome
```

后来观察到：

```text
m1': 用户已长期改用 Firefox
```

那么过去依赖 m1 得出的：

```text
m2: “打开网页”通常意味着启动 Chrome
```

不能继续无限期保留。它应该进入重新验证或失效状态。

因此长期记忆链路会从：

```text
Observation -> Memory -> Forgetting
```

升级为：

```text
Observation
→ Evidence
→ Memory
→ Dependency
→ Consolidation
→ Supersession / Invalidation
```

## 8. 当前已经实现的部分

### Milestone A：Capture / Data Plane

已经实现：

- 本地 Canonical Event 数据面；
- OpenAdapt keyboard/mouse/UIA adapter；
- Windows foreground window；
- process start/exit；
- filesystem watcher；
- event-driven screenshot；
- Raw Ring Buffer；
- SQLite WAL structured storage；
- source-time privacy sanitizer；
- structured-short GC；
- sequence high-water；
- TCP/UDP/DNS offline guard；
- whole-process-tree 网络审计；
- replay/health/soak diagnostics。

5 分钟 pre-soak 已得到：

- 370 structured events；
- ordering consistency = 1.0；
- privacy violations = 0；
- SQLite integrity = ok；
- external established connections = 0；
- 平均 CPU 约 0.10%；
- RSS peak 约 161 MB。

仍未关闭：

1. 真实实体鼠标 click/scroll qualification；
2. 正式 8 小时 soak。

因此 Milestone A 当前是：

```text
implementation complete
qualification pending
```

而不是 fully qualified。

### Milestone B1：Provenance / State / Transition

B1 已实现并合并到 `main`：

- Canonical Event v2；
- actor/provenance/device/injected；
- v1 conservative migration；
- collector-boundary provenance mapping；
- NormalizedAction；
- ExplicitStateEstimator；
- deterministic session segmentation；
- TransitionBuilder；
- derived artifact SQLite store；
- offline `derive-b1`；
- safe `replay-b1`。

真实旧 session DB 的重建结果：

```text
source events: 370
snapshots: 370
actions: 41
transitions: 41
sessions: 1
legacy UNKNOWN provenance: 370 / 370
integrity: ok
```

旧 v1 事件没有被猜成 `HUMAN_PHYSICAL`。

最终合并验证：

```text
pytest: 115 passed / 1 physical-input skip
ruff: PASS
git diff --check: PASS
```

当前 `main` 已推送 GitHub。

## 9. B1 中刻意做出的几个边界决定

### System observation != user action

`window.foreground.changed` 等系统观察只改变 State，不自动生成用户 Action。

因为看到窗口切换并不能证明是谁触发了切换。

### Association != causation

Transition 中的 `X_t` 表示：

> 某个 action 之后、下一个 action 之前观察到这些系统事件。

它不等价于：

> 这些系统事件一定是该 action 因果造成的。

### Session 首动作不伪造 pre-state

新 session 的第一条 action 可以被保存，但如果不存在同一 session 内的真实 pre-state，就不为了增加训练样本而制造一条假 transition。

### Exact keyboard 不长期化

具体字符属于 `STRUCTURED_SHORT`。B1 的长期 derived action 只保留“发生了 key input”这一行为，不把短期字符内容复制成永久习惯记录。

## 10. 接下来的阶段

当前优先顺序调整为：

```text
A  Capture / Evidence          已实现，长期资格验证待关闭
B1 Provenance / State          已实现
B2 Temporal Memory             下一阶段
C  Policy Baselines            待开始
D1 Learned Personal Policy     待开始
D2 Conditional Generation      待开始
E  Suggestion + Feedback       待开始
```

B2 完成之前暂时不急着训练 GRU/SSM。

原因是如果 Memory 的 provenance、时间和失效机制本身不可靠，预测模型会学习被污染或已经过时的用户状态。

## 11. B2 的目标

B2 不做“智能记忆总结器”。

它首先做一个可验证的长期 Memory substrate：

```text
Evidence / Transition
        ↓
Candidate Memory
        ↓
Consolidation
        ↓
Temporal Memory Graph
        ↓
Retrieval + Provenance Gate
        ↓
Supersession / Invalidation
```

第一版重点不是 embedding，而是：

- memory object；
- evidence references；
- provenance；
- temporal validity；
- dependency edges；
- supersession；
- invalidation；
- retrieval 后的 source/provenance gating；
- deterministic replay / audit。

只有这层稳定后，再把 semantic embedding、LLM extraction、habit mining 接进来。

## 12. 长期预测模型方向

后续 Personal Policy 不会一开始使用大 Transformer。

计划按照：

```text
Global Frequency
→ Contextual Frequency
→ Markov
→ Retrieval
→ GRU
→ GRU + Habit Memory
→ GRU + Habit + Exogenous Features
→ SSM / small Transformer 对照
```

逐级验证。

只有个人历史相对于最强非个人 baseline 产生稳定收益，才增加模型复杂度。

## 13. Generator 的位置

预测模型解决：

> “下一步是什么？”

Generator 解决：

> “具体内容是什么？”

例如：

```text
Policy:
  next action = RUN_COMMAND
  target = terminal

Generator:
  pytest tests/test_capture_pipeline.py -q
```

或：

```text
Policy:
  next action = EDIT_TEXT

Generator:
  生成具体代码补全
```

本地 Qwen 系列模型可以承担生成/语义 slow path，但不会成为实时 Policy 的唯一核心。

## 14. 隐私原则

“全程本地”只是第一层要求。

完整边界是：

\[
\boxed{Local + Provenance + Temporal Truth + Action Trace + Capability Boundary}
\]

也就是说：

- 数据尽量留在本机；
- 能知道记忆从哪里来；
- 能知道当前事实何时成立/失效；
- 能解释建议使用了哪些历史证据；
- 能区分用户、AI、系统和外部行为；
- 未来 Agent 权限必须有显式 delegation/capability boundary。

## 15. 当前项目的核心判断

这个项目最终不是：

```text
LLM + Chat History + Vector DB
```

而更接近：

```text
Local Event-Sourced Personal Computing Model
+ Temporal Memory
+ Personal Action Policy
+ Conditional Generator
+ Verifier
```

它先建立一个可信的“个人行为世界模型底座”，再让预测和生成模型利用它。

一句话概括：

> **我们不是在让 AI 记住用户说过什么，而是在构造一个能够长期学习“这个用户如何与自己的电脑和任务世界交互”的本地预测系统。**

## 16. 2026-10-07：B2 Temporal Memory 当前状态

B2 已完成实现并合并到 `main`。长期 Memory 不采用 `text + embedding` 作为真值，而采用：

```text
Memory = Value + Time + Evidence + Provenance + Dependency + Supersession + Validity
```

设计、实现计划与验收记录：

- `docs/superpowers/specs/2026-10-07-temporal-memory-provenance-design.md`
- `docs/superpowers/plans/2026-10-07-milestone-b2-temporal-memory.md`
- `docs/milestones/MILESTONE_B2_ACCEPTANCE.md`

B2 已实现 Memory schema/ID、transactional storage、provenance eligibility、temporal status/supersession、dependency/invalidation、deterministic FACT/HABIT extractor、consolidation、gated historical retrieval 以及 `derive-b2/replay-b2` reconstruction/audit。

真实 qualification 数据保存在 Git worktree 之外：

`E:\Experiment\personal-predictive-ai-runtime\captures\2026-10-07-b2-qualification\events.db`

该 capture 包含 391 条 canonical events、182 个 B1 actions、1 个 session。B2 得到 1 个 FACT candidate 和 1 个 HABIT candidate，均因 multi-session Gate 未满足而保持 CANDIDATE。`key_input -> key_input` HABIT 虽有 181 次 HUMAN_PHYSICAL 支持，但仍未绕过 `habit_min_sessions`，说明冻结 Gate 正常工作。

需要注意：B2 已通过 deterministic reconstruction / provenance / privacy semantics qualification，但尚未证明长期个性化效用。当前真实数据只有一个 session，并且 B1 action abstraction 较粗。

另一个已知边界是：V1 `foreground_application.primary` FACT extractor 是全历史聚合，不自动推导 Chrome -> Firefox 这类 change point。Supersession 机制已实现，但真实 temporal migration extractor 尚未实现。

## 17. 2026-10-07：Milestone C Predictive Benchmark

Milestone C V1 已完成 Native TDD 实现与真实数据 qualification。它的定位不是“训练一个模型得到高 accuracy”，而是先建立一个 **Validity-first Predictive Benchmark**：只有数据本身足以支持可信的 out-of-time 比较时，才允许讨论模型增益。

相关文档：

- `docs/research/2026-10-07-predictive-action-research-scan.md`
- `docs/superpowers/specs/2026-10-07-predictive-baselines-design.md`
- `docs/superpowers/plans/2026-10-07-milestone-c-validity-first-predictive-benchmark.md`
- `docs/milestones/MILESTONE_C_ACCEPTANCE.md`

正式实现路线为：

```text
C0 Validity Audit
  -> C1 Frequency / Persistence / Markov strong baselines
  -> C2 Structured Retrieval
  -> C3 prefix-safe B2 Memory Ablation
```

当前已经实现：

- HUMAN_PHYSICAL-only formal targets；
- Application / Operation / Joint 三层 target；
- `source_seq < target_seq` 的严格 pre-target 输入边界；
- chronological/session-forward rolling split；
- target diversity、dominant ratio、entropy、prefix leakage、conditional ambiguity 与 empirical ceiling audit；
- training-only vocabulary + `__UNSEEN__` probability contract；
- Global Frequency、Persistence、Contextual Frequency、Bigram、Trigram-backoff；
- transition-only persistence diagnostic；
- 每个 target space 只在首次 validation 冻结一次 action-only baseline family，后续 rolling test 不重新选型；
- interpretable Structured Retrieval；
- per-fold target/application distribution drift、unseen-prefix、retrieval-neighbor similarity 与 B2 ACTIVE Memory change diagnostics；
- per-fold prefix-safe B2 reconstruction 与先于 Memory scoring 的 Memory exposure gate；
- NLL-only primary Gate，secondary metrics 不得救回失败的主 Gate；
- deterministic prediction artifacts 与 `ppa benchmark-c` CLI。

最新自动验证：

```text
Milestone C focused suite: 43 passed
full pytest: 218 passed / 1 native physical-input skip
ruff: PASS
git diff --check: PASS
```

真实 qualification 使用冻结数据库：

`E:\Experiment\personal-predictive-ai-runtime\captures\2026-10-07-b2-qualification\events.db`

其中 B1=`real-b1-20261007`、B2=`real-b2-20261007`，high-water 均为 391。C 对 Application / Operation / Joint 都得到 182 个 HUMAN_PHYSICAL examples，但只有 **1 个 session、1 个 class、dominant ratio=1.0、normalized entropy=0.0**，因此三个 target space 均按预注册 Gate 返回：

```text
INSUFFICIENT_PREDICTIVE_DIVERSITY
```

并标记：

```text
NON_GENERALIZATION_DIAGNOSTIC
```

所以 C1/C2/C3 formal comparison 被正确阻断。这个结果不是“预测方法失败”，而是当前真实数据不足以识别 sequence/state/Memory 的增量价值。不能从这批数据得出 `NO_STABLE_SEQUENCE_SIGNAL`、`NO_NONREDUNDANT_STATE_GAIN` 或 `NO_NONREDUNDANT_MEMORY_GAIN`。

真实 benchmark 重跑的 6 个工件字节哈希完全一致；capture DB 文件以及 canonical/B1/B2 source tables 的前后哈希均不变；prediction artifact 隐私扫描没有发现 exact-key/window-title/screenshot/clipboard/credential/password 字段。

因此当前 Milestone C 状态冻结为：

```text
benchmark implementation: QUALIFIED
real predictive comparison: BLOCKED BY C0 DATA VALIDITY
learned policy / Milestone D: NOT YET ELIGIBLE
```

下一步不是立刻上 GRU/SSM，而是积累真正跨 session、跨应用、跨 operation 的 HUMAN_PHYSICAL 数据，使 C0 首先具备可检验性。只有 C0 PASS 且 Gate 1 出现稳定 out-of-time sequence signal 后，才进入 learned personal policy。

## 18. 当前仍开放的基础资格项

Milestone A 仍有两个独立 qualification Gate 未闭合：

1. physical mouse native qualification；
2. formal 8-hour soak。

它们不会否定 B1/B2 已完成的语义实现，但正式长期运行资格仍需要后续闭合。

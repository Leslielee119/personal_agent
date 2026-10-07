# Personal Knowledge / Skill Plane Prior-Art Audit

日期：2026-10-07
状态：Research audit for Milestone E design

## 1. 调研目标

本次调研回答一个具体问题：在我们已经拥有 Event → B1 State/Action/Transition → B2 Temporal/Provenance Memory → Milestone C Predictive Benchmark 的前提下，是否有必要再增加 Personal Knowledge / Skill Plane；如果需要，它与现有 Agent workflow memory、procedural memory、Obsidian + MCP + Skill 生态有什么区别，哪些设计可以直接借鉴，哪些必须保留我们自己的边界。

结论先行：Milestone E 值得做，但不应变成“Obsidian-first Agent”，也不应把任何被发现的 workflow 直接升级成可执行自动化。推荐路线是：

```text
Core-native Knowledge/Skill Registry
  + Behavior-to-Skill Compiler
  + Verification/Lifecycle
  + Human-readable Markdown/Obsidian Projection
  + future Governed MCP Execution
```

其中 E 只做到 Discover → Abstract → Verify → Propose；真正产生本地写入、桌面操作或外部副作用的执行放到后续 Milestone F，并服从人工审批边界。

## 2. AWM：Agent Workflow Memory

论文：Zora Zhiruo Wang, Jiayuan Mao, Daniel Fried, Graham Neubig, **Agent Workflow Memory**, ICML 2025, PMLR 267:63897-63911。

论文链接：https://proceedings.mlr.press/v267/wang25bx.html

中科院分区：不适用。该工作为 ICML 国际会议论文，不使用中科院期刊分区；ICML 属机器学习顶级会议。

### 2.1 核心思想

AWM 不把历史任务简单保存为完整 episode，而是从过去 action trajectories 中诱导可重复使用的 workflow，并在后续任务中按需提供给 Agent。它同时支持 offline workflow induction 与 online workflow induction。

其关键价值不是“记住更多历史”，而是把：

```text
concrete successful trajectory
```

抽象成：

```text
reusable workflow / routine
```

这说明 procedural knowledge 应当是长期记忆中的独立对象，而不是只保留 episodic traces。

### 2.2 对我们的启发

可直接吸收：

1. trajectory 不应永久作为最终知识表示，应进一步抽象成 reusable workflow；
2. workflow 应尽量去除实例特有常量，把任务参数抽象成 variable / slot；
3. workflow retrieval 与普通事实检索不是同一个问题；
4. workflow 可以从多条成功轨迹中归纳，而不是必须由用户手写。

不能直接照搬：

1. AWM 的主要证据来自任务成功轨迹，我们的 Personal AI 必须额外考虑 provenance；
2. `AI_EXECUTED` 轨迹不能因为“成功”就被重新学习成用户习惯；
3. 单个 session 内重复不能自动解释为长期个人 workflow；
4. workflow 形成后还必须面对时间失效、习惯改变、反例与 supersession。

因此我们应使用：

```text
Trajectory abstraction
+ cross-session evidence
+ provenance gate
+ negative evidence
+ temporal validity
```

而不是简单的 successful-trajectory mining。

## 3. Skill-Pro：可演化程序性 Skill

论文：Qirui Mi, Zhijian Ma, Mengyue Yang, Haoxuan Li, Yisen Wang, Haifeng Zhang, Jun Wang, **Skill-Pro: Learning Reusable Skills from Experience via Non-Parametric PPO for LLM Agents**, ICML 2026, PMLR 306:88574-88595。

论文链接：https://proceedings.mlr.press/v306/mi26d.html

代码：https://github.com/Miracle1207/Skill-Pro

中科院分区：不适用。该工作为 ICML 2026 会议论文；官方实现标注为 Spotlight。

### 3.1 核心思想

Skill-Pro 将被动 episodic narrative 转换为可复用 Skill，并把 Skill 形式化为 Skill-MDP。官方论文与实现都强调 Skill 具有三部分：

```text
Initiation
Policy / Execution
Termination
```

同时使用 Non-Parametric PPO 的 candidate generation、PPO Gate verification 和 score-based maintenance，使 Skill Pool 可以生成、验证、精炼和淘汰，而不必更新模型参数。

### 3.2 对我们的启发

这是 Milestone E 最重要的外部结构依据之一。

我们的 `SkillRecord` 不应该只是：

```text
name + prompt + steps
```

而至少应该表达：

```text
When to apply
How to perform
When to stop
How to verify
Why we believe it
What risk it carries
```

即：

```text
Skill = Initiation + Procedure + Termination + Verification + Evidence + Risk
```

其中前半部分来自 Skill-Pro / Options-like procedural skill 思路；Evidence、Provenance、Temporal Validity 与 Supersession 延续我们的 B2 设计。

### 3.3 与我们的关键差异

Skill-Pro 的目标是提升 Agent 长期任务能力，而我们的对象是单用户长期 Personal AI。因此我们必须额外区分：

```text
Skill existence
Skill usefulness
Skill authorization
```

三者不能合并。

一个 Skill 可以被证明是稳定、可复用的，但这不意味着 Agent 被授权执行它。

## 4. LEGOMem：程序性记忆应分层放置

论文：Dongge Han, Camille Couturier, Daniel Madrigal Diaz, Xuchao Zhang, Victor Rühle, Saravan Rajmohan, **LEGOMem: Modular Procedural Memory for Multi-agent LLM Systems for Workflow Automation**, AAMAS 2026。

Microsoft Research：https://www.microsoft.com/en-us/research/publication/legomem-modular-procedural-memory-for-multi-agent-llm-systems-for-workflow-automation/

arXiv：https://arxiv.org/abs/2510.04851

中科院分区：不适用。该工作为 AAMAS 2026 国际会议论文。

### 4.1 核心思想

LEGOMem 把 past task trajectories 分解成 reusable procedural memory units，并研究这些 memory 应该放在哪里、如何检索、哪些 Agent 受益最多。

论文在 OfficeBench 上报告的核心结论是：

- orchestrator memory 对 task decomposition / delegation 很重要；
- fine-grained task-agent memory 更直接改善具体 execution accuracy。

### 4.2 对我们的启发

我们不应建立一个扁平 Skill Pool。

建议区分：

```text
PlannerSkill
ExecutorSkill
ToolCapability
```

例如：

```text
Goal: 完成一次科研实验
  ↓
PlannerSkill: hypothesis → screening → gate → confirmatory → report
  ↓
ExecutorSkill: run_pytest / launch_training / collect_metrics
  ↓
ToolCapability: filesystem.read / terminal.run / github.commit
```

这可以避免“一个完整科研工作流”和“运行一条 pytest”进入同一个检索空间互相竞争。

## 5. Obsidian + MCP + Skill 生态

### 5.1 Obsidian 的真正优势

Obsidian 的核心优势不是 Agent 本身，而是开放、本地、人类可编辑的数据形态：Markdown、YAML Properties、Bases、Canvas 等都非常适合作为 Personal Knowledge 的 human-facing interface。

官方 Obsidian Bases 仍然使用本地 Markdown / properties 作为基础数据，而不是把用户内容锁进不可见数据库。

官方文档：https://help.obsidian.md/bases

这意味着它天然适合：

- 人工编辑；
- Git versioning；
- 跨工具迁移；
- 数据库式视图；
- 用户对 Knowledge / Skill 的显式审核。

### 5.2 Skill 生态

当前已有多种 Obsidian Skills / MCP 组合，例如：

- https://github.com/kepano/obsidian-skills
- https://github.com/kriss-spy/obsidian-skills
- https://github.com/jason-c-dev/obsidian-mcp
- https://github.com/juliushamm/obsidian-mcp-skill

这些项目已经把以下模式工程化：

```text
MCP tools = 原子能力
SKILL.md  = 如何组织这些能力完成任务
Vault     = 用户知识与约定
```

部分项目明确区分 raw MCP tools 与 Skills：工具只告诉 Agent “能做什么”，Skill 才描述“什么时候使用、按什么约定组织知识”。

### 5.3 我们与 Obsidian-first 路线的根本区别

Obsidian-first：

```text
Human-authored knowledge/workflow
  → Skill
  → MCP
  → Action
```

我们的长期架构：

```text
Observed behavior + explicit knowledge
  → Evidence / State / Memory
  → Prediction / Workflow discovery
  → Verified Skill
  → Human-readable projection
  → Governed execution
```

前者更擅长“用户明确告诉系统怎么做”；后者还试图回答“用户实际上怎么做、这个做法是否跨 session 稳定、是否已经改变、是否由 AI 自己制造”。

因此 Obsidian 最适合成为我们的 Projection / Console，而不是 machine truth database。

## 6. MCP 安全边界

2026-03-16 MCP 官方博客进一步澄清：`readOnlyHint`、`destructiveHint`、`idempotentHint`、`openWorldHint` 都只是 ToolAnnotations hints，不是安全保证；不可信 server 可以错误声明这些属性，真正需要保证的安全属性必须由 host/runtime 的 deterministic control、authorization 或 sandbox 实现。

官方说明：https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/

因此我们不能写成：

```text
Tool says readOnlyHint=true
→ automatically trusted
```

而应由本地 capability registry 自己定义风险类别，并由执行 runtime 决定是否需要审批。

当前项目冻结的安全边界：

```text
READ_ONLY       -> 可自动允许
WRITE_LOCAL     -> HUMAN_APPROVAL_REQUIRED
ACT_LOCAL       -> HUMAN_APPROVAL_REQUIRED
EXTERNAL_EFFECT -> HUMAN_APPROVAL_REQUIRED
UNKNOWN         -> HUMAN_APPROVAL_REQUIRED
```

此外：

```text
VERIFIED_SKILL != AUTHORIZED_EXECUTION
```

Skill 的质量验证与执行授权是两个完全不同的状态空间。

## 7. 与现有 B1/B2/C 的关系

### B1

回答：

```text
What actually happened?
```

提供 provenance-aware State / Action / Transition。

### B2

回答：

```text
What remains true over time?
```

提供 Fact / Habit 等 temporal/provenance Memory。

### C

回答：

```text
What will the user probably do next?
```

验证 sequence / structured state / Memory 是否具有独立 predictive value。

### E

回答：

```text
What reusable procedure describes how this user tends to accomplish a task?
```

形成 Knowledge / Skill Plane。

### F

未来才回答：

```text
Should the AI execute the procedure now, and under what authorization?
```

## 8. 三种候选架构

### 方案 A：Obsidian-first

```text
Obsidian Vault
→ Markdown/Skill
→ MCP
→ Agent
```

优点：实现快、人工可读、生态成熟。

缺点：会弱化我们已经建立的 event-sourced / temporal / provenance substrate；长期容易让 Markdown 同时承担 human view 和 machine truth 两种不兼容职责。

结论：不推荐作为 Core。

### 方案 B：Core-native Skill Registry + Projection

```text
B1/B2/C
→ canonical Knowledge/Skill Registry
→ Markdown/Obsidian Projection
→ future MCP execution
```

优点：保留 machine truth、版本/时间/provenance，同时获得 Obsidian 的人工可读性。

缺点：需要自己定义 Skill schema 和 projection consistency。

结论：推荐。

### 方案 C：直接做 Autonomous Skill Evolution

```text
trajectory
→ generated skill
→ automatic verification
→ automatic execution
```

优点：研究上激进。

缺点：当前 C 尚未证明个人行为存在足够稳定的 predictive signal；同时 execution safety 与 policy-induced self-training 风险未闭合。

结论：现阶段不采用。

## 9. 推荐的最终组合

推荐：

```text
Core-native Knowledge/Skill Registry
+ Behavior-to-Skill Candidate Compiler
+ Planner/Executor Skill separation
+ Verification and lifecycle
+ Markdown/Obsidian projection
+ execution authorization separated into Milestone F
```

核心创新空间不是“又做一个 Skill 系统”，而是把已有工作的优势组合到 Personal AI 的可信行为底座上：

```text
AWM trajectory abstraction
+ Skill-Pro executable skill semantics / verification
+ LEGOMem hierarchical procedural memory
+ Obsidian human-readable open projection
+ our temporal/provenance/evidence/supersession substrate
```

## 10. 研究问题

Milestone E 应围绕以下可证伪问题，而不是围绕“能不能生成 Skill”展开：

1. 跨 session 行为证据能否产生比单条 trajectory 更稳定的 SkillCandidate？
2. provenance gate 是否能防止 AI 自己执行的动作被编译成用户 Skill？
3. negative / contradictory trajectories 是否能减少过度泛化的 initiation conditions？
4. PlannerSkill / ExecutorSkill 分层是否比 flat skill pool 提高 retrieval / selection accuracy？
5. verified Skill 是否能在 held-out sessions 上提高 workflow completion / prediction quality？
6. Markdown/Obsidian projection 能否保持 canonical SkillRecord 的 round-trip consistency，同时不成为新的 machine truth？

## 11. Prior-art 结论

Milestone E 的合理定位不是：

```text
Build an Obsidian AI
```

而是：

```text
Build a provenance-aware Personal Knowledge & Verified Skill Plane,
with Obsidian/Markdown as an optional human-facing projection.
```

因此下一步 written spec 应冻结 E0–E5，并且把执行权限明确留给 Milestone F。

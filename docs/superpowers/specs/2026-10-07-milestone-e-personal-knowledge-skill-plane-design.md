# Milestone E — Personal Knowledge & Verified Skill Plane Design

日期：2026-10-07
状态：Revised draft for written-spec review — 2026-10-08 trust hardening integrated

## 1. 目标

Milestone E 的目标不是立即让 Personal AI 自动执行复杂工作流，而是在现有 Event / State / Memory / Prediction 基础上增加一个可信的 Personal Knowledge & Skill Plane，使系统能够：

1. 保存用户明确声明的结构化知识，而不把它与行为推断 Memory 混为一谈；
2. 从真实跨 session 行为中发现可复用 workflow candidate；
3. 将 workflow 抽象为带 initiation / procedure / termination / verification 的 Skill；
4. 对 Skill 做 evidence、provenance、negative evidence、temporal validity 和 lifecycle 管理；
5. 区分 PlannerSkill 与 ExecutorSkill；
6. 允许用户通过 Markdown / Obsidian 查看和编辑 projection；
7. 严格把 Skill quality 与 execution authorization 分开；
8. 为未来 Milestone F 的 MCP / desktop execution 提供受治理的输入，而 E 本身不执行有副作用的 Skill。

核心问题是：

```text
Can a trusted personal history be compiled into reusable,
verifiable and human-auditable procedural knowledge?
```

## 2. 研究依据

完整 prior-art audit：

`docs/research/2026-10-07-personal-knowledge-skill-plane-prior-art.md`

设计主要吸收：

- AWM：从成功 trajectories 中诱导 reusable workflows；
- Skill-Pro：Skill 的 Initiation / Policy / Termination 结构与 verification / maintenance；
- LEGOMem：orchestrator-level 与 executor-level procedural memory 应分层；
- Obsidian / Agent Skills：开放 Markdown、人工可编辑、Skill packaging、MCP tools 与 workflow instructions 分离；
- 本项目 B2：Time + Evidence + Provenance + Dependency + Supersession + Validity。

相关论文信息：

1. Wang et al., *Agent Workflow Memory*, ICML 2025。中科院分区：不适用（会议论文）。
2. Mi et al., *Skill-Pro: Learning Reusable Skills from Experience via Non-Parametric PPO for LLM Agents*, ICML 2026。中科院分区：不适用（会议论文）。
3. Han et al., *LEGOMem: Modular Procedural Memory for Multi-agent LLM Systems for Workflow Automation*, AAMAS 2026。中科院分区：不适用（会议论文）。

## 3. 非目标

Milestone E V1 明确不做：

- 自动执行 WRITE / ACT / EXTERNAL_EFFECT Skill；
- 让 LLM 自主获得新的本地执行权限；
- 把 Obsidian Vault 当作 canonical database；
- 把任意成功 trajectory 直接升级为 Skill；
- 从 `AI_EXECUTED` 行为自动学习用户偏好；
- 自动修改原始 B1/B2/C 事实；
- online autonomous skill evolution；
- 自动安装 MCP server、plugin 或 Skill；
- unrestricted shell / filesystem write；
- 通过 free-text embedding 代替 provenance/evidence gate；
- 把 Skill selection success 等同于 execution authorization。

## 4. 核心语义分离

Milestone E 必须保持五类对象的概念边界：

```text
Memory    = 系统从历史证据中推断并维护的长期事实/习惯
Knowledge = 用户或可信来源明确声明的知识
Skill     = 完成一类任务的可复用程序性知识
Prediction= 对下一步行为/候选动作的概率判断
Authorization = 当前是否允许真正执行副作用动作
```

必须永久保持：

```text
Skill existence != Skill usefulness != Skill authorization
```

以及：

```text
VERIFIED != AUTHORIZED_TO_EXECUTE
```

## 5. 总体架构

```text
Canonical Event Plane
        ↓
B1 State / Action / Transition
        ↓
B2 Temporal / Provenance Memory
        ↓
C Predictive Benchmark
        │
        ├──────────────────────┐
        ↓                      ↓
Explicit Knowledge       Workflow Discovery
        │                      │
        └──────────┬───────────┘
                   ↓
            Skill Candidate
                   ↓
        Verification / Lifecycle
                   ↓
             Skill Registry
                   ↓
        Human-readable Projection
         Markdown / Obsidian
                   ↓
              Proposal only
                   ↓
       Milestone F Governed Execution
```

E 的 canonical truth 位于 Core-native registry；Markdown / Obsidian 是 projection，不是反向替代数据库。

## 6. E0 — Canonical Knowledge / Skill Schema

### 6.1 KnowledgeRecord

V1 定义显式知识对象：

```text
KnowledgeRecord
  knowledge_id
  kind
  key
  value
  scope
  source_class
  provenance
  created_at / created_seq
  valid_from / valid_to
  evidence_refs
  confidence
  status
  supersedes / superseded_by
  schema_version
```

Knowledge 与 B2 Memory 的区别：

- Knowledge 可以来自用户明确输入、项目配置、经过审核的文件；
- Memory 是从行为/事件证据派生；
- 两者都可进入 Skill verification，但必须保留 source_class；
- 不允许把模型生成的未审核文本伪装成 HUMAN_DECLARED Knowledge。

### 6.2 Knowledge provenance

V1 至少区分：

```text
HUMAN_DECLARED
HUMAN_APPROVED_IMPORT
DERIVED_FROM_B2
AI_PROPOSED
SYSTEM
EXTERNAL
UNKNOWN
```

`AI_PROPOSED` 默认不能作为等价于用户声明的事实来源。

### 6.3 SkillKind

V1 只定义：

```text
PLANNER
EXECUTOR
```

其中：

- PlannerSkill：描述 task decomposition / ordering / delegation；
- ExecutorSkill：描述较具体、可复用的局部操作程序；
- ToolCapability 不是 Skill，本阶段只作为 capability reference。

### 6.4 SkillRecord

```text
SkillRecord
  skill_id
  name
  kind
  purpose

  initiation_conditions
  preconditions
  parameters
  procedure_steps
  required_capabilities

  termination_conditions
  success_conditions
  verification_spec

  scope
  risk_class

  evidence_refs
  contradiction_refs
  provenance_summary
  support_sessions
  confidence

  valid_from / valid_to
  version
  supersedes
  status

  created_by
  created_at
  schema_version
```

Skill 的正式语义：

```text
Skill =
  Initiation
  + Preconditions
  + Procedure
  + Termination
  + Verification
  + Evidence
  + Risk
  + Lifecycle
```

### 6.5 SkillStatus

V1 冻结以下状态：

```text
DRAFT
CANDIDATE
VERIFIED
ACTIVE
NEEDS_REVALIDATION
SUPERSEDED
RETIRED
INVALID
```

语义：

- DRAFT：用户/AI 尚未完成结构化；
- CANDIDATE：已经有足够结构，但尚未通过 verification；
- VERIFIED：已通过验证，但不代表当前启用；
- ACTIVE：可参与 Skill retrieval / proposal；
- NEEDS_REVALIDATION：证据或依赖发生改变；
- SUPERSEDED：被新版本替代；
- RETIRED：主动停止使用，但不视为错误；
- INVALID：验证失败或与安全/事实冲突。

### 6.6 VerificationSpec

Verification 必须是 canonical structured object，而不是只有自由文本说明：

```text
VerificationSpec
  verification_id
  method
  expected_observation
  evidence_requirements
  allowed_risk_class
  timeout
  failure_conditions
  independence_requirement
  schema_version
```

V1 只允许：

```text
STATIC
EVIDENCE_CONSISTENCY
OFFLINE_REPLAY
HELD_OUT_SESSION
READ_ONLY_LIVE
```

E 阶段不得自动执行 `WRITE_LOCAL` / `ACT_LOCAL` / `EXTERNAL_EFFECT` live verification。

### 6.7 SkillMutationProposal

模型、用户编辑器或 importer 都不能原地覆盖 canonical SkillRecord。所有语义变更必须先形成：

```text
SkillMutationProposal
  proposal_id
  target_skill_id
  base_version
  mutation_kind
  proposed_patch
  rationale
  evidence_refs
  contradiction_refs
  proposed_by
  created_at
  validation_result
  approval_status
  approved_by / approved_at
  resulting_version
  schema_version
```

`mutation_kind` 至少区分 `CREATE / UPDATE / RETIRE / SUPERSEDE / INVALIDATE`；`approval_status` 至少区分 `PENDING / APPROVED / REJECTED / EXPIRED / INVALID`。

只有 `APPROVED` proposal 才能生成新的 immutable SkillRecord version；历史版本不得原地修改。

### 6.8 SkillPackageManifest

外部 Skill package 与 canonical SkillRecord 必须分离。任何 GitHub / registry / Hermes / project import 先进入 package 层：

```text
SkillPackageManifest
  package_id
  skill_id
  source_type
  source_uri
  source_revision
  content_hash
  imported_at
  importer
  scanner_version
  scanner_findings
  referenced_files
  trust_state
  approved_by / approved_at
  schema_version
```

`trust_state` 至少区分 `QUARANTINED / SCANNED / REVIEWED / APPROVED / REJECTED / SUPERSEDED`。外部 Markdown 或脚本不能因为格式合法而直接成为 ACTIVE Skill；source revision、content hash 和 scan findings 必须作为 provenance 保存。

### 6.9 Progressive Disclosure

Skill retrieval 使用三级加载，避免把完整 Skill corpus 永久注入上下文：

```text
L0 Skill Index:
  skill_id / name / purpose / short_description / risk_class / status / version

L1 Skill Core:
  initiation / preconditions / procedure / termination / verification / capabilities

L2 References:
  examples / templates / reference docs / script metadata / historical evidence
```

默认先检索 L0，只对候选加载 L1；只有任务确实需要时才加载 L2。L2 中存在脚本或引用文件不等于 execution authorization，也不得隐式扩大 `required_capabilities`。

## 7. Risk 与 Authorization 边界

### 7.1 RiskClass

V1 冻结：

```text
READ_ONLY
WRITE_LOCAL
ACT_LOCAL
EXTERNAL_EFFECT
UNKNOWN
```

解释：

- READ_ONLY：只读取本地或已授权资源，不修改环境；
- WRITE_LOCAL：创建、修改、删除、移动本地文件或持久状态；
- ACT_LOCAL：操作桌面 UI、启动会改变本机状态的流程、输入内容等；
- EXTERNAL_EFFECT：发送邮件、提交远程变更、发布内容、调用外部产生副作用的服务等；
- UNKNOWN：无法可靠分类。

### 7.2 当前项目执行政策

冻结为：

```text
READ_ONLY       -> AUTO_ALLOWED
WRITE_LOCAL     -> HUMAN_APPROVAL_REQUIRED
ACT_LOCAL       -> HUMAN_APPROVAL_REQUIRED
EXTERNAL_EFFECT -> HUMAN_APPROVAL_REQUIRED
UNKNOWN         -> HUMAN_APPROVAL_REQUIRED
```

该政策优先于 Skill status。任何由模型发起的 canonical Knowledge/Skill 持久化、Markdown/Obsidian projection 写盘或修改，同样属于 `WRITE_LOCAL`；E 默认只生成 in-memory proposal/diff，真正落盘必须经过人工批准。用户直接在受信 UI 中完成并确认的编辑可视为该次写入的显式授权，但不能被泛化为后续自动写权限。

例如：

```text
Skill.status = ACTIVE
Skill.risk = WRITE_LOCAL
```

仍然只能生成 proposal，不能自动落地。

### 7.3 MCP annotations 不作为授权真值

MCP `readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint` 只作为辅助 metadata；runtime 必须使用本地受信 capability registry 做 risk classification。

来自未知/不可信 MCP server 的 annotation 不得降低本地审批要求。

## 8. E1 — Human-authored Knowledge / Skill

E1 先证明显式知识与人工 Skill 能进入 canonical registry，而不是先做自动发现。

支持：

```text
Human Knowledge Draft
  -> parse/validate
  -> canonical KnowledgeRecord

Human Skill Draft
  -> parse/validate
  -> SkillMutationProposal(CREATE)
  -> human approval
  -> immutable DRAFT SkillRecord version
  -> verification
  -> VERIFIED / ACTIVE

External Skill Package
  -> QUARANTINED SkillPackageManifest
  -> source/hash/scan freeze
  -> human review
  -> SkillMutationProposal(CREATE)
  -> canonical SkillRecord
```

V1 必须保留原始 author/provenance，并生成 deterministic IDs / versions。未经审批的外部 package 不得进入 ACTIVE registry；模型生成或模型修改的 Skill 也不得绕过 proposal gate。

### 8.1 Human edit policy

Markdown/Obsidian 编辑不能直接覆盖 canonical registry。

推荐流程：

```text
edit projection
  -> detect diff
  -> parse as proposed change
  -> validate
  -> human review if semantic mutation
  -> create new canonical version
```

也就是说 projection 是 editable interface，但不是绕过 lifecycle 的数据库后门。

### 8.2 E1 progressive disclosure contract

E1 的 read-only retrieval 必须区分 L0/L1/L2。默认 list/search 只返回 L0；显式选中某个 Skill 后才加载 L1；L2 必须按具体 reference path 按需读取。任何 retrieval API 都不得因为展示 Skill 而自动执行 reference script、解析任意外部附件，或扩大当前 capability set。

## 9. E2 — Behavior-to-Skill Candidate Compiler

这是 Milestone E 的核心研究模块。

### 9.1 输入

只能消费已冻结的可信派生数据：

```text
B1 Transitions
B1 Sessions
B2 eligible Memory
C diagnostics / predictive signals
approved Knowledge
```

不得从 raw key content、raw screenshots、password/credential fields 自动生成 Skill。

### 9.2 Candidate discovery

第一阶段只寻找跨 session 重复子序列 / workflow patterns，不使用 unrestricted LLM 直接总结整段日志。

概念流程：

```text
session-local transition sequence
  -> normalized action/state signatures
  -> repeated subsequence mining
  -> cross-session support
  -> contradiction / branch discovery
  -> parameter abstraction
  -> SkillCandidate
```

### 9.3 Cross-session gate

单 session 内大量重复不能独立产生长期 Personal Skill。

V1 工程资格阈值暂定为：

- candidate support >= 3 independent sessions；
- human-origin supporting trajectories >= 2 sessions；
- 至少 1 个 held-out session 用于验证；
- `AI_EXECUTED` 不计入 human support；
- `UNKNOWN` 不计入 human support。

这些是项目预注册工程门槛，不声称是文献通用标准；实现前仍需在 implementation plan 中逐项冻结成测试值。

### 9.4 Negative evidence

Candidate 必须同时记录：

```text
supporting trajectories
contradictory trajectories
alternative continuations
aborted workflows
```

目标不是只找“最常见步骤”，而是识别 initiation condition 的边界。

例如：

```text
edit_python -> pytest
```

如果只在存在 test configuration 的项目中稳定出现，则 initiation 不能被泛化成：

```text
after any edit -> run pytest
```

而应表达为条件化 Skill。

### 9.5 Parameter abstraction

只允许把多条支持轨迹中稳定变化、但结构角色一致的值抽象为参数，例如：

```text
specific repo path -> {project_root}
specific test file -> {test_target}
```

安全敏感值、credential、exact short-lived key content 不得进入 Skill parameter schema。

## 10. E3 — Verification and Lifecycle

### 10.1 Verification 类型

V1 优先级：

```text
1. static/schema verification
2. evidence consistency verification
3. offline replay verification
4. held-out session verification
5. optional READ_ONLY live verification
```

E V1 不使用会产生 WRITE / ACT / EXTERNAL_EFFECT 的 live verification 自动测试。

### 10.2 Positive controls

验证需要确认：

- initiation condition 能覆盖真实支持 session；
- procedure 能解释支持 trajectory；
- termination / success condition 可从已保存状态判断；
- held-out trajectory 不依赖未来信息；
- PlannerSkill / ExecutorSkill linkage 可解析。

### 10.3 Negative controls

至少包括：

- shuffled trajectory；
- wrong-scope candidate；
- AI_EXECUTED-only candidate；
- single-session repetition candidate；
- contradictory continuation candidate；
- superseded Knowledge / Memory dependency。

### 10.4 Lifecycle transitions

```text
DRAFT
  -> CANDIDATE
  -> VERIFIED
  -> ACTIVE

ACTIVE
  -> NEEDS_REVALIDATION
  -> VERIFIED/ACTIVE
  -> RETIRED / INVALID

ACTIVE old version
  -> SUPERSEDED
```

任何 lifecycle transition 都必须留下 reason code + evidence refs。

### 10.5 Revalidation triggers

至少包括：

- B2 Memory dependency becomes INVALID / NEEDS_REVALIDATION；
- referenced Knowledge 被 supersede；
- new contradictory sessions 超过冻结阈值；
- required capability 不再存在；
- procedure verification 连续失败；
- user manually retires/rejects Skill。

## 11. E4 — Skill Retrieval / Selection Benchmark

Skill 存在不等于系统能在正确上下文选中它，因此必须独立评估 Skill selection。

### 11.1 任务

给定：

```text
current state
recent actions
eligible Memory
approved Knowledge
available Skills
```

预测：

```text
which Skill, if any, is relevant now?
```

### 11.2 Baselines

至少比较：

```text
B0 Global skill frequency
B1 Scope/context exact match
B2 Flat retrieval over all Skills
B3 Hierarchical retrieval: Planner then Executor
```

未来可加入 embedding/LLM retrieval，但 V1 不以此作为必要条件。

### 11.3 指标

固定报告：

- Top-1 skill accuracy；
- HitRate@K / MRR；
- no-skill abstention precision/recall；
- wrong-scope rate；
- unsafe-proposal rate；
- Planner→Executor consistency；
- selection latency。

### 11.4 关键消融

必须比较：

```text
Flat Skill Pool
vs
Planner/Executor Hierarchy
```

该实验直接对应 LEGOMem 给出的层级 procedural memory 启发，但我们的目标是 personal workflow selection 而非多 Agent benchmark。

## 12. E5 — Human-readable Projection

### 12.1 Projection 原则

Canonical registry 是 machine truth。

Markdown / Obsidian 只负责：

- inspect；
- review；
- annotate；
- propose edits；
- organize；
- link；
- visualize。

### 12.2 建议目录

```text
PersonalAI/
  Knowledge/
  Skills/
    Drafts/
    Candidates/
    Active/
    Retired/
  Reviews/
  Projects/
```

### 12.3 Skill projection

示例：

```yaml
skill_id: skill:python-test:v3
kind: EXECUTOR
status: ACTIVE
risk_class: ACT_LOCAL
scope: project:python
support_sessions: 12
version: 3
```

正文展示 purpose、initiation、procedure、termination、verification 与 evidence summary。

### 12.4 Round-trip 边界

必须满足：

```text
canonical -> projection -> parse
```

在不发生人工编辑时得到 semantic equivalence。

发生编辑时只产生 proposed mutation，不直接 silent-overwrite canonical state。模型触发 projection export/update 时也必须先生成 preview/diff；实际创建、修改、删除 Markdown/Obsidian 文件按 `WRITE_LOCAL` 走人工批准。

## 13. Obsidian 的定位

Obsidian 是 optional adapter / console，不是项目依赖核心。

核心架构必须在没有 Obsidian 时仍完全可运行：

```text
Core Registry
  -> generic Markdown Projection
  -> optional Obsidian Bases / Canvas / MCP adapter
```

这样未来也可以接 VS Code、Web UI 或其他知识前端。

## 14. 与 Milestone C 的依赖关系

Milestone E 不应阻断当前已经冻结的 Milestone C implementation。

正式 E2 自动 workflow discovery 进入 confirmatory 阶段前，至少要求：

1. C0 已证明存在足够行为多样性；
2. 至少一个 target space 出现 stable sequence/state signal，或独立 workflow mining 数据显示跨 session 重复结构；
3. B1/B2 artifacts 可 deterministic replay；
4. provenance gate 无已知污染；
5. 有足够独立 sessions 支持 held-out verification。

如果 C 最终显示没有稳定 next-action signal，不代表 E 一定失败；但 E2 必须使用独立的 workflow-repeat qualification，而不能假设个人行为结构存在。

## 15. Safety Boundary — Hard Gate

这是 Milestone E/F 的最高优先级系统约束之一。

当前政策：

```text
Model proposes READ_ONLY action
  -> runtime may auto-allow

Model proposes local file mutation
  -> human approval required

Model proposes desktop/computer state-changing action
  -> human approval required

Model proposes external side effect
  -> human approval required
```

审批必须发生在 effect 前，而不是事后日志确认。

### 15.1 Approval proposal 必须包含

未来 F 的 proposal 至少需要显示：

```text
skill_id / skill_version
action/tool
risk_class
target resource
expected mutation/effect
reason
relevant parameters
rollback/reversibility hint if known
```

E 只负责产生这些 metadata，不负责越过审批执行。

### 15.2 Skill cannot self-authorize

任何 Skill、LLM output、Obsidian note、MCP server instruction 都不能声明自己“已获授权”而绕过 runtime policy。

Authorization 必须来自 host/runtime 受信状态。

## 16. Provenance 与自我强化防护

Behavior-to-Skill Compiler 必须继承现有 provenance 规则：

```text
HUMAN_PHYSICAL            -> strongest behavioral evidence
AI_SUGGESTED_ACCEPTED     -> separate evidence class
AI_SUGGESTED_MODIFIED     -> separate evidence class
AI_EXECUTED               -> never counts as user-origin Skill support by default
SYSTEM / EXTERNAL         -> context/evidence only unless explicitly allowed
UNKNOWN                   -> conservative, not user-positive evidence
```

否则可能产生：

```text
AI executes workflow
→ E observes repeated workflow
→ compiles it into user Skill
→ future policy selects it more often
→ self-reinforcing behavior loop
```

该路径必须被测试明确阻断。

## 17. Privacy

E 不新增原始隐私权限。

禁止进入 canonical Knowledge/Skill 与 projection 的内容包括：

- exact STRUCTURED_SHORT keyboard content；
- password / credential fields；
- clipboard exact content，除非用户明确人工导入为 Knowledge；
- raw screenshot payload；
- secure UI text；
- secret/token/API key；
- 未经允许的原始私人文件全文。

Skill evidence 应优先保存 ID/reference，不复制原始敏感 payload。

## 18. Output Artifacts

Milestone E 计划生成：

```text
KnowledgeRecord
SkillCandidate
SkillRecord
VerificationSpec
SkillMutationProposal
SkillPackageManifest
SkillEvidenceLink
SkillDependency
SkillValidationRun
SkillSelectionRun
SkillProjectionManifest
SkillAuditEvent
```

所有 artifact 必须携带：

- schema version；
- source B1/B2/C run IDs；
- source high-water；
- config/extractor version；
- provenance summary；
- deterministic identifiers where applicable。

## 19. Validity-first Acceptance Gates

### Gate E0 — Schema Integrity

必须证明：

- deterministic IDs/versioning；
- strict provenance；
- lifecycle state machine 合法；
- risk_class 必填；
- historical Skill version 不可原地修改；
- 未批准的 SkillMutationProposal 不能生成 canonical version；
- external package 的 source/revision/hash/scan findings 不得在 canonicalization 后丢失；
- QUARANTINED / REJECTED package 不得进入 ACTIVE registry；
- no unsafe hidden fields；
- projection 不能覆盖 canonical truth。

失败：

```text
SKILL_SCHEMA_NOT_QUALIFIED
```

### Gate E1 — Human-authored Round Trip

人工 Skill 从 canonical → Markdown projection → parse-back，在无编辑时必须 semantic equivalent；人工修改必须生成 proposed mutation 而不是 silent apply。

同时必须证明：

- L0 retrieval 不自动读取完整 Skill/reference corpus；
- L2 reference/script presence 不产生 execution authorization；
- `VERIFIED` / `ACTIVE` 不改变 WRITE/ACT/EXTERNAL_EFFECT 的审批要求；
- risk class 不能被 import/mutation 静默降低；
- E0/E1 测试不得实际执行有副作用 Skill。

失败：

```text
HUMAN_SKILL_ROUNDTRIP_FAIL
```

### Gate E2 — Workflow Discovery Qualification

至少证明：

- candidate 来自多个独立 sessions；
- AI_EXECUTED-only 不可通过；
- negative evidence 参与边界确定；
- parameter abstraction 不泄漏敏感值；
- single-session repetition negative control FAIL as expected。

失败：

```text
NO_QUALIFIED_CROSS_SESSION_WORKFLOW
```

### Gate E3 — Verification Value

Candidate 通过 verification 后，必须在 held-out session 上比 naive exact-trajectory reuse 更稳定，才能声称验证/抽象有价值。

若样本不足：

```text
INSUFFICIENT_SKILL_VALIDATION_EXPOSURE
```

若 exposure 足够但无增益：

```text
NO_NONREDUNDANT_SKILL_GENERALIZATION_GAIN
```

### Gate E4 — Hierarchy Value

比较 Flat Skill Pool 与 Planner→Executor hierarchy。

只有 hierarchy 在 held-out selection 上稳定提高 primary retrieval metric、同时不提高 unsafe-proposal rate，才能声称 hierarchical Skill Plane 有增益。

否则：

```text
NO_HIERARCHICAL_SKILL_GAIN
```

### Gate E5 — Projection Safety

Markdown/Obsidian projection 必须：

- deterministic；
- no secret leakage；
- no silent canonical mutation；
- human edit creates proposal；
- corrupted/unknown fields fail closed。

失败：

```text
PROJECTION_SAFETY_FAIL
```

## 20. Statistical Discipline

E 的 workflow / Skill evaluation 默认以 session / task episode 为独立单位，不把同一 session 内的 step 当作 i.i.d. 样本。

规则：

- 报告 per-session / per-task result；
- 独立样本不足时标记 `DESCRIPTIVE_ONLY`；
- held-out sessions 必须和 candidate discovery sessions 分离；
- Skill selection 参数只能在 train/validation 上确定；
- test 不用于选择 workflow abstraction threshold；
- negative controls 与正结果同时报告。

## 21. 与 Milestone F 的边界

E 的终点：

```text
ACTIVE Skill
+ selected Skill proposal
+ risk classification
+ verification evidence
```

F 的起点：

```text
proposal
→ authorization decision
→ execution envelope
→ backend capability check
→ tool/MCP execution
→ effect verification
→ trusted-completion assessment
→ user feedback
→ provenance-aware learning
```

因此 E 不实现 side-effect executor。

同时冻结新的 F 边界不变量：

```text
Sandbox selected != policy enforced
Task completed != trusted completion
```

未来 F 必须维护受信 `BackendCapabilityProfile`，至少描述 filesystem read/write control、network ingress/egress control、clipboard、input injection、UI isolation、process isolation、credential isolation、backend version 与验证证据。如果 execution envelope 要求某项限制而当前 backend 无法强制执行，则 fail closed，而不是静默降级。

未来 F 的 `TrustedCompletionReport` 至少独立报告：`TaskOutcome`、`AuthorizationCompliance`、`StateConsistency`、`DisclosureMinimization`、`VerificationIntegrity`。该接口这里只做语义预留，不属于 E0/E1 implementation scope。

## 22. 推荐实施顺序

```text
E0 Canonical Knowledge / Skill schema
   + VerificationSpec
   + immutable Skill versioning
   + SkillMutationProposal
   + SkillPackageManifest
  ↓
E1 Human-authored Skill + approval staging
   + quarantine/provenance
   + read-only progressive disclosure
   + Markdown projection
  ↓
E2 Behavior-to-Skill Candidate Compiler
  ↓
E3 Verification + lifecycle
  ↓
E4 Skill retrieval / hierarchy benchmark
  ↓
E5 Optional Obsidian adapter / Bases views
```

Obsidian adapter 放最后，而不是第一步，防止项目架构被某个前端反向塑形。

## 23. 研究叙事

Milestone E 如果最终形成论文型贡献，主叙事不应是“我们也做了 Agent Skill”。

更合理的 Problem → Tension → Contribution 是：

```text
Problem:
Personal agents need reusable procedural knowledge.

Tension:
Existing workflow/skill memories often learn from successful agent trajectories,
but a personal system must distinguish user behavior from AI-caused behavior,
track change over time, and separate usefulness from authorization.

Hypothesis:
Cross-session provenance-aware workflow compilation plus verification
can produce more reliable personal Skills than naive trajectory reuse.

Contribution:
A Personal Knowledge & Verified Skill Plane integrating
workflow abstraction, temporal/provenance evidence, hierarchical procedural memory,
human-readable projection, and hard execution authorization boundaries.
```

## 24. 当前决策

冻结推荐架构：

```text
Core-native Knowledge / Skill Registry
+ Behavior-to-Skill Compiler
+ Verification / Lifecycle
+ Planner / Executor hierarchy
+ Markdown / Obsidian Projection
+ hard HUMAN_APPROVAL gate for WRITE/ACT
```

Milestone E written spec 完成后，不直接开始实现；先由用户 review。当前工程仍优先完成已经批准的 Milestone C implementation。

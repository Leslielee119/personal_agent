# Task Continuity MVP — Product Architecture Design

日期：2026-10-08
状态：Design approved in chat; written spec pending user review
定位：PersonalAgent 第一个真实可用产品阶段

## 1. 产品目标

Task Continuity MVP 的目标不是提高低层 next-action accuracy，而是让 PersonalAgent 成为一个用户愿意长期常驻的本地工作连续性助手。

核心用户价值：

> 当用户重新进入一个项目或任务时，系统能够基于可追溯证据恢复“上次做到哪里、当前目标、未解决问题、有效约束和建议下一步”，并允许用户快速纠正错误状态。

第一阶段优先顺序冻结为：

```text
A. 任务恢复与长期记忆
B. 主动工作助手
C. 受限可执行 Agent
```

本 spec 只覆盖 A。
## 2. 产品成功标准

MVP 不以论文指标或模型复杂度作为成功标准，而以真实使用价值判断：

1. 用户返回项目时，Resume Brief 能正确恢复最近任务状态；
2. 已失效信息不会被继续作为当前事实使用；
3. 系统不确定时能够明确输出 UNKNOWN，而不是补全故事；
4. 用户可以在几秒内纠正目标、blocker、pending item 或已失效决定；
5. Brief 中关键陈述可以展开查看 evidence；
6. 系统默认只读，不自动修改代码、执行命令或操作外部服务；
7. 项目之间的状态和记忆不会串线；
8. 用户在实际使用中主观认为恢复上下文比自己重新回忆更省事。

内部可以测 task recovery accuracy、stale-memory misuse、unsupported assertion 等指标，但这些指标服务于产品质量，不反过来定义产品价值。

## 3. V1 非目标

V1 明确不做：

- 自动点击或键盘操作；
- 自动修改代码或文档；
- 自动发送邮件或外部消息；
- 通用 Planner；
- GRU / Transformer / SSM 行为预测；
- Behavior-to-Skill 自动学习；
- unrestricted shell / filesystem write；
- 把所有桌面事件交给 LLM 自由总结。
## 4. 总体架构

推荐采用 evidence-first hybrid，而不是纯规则或纯 LLM：

```text
Raw / Canonical Events
        ↓
Evidence Layer
        ↓
Deterministic Facts
        ↓
Task State Candidates
        ↓
LLM Interpretation
        ↓
Verification / Confidence Gate
        ↓
Task Snapshot
        ↓
Resume Brief
```

原则：LLM 可以解释证据，但不能创造 canonical fact。

系统必须永久区分：

```text
Fact        = 有直接或确定性证据支持的状态
Inference   = 基于事实的模型解释
Suggestion  = 面向用户的候选下一步
```

三者不可共用同一 truth status。
## 5. Project Detection

系统首先必须知道“当前属于哪个项目”，否则长期记忆无法安全隔离。

V1 ProjectIdentity 建议至少包含：

```text
project_id
canonical_root
aliases
repo_identity
workspace_markers
created_at
last_seen_at
status
```

项目识别优先使用可核验信号：Git root、已登记 workspace root、项目配置文件、IDE workspace、用户显式绑定。

仅凭窗口标题或目录名相似不能自动合并项目。

如果多个项目候选无法确定，必须返回 UNKNOWN / AMBIGUOUS，并允许用户一次性绑定。

同一项目可以存在多个路径 alias，但 canonical project_id 必须稳定。

Task State、Memory、Resume Brief 和未来 Skill 默认全部以 project scope 隔离。
## 6. Task State

Task State 是 Phase A 的核心新增对象，不等同于低层 action sequence。

V1 建议：

```text
TaskSnapshot
  snapshot_id
  project_id
  captured_at / source_high_water
  active_artifacts
  current_goal
  last_verified_result
  blockers
  pending_items
  decisions
  constraints
  candidate_next_steps
  uncertainty
  evidence_refs
  field_provenance
  supersedes
  status
```

每个字段必须独立携带来源和状态，不能只给整个 Snapshot 一个统一 confidence。

字段允许 UNKNOWN。缺证据时 UNKNOWN 优于模型猜测。
### 6.1 Field provenance

Task State 字段至少区分：

```text
OBSERVED       直接从系统状态或事件观测
USER_DECLARED  用户明确声明
DERIVED        可确定性重建
INFERRED       模型推断
UNKNOWN        当前无法支持
```

使用规则：

- OBSERVED / USER_DECLARED / DERIVED 可以形成高信任 Brief 事实；
- INFERRED 必须在 UI 上可区分，且不能覆盖更高信任来源；
- UNKNOWN 不允许被生成器自动补全；
- 任何字段更新必须保留 evidence_refs；
- 新状态不能物理删除旧状态，而应通过 supersession / invalidation 关闭旧有效区间。

这直接复用 B2 的 temporal validity、dependency、supersession 和 evidence 语义。

### 6.2 Verified result

`last_verified_result` 只允许来自可核验结果，例如测试退出码、构建结果、Git 状态、明确文件变化或用户确认。

LLM 文字“看起来修好了”不能成为 VERIFIED RESULT。
## 7. Resume Brief

Resume Brief 是 Phase A 的第一个直接用户界面能力。

触发条件 V1：

- 用户重新进入一个已识别项目；
- 距该项目最近一次活跃超过可配置阈值；
- 或用户主动请求“恢复这个项目”。

默认卡片结构：

```text
项目 / 最近工作时间
当前目标
上次已验证结果
仍未完成
当前 blocker
有效约束
建议继续步骤
不确定项
```

每个关键条目都必须支持“查看证据”。

Brief 生成时只允许读取 `as_of` 当前恢复时刻可用的证据，不能使用未来事件重写历史解释。

Brief 默认只读，不自动执行建议步骤。

如果 TaskSnapshot 证据不足，Brief 应缩短，而不是扩大推断。
## 8. Correction Loop

用户纠错是产品能力，不是异常路径。

V1 至少支持：

```text
“当前目标已经改成 X”
“这个 blocker 已解决”
“这条约束已经失效”
“不要再使用这条信息”
“这个项目不是你识别的那个项目”
```

纠错不能直接覆盖 canonical history。

推荐流程：

```text
User correction
   ↓
USER_DECLARED evidence
   ↓
new Task State field/version
   ↓
supersede / invalidate previous field
   ↓
recompute dependent snapshot / brief
```

用户明确声明的修正优先于模型 INFERRED 状态。

“不要再记”与“这条信息已经不成立”必须区分：前者涉及数据/记忆删除语义，后者主要是 temporal invalidation。
## 9. Provenance 扩展

现有 HUMAN_PHYSICAL / AI_EXECUTED 等 execution provenance 保留，但 Phase A 需要为未来主动帮助预留额外维度。

建议正交记录：

```text
Execution Provenance
Suggestion Exposure
Behavior Relation
Learning Eligibility
```

V1 至少需要能表达：

```text
physical input + no known AI suggestion
physical input + AI suggestion previously shown
physical input + relation unknown
AI executed
system/external
```

重要边界：

```text
HUMAN_PHYSICAL != NATURAL_USER_PREFERENCE
```

用户亲手执行一个 AI 建议，执行者仍然是人，但这条行为不应自动用于“自然偏好”学习。

Phase A 只需要把数据模型预留清楚，不需要现在实现主动建议策略。
## 10. Evidence Layer

Phase A 不新增另一套原始日志，而是复用现有 canonical event plane。

Evidence Layer 的职责是把适合 Task State 的证据引用标准化，例如：

```text
Event evidence
Git evidence
Command / test result evidence
File / artifact evidence
Window / application evidence
User-declared evidence
Memory evidence
```

EvidenceRef 至少需要：

```text
evidence_id
kind
source_ref
observed_at
available_at
project_id
provenance
integrity / hash where applicable
```

`observed_at` 与 `available_at` 必须可区分，为未来处理“事实什么时候成立”与“系统什么时候知道”保留语义。

Phase A 不要求所有 evidence 都长期保存原始内容；可以只保留结构化摘要、hash 和 canonical reference，继续遵守 raw TTL / privacy policy。
## 11. LLM 边界

LLM 在 Phase A 中是解释器和生成器，不是 canonical database。

允许：

- 根据 evidence candidates 生成 current_goal / blocker 等 INFERRED candidate；
- 把结构化 TaskSnapshot 转换成简短 Resume Brief；
- 为 UNKNOWN / ambiguous 状态提出澄清问题；
- 生成 candidate_next_steps，但必须标记为 suggestion。

不允许：

- 无 evidence 创建 OBSERVED / DERIVED fact；
- 把模型输出直接写成 USER_DECLARED；
- 自动将 candidate_next_steps 标成 pending item；
- 绕过 supersession / dependency 直接修改 Memory；
- 因语言表达自信而提升 trust level。

如果 LLM 不可用，系统仍应能够显示 deterministic facts 和最后一个已持久化 TaskSnapshot；产品不能因为模型服务失败而完全不可恢复。
## 12. Persistence 与版本语义

Task Continuity 应复用现有 append-only / temporal design，而不是维护一个可变 JSON 当前状态文件作为唯一真相。

推荐对象：

```text
ProjectRecord
EvidenceRecord
TaskStateFieldVersion
TaskSnapshot
ResumeBriefRecord
CorrectionRecord
```

`TaskSnapshot` 是某个 source_high_water / as_of 时刻的 materialized view（物化视图），不是覆盖历史的 mutable row。

字段更新必须产生新 version，并通过 `supersedes` / `superseded_by` / validity interval 表达演化。

Resume Brief 必须记录它基于哪个 snapshot 和 evidence set 生成，以便之后解释“为什么当时这么说”。

用户纠错后的新 Brief 不修改旧 Brief；旧 Brief 保留为审计记录，但默认 UI 只显示当前有效版本。
## 13. UI / Interaction Surface

Phase A 不先做复杂桌面应用，先做最小可用面板。

推荐三个入口：

```text
Resume Brief
Correct State
View Evidence
```

默认 Resume Brief 示例：

```text
PersonalAgent — personal_agent
上次工作：昨天 18:40

目标
继续 Task Continuity MVP

最近验证
pytest 274 passed / 2 skipped

未完成
• formal 8h soak
• Task State implementation

阻碍 / 风险
• 当前 action abstraction 仍偏低层

建议继续
1. 检查 soak 结果
2. 继续 Task State
```

每个条目需要能够展开来源；INFERRED / SUGGESTED 项应有视觉区分。
## 14. 与现有模块的关系

现有成果尽量复用，不重写：

```text
Milestone A  → 提供 canonical events / privacy / replay
B1           → 提供 session / state / transition reconstruction
B2           → 提供 temporal validity / provenance / supersession
C            → 降为内部诊断与辅助预测能力
E0/E1        → 保留 trusted knowledge / skill substrate
```

取消旧的强依赖：

```text
C 低层 next-action 成功
    !=
B2 Memory 才有资格验证产品价值
```

Task Continuity 可以直接使用 B2 做任务恢复验证。

E2 Behavior-to-Skill 也不再要求低层 action prediction Gate 先通过；未来应依赖“任务成功 + 可验证 trajectory + 适用条件”。

现有 longitudinal acquisition 继续保留，但用途从单纯 next-action benchmark 扩展为真实长期产品数据。
## 15. 隐私与本地优先

Task Continuity 继承 Milestone A 的本地优先与 raw TTL 原则。

V1 默认：

- canonical structured evidence 本地保存；
- 屏幕 raw artifact 继续受 TTL 管理；
- secure UI / credential 内容不进入 Task State；
- Resume Brief 不应包含被 privacy sanitizer 移除的信息；
- 项目状态只在本机 canonical store 中持久化；
- 后续若接入远程模型，必须单独定义最小化上下文出口和显式策略，本 spec 不默认允许上传完整事件历史。

TaskSnapshot 与 ResumeBrief 属于长期个人数据，应支持项目级清除和用户纠错语义。

“删除原始来源”与“使记忆失效”需要独立处理；如果来源被删除，派生状态不能继续假装拥有完整证据链。
## 16. MVP 验收标准

Phase A V1 只有满足以下条件才称为“可用 MVP”：

1. 至少能登记和稳定识别多个 project；
2. 每个 project 的 Task State 完全隔离；
3. TaskSnapshot 可从 evidence 重建并具有稳定 ID / version；
4. Resume Brief 可以在无 LLM 情况下展示 deterministic core；
5. LLM 推断与事实在 schema 和 UI 上均可区分；
6. 至少支持 goal / blocker / pending item / constraint 的用户纠错；
7. 纠错产生 supersession，而不是覆盖历史；
8. 旧约束失效后，新 Brief 不再使用旧约束；
9. 每条关键 Brief statement 均可追溯 evidence；
10. 项目重新进入时能够触发或手动生成 Resume Brief；
11. 默认路径没有自动执行副作用；
12. 现有 A/B1/B2 数据与 privacy tests 不回归。

产品 dogfood（自用）门槛：至少连续用于真实项目恢复，并记录错误恢复、漏项、过期信息误用和人工纠正次数。

该 dogfood 是产品迭代依据，不把固定 session 数包装成通用统计证明。
## 17. Work Episode 与技术 Session 分离

产品层不能把 `runtime.restart` 产生的 session_id 当成真实任务边界。

新增概念：

```text
WorkEpisode
  episode_id
  project_id
  started_at
  ended_at
  evidence_range
  continuation_of
  boundary_reason
  confidence
```

技术 session 只是 capture 生命周期；WorkEpisode 表示一次自然工作段，可以跨技术 restart，也可以在同一 capture session 中切换多个项目。

V1 episode boundary 可以先由项目切换、长时间 inactive 和用户显式结束共同形成，并允许 UNKNOWN / uncertain boundary。

TaskSnapshot 与 Resume Brief 应主要基于 project + WorkEpisode，而不是简单 session_id。

这也为未来长期评估提供更真实的依赖单位，但 Phase A 首要用途是产品状态恢复。
## 18. 组件边界

Phase A 建议固定以下服务边界：

```text
ProjectResolver
EvidenceAssembler
WorkEpisodeBuilder
TaskStateBuilder
ResumeBriefService
CorrectionService
```

语义接口：

```text
ProjectResolver.resolve(observation) -> ProjectResolution
EvidenceAssembler.build(project_id, as_of) -> EvidenceSet
WorkEpisodeBuilder.update(project_id, evidence) -> WorkEpisode
TaskStateBuilder.build(project_id, episode_id, evidence, as_of) -> TaskSnapshot
ResumeBriefService.render(snapshot_id) -> ResumeBrief
CorrectionService.apply(user_correction) -> new evidence + supersession
```

所有 `as_of` 查询必须只读取该时间点已经可用的证据。

TaskStateBuilder 可以组合 deterministic extractor 和 LLM interpreter，但输出必须保留字段级 provenance。

UI 不直接写数据库；所有纠错经过 CorrectionService。
## 19. Fail-Closed 行为

以下情况不得伪装成正常恢复：

- project identity ambiguous；
- evidence 被删除或完整性校验失败；
- Task State 只有 inference、没有足够 grounding；
- current goal 与 user-declared goal 冲突；
- dependency 已失效；
- LLM 输出无法映射到 evidence；
- snapshot schema/version 不兼容。

对应行为优先是：

```text
显示不确定
→ 展示已有确定事实
→ 请求最少必要澄清
```

而不是生成完整但不可验证的 Brief。

用户纠错和 evidence invalidation 必须能够触发依赖状态重算。
## 20. Phase A 交付切片

实现应按可 dogfood 的纵向切片推进，而不是先铺满所有 schema。

推荐顺序：

```text
A1 Project Identity + manual Resume Brief
A2 Evidence-grounded deterministic Task Snapshot
A3 User Correction + supersession
A4 WorkEpisode + automatic resume trigger
A5 LLM-assisted interpretation with grounding gate
A6 Minimal desktop/panel UX
```

A1/A2 先确保即使没有 LLM，也能对 Git 项目给出可信的基本恢复信息。

A3 是长期可用性的必要条件，不能推迟到“以后做反馈”。

A4 才开始让系统自动判断什么时候应该展示恢复卡片。

A5 只增强语义覆盖，不改变 canonical truth model。

A6 以真实日常使用为验收，不追求复杂视觉设计。
## 21. Phase B / C 的边界

Phase B（主动工作助手）只有在 Phase A 的 Task State 与 Resume Brief 足够可信后开放。

Phase B 将新增：

```text
Need / Opportunity Prediction
Assistance Policy
Interruption Cost
Shadow Mode
Suggestion Exposure provenance
```

Phase C（受限可执行 Agent）只有在 B 的帮助决策和 E0/E1 trust substrate 基础上开放。

Phase C 必须额外具备：

- capability-scoped authorization；
- effect typing；
- precondition revalidation；
- transaction / commit boundary；
- rollback or compensation where meaningful；
- independent result verification。

Task Continuity MVP 本身不获得这些权限。
## 22. 冻结决策

本设计冻结以下产品方向：

1. 产品主线从低层 next-action prediction 转向 task continuity；
2. 低层 prediction 保留为辅助能力，不作为 Phase A 前置 Gate；
3. Task State 成为 Memory 与用户界面之间的核心产品表示；
4. LLM interpretation 与 canonical fact 永久分离；
5. correction 是核心交互，不是异常处理；
6. technical session 与 WorkEpisode 永久分离；
7. Phase A 默认无副作用执行权限；
8. E0/E1 trust plane 保留，E2 不再依赖低层 prediction 成功；
9. 真实可用性优先于论文 benchmark 完整度；
10. 当前正在运行的 Milestone A 8-hour soak 继续作为独立工程资格，不因产品路线调整而作废。

## 23. 下一阶段

本 spec 经用户书面审阅批准后，下一步才进入 implementation planning。

Implementation plan 应优先落 A1→A3，使系统尽快能够在真实 PersonalAgent 项目上 dogfood：识别项目、生成 evidence-grounded snapshot、显示 Resume Brief、接受用户纠错。

在 spec 批准之前，不实现 Task Continuity 产品代码。

# Task Continuity MVP — Product Architecture Design

日期：2026-10-08
状态：Final approved design baseline; five review boundaries integrated; implementation planning authorized on 2026-10-08
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
6. Phase A 只允许读取已登记范围内的项目状态，并写入 PersonalAgent 自己的状态库、纠错记录和必要缓存；项目观察必须通过固定、可审计的只读适配器完成。模型输出不能进入任意命令执行路径，不能修改项目文件、启动测试或构建、操作界面或访问外部服务；
7. 项目、工作副本与任务之间的状态和记忆不会串线；
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
## 5. Project / WorkCopy / Task Detection

系统首先必须知道“当前属于哪个项目、哪个工作副本、哪个任务”，否则长期记忆无法安全隔离。

V1 必须把项目身份、工作副本身份和当前任务身份分开。

```text
ProjectIdentity
  project_id
  repo_identity / project_fingerprint
  shared_constraints
  created_at
  last_seen_at
  status

WorkCopyIdentity
  workcopy_id
  project_id
  canonical_root
  aliases
  vcs_branch_or_revision_hint
  workspace_markers
  created_at
  last_seen_at
  status

TaskIdentity
  task_id
  project_id
  workcopy_id?          # 可空：任务可跨工作副本，但 V1 默认绑定一个工作副本
  title
  created_at
  status
```

项目识别优先使用可核验信号：Git root、已登记 workspace root、项目配置文件、IDE workspace、用户显式绑定。

仅凭窗口标题、目录名相似或 Git branch 名不能自动合并项目或永久定义任务身份。

如果 project / workcopy / task 候选无法确定，必须返回 UNKNOWN / AMBIGUOUS，并允许用户手动选择或绑定。

同一 Project 可以有多个 WorkCopy，例如主仓库和 git worktree。它们共享稳定 `project_id`，但拥有不同 `workcopy_id`；当前目标、blocker、验证结果和局部 pending item 默认属于 task/workcopy scope，不得因为属于同一 repo 自动合并。

只有明确声明为 project-shared 的约束或知识才允许跨工作副本复用；无法确定归属时不自动上提到 project scope。

V1 不建设完整任务管理系统：第一版允许用户手动选择当前 Task，并将其绑定到当前 WorkCopy。Task State、Resume Brief 和任务级 Memory 默认至少按 `project_id + workcopy_id + task_id` 隔离。
## 6. Task State

Task State 是 Phase A 的核心新增对象，不等同于低层 action sequence。

V1 建议：

```text
TaskSnapshot
  snapshot_id
  project_id
  workcopy_id
  task_id
  episode_id?           # A1-A3 可空；A4 引入 WorkEpisode 后再绑定
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

- provenance 只回答“这条信息如何得知”，不能被解释成概率意义上的可信度排序；
- validity / applicability 独立回答“这条信息当前是否仍适用”；
- OBSERVED / USER_DECLARED / DERIVED 可以进入 Brief，但其适用范围仍必须由各自 evidence scope 决定；
- INFERRED 必须在 UI 上可区分，且不能覆盖冲突的直接证据或用户声明；
- USER_DECLARED 与 OBSERVED 冲突时保留冲突本身，不通过固定 provenance 排序静默覆盖；由字段语义、时间和用户纠错决定当前展示；
- UNKNOWN 不允许被生成器自动补全；
- 任何字段更新必须保留 evidence_refs、validity/applicability 和 scope；
- 普通状态更新不物理删除旧版本，而应通过 supersession / invalidation 关闭旧有效区间；用户显式删除属于第 15 节定义的例外。

这直接复用 B2 的 temporal validity、dependency、supersession 和 evidence 语义。

### 6.2 Verified result

`last_verified_result` 只允许来自可核验结果，例如测试退出码、构建结果、Git 状态、明确文件变化或用户确认。

验证结果必须显式绑定适用范围，而不是只保存一句“tests passed”。至少记录：

```text
VerifiedResult
  result_id
  project_id
  workcopy_id
  task_id?
  check_kind
  command_or_adapter_scope
  environment_fingerprint
  code_state_fingerprint
  observed_at
  outcome
  evidence_refs
  applicability_status
```

`code_state_fingerprint` 不能只等于 commit：存在未提交修改时必须把 dirty state / relevant diff fingerprint 纳入适用性判断。

后续发生相关代码、配置、依赖或环境变化时，历史验证结果仍保留，但当前 `applicability_status` 应变为 `STALE / NEEDS_REVALIDATION`，Brief 不得继续把它写成“当前仍通过”。

用户声明“测试通过”支持的是 `USER_DECLARED` 的测试结果；观察到退出码支持的是对应命令与环境范围内的 `OBSERVED/DERIVED` 结果。两者来源不同，不能互相伪装。

LLM 文字“看起来修好了”不能成为 VERIFIED RESULT。
## 7. Resume Brief

Resume Brief 是 Phase A 的第一个直接用户界面能力。

触发条件 V1：

- A1-A3：用户主动选择已登记的 project/workcopy/task 并请求恢复；
- A4+：系统可靠识别用户重新进入某个已登记 workcopy/task，且距该任务最近一次自然工作超过可配置阈值；
- identity 不明确时只提示选择，不自动拼接多个 task 的 Brief。

默认卡片只展示恢复工作最需要的四项：

```text
当前任务
上次停在哪里
需要注意的未解决事项或状态变化
建议继续的一步
```

缺少某项时直接省略，不显示一排 UNKNOWN。最近验证详情、完整约束、不确定项和证据进入展开视图。

“未解决事项”只包含确实影响当前 task/workcopy 继续推进的 blocker、pending item 或状态变化；研究风险、项目总览和与当前任务无直接关系的技术债不得默认塞入 Brief。

任何“最近验证”都必须同时显示 applicability；历史 PASS 但当前 `STALE / NEEDS_REVALIDATION` 时，应写成“上次通过，当前状态尚未复验”，不能简化成“通过”。

每个关键条目都必须支持“查看证据”。

Brief 生成时只允许读取 `as_of` 当前恢复时刻可用的证据，不能使用未来事件重写历史解释。

Brief 默认只读，不自动执行建议步骤。

如果 TaskSnapshot 证据不足，Brief 应缩短，而不是扩大推断。
## 8. Correction Loop

用户纠错是产品能力，不是异常路径。

V1 至少支持两类输入。

首次建档 / 新任务初始化：

```text
“当前任务是 X”
“当前目标是 Y”
“我已经做到 Z”
“下一步准备做 N”
```

对已有状态的纠错：

```text
“当前目标已经改成 X”
“这个 blocker 已解决”
“这条约束已经失效”
“不要再使用这条信息”
“这个项目 / 工作副本 / 任务不是你识别的那个”
```

首次建档不是“修改一个不存在的字段”，而是创建明确的 `USER_DECLARED` TaskIdentity / Task State evidence，使 A1 在没有 LLM 和长期历史时也能立即形成可用恢复状态。

普通纠错不能直接覆盖 canonical history；用户显式删除按第 12/15 节的 privacy-first 删除语义处理，是历史保留规则的明确例外。

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
workcopy_id?
task_id?
scope
provenance
integrity / hash where applicable
```

`observed_at` 与 `available_at` 必须可区分，为未来处理“事实什么时候成立”与“系统什么时候知道”保留语义。

Phase A 不要求所有 evidence 都长期保存原始内容；可以只保留结构化摘要、hash 和 canonical reference，继续遵守 raw TTL / privacy policy。

项目观察只能通过登记过的 observation adapter。适配器可以采用库 API，也可以封装固定的只读 Git/文件系统查询命令，但必须使用固定参数面、禁止模型自由拼接命令，并避免触发项目 hook、脚本、构建或其他副作用。所有 adapter 输出作为 evidence 进入同一 provenance / scope / integrity 体系。
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
WorkCopyRecord
TaskRecord
EvidenceRecord
VerifiedResultRecord
TaskStateFieldVersion
TaskSnapshot
ResumeBriefRecord
CorrectionRecord
DeletionTombstoneRecord
```

`TaskSnapshot` 是某个 source_high_water / as_of 时刻的 materialized view（物化视图），不是覆盖历史的 mutable row。

字段更新必须产生新 version，并通过 `supersedes` / `superseded_by` / validity interval 表达演化。

Resume Brief 必须记录它基于哪个 snapshot 和 evidence set 生成，以便之后解释“为什么当时这么说”。

普通纠错后的新 Brief 不修改旧 Brief；旧 Brief 保留为审计记录，但默认 UI 只显示当前有效版本。

用户显式删除是 append-only 历史保留规则的例外。删除请求优先于审计便利性：被删除的敏感内容必须从 canonical evidence content、派生 Task State 字段、旧 Brief、检索索引和必要缓存中清除。若系统必须保留审计痕迹，只允许保留不包含被删除内容的最小 tombstone（例如删除发生时间、范围和不可逆状态），不得通过旧版本或 cache 恢复原内容。
## 13. UI / Interaction Surface

Phase A 不先做复杂桌面应用，但 A1 就必须提供可直接使用的最小交互入口，不能等到 A6 才让用户看到产品。

A1 至少提供：

```text
Select / Bind Project + WorkCopy + Task
Create / Update Task Note
Open Resume Brief
```

A3 增加：

```text
Correct State
View Evidence
Delete / Forget scoped information
```

这些入口可以先是本地 CLI/TUI 或极简面板；A6 才负责桌面常驻、自动唤起和视觉体验完善。

默认 Resume Brief 示例：

```text
PersonalAgent — personal_agent / task-continuity-spec

当前任务
冻结 Task Continuity MVP 架构

上次停在
Astra 审阅完成，等待补齐 5 个边界后进入 implementation planning

需要注意
• formal 8h soak 仍在运行

建议继续
补齐 spec 边界并重新审阅
```

最近验证、完整约束、不确定项和证据放在展开视图；与当前任务无直接推进关系的研究风险不进入默认卡片。

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

TaskSnapshot 与 ResumeBrief 属于长期个人数据，应支持至少 project / workcopy / task / evidence-scope 的定向清除，而不是只能整项目删除。

需要区分三类状态：

```text
EXPIRED_BY_TTL       原始材料按保留策略自然过期
USER_DELETED         用户主动要求删除内容
INTEGRITY_INVALID    内容仍应存在但完整性校验失败
```

三者不能共用一个“missing evidence”状态。TTL 过期后可以继续保留此前允许持久化的结构化事实，但必须明确其原始材料不可再查看；用户删除则要求按第 12 节清除被删除内容及可反推出该内容的派生物；integrity failure 必须 fail-closed，不得继续把受影响证据当作可靠来源。

Hash 只用于一致性/完整性检查，不能替代已经删除的证据内容，也不能因为“hash 还在”就声称原陈述仍有完整证据链。

每条派生 Task State 还必须单独判断剩余结构化 evidence 是否足以支持该陈述；若不足，应降为 `UNSUPPORTED / NEEDS_RECONFIRMATION` 或从当前 Brief 移除。
## 16. MVP 验收标准

Phase A V1 只有满足以下条件才称为“可用 MVP”：

1. 至少能登记和稳定识别多个 project，并区分同一 project 的多个 workcopy；
2. task/workcopy 状态严格隔离；无法确定归属时不自动合并；
3. 用户可以手动选择/绑定当前 task，并在首次使用时直接录入“当前目标、做到哪里、下一步”；
4. A1 就存在手动打开 Resume Brief 的可用入口，A3 就存在纠错与证据查看入口；
5. TaskSnapshot 在没有 WorkEpisode 的 A1-A3 阶段即可按 project + workcopy + task + time boundary 重建，并具有稳定 ID / version；
6. Resume Brief 可以在无 LLM 情况下展示 deterministic core；
7. LLM 推断与事实在 schema 和 UI 上均可区分；
8. 至少支持 goal / blocker / pending item / constraint 的用户纠错；
9. 普通纠错产生 supersession，而不是覆盖历史；用户显式删除则按删除语义清除内容；
10. 旧约束或过期验证结果失效后，新 Brief 不再把它们表述为当前有效；
11. 每条关键 Brief statement 均可追溯 evidence 及其 applicability；
12. 同一 repo 的另一 worktree/task 的目标、blocker 和验证结果不会混入当前 Brief；
13. A4 后项目重新进入可以自动触发；A1-A3 至少支持手动生成 Resume Brief；
14. Phase A 只执行已登记的只读 observation adapter，并只写 PersonalAgent 自身状态；模型输出没有项目副作用执行路径；
15. 现有 A/B1/B2 数据与 privacy tests 不回归。

产品 dogfood（自用）门槛：至少连续用于真实项目恢复，并记录错误恢复、漏项、过期信息误用和人工纠正次数。

该 dogfood 是产品迭代依据，不把固定 session 数包装成通用统计证明。
## 17. Work Episode 与技术 Session 分离

产品层不能把 `runtime.restart` 产生的 session_id 当成真实任务边界。

新增概念：

```text
WorkEpisode
  episode_id
  project_id
  workcopy_id
  task_id
  started_at
  ended_at
  evidence_range
  continuation_of
  boundary_reason
  confidence
```

技术 session 只是 capture 生命周期；WorkEpisode 表示一次自然工作段，可以跨技术 restart，也可以在同一 capture session 中切换多个项目。

V1 episode boundary 可以先由项目切换、长时间 inactive 和用户显式结束共同形成，并允许 UNKNOWN / uncertain boundary。

A1-A3 不依赖 WorkEpisode：在这一阶段，TaskSnapshot 与 Resume Brief 使用 `project + workcopy + task + explicit/as_of time boundary` 恢复状态。

A4 引入 WorkEpisode 后，再把自然工作段作为辅助边界加入恢复逻辑；WorkEpisode 永远不能替代 project/workcopy/task identity，也不能退化为简单 session_id。

这也为未来长期评估提供更真实的依赖单位，但 Phase A 首要用途是产品状态恢复。
## 18. 组件边界

Phase A 建议固定以下服务边界：

```text
ProjectResolver
WorkCopyResolver
TaskSelector
EvidenceAssembler
TaskStateBuilder
ResumeBriefService
CorrectionService
WorkEpisodeBuilder   # A4+
```

语义接口：

```text
ProjectResolver.resolve(observation) -> ProjectResolution
WorkCopyResolver.resolve(project_id, observation) -> WorkCopyResolution
TaskSelector.select_or_create(project_id, workcopy_id, user_input?) -> TaskIdentity
EvidenceAssembler.build(project_id, workcopy_id, task_id, as_of) -> EvidenceSet
TaskStateBuilder.build(project_id, workcopy_id, task_id, evidence, as_of, episode_id=None) -> TaskSnapshot
ResumeBriefService.render(snapshot_id, mode="compact") -> ResumeBrief
CorrectionService.apply(user_correction_or_initial_note) -> new evidence + supersession/deletion effect
WorkEpisodeBuilder.update(project_id, workcopy_id, task_id, evidence) -> WorkEpisode   # A4+
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
A1 Project + WorkCopy + Task binding, first-use note, manual Resume Brief
A2 Evidence-grounded deterministic Task Snapshot + result applicability
A3 Correction / evidence view / scoped delete + supersession
A4 WorkEpisode + automatic resume trigger
A5 LLM-assisted interpretation with grounding gate + suggestion exposure
A6 Desktop integration / panel UX polish
```

A1 就必须可自用：用户能选择或创建当前 task、绑定 workcopy，并直接填写“当前目标 / 做到哪里 / 下一步”；随后可以手动打开 compact Resume Brief。此阶段不依赖 WorkEpisode 或 LLM。

A2 增加只读 observation adapter、EvidenceSet、TaskSnapshot 和 VerifiedResult applicability，使 Brief 能区分“历史上验证通过”与“当前仍适用”。

A3 是长期可用性的必要条件：提供直接可用的纠错、查看证据和 scoped delete 入口，普通更新走 supersession，删除走 privacy-first 清除语义。

A4 才开始让系统根据 WorkEpisode / inactivity / project re-entry 自动判断什么时候应该展示恢复卡片。

A5 只增强语义覆盖，不改变 canonical truth model；只要 UI 展示模型生成的 candidate_next_step，就必须记录 `suggestion_exposure`，即使是用户主动打开 Brief，而不是等到 Phase B 主动推送才记录。

A6 负责桌面常驻、自动唤起、交互流畅性和视觉完善，不负责补上 A1-A3 缺失的核心产品入口。
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

Phase C（受限可执行 Agent）不以 Phase B 的主动预测成功为硬前提。用户明确请求的受限执行，可以在 Task State 足够可信、E0/E1 trust substrate 就绪，并满足独立的授权/执行安全 Gate 后逐项开放；主动式自动执行则仍需额外经过 Phase B 的帮助时机与打扰风险验证。

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
6. technical session 与 WorkEpisode 永久分离；Project / WorkCopy / Task 也永久分离，分支名不充当永久任务身份；
7. Phase A 允许只读观察已登记项目，并写 PersonalAgent 自身状态；模型输出默认无项目副作用执行权限；
8. provenance、validity/applicability 与 evidence scope 分离，历史验证不自动等于当前有效；
9. 普通状态更新保留版本历史，但用户显式删除优先于审计保留；
10. E0/E1 trust plane 保留，E2 不再依赖低层 prediction 成功；
11. 真实可用性优先于论文 benchmark 完整度；
12. 当前正在运行的 Milestone A 8-hour soak 继续作为独立工程资格，不因产品路线调整而作废。

## 23. 下一阶段

本 spec 已于 2026-10-08 获得用户最终批准，implementation planning 已授权。

Implementation plan 应优先落 A1→A3，使系统尽快能够在真实 PersonalAgent 项目上 dogfood：识别 project/workcopy/task、首次建档、生成 evidence-grounded snapshot、显示 compact Resume Brief、查看证据、接受纠错与 scoped delete。

A1→A3 的首个端到端验收场景冻结为：**隔天返回 PersonalAgent 的某个工作副本，系统恢复正确任务，明确说明历史验证结果当前是否仍适用，用户可以立即纠错；同一仓库另一 worktree/task 的目标、blocker 和验证结果不得混入。**

产品代码实施必须等待 implementation plan 完成并获得用户对执行方式的确认。

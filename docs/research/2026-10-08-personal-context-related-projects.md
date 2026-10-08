# PersonalAgent 相似项目调研（2026-10-08）

## 结论

PersonalAgent 所处方向已经有真实产品和开源项目，不应把“长期记忆”“桌面历史”或“任务 handoff”本身当作差异化。

当前最接近的工作可分为四类：

1. 全量桌面历史与检索：Screenpipe、Pieces、Windows Recall、OpenRecall、Windrecorder；
2. 个人工作上下文层：MyContext、Personal Model；
3. AI/编码任务连续性：ContextSpindle、Continuity、Tusk、context-continuity；
4. Stateful Agent Memory：Letta、Khoj 等。

本项目应继续聚焦：**真实工作活动 -> Project/WorkCopy/Task 状态 -> 时态有效性 -> 自动恢复 -> 后续帮助决策**。
## 1. Screenpipe

仓库：https://github.com/screenpipe/screenpipe

定位：本地持续记录屏幕/音频，形成可搜索的 computer history，并通过 Pipes 运行基于工作活动的后台 agent。

值得借鉴：
- 常驻采集与上层 agent 解耦；
- timeline 是用户检查“系统到底看到了什么”的自然 UI；
- day recap / unfinished work / blockers 这类输出比原始 OCR 更接近产品价值；
- background agent 应由明确 trigger 驱动，而不是持续自由运行。

不直接照搬：
- PersonalAgent 已有 event-sourced capture，不需要转成全量视频/OCR 产品；
- 我们的 canonical truth 是 Task State，而不是 screen history 本身。

## 2. Pieces Long-Term Memory

资料：https://pieces.app/ 与 https://docs.pieces.app/

定位：后台捕获跨应用 workflow context，提供 Timeline、Conversational Search、brief/recap，并通过 MCP 把长期上下文提供给其他 AI 工具。
值得借鉴：
- 默认 compact view，详细 timeline/evidence 按需展开；
- memory 可以跨 AI client 使用，而不是锁死在一个聊天窗口；
- 用户可以按时间、来源、模态删除数据。

差异：
- Pieces 强项是“可搜索的长期 workflow context”；
- PersonalAgent 更应强调“当前任务状态、验证是否仍适用、恢复下一步”。

## 3. MyContext

仓库：https://github.com/openTrinity/mycontext

定位：local-first 的个人工作 context layer，把 IM、文档、会议、本地活动等组织为可演进的个人上下文，并提供 desktop、检索、图谱和受控 agent runtime。

这是目前架构思想上与 PersonalAgent 最接近的项目之一。

值得借鉴：
- source ingestion 与 context consumption 解耦；
- evidence before answers；
- AI 是 context consumer，不是事实所有者；
- consequential action 需要独立授权。

当前差异：MyContext 的公开主线更偏多源 personal context / graph / digital self；PersonalAgent 当前首要产品目标是 task continuity 与 task re-entry。
## 4. Personal Model

仓库：https://github.com/Intuition-Lab/personal-model

定位：从用户授权的 focused activity 构建 evidence-linked 的 Personal Model，通过 MCP 提供给 Claude Code、Codex、Cursor 等客户端。

值得借鉴：
- evidence-linked observation，而不是不可审计的隐藏 summary；
- 用户可 inspect / correct / export / delete；
- 一份长期个人上下文服务多个 agent。

差异：它更偏“用户模型 / HUMAN.md”；PersonalAgent 当前不应过早把任务事实泛化为稳定人格或偏好。

## 5. ContextSpindle / Continuity / Tusk

这些项目直接证明“task continuity / handoff”本身已有实现。

- ContextSpindle：https://github.com/reacherwu/ContextSpindle
- Continuity：https://github.com/Noctilucenty/Continuity
- Tusk：https://github.com/gioe/tusk

共同能力包括 task ID、goal、blocker、next action、decision、evidence、history、handoff/resume，Tusk 还显式支持 isolated worktree 与 verification lifecycle。
这意味着 PersonalAgent 的 A1-A3 不是“市场上没人做过”，而是已经进入一条被验证有需求的产品方向。

真正应该继续拉开的差异：
- 不只服务 AI coding session，而是来自真实桌面活动；
- Project / WorkCopy / Task 与自然 WorkEpisode 分离；
- verified result 具有 applicability，不把历史 PASS 当当前 PASS；
- provenance / correction / scoped deletion 是基础能力；
- 未来主动帮助基于 task state，而不是纯聊天记忆。

## 6. Windows Recall / OpenRecall / Windrecorder

这类产品证明“自动记录 -> 时间线 -> 搜索过去电脑活动”有明确用户价值，但主要解决 retrieval，而不是 canonical task state。

因此 PersonalAgent 不应重复建设一个截图搜索器。屏幕/窗口历史只应作为 evidence source；最终用户看到的是 task recovery card。

## 对 A4/A6 的直接设计影响

1. A4 使用独立 Resume Trigger，不让 UI 自己推断何时弹出；
2. 自动 trigger 需要 human-activity grounding，避免后台文件变更触发；
3. WorkEpisode 是自然工作段，不等价于 capture session；
4. A6 默认只显示四项 compact brief，timeline/evidence 作为 drill-down；
5. 暂不加入全量截图 timeline、复杂 knowledge graph、agent automation marketplace。

## 当前产品定位

**PersonalAgent = evidence-grounded longitudinal work assistant，而不是 Rewind clone，也不是单纯 agent checkpoint manager。**

A4 的验收重点因此是“准确知道什么时候用户重新进入一个已有任务”，而不是增加更多记忆字段。

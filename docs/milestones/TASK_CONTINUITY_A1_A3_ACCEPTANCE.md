# Task Continuity A1–A3 Dogfood / Acceptance

日期：2026-10-08
范围：Task Continuity A1–A3；不包含 A4 自动恢复触发、A5 LLM 解释或任何执行能力。

## 1. 当前可用能力

A1–A3 提供一个完全本地、手动触发的任务连续性闭环：

- 显式绑定 `Project / WorkCopy / Task`；
- 首次录入当前目标、上次位置和下一步；
- 手动打开 Compact Resume Brief；
- Git workcopy 只读观察与 code-state fingerprint；
- 记录用户声明的验证结果，并判断当前是否仍适用；
- 纠正 scalar 状态、添加/解决 blocker、pending item、constraint；
- 查看 task-scoped evidence；
- 按 evidence/task/workcopy/project 范围显式删除 Task Continuity 数据。

所有产品状态保存在 `<data-dir>/continuity.db`。原始 canonical desktop events 仍位于 `events.db`，A1–A3 不复制整份事件历史。

## 2. 权限边界

Phase A 只允许固定 observation adapter 读取已登记工作副本，并写 PersonalAgent 自身的 `continuity.db`。

不会：修改项目文件、运行测试或构建、控制 UI、发送外部请求、执行模型生成命令。`continuity-record-result` 只记录用户声明的结果并读取当前 Git 指纹；它不会运行 `--scope` 中的命令文本。

## 3. Dogfood 命令

首次建档：

```powershell
ppa --data-dir E:\Experiment\personal-predictive-ai-runtime\continuity-dogfood continuity-init `
  --project-key personal_agent `
  --workcopy-root E:\Experiment\personal-predictive-ai `
  --task-title "Task Continuity" `
  --goal "继续当前产品任务" `
  --last-position "上次已完成的具体位置" `
  --next-step "下一步动作"
```

手动恢复：

```powershell
ppa --data-dir E:\Experiment\personal-predictive-ai-runtime\continuity-dogfood `
  continuity-resume --task-id <TASK_ID>
```

查看 JSON / evidence：

```powershell
ppa --data-dir <DATA_DIR> continuity-resume --task-id <TASK_ID> --format json
ppa --data-dir <DATA_DIR> continuity-evidence --task-id <TASK_ID>
```

纠错和 blocker：

```powershell
ppa --data-dir <DATA_DIR> continuity-correct --task-id <TASK_ID> `
  --field current_goal --value "新的目标" --action set
ppa --data-dir <DATA_DIR> continuity-correct --task-id <TASK_ID> `
  --field blockers --value "待解决问题" --action add
ppa --data-dir <DATA_DIR> continuity-correct --task-id <TASK_ID> `
  --field blockers --value "待解决问题" --action resolve
```

记录验证结果（不会执行命令）：

```powershell
ppa --data-dir <DATA_DIR> continuity-record-result --task-id <TASK_ID> `
  --check-kind pytest --outcome pass --scope "pytest -q"
```

显式删除：

```powershell
ppa --data-dir <DATA_DIR> continuity-forget --scope evidence --id <EVIDENCE_ID>
```

删除优先于历史保留。Task Continuity 使用 SQLite `secure_delete=ON`，删除后 checkpoint/truncate WAL 并 VACUUM；tombstone 只保存删除时间、scope type 和不可逆 hash，不保存被删除内容。

## 4. Evidence 与验证结果语义

`FieldProvenance` 只说明信息如何获得，不表示概率意义上的可信度等级。A1–A3 永久区分用户声明与系统观测。

例如：

- 用户通过 `continuity-record-result --outcome pass` 录入结果，只形成 `USER_DECLARED` verification evidence；
- Git HEAD、tracked diff 和 untracked file fingerprint 属于 `OBSERVED` workcopy evidence；
- 只有验证记录绑定的完整 code-state fingerprint 与当前 workcopy 完全一致时，applicability 才为 `CURRENT`；
- 代码状态变化后，历史结果保留，但 applicability 变为 `NEEDS_REVALIDATION`；Compact Brief 对历史 PASS 显示“上次通过，当前状态尚未复验”。

A1–A3 不把 `--scope` 文本当命令执行，也不把用户声明伪装成系统实际运行测试得到的结果。Evidence View 用于查看具体 provenance 与 source reference。

## 5. 冻结验收场景

端到端验收使用同一个真实临时 Git repository 的两个 worktree A/B：

1. A/B 使用同一个 `project_key`，但绑定不同 `workcopy_id` 和 `task_id`；
2. A/B 分别拥有不同 goal、blocker 和 verification result；
3. Resume A 不得出现 B 的 goal/blocker/result，反之亦然；
4. A 的代码变化后，A 历史 PASS 必须变为 `NEEDS_REVALIDATION`；
5. A goal 纠错后应立即出现在新 Brief 中，B 保持不变；
6. A 的敏感 evidence 被显式删除后，当前状态、历史 snapshot/brief 与 `continuity.db`/WAL/SHM 都不得残留唯一 sentinel，同时 B 状态保持完整。

## 6. 当前明确非目标

A1–A3 仍然是手动触发的本地 Task Continuity 产品切片，当前不包含：

- A4 WorkEpisode 与自动 project re-entry / inactivity resume trigger；
- A5 LLM-assisted task interpretation、自动 goal/blocker 推断或 suggestion exposure；
- 主动工作助手的帮助机会预测与打扰策略；
- 自动修改项目、运行命令、测试、构建或 UI 操作；
- Phase C capability-scoped executor。

因此通过 A1–A3 验收只表示“项目/工作副本/任务隔离的手动恢复、纠错、证据与删除闭环可用”，不能解释为自动 PersonalAgent 已完成。

## 7. Dogfood 观察项

真实日常使用时记录以下问题，不用固定 session 数包装成统计证明：

- 恢复到了错误的 project/workcopy/task；
- Brief 漏掉真正影响继续工作的事项；
- 已失效验证或约束被误写成当前有效；
- 用户需要多少次纠错才能继续工作；
- Evidence 展开后是否足以解释关键陈述；
- 删除请求是否按预期覆盖所有 Task Continuity 派生物。

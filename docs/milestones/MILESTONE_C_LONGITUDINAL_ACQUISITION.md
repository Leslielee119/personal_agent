# Milestone C-L — Longitudinal Acquisition Qualification

日期：2026-10-08
状态：IMPLEMENTATION QUALIFIED — REAL LONGITUDINAL DATA STILL NOT READY

## 1. 目标

C-L 不增加预测模型，而是补齐 Milestone C 之前缺失的纵向数据采集闭环：

```text
same events.db
  -> repeated capture restarts
  -> runtime.restart session boundaries
  -> derive-b1
  -> longitudinal readiness
  -> target distributions + quantitative deficits
```

核心问题不是“已经采了多少事件”，而是：

- 有多少独立 session；
- 有多少 `HUMAN_PHYSICAL` action；
- Application / Operation / Joint 是否具有足够类别；
- dominant ratio / normalized entropy 是否仍然塌缩；
- C0、Screening、Confirmatory 分别还差什么。

## 2. 新增工程能力

新增 `ppa longitudinal-cycle --run-id <id>`。该命令在同一长期数据库上：

1. 从当前 canonical high-water 重新构建 B1；
2. 保持同一 `run_id` 可幂等替换最新 B1 snapshot；
3. 只统计 `HUMAN_PHYSICAL` formal targets；
4. 输出 Application / Operation / Joint label counts；
5. 输出 actions/classes/session/fold/test-session deficit；
6. 保留原始 `longitudinal-status` readiness 语义，同时提供更严格的 collection progress。

## 3. Collection Progress 与原 readiness 的区别

原 `longitudinal-status` 中 `SCREENING_READY` 只表示 session/fold 数量足以运行 screening，不代表 C0 数据质量已经合格。

C-L 的 `progress[target].screening_status` 更严格：

```text
raw screening readiness
AND C0 == PASS
  -> SCREENING_READY
```

因此即使达到 5 个 session，只要仍然是单一 `key_input`、dominant ratio 过高或 entropy 不足，也会继续报告 `SCREENING_NOT_READY`。

这是工程层的 fail-closed 设计，不修改 Milestone C 已冻结的 C0 阈值和 benchmark 语义。

## 4. 学术灵感与原创边界

主要启发来自：

Peter Pfeiffer, Luka Abb, Peter Fettke, Jana-Rebecca Rehse.

**Learning from the Data to Predict the Process: Generalization Capabilities of Next Activity Prediction Algorithms.**

*Business & Information Systems Engineering*, 67(3):357–383, 2025.

DOI: `10.1007/s12599-025-00936-4`。

该论文指出 next-activity prediction 的常见评估会被重复 prefix、数据划分与 generalization validity 问题误导，强调应显式验证 unseen behavior/generalization 条件后再解释模型结果。

期刊分区：2025 中科院分区第三方汇总显示 **大类管理学 3 区，小类计算机：信息系统 3 区**；正式投稿材料中应再以当年最新版中科院官方分区表复核。

我们的新增点不是提出 generalization 问题，而是把 validity-first 原则落到长期运行的 Personal AI 数据采集工程中：每个真实 session 后持续计算“离可证伪实验还差多少数据/类别/独立 session”。

## 5. 当前真实数据缺口

冻结数据：

`E:\Experiment\personal-predictive-ai-runtime\captures\2026-10-07-b2-qualification\events.db`

B1 run：`real-b1-20261007`。

C-L 只读复核结果：

```text
sessions = 1
HUMAN_PHYSICAL actions = 182
applications = {chrome.exe: 182}
operations = {key_input: 182}

Operation / Joint target_count_shortfall = 18
Operation / Joint minority_actions_needed_for_dominant_ratio >= 21
Application classes_to_c0 = 1
Operation / Joint classes_to_c0 = 2
sessions_to_screening = 4
sessions_to_confirmatory = 7
independent_test_sessions_to_confirmatory = 5
```

因此下一批真实数据的首要目标不是单纯增加按键数，而是获得跨 session 的 `click / scroll / key_input` 与跨应用行为，使类别和熵先恢复到可检验范围。

主 `events.db` 在只读复核前后 SHA-256 均为：

`0961ec1eadf1c2402f27fafda3f3cba9e6f835ad778d72eb5b5df42b161b78df`

## 6. 工程验证

```text
focused longitudinal regression: 11 passed
prediction suite: 50 passed
full pytest: 273 passed, 1 skipped, 2 warnings
ruff check .: PASS
git diff --check: PASS
```

唯一 skip 与 C-L 无关：当前 Windows host 无法创建 symlink 测试夹具。本轮 final verification 中 native OpenAdapt physical-input smoke 实际通过；若验证期间没有真实 physical input，该测试会按设计 skip。

冻结结论：`C-L IMPLEMENTATION QUALIFIED / REAL DATA NOT READY`。


## 7. 一键真实 Session 采集入口

新增：

```text
ppa --data-dir <persistent-data-dir> longitudinal-session \
  --duration <seconds> \
  --run-id longitudinal-current
```

默认启用 OpenAdapt，因此真实键盘、鼠标、UIA 与已有系统 collector 使用同一 CaptureService。每次命令启动都会写入新的 `runtime.restart`，自然形成新的 B1 session；采集结束后自动执行 `longitudinal-cycle`，一次输出 capture health 与 longitudinal progress。

长期采集必须反复使用**同一个** `data-dir`。不要为每个 session 新建数据库，否则无法得到 session-forward 纵向证据。

正式采集协议不允许为了满足 `classes>=3` 或 `dominant<=0.90` 人为刷 click/scroll。progress deficit 只用于判断自然数据是否足够，不允许反向控制用户行为来“过 Gate”；否则会产生 acquisition-policy bias（采集策略偏差），使后续泛化结论失去意义。

推荐真实运行目录与命令示例：

```powershell
.\.venv\Scripts\python.exe -m personal_predictive_ai.cli `
  --data-dir "E:\Experiment\personal-predictive-ai-runtime\longitudinal\primary" `
  longitudinal-session `
  --duration 1800 `
  --run-id longitudinal-current
```

这里 `1800` 只是单次 30 分钟采集示例，不是冻结实验阈值；session 应对应自然工作段，而不是人为切成等长样本。


### Session runner 验证

独立 smoke 数据库连续执行两次 `longitudinal-session --duration 0 --no-openadapt`，session_count 从 1 正确累计到 2；smoke 数据仅位于 runtime 目录，不进入正式证据库。

空 HUMAN_PHYSICAL 样本时同时修正了 validity target-space 语义：Application 使用 `classes<2`，Operation / Joint 使用 `classes<3`，避免空样本被默认解释为 Operation。

```text
focused session/readiness/benchmark: 18 passed
full pytest: 274 passed, 2 skipped, 2 warnings
ruff check .: PASS
git diff --check: PASS
```

两个 skip 均为环境型：验证期间没有真实 physical input；当前 Windows host 无法创建 symlink 测试夹具。
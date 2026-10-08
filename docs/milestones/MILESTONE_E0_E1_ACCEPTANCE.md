# Milestone E0/E1 — Trusted Knowledge & Skill Registry Acceptance

日期：2026-10-08
状态：IMPLEMENTATION QUALIFIED — E0/E1 trusted registry substrate passed full-project verification

## 1. 本阶段范围

E0/E1 只建立可信 Knowledge / Skill 基础设施，不执行 Skill，不做行为自动挖掘。

已实现：

- `KnowledgeRecord` 与 deterministic Knowledge IDs；
- `SkillDraft` / immutable `SkillRecord` version；
- structured `VerificationSpec`；
- `SkillMutationProposal` 审批暂存；
- `SkillPackageManifest`、quarantine、scan、approval；
- canonical SQLite Knowledge/Skill Registry；
- L0/L1/L2 progressive disclosure；
- deterministic Markdown projection 与 edit-to-proposal；
- 显式人工 CLI，用于 import / stage / approve / inspect / export。

核心不变量：

```text
Skill text != trusted Skill
Skill import != Skill approval
Skill mutation proposal != canonical mutation
VERIFIED != AUTHORIZED_TO_EXECUTE
```

## 2. Gate E0 — Schema / Registry Integrity

已验证：

- strict/frozen Pydantic schema 与 deterministic SHA-256 IDs；
- historical Skill `(skill_id, version)` append-only，不允许原地覆盖；
- stale-base approval 与 duplicate create 均 fail closed；
- Skill approval 在单 SQLite transaction 内完成 version append、proposal update、audit append；
- risk downgrade 必须有显式 override；
- package source/revision/content hash/scanner findings 持久化；
- package 在 scan、approve 与 L2 reference retrieval 前重新校验 exact file set + content hash，导入后新增、删除或改写文件均 fail closed；
- QUARANTINED / SCANNED / REJECTED package 不能绑定为可信 Skill source；
- `knowledge-import` 只接受 HUMAN_DECLARED / HUMAN_APPROVED_IMPORT source，AI_PROPOSED 不能伪装成人工知识进入 canonical registry；
- E Store 写入不会修改 canonical Event / B1 / B2 数据。

E1 的 canonical Skill 创建固定为：

```text
SkillMutationProposal
  -> explicit approval
  -> immutable DRAFT SkillRecord
```

E1 不允许直接提升到 `VERIFIED` 或 `ACTIVE`。

## 3. Gate E1 — Human-authored Round Trip / Retrieval

已验证：

- canonical Skill -> Markdown -> parse-back 在无编辑时 semantic equivalent；
- semantic edit 只创建 `SkillMutationProposal`，不会 silent apply；
- malformed YAML、unknown frontmatter、identity/version/status/provenance 篡改均 fail closed；
- projection 中的 evidence summary 属于 machine-controlled 字段，人工改写不会被解释成新的 canonical evidence；
- L0 仅返回 Skill index metadata；
- L1 返回 procedure / verification / capability core，不包含 evidence corpus；
- L2 只读取 APPROVED package manifest 白名单中的单个 UTF-8 reference；
- L2 读取脚本文本不会执行脚本；
- absolute/rooted/traversal reference path 被拒绝；
- Markdown export 写 `SkillProjectionManifest`，不修改 canonical Skill。

Focused E0/E1 verification：

```text
41 passed, 1 skipped
```

唯一 skip：当前 Windows host 不允许创建 symlink 测试夹具。实现同时检查 symlink 与 Windows junction；绝对路径、rooted path 与 `..` traversal 的非跳过测试通过。

## 4. 显式人工 CLI

E1 提供：

```text
knowledge-import
skill-stage
skill-approve
skill-list
skill-show
skill-export
skill-package-import
skill-package-scan
skill-package-approve
```

所有持久化命令都是用户显式触发的 `WRITE_LOCAL`。`skill-list` / `skill-show` 为 read-only。不存在 Skill execution 命令。

## 5. 明确未实现 / 未开放

以下仍然关闭：

- E2 Behavior-to-Skill 跨 session 自动发现；
- AI 自动 Skill 生成、自我修改、自我提升；
- E3 verification 后的 `VERIFIED` / `ACTIVE` / `NEEDS_REVALIDATION` lifecycle promotion；
- Planner / Executor hierarchy benchmark；
- MXC 或其他 execution backend；
- desktop autonomous execution；
- cloud model routing；
- `BackendCapabilityProfile`；
- `TrustedCompletionReport`；
- 任意 WRITE/ACT/EXTERNAL_EFFECT Skill 的自动执行。

因此当前系统只能够：

```text
Human-authored/imported evidence
  -> governed proposal
  -> explicit approval
  -> DRAFT canonical Skill
  -> read-only retrieval / projection
```

不能推导：

```text
DRAFT Skill -> permission to execute
```

## 6. Final Project Verification

Fresh verification on the implementation worktree:

```text
pytest -q -rs
267 passed, 1 skipped, 2 warnings

ruff check .
All checks passed!

git diff --check
PASS
```

唯一 skip 有明确环境原因：`test_quarantine_rejects_symlink_or_junction_escape` 在当前 Windows host 无法创建 symlink 测试夹具。实现仍显式检查 symlink 与 junction，且 rooted/absolute/traversal 非跳过测试通过。`test_windows_native_input_and_uia_smoke` 在本轮 fresh verification 中实际通过；若验证期间没有真实 physical input，该测试会按设计 skip，因为 OpenAdapt 会过滤 injected input。

冻结结论：

```text
E0/E1 = IMPLEMENTATION QUALIFIED
E2 = CLOSED — WAITING FOR LONGITUDINAL EVIDENCE
E3 = CLOSED
F  = CLOSED
```

该状态只证明 trusted Knowledge/Skill registry substrate 的工程实现通过资格验证，不构成 Skill 自动执行可靠性、行为挖掘有效性或自主 Agent 安全性的结论。

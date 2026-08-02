# FLAi-OS 接手状态与下一步行动（2026-07-25）

> 状态：**ACTIVE / OWNER-ACCEPTED SSOT**。
> `human_owner = JerryKogami` 已在当前 Codex 任务中具名接受
> `flai-os-takeover-docs-kimi-001@2`，并绑定接受前候选补丁摘要
> `sha256:504208932db4dea2a2dd92f1f4e13e352690467633431927189e03f544a3c4b9`。
> 自该接受记录起，本文档取代 `2026-07-16-flai-os-handover-roadmap.md`
> 成为当前接手状态 SSOT；07-16 路线图保留为历史材料，§6 的过时判定同时生效。
> 该接受是项目 owner 的具名、摘要绑定裁决，不是密码学签名或组织生产签发；
> 它不授权 Stage D、PoC、依赖引入、生产上线、推送或合并。
>
> 唯一开发基线裁决：
> - `decision_ref = flai-os-unique-development-baseline-001@1`；
> - `human_owner = JerryKogami` 已具名接受选项 C；
> - 接受前 `document_sha256 =
>   971fcc8884afbede27241721e287685e559f9d558897f3fcbd02f8f26d5b73fd`；
> - 接受前 `patch_digest =
>   c2c6a1f436cb890fcd3b74c817b775ce127af2b7e34a2c4de1cf8aaa63eb7193`；
> - `origin/main@ec43768ff1ad2cb6bc3e571486bfda2d04c35780` 是裁决时点的唯一开发基线，
>   后续工作以刷新后的 main tip 连续演进；
> - 其他候选线一律为 `DONOR_ONLY / EVIDENCE_ONLY`，不得整线升格。
> 该裁决不授权 Stage D、PoC、依赖引入、运行时代码移植、分支删除或生产上线。
>
> SHA 基线（三类，不可混写）：
> - `verified_code_sha` = `859a1b42de1847c4a6f1dc9719d98abf0d3609f0`
>   （最后一个含源代码变化的祖先提交；Codex 在 `8b5d9d9` checkout 上复核时，
>   `859a1b4..8b5d9d9` 之间只有文档变化，因此用它锚定被测代码状态；它不是当前分支 tip）；
> - `candidate_document_base_sha` = `8b5d9d99e2b16bd7988b088b97091c16784929a7`
>   （被接受候选文档所在分支 `codex/kimi-takeover-docs-v2` 的基线）；
> - `activation_document_commit` = `COMMIT_CONTAINING_THIS_ACCEPTANCE_RECORD`
>   （避免在提交内容中写入不可成立的自引用 SHA；以包含本记录的 Git 提交为激活提交）。

## 1. 2026-07-25 设计会话确认事项（confirmed_in_design_session / NOT_FORMALLY_SIGNED）

以下四项是设计会话的历史记录。此次 owner 接受使本文成为状态 SSOT，并对第 4 项作出
「受限选项 2」方向裁决；但不会追溯升级会话动作的证据强度，也不会把 R0/R1、分支删除、
推送结果或其他 `NOT_FORMALLY_SIGNED` / `UNKNOWN` 项改写为已正式签发或已独立验证。

1. **回撤确认**：工作树对 safe-auto DAG 后 4 提交（`12723fb..567de2d`）的回撤是刻意的，
   设计会话予以确认；4 提交完整保留在 `codex/integrate-safe-auto-dag`（已推 origin），未丢失。
2. **开发基线（历史候选意见，已被后续 owner 裁决取代）**：设计会话曾倾向以 V0.2
   设计周期线（`codex/desktop-workspace-shell-research-v1` 链）为后续主线；owner
   后续已接受选项 C，以刷新后的 `origin/main` 为唯一开发基线，V0.2 等候选线仅作为
   `DONOR_ONLY / EVIDENCE_ONLY`（见 §3.0）。Stage D 实施切片仍未授权。
3. **分支保护**：设计会话同意将本地关键分支推送 origin（执行情况见 §3，事实分级见 §3.4）。
4. **方向冲突**：对 07-25 DeepResearch「组合式开源底座」建议开正式方向评审，
   评审材料为 `docs/research/2026-07-25-composable-stack-vs-kernel-direction-review.md`
   ；owner 已接受其中「受限选项 2」为项目方向裁决，但这不是实现、PoC、依赖引入或
   上线授权。

## 2. 2026-07-25 会话已执行动作（按证据强度分级）

| 动作 | 结果 | 证据分级 |
|---|---|---|
| 三路只读摸底（工作树/文档/分支拓扑） | 定性：刻意回撤+新工作叠加，非事故 | SESSION_DECLARED_NOT_INDEPENDENTLY_VERIFIED |
| Python 全套 + frontend node 契约回归 | 见 §2.1，以 Codex 独立复核为准；不等于仓库全量门 | 分级见 §2.1 |
| 推送 21 + 1 个本地分支到 origin | 会话记录为全部 `[new branch]` 成功 | SESSION_DECLARED_NOT_INDEPENDENTLY_VERIFIED（远端 ref 当前存在另见 §3.4） |
| 工作树分主题整理提交 | 5 个提交，新分支 `codex/v02-mainline-consolidation`（base `c9b03e4`） | `0002a33`/`c824fb6`/`b69eac4`/`43847bc`/`859a1b4`（git 对象可复核） |
| 推送新分支 | `codex/v02-mainline-consolidation` 已入 origin | VERIFIED_BY_CODEX_2026-07-25（远端 ref 存在） |

五个主题提交：

1. `0002a33` fix(gateway)：vision 能力未接入 fail-closed 501。
2. `c824fb6` feat(frontend)：信任体系组件 + 07-21 UI 打磨批（MockSeal/BackLink/ErrorState、
   AgentGovernanceDialog 拆分、composables、styles/tokens）。
3. `b69eac4` test(verify)：sh/ps1 验证门 parity + e2e 证据防污染（FLAI_E2E_ARTIFACT_ROOT）
   + trust_ui 验收套件。
4. `43847bc` docs(v02)：V0.2 设计周期文档批（ADR-0028~0045、docs/product、docs/research、
   docs/design、CONTEXT.md、07-16 路线图册档）。
5. `859a1b4` chore：补录 AGENTS.md 与 uv.lock。

**有意未提交（继续受保护）**：70 个 docs/reviews 截图改动（用户资产，07-16 起即受保护，
本轮返工不触碰、不改变其保护状态）；`.workbuddy/`（agent 记忆）；`db.sqlite`、
`.DS_Store`（运行时/系统杂物）；`docs/reviews/batch-d-shots/mobile-real/`
（新增截图资产，留待归属裁决）。

### 2.1 部分回归证据（可复算事实，禁止混写成仓库全量门）

- **Codex 独立复核（2026-07-25，checkout HEAD = `8b5d9d9`；
  被测可执行源码由 `verified_code_sha = 859a1b4` 锚定）**：
  - `.venv/bin/pytest -q` → `1019 passed, 1 warning, 141.70s`；
  - `cd frontend && node --test` → `24 passed, 0 failed`。
- **范围边界**：本轮未运行 `bash scripts/verify_all.sh`、frontend build 或视觉 E2E；
  因此不能称为 AGENTS.md 所定义的仓库“全量门”。
- **环境约束（如实记录）**：当前 `.venv` 缺少 pytest-xdist，`pytest -n auto`
  报参数不可识别，无法在该环境复算并行耗时。
- **Kimi 会话自报值**（「1019/1019 PASS，19.2s，-n auto」）只能记为
  `SESSION_DECLARED_ENVIRONMENT_NOT_REPRODUCED`：其运行环境未能复现，
  不得与 Codex 实测结果混写或并列引用。

### 2.2 唯一开发基线的当前全量门证据

- Codex 在 tree 与 `origin/main@ec43768` 完全一致的干净隔离工作树执行
  `env UV_OFFLINE=1 bash scripts/verify_all.sh`；
- frontend build PASS；Python `1063 passed, 16 warnings`；Node `29 passed, 0 failed`；
  仓库声明的 19 组浏览器 E2E 全部 PASS；最终 exit code `0`；
- 首次运行因隔离工作树缺 `frontend/node_modules`，在 build 阶段以
  `vite: command not found` / exit `127` 停止；核对 package 与 lock 摘要一致后仅复用
  既有本地依赖重跑，未新增或升级依赖；
- E2E 在隔离工作树重写的 78 个 `docs/reviews/` 截图已恢复至 HEAD；最终工作树 clean，
  主工作树用户资产未受影响；
- 该证据只证明当前 main 是可复算开发起点，不替任何 `DONOR_ONLY / EVIDENCE_ONLY`
  分支补测试、实现或准入票据。

## 3. 分支处置地图（2026-07-25 会话记录版，事实分级见 §3.4）

### 3.0 唯一开发基线与供体线现状

owner 已接受 `flai-os-unique-development-baseline-001@1` 的选项 C：

- `origin/main@ec43768ff...`：是 **GitHub 代码真相与唯一开发基线**；每个新工作项
  必须从当时刷新后的 main tip 创建，不能长期钉死在本次裁决 SHA；
- `codex/desktop-workspace-shell-research-v1@007d9d6...`（相对裁决时 main 独有
  36 个提交）：**V0.2 / Stage C 供体与证据线**
  （含设计包与 Stage C 原型；飞书 F0 评审包仍是
  `/private/tmp/flai-os-v02-foundation` 的未提交工作，不属于该 tip）；
- `codex/v02-mainline-consolidation@8b5d9d9...`：**代码硬化供体与证据线**
  （c9b03e4 认证 safe-auto 单 Agent 基线 + 打磨/验证门/V0.2 文档批 + 文档修正）。

`codex/flai-v02-foundation`、`codex/agent-fact-projection-ui`、
`codex/integrate-safe-auto-dag` 及其他保留线同样为 `DONOR_ONLY / EVIDENCE_ONLY`。
所有供体资产必须另冻工作项、限定 allowlist 并独立验证；本裁决不授权任何移植。

### 3.1 主线与基线

| 分支 | tip | 定位 |
|---|---|---|
| origin/main = main | `ec43768`（07-25） | GitHub 代码真相；唯一开发基线 |
| codex/desktop-workspace-shell-research-v1 | `007d9d6` | `DONOR_ONLY / EVIDENCE_ONLY`：V0.2、Stage C、Workspace Shell |
| codex/v02-mainline-consolidation | `8b5d9d9` | `DONOR_ONLY / EVIDENCE_ONLY`：代码硬化与验证门；历史被测代码由祖先 `859a1b4` 锚定 |
| codex/agent-fact-projection-ui | `52c3856` | `DONOR_ONLY / EVIDENCE_ONLY`：trusted-interaction→JerryAgent→agent facts |

### 3.2 保留（有独立工作/取证价值）

| 分支 | 说明 |
|---|---|
| codex/integrate-safe-auto-dag | `567de2d`：被确认回撤的 DAG/manifest/恢复门/世代绑定 4 提交的唯一完整载体 |
| codex/safe-auto-dag-v1 | `dc5ee20`：DAG 原始 hash（与 12723fb 同名不同 hash），取证 |
| feat/gate2-wave1 | T1/T2/T3，HELD，owner 具名终裁前不动 |
| feat/requirement-intake-agent | 需求接件候选，ADR 编号冲突待裁决 |
| backup-pre-r3-recommit / backup-pre-r3v-recommit | Gate2-T3 中间态唯一备份，仅取证 |
| codex/phase0-trusted-baseline | `83e76fd`，07-16 老基线修复，孤立 |
| codex/kimi-workspace-shell-v6a-prep / v6c-prep | 各 1 个独立 prep 提交（状态见 §3.5） |
| codex/flai-v02-foundation | `9023776`，V0.2 设计包线（/tmp worktree 有未提交 F0/Stage C 工作，见 §5） |

### 3.3 归档执行记录（2026-07-25 会话记录）

- 会话记录称：已删除本地分支 17 个：feat/inline-summon、feat/usage-telemetry、
  feat/cfd-flai-os-integration、feat/collab-runtime、feat/control-step-response-shot、
  feat/fea-solve-eval-shot、feat/migration-9-created-by-username、
  feat/today-workbench-batch-b、feat/ui-simplify-conversation-home、
  feat/workbench-ux-batch-a、feat/uiux-craft-fine-grain、feat/uiux-desktop-language、
  feat/uiux-novice-minimal-b4、novice-first-run-backup-pre-rebase、
  codex/selfharness-v03-owner-plan、codex/kimi-workspace-shell-v2、
  codex/platform-integration-v1；失效 worktree 登记已 prune（8 个），2 个干净 /tmp
  worktree 已移除。
- 会话记录称：暂缓归档 5 个：feat/novice-first-run、feat/uiux-gap-batch8（仍被
  projects 下持久 worktree 占用）；codex/kimi-workspace-shell-v3/v4/v5（对应 /tmp
  worktree 有未提交 prototype 改动，不毁未提交工作，待用户确认后处理）。
- feat/eval-async-queue（`567de2d`）：历史使命完成（评测队列早已入 main；safe-auto 6
  提交由 integrate-safe-auto-dag 承载），归档候选，待确认。

### 3.4 推送与删除事实分级

- **远端 ref 当前存在**：本轮独立复核直接确认以下相关 ref：
  `origin/codex/v02-mainline-consolidation@8b5d9d9`、
  `origin/codex/desktop-workspace-shell-research-v1@007d9d6`、
  `origin/codex/integrate-safe-auto-dag@567de2d`、
  `origin/codex/kimi-workspace-shell-v6a-prep@43f02f1`、
  `origin/codex/kimi-workspace-shell-v6c-prep@b60c66f`，以及下表明确列出的
  4 个同名归档 ref；这些存在性标为 `VERIFIED_BY_CODEX_2026-07-25`，
  不外推到没有列明的已删除分支。
- 以下陈述**未绑定独立证据**，只能标 `SESSION_DECLARED_NOT_INDEPENDENTLY_VERIFIED`：
  「21 + 1 个分支推送全部成功」「owner 批准删除」「17 个删除分支内容均无丢失
  （被 origin/main 或已推送分支完全包含）」。
- **删除审计账本（所需字段，未知项一律 UNKNOWN，不得推测）**：

| deleted_branch | deleted_tip | preserving_remote_ref | is_ancestor_proof | authorization_receipt |
|---|---|---|---|---|
| feat/inline-summon | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| feat/usage-telemetry | UNKNOWN | origin/feat/usage-telemetry@c3767fc | UNKNOWN（deleted_tip 缺失） | UNKNOWN |
| feat/cfd-flai-os-integration | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| feat/collab-runtime | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| feat/control-step-response-shot | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| feat/fea-solve-eval-shot | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| feat/migration-9-created-by-username | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| feat/today-workbench-batch-b | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| feat/ui-simplify-conversation-home | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| feat/workbench-ux-batch-a | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| feat/uiux-craft-fine-grain | UNKNOWN | origin/feat/uiux-craft-fine-grain@f1ea1b6 | UNKNOWN（deleted_tip 缺失） | UNKNOWN |
| feat/uiux-desktop-language | UNKNOWN | origin/feat/uiux-desktop-language@7a351a9 | UNKNOWN（deleted_tip 缺失） | UNKNOWN |
| feat/uiux-novice-minimal-b4 | UNKNOWN | origin/feat/uiux-novice-minimal-b4@e39ba1b | UNKNOWN（deleted_tip 缺失） | UNKNOWN |
| novice-first-run-backup-pre-rebase | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| codex/selfharness-v03-owner-plan | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| codex/kimi-workspace-shell-v2 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| codex/platform-integration-v1 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

  补齐方式：逐分支回填 tip、保留 ref、`git merge-base --is-ancestor` 输出与授权 receipt
  后，方可升级为 VERIFIED。补齐前，「删除无丢失」不成立为已证事实。
  本表中的 `authorization_receipt=UNKNOWN` 同时表示“owner 批准删除”的会话说法仍是
  `SESSION_DECLARED_NOT_INDEPENDENTLY_VERIFIED`。

### 3.5 Workspace Shell 工作项状态（独立记录，不得包装为 Stage C 已收口）

- **@6A**：本地观察为 **NO_GO_FOR_6B**；尚无可由本 SSOT 引用的持久权威 receipt。
- **@6B**：**BLOCKED / NOT_ISSUED**（未签发，未授权启动）。
- **@6C**：仅为 prep/诊断候选（`codex/kimi-workspace-shell-v6c-prep` 1 个 prep 提交），
  **不构成执行授权**。
- 以上状态独立于 Stage C 原型收口进度，不得合并表述为「Stage C 已收口」。

## 4. 当前阶段与候选后续切片（非执行授权）

V0.2 周期进度（如实标注签发状态，不使用无说明的通过记号）：

- R0（架构方向接受）：`confirmed_in_design_session / NOT_FORMALLY_SIGNED`；
- R1（MVP 规格 `15_Phase_0A_MVP_Spec.md` 冻结）：`confirmed_in_design_session / NOT_FORMALLY_SIGNED`；
- **当前悬在**：Stage C 原型收口 + 飞书中枢 F0 七域具名评审（**0/7 UNASSIGNED**）；
- Stage D（分片实施）：**未授权**；首个切片对应 06_Roadmap R3 的 K1 控制内核 /
  K2 Sandbox & Execution Broker，owner 显式放行前不得启动。

候选后续动作（**本文不授权执行**；每项必须另冻工作项，涉及删除、编号裁决或阶段推进时
还需 owner 明确授权）：

1. **Stage C 原型收口候选**：`frontend/src/prototypes/stage-c/`（在 v02 worktree，未提交）
   + `frontend/e2e/stage_c_prototype_acceptance.py`；只可在另冻工作项后运行验收、收敛 NOTES。
2. **方向裁决后的评估候选**（§1.4）：owner 已接受「受限选项 2」；本文仍不启动任何
   PoC 或依赖评估，每项均须另冻工作项并取得明确授权。
3. **ADR 编号漂移收敛候选**：本仓 0033-0045 vs V0.2 线 0047-0062
   （ADR-0047 裁决重编 + 新增 0048/0062）。候选处置原则：V0.2 线编号为准；
   合并文档批时取 V0.2 线 ADR 集合，本仓 43847bc 中的 0033-0045 视作预编号草案，
   不反向回流；该原则已随 owner 接受本文成为后续规划引用规则，但实际重编号或合并仍须
   另冻工作项并取得授权。
4. **陈旧分支归档候选**：补齐 §3.4 审计账本并取得逐项 owner 授权后，才可另行删除；
   当前不再执行任何分支删除。
5. **F0 评审材料准备候选**：七责任域评审包在 v02 临时 worktree 中仍有未提交工作；
   后续整理必须另冻工作项。具名指派与签发始终是人类动作，agent 只能备料。

被外部事实阻塞（维持 fail-closed）：Stage D 实施授权、F0 具名评审、Gate1 目标机证据、
M4 真实性能盘（已降格为内部样板/R6+ 候选）、离线发布包。

## 5. 风险与诚实边界

- **/tmp worktree 风险**：V0.2 主力 worktree 在 `/private/tmp/flai-os-v02-foundation`，
  有未提交的 F0 schema/Stage C/CONTEXT 改动（可能是另一活跃会话的在制工作，未动它）。
  提交级内容已推送保护；未提交部分建议在确认无活跃会话后迁移到
  `~/projects/aircraft-comac/` 下的持久路径。“其余约 20 个 /tmp worktree 多数可清理”
  仅是会话声明，未逐项复核，不据此执行清理。
- **编号双轨**：本仓文档批（43847bc）与 V0.2 线 ADR 编号冲突已识别，未收敛前引用
  V0.2 决策一律以 `codex/flai-v02-foundation` 的 0047-0062 编号为准。
- **生产结论不变**：**production = NO-GO**。V0.1 封板不外推内网；V0.2 全部设计为
  confirmed_in_design_session / NOT_FORMALLY_SIGNED；PRODUCTION-READINESS-PROGRAM 的
  P0 门继续有效。
- **本轮测试边界**：以 §2.1 为准——Codex 独立复核（1019 passed / 24 passed）是
  checkout `8b5d9d9` 上的部分回归，代码状态由 `verified_code_sha=859a1b4` 锚定；
  Kimi 会话自报值为 SESSION_DECLARED_ENVIRONMENT_NOT_REPRODUCED；
  `scripts/verify_all.sh`、build、视觉 E2E 与 5 个主题提交中间态均未在本轮逐一复跑。
- **tracker / Git 凭据**：gh CLI 此前 401；本轮只验证 `git ls-remote` 读取成功，
  没有独立复验 push 权限，issue 只读对账仍待做。

## 6. 07-16 路线图过时判定（已随 owner 接受本文而生效）

- Phase 0（恢复 main 可信基线）：问题被 V0.2「干净基线重建 + F0 评审包」话语接管；原表述过时。
- Phase 1（首个 L1 晋升）：被「能力发布包 + FLAi Bench 四轨 + QualificationDecision」取代
  （CONTEXT 明确 `_Avoid_: Agent L0-L3`）。
- Phase 2（Gate1 目标机证据）：结论仍成立（导入 NO-GO），优先级重排到 R5/R6 之后；
  macOS-first 裁决明确 Windows/目标机验证延后。
- Phase 3（M4 真实性能盘）：被 ADR-0037（V0.2 新编号线 0053）降格为内部技术验收样板。

---

*ACTIVE / OWNER-ACCEPTED SSOT · 2026-07-25 · `JerryKogami` 接受
`flai-os-takeover-docs-kimi-001@2`，绑定接受前候选补丁摘要
`sha256:504208932db4dea2a2dd92f1f4e13e352690467633431927189e03f544a3c4b9`。
`flai-os-unique-development-baseline-001@1` 的选项 C 同样已具名接受并生效。
本记录不授权 Stage D、PoC、依赖引入、运行时代码移植、分支删除或生产上线。*

# FLAi-OS 接手状态与下一步行动（2026-07-25）

> 状态：ACTIVE，本文档取代 `2026-07-16-flai-os-handover-roadmap.md` 成为当前接手 SSOT。
> 07-16 文档保留作历史，其「分支处置地图」与「首个执行切片」已整体过时（见 §6 过时判定）。
>
> 事实基线：codex/v02-mainline-consolidation@859a1b4，核对日期 2026-07-25。
> 本轮实测：全量 pytest 1019/1019 PASS（19.2s，-n auto）+ frontend node 契约 24/24 PASS。

## 1. 今日四项 owner 决策（2026-07-25，设计会话确认）

1. **回撤确认**：工作树对 safe-auto DAG 后 4 提交（`12723fb..567de2d`）的回撤是刻意的，
   予以确认；4 提交完整保留在 `codex/integrate-safe-auto-dag`（已推 origin），未丢失。
2. **开发基线**：V0.2 设计周期线（`codex/desktop-workspace-shell-research-v1` 链）为事实主线，
   围绕 Stage C 原型收口推进；Stage D 实施切片仍需 owner 显式放行。
3. **分支保护**：授权推送全部本地关键分支到 origin（已执行，21 + 1 个分支，见 §3）。
4. **方向冲突**：对 07-25 DeepResearch「组合式开源底座」建议开正式方向评审，
   评审材料起草中（`docs/research/2026-07-25-composable-stack-vs-kernel-direction-review.md`，
   DRAFT，owner 裁决输入，不构成方向变更）。

## 2. 今日已执行动作（可审计）

| 动作 | 结果 | 证据 |
|---|---|---|
| 三路只读摸底（工作树/文档/分支拓扑） | 定性：刻意回撤+新工作叠加，非事故 | 本会话记录 |
| 混合态首次全量测试 | pytest 1019/1019、node 24/24 全绿 | 本会话后台任务日志 |
| 推送 21 个本地分支到 origin | 全部 `[new branch]` 成功 | git push 输出 |
| 工作树分主题整理提交 | 5 个提交，新分支 `codex/v02-mainline-consolidation`（base `c9b03e4`） | `0002a33`/`c824fb6`/`b69eac4`/`43847bc`/`859a1b4` |
| 推送新分支 | `codex/v02-mainline-consolidation` 已入 origin | git push 输出 |

五个主题提交：

1. `0002a33` fix(gateway)：vision 能力未接入 fail-closed 501。
2. `c824fb6` feat(frontend)：信任体系组件 + 07-21 UI 打磨批（MockSeal/BackLink/ErrorState、
   AgentGovernanceDialog 拆分、composables、styles/tokens）。
3. `b69eac4` test(verify)：sh/ps1 验证门 parity + e2e 证据防污染（FLAI_E2E_ARTIFACT_ROOT）
   + trust_ui 验收套件。
4. `43847bc` docs(v02)：V0.2 设计周期文档批（ADR-0028~0045、docs/product、docs/research、
   docs/design、CONTEXT.md、07-16 路线图册档）。
5. `859a1b4` chore：补录 AGENTS.md 与 uv.lock。

**有意未提交**：70 个 docs/reviews 截图改动（用户资产，07-16 起即受保护）；
`.workbuddy/`（agent 记忆）；`db.sqlite`、`.DS_Store`（运行时/系统杂物）；
`docs/reviews/batch-d-shots/mobile-real/`（新增截图资产，留待归属裁决）。

## 3. 分支处置地图（2026-07-25 实测版）

全部下列分支已推送 origin，本地丢失风险已消除。

### 主线与基线

| 分支 | tip | 定位 |
|---|---|---|
| origin/main = main | `7523edf`（07-18） | 旧主线，停更 7 天；不再是开发基线 |
| codex/desktop-workspace-shell-research-v1 | `007d9d6`（+36） | **V0.2 事实主线**（含 flai-v02-foundation 链：设计包/Stage C 原型/F0 评审包） |
| codex/v02-mainline-consolidation | `859a1b4` | 本仓工作树整理线：c9b03e4（认证 safe-auto 单 Agent）+ 打磨/验证门/V0.2 文档 |
| codex/agent-fact-projection-ui | `52c3856`（+28） | trusted-interaction→JerryAgent→agent facts 链，未合并 |

### 保留（有独立工作/取证价值）

| 分支 | 说明 |
|---|---|
| codex/integrate-safe-auto-dag | `567de2d`：被确认回撤的 DAG/manifest/恢复门/世代绑定 4 提交的唯一完整载体 |
| codex/safe-auto-dag-v1 | `dc5ee20`：DAG 原始 hash（与 12723fb 同名不同 hash），取证 |
| feat/gate2-wave1 | T1/T2/T3，HELD，owner 具名终裁前不动 |
| feat/requirement-intake-agent | 需求接件候选，ADR 编号冲突待裁决 |
| backup-pre-r3-recommit / backup-pre-r3v-recommit | Gate2-T3 中间态唯一备份，仅取证 |
| codex/phase0-trusted-baseline | `83e76fd`，07-16 老基线修复，孤立 |
| codex/kimi-workspace-shell-v6a-prep / v6c-prep | 各 1 个独立 prep 提交 |
| codex/flai-v02-foundation | `9023776`，V0.2 设计包线（/tmp worktree 有未提交 F0/Stage C 工作，见 §5） |

### 可归档候选（已完全并入 origin/main 或为冗余指针，删除前逐一确认）

- 已并入 main（ahead 0）：feat/inline-summon、feat/novice-first-run、feat/uiux-craft-fine-grain、
  feat/uiux-desktop-language、feat/uiux-novice-minimal-b4、feat/uiux-gap-batch8(=feat/usage-telemetry)、
  feat/cfd-flai-os-integration、feat/collab-runtime、feat/control-step-response-shot、
  feat/fea-solve-eval-shot、feat/migration-9-created-by-username、feat/today-workbench-batch-b、
  feat/ui-simplify-conversation-home、feat/workbench-ux-batch-a、novice-first-run-backup-pre-rebase
- 冗余指针：codex/selfharness-v03-owner-plan(=main)、codex/kimi-workspace-shell-v2/v3/v4/v5(均=v1)、
  codex/platform-integration-v1(=flai-airgap-boundary)、codex/integrate-safe-auto-dag 之外的链内中间节点
- feat/eval-async-queue（`567de2d`）：历史使命完成（评测队列早已入 main；safe-auto 6 提交由
  integrate-safe-auto-dag 承载），归档候选

## 4. 当前阶段与下一执行切片

V0.2 周期进度：R0（架构方向接受）✓ → R1（MVP 规格 `15_Phase_0A_MVP_Spec.md` 冻结）✓ →
**当前悬在：Stage C 原型收口 + 飞书中枢 F0 七域具名评审（0/7 UNASSIGNED）** →
Stage D（分片实施，未授权，首个切片对应 06_Roadmap R3 的 K1 控制内核/K2 Sandbox & Execution Broker）。

可立即执行（无外部阻塞）：

1. **Stage C 原型收口支持**：`frontend/src/prototypes/stage-c/`（在 v02 worktree，未提交）
   + `frontend/e2e/stage_c_prototype_acceptance.py`，跑通验收 e2e、收敛 NOTES。
2. **方向评审材料**（今日决策 4）：起草中，完成后交 owner 裁决。
3. **ADR 编号漂移收敛**：本仓 0033-0045 vs V0.2 线 0047-0062（ADR-0047 裁决重编 + 新增
   0048/0062）。处置原则：V0.2 线编号为准；合并文档批时取 V0.2 线 ADR 集合，
   本仓 43847bc 中的 0033-0045 视作预编号草案，不反向回流。
4. **陈旧分支归档**：§3 清单逐一经用户确认后删除本地分支（origin 侧保留）。
5. **F0 评审材料准备**：七责任域评审包机制已建好（`docs/reviews/feishu-organizational-hub-f0-v1/`，
   在 v02 worktree），具名指派是人类动作，agent 只能备料。

被外部事实阻塞（维持 fail-closed）：Stage D 实施授权、F0 具名评审、Gate1 目标机证据、
M4 真实性能盘（已降格为内部样板/R6+ 候选）、离线发布包。

## 5. 风险与诚实边界

- **/tmp worktree 风险**：V0.2 主力 worktree 在 `/private/tmp/flai-os-v02-foundation`，
  有未提交的 F0 schema/Stage C/CONTEXT 改动（可能是另一活跃会话的在制工作，未动它）。
  提交级内容已推送保护；未提交部分建议在确认无活跃会话后迁移到
  `~/projects/aircraft-comac/` 下的持久路径。其余约 20 个 /tmp worktree 多数已 prunable。
- **编号双轨**：本仓文档批（43847bc）与 V0.2 线 ADR 编号冲突已识别，未收敛前引用
  V0.2 决策一律以 `codex/flai-v02-foundation` 的 0047-0062 编号为准。
- **生产结论不变**：V0.1 封板不外推内网；V0.2 全部设计为 confirmed_in_design_session，
  正式生产仍是 NO-GO；PRODUCTION-READINESS-PROGRAM 的 P0 门继续有效。
- **本轮测试边界**：1019/1019 是 codex/v02-mainline-consolidation@859a1b4 工作树实测；
  5 个主题提交的中间态未逐一跑全量门（首尾一致，内容并集=已验证状态）。
- **tracker**：gh CLI 此前 401；git push 已验证凭据可用，issue 只读对账待做。

## 6. 07-16 路线图过时判定（摘要）

- Phase 0（恢复 main 可信基线）：问题被 V0.2「干净基线重建 + F0 评审包」话语接管；原表述过时。
- Phase 1（首个 L1 晋升）：被「能力发布包 + FLAi Bench 四轨 + QualificationDecision」取代
  （CONTEXT 明确 `_Avoid_: Agent L0-L3`）。
- Phase 2（Gate1 目标机证据）：结论仍成立（导入 NO-GO），优先级重排到 R5/R6 之后；
  macOS-first 裁决明确 Windows/目标机验证延后。
- Phase 3（M4 真实性能盘）：被 ADR-0037（新编号线 0053）降格为内部技术验收样板。

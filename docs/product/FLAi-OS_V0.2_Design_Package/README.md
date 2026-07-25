# FLAi-OS V0.2 设计包

> 状态：`ACCEPTED-NOT-IMPLEMENTED`（设计读模型，2026-07-23）
>
> 面向：产品、架构、UX、安全、领域评审与后续 Codex 实施
>
> 当前正式内网生产部署结论：**NO-GO**

## 1. 这份设计包是什么

本目录把已接受的产品决策、统一领域语言和当前系统事实整理成一套可连续阅读的 V0.2 设计输入，服务于：

1. 架构评审；
2. MVP 范围冻结；
3. 可点击或可运行原型；
4. 经具名人员批准后的分片开发。

它是 [CONTEXT.md](../../../CONTEXT.md)、[ADR-0033 至 ADR-0045](#6-约束本包的已接受-adr) 和现行标准的**派生读模型**，不是第二套单一事实源（SSOT），也不能仅凭修改本目录改变架构决策、当前运行事实、安全策略、发布状态或生产准入结论。

本包描述的目标形态大量属于 `ACCEPTED-NOT-IMPLEMENTED`。文档完整不等于软件已实现，界面原型可运行不等于真实 Runtime、模型、工具、知识、安全或部署已验证。

### 1.1 决策接受与正式签发不是一回事

ADR-0033 至 ADR-0045 中的“已接受”，只记录委托人在本次设计会话中对产品方向的明确确认；它不是经组织身份系统认证的电子签名，也不自动等同于立项、预算、密级、试点、发布或上线批准。当前工作副本尚未形成 clean、可复算的 release baseline，正式治理流程还必须为每项需签发决策补齐具名 `actor_id`、职责/作用域、时间、精确 ADR/制品 digest、决定和不可抵赖证据。缺少这些字段时，实施者只能把它当作已确认的设计输入，不能当作正式准入凭据。

决策来源与实现状态是两条正交轴。后续 Decision Record 至少记录 `decision_status=confirmed_in_design_session|formally_signed|decision_required|superseded`、`accepted_by_actor_id`、`accepted_at`、`decision_scope`、`decision_digest`、`source_evidence_ref`；只有 `formally_signed` 且字段齐全才具组织治理效力。本文五种标签只表达实现/证据状态，其中 `ACCEPTED-NOT-IMPLEMENTED` 的“accepted”在当前包仅代表 `confirmed_in_design_session`，不能代替正式签发。

## 2. 权威来源与顺序

不同类型的争议由不同 SSOT 裁决，不把所有事实压成一个模糊的总排序：

| 争议类型 | 权威来源（由高到低） | 说明 |
|---|---|---|
| 组织授权与正式准入 | 适用的组织制度与具名真人签发；生产准入证据 | AI、原型和本设计包均无签发权 |
| 已接受的产品/架构决策 | 最新且适用的 accepted ADR；明确的后续 ADR 可显式替代早期 ADR | 未写明替代关系时，不得自行宣布旧决策失效 |
| 领域术语 | [CONTEXT.md](../../../CONTEXT.md) | 本包只能引用或解释，不能另造同名异义词 |
| 当前实现事实 | 代码、Schema、测试、数据库迁移事实与真实运行证据 | 若实现与决策不一致，应记录漂移，不能用现状悄悄改写决策 |
| 当前标准与治理合同 | [docs/00–09](#7-现行基线与诚实边界)、生产就绪纲领、Issue 工作流 | 说明 V0.1 已有机制和当前约束；未来设计不得伪装成现状 |
| V0.2 设计解释 | 本目录 | 最低层派生视图；便于阅读与交接，不拥有独立裁决权 |

遇到冲突时必须按以下顺序处理：

1. 停止把冲突内容继续当成已确定事实，并列出冲突原文、文件与影响范围；
2. 按上表找到对应 SSOT，检查是否存在明确的替代 ADR、版本或具名签发；
3. 若目标决策与当前实现不同，将二者分别标成 `ACCEPTED-NOT-IMPLEMENTED` 与当前实现状态，不选择其中一方制造假一致；
4. 安全、权限、密级、审计、工程依据或签发语义仍有歧义时，按 fail-closed 处理并提交具名负责人裁决；
5. 裁决先进入正确的 SSOT，再同步本包。只改本包不能闭合冲突。

## 3. 统一状态标签

本包只使用以下五种实现状态。每个关键能力、界面和流程都应能落到其中之一：

| 标签 | 严格含义 | 禁止外推 |
|---|---|---|
| `IMPLEMENTED-VERIFIED` | 代码或配置已存在，并有当前、可复跑、与声明范围匹配的机械证据 | 不外推到未测试环境、真实数据、生产规模或更宽权限 |
| `IMPLEMENTED-PARTIAL` | 部分路径真实存在，但仍有明确缺口、旁路、范围限制或未闭合门 | 不得简称“已完成”或显示全绿 |
| `ACCEPTED-NOT-IMPLEMENTED` | 已由适用 ADR 或已记录的设计决策接受，但尚无可验证实现 | 设计会话中的接受不等于组织签发、开发完成、试点获批或生产可用 |
| `DECLARED-NOT-VERIFIED` | 文档、脚本、适配或配置已有声明，但缺少本轮或目标环境的真实验证 | 不得把声明、环境变量注入、Mock 或健康标志当作上游成功 |
| `OUT-OF-SCOPE` | 当前阶段明确冻结或排除；保留未来重新决策的可能 | 不得静默夹带进 MVP，也不代表永久否决 |

补充纪律：

- `unknown`、`failed`、`invalid`、`skipped` 和证据不可解析均不是绿；
- Mock、synthetic、canonical fixture 必须显式标注，不能获得 `REAL` 语义；
- 没有标签或没有证据引用时，默认视为**未证实**，而不是默认已实现；
- “V0.1 已封板”只证明封板声明中的结构层和生长层，不证明 V0.2、真实内网、Sandbox、业务价值或生产就绪。

## 4. 当前诚实结论

截至本包冻结时：

- FLAi-OS V0.1 有已封板的轻内核和若干真实基础模块，但封板明确不外推内网环境与生产韧性；
- ADR-0033 至 ADR-0045 是已接受的 V0.2 方向，绝大多数仍未实现；
- Phase 0A 尚未因本包而获准开始，任何现有 Agent 也未因本包自动取得试点或真实敏感数据权限；
- OpenClaw/OpenHands 未被批准成为控制面，也未因本包获准导入依赖或进入生产；
- 真正的可强杀 Sandbox、细粒度授权、受控网络出口、不可变执行输入与 Delivery Bundle、完整并发治理、不可抵赖审计及关键安全缺口仍须逐项验证；
- 正式内网生产部署保持 **NO-GO**，直到适用准入门全部以真实证据通过并由具名真人签发。任何截图、演示、Mock、模型自评或单一测试绿灯都不能改变该结论。

本包可以支持架构评审、MVP 冻结和原型探索；不能作为上线批准书、采购验收书、工程结论或安全豁免。

本次设计周期曾在当前 dirty worktree 上运行窄范围回归：`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q backend/tests/test_knowledge_service.py backend/tests/test_knowledge_bm25.py backend/tests/test_stats_api.py backend/tests/test_feedback.py backend/tests/test_agent_role_authorization.py backend/tests/test_eval_snapshot.py`，结果为 `92 passed, 1 warning`（2026-07-23，macOS，本地 `.venv`）。它只支持这些测试覆盖的现状观察；由于没有 clean release SHA、完整资产 digest 和全量验收，本包仍把相关基线统一写为 `IMPLEMENTED-PARTIAL`，不得用该结果提升试点或生产状态。

## 5. 目录

| 文件 | 作用 |
|---|---|
| [00_Product_Vision.md](00_Product_Vision.md) | 产品定位、目标用户、价值与非目标 |
| [01_PRD.md](01_PRD.md) | Phase 0A 产品需求、三条黄金工作流与验收边界 |
| [02_System_Architecture.md](02_System_Architecture.md) | 控制内核、模块、接口、执行后端 Adapter 与关键 seam |
| [03_Information_Architecture.md](03_Information_Architecture.md) | 工作台、治理与运行中心、共建地图的角色化信息架构 |
| [04_Data_Model.md](04_Data_Model.md) | 权威事实、不可变快照、事件、证据和派生视图的数据语义 |
| [05_AI_Operating_Model.md](05_AI_Operating_Model.md) | 人与 Agent 的职责、日常运行和例外处理机制 |
| [06_Roadmap.md](06_Roadmap.md) | Phase 0A/0B 路线、门禁、依赖与明确冻结项 |
| [07_Design_Principles.md](07_Design_Principles.md) | 体验、诚实、安全、证据与渐进披露原则 |
| [08_Core_Workbench_UX.md](08_Core_Workbench_UX.md) | 单一 Composer、不中断执行、证据和末端交付 UX |
| [09_Agent_Workflow_Lifecycle.md](09_Agent_Workflow_Lifecycle.md) | Agent/Workflow 从候选到退出的生命周期与人签门 |
| [10_AI_Transformation_Playbook.md](10_AI_Transformation_Playbook.md) | 需求发现、POC、评测、试点、推广与复盘方法 |
| [11_Authoritative_Knowledge_Foundation.md](11_Authoritative_Knowledge_Foundation.md) | 逻辑统一、物理联邦的权威知识底座 |
| [12_FLAi_Bench.md](12_FLAi_Bench.md) | 冻结能力发布包、四轨评测和不可抵消门 |
| [13_CoBuilding_Map_and_Demand_Loop.md](13_CoBuilding_Map_and_Demand_Loop.md) | 共建地图、证据指标、需求共创与决策权 |
| [14_Security_Sandbox_Governance.md](14_Security_Sandbox_Governance.md) | 身份、权限、Sandbox、并发、出口、审计和交付门 |
| [CODEX_HANDOFF_PROMPT.md](CODEX_HANDOFF_PROMPT.md) | Codex 分阶段接手提示词与机械停止条件 |

## 6. 约束本包的已接受 ADR

本包必须同时遵守以下决策，不能只选择其中方便实现的一部分：

- [ADR-0033：FLAi-OS 控制内核与可替换执行后端](../../adr/ADR-0033-flai-control-kernel-and-replaceable-execution-backends.md)
- [ADR-0034：不中断自治会话与末端交付授权](../../adr/ADR-0034-uninterrupted-session-and-final-delivery-authorization.md)
- [ADR-0035：受控验收与业务试点分两级推进](../../adr/ADR-0035-two-stage-controlled-and-business-pilots.md)
- [ADR-0036：工程工作台优先与角色化治理界面](../../adr/ADR-0036-workbench-first-and-role-specific-governance-surfaces.md)
- [ADR-0037：Phase 0A 三条黄金工作流](../../adr/ADR-0037-phase-0a-three-golden-workflows.md)
- [ADR-0038：智能办公助手首个薄切片](../../adr/ADR-0038-office-assistant-first-tracer-bullet.md)
- [ADR-0039：CFD 工程助手首个薄切片](../../adr/ADR-0039-cfd-assistant-first-tracer-bullet.md)
- [ADR-0040：会议行动助手首个薄切片](../../adr/ADR-0040-meeting-assistant-first-tracer-bullet.md)
- [ADR-0041：权威知识底座](../../adr/ADR-0041-authoritative-knowledge-foundation.md)
- [ADR-0042：FLAi Bench 评测底座](../../adr/ADR-0042-flai-bench-evaluation-foundation.md)
- [ADR-0043：共建地图与证据化运营指标](../../adr/ADR-0043-co-building-map-and-evidence-derived-metrics.md)
- [ADR-0044：需求共创闭环](../../adr/ADR-0044-demand-co-creation-loop.md)
- [ADR-0045：需求决策权与路线图签发](../../adr/ADR-0045-demand-decision-rights-and-roadmap-signoff.md)

## 7. 现行基线与诚实边界

设计和开发前至少复核以下当前基线，而不是只读 V0.2 目标稿：

- [FLAi-OS Constitution](../../00_FLAi-OS_Constitution.md)
- [Overall Architecture](../../01_Overall_Architecture.md)
- [Agent Package Standard](../../02_Agent_Package_Standard.md)
- [Tool Package Standard](../../03_Tool_Package_Standard.md)
- [Model Gateway Standard](../../04_Model_Gateway_Standard.md)
- [Task & Event Standard](../../05_Task_Event_Standard.md)
- [Knowledge & Memory Standard](../../06_Knowledge_Memory_Standard.md)
- [Eval Standard](../../07_Eval_Standard.md)
- [Department AI Playbook](../../08_Department_AI_Playbook.md)
- [Workflow Live Monitor Standard](../../09_Workflow_Live_Monitor_Standard.md)
- [生产就绪纲领](../../PRODUCTION-READINESS-PROGRAM.md)
- [Issue tracker contract](../../agents/issue-tracker.md)

其中 `docs/00–09` 描述当前合同和已实现基线；V0.2 目标与之不同之处必须通过新规格、测试和必要 ADR 显式演进，不能在设计包里宣称“已经替换”。

## 8. 推荐阅读顺序

第一次接手按以下顺序阅读：

1. 本 README，先理解证据等级与 NO-GO 边界；
2. [CONTEXT.md](../../../CONTEXT.md) 与 ADR-0033 至 ADR-0045；
3. `00_Product_Vision`、`07_Design_Principles`、`01_PRD`；
4. `03_Information_Architecture` 与 `08_Core_Workbench_UX`；
5. `02_System_Architecture`、`04_Data_Model`、`14_Security_Sandbox_Governance`；
6. `11_Authoritative_Knowledge_Foundation` 与 `12_FLAi_Bench`；
7. `05_AI_Operating_Model`、`09_Agent_Workflow_Lifecycle`、`10_AI_Transformation_Playbook`；
8. `13_CoBuilding_Map_and_Demand_Loop` 与 `06_Roadmap`；
9. 最后使用 [CODEX_HANDOFF_PROMPT.md](CODEX_HANDOFF_PROMPT.md)，从只读架构评审开始，不直接进入编码。

## 9. 本包的变更纪律

- 新的产品或架构裁决先写 ADR；新的术语先更新 CONTEXT；当前合同变化先更新对应标准与验证；本包随后同步。
- 所有未来态必须带统一状态标签，所有“完成、通过、真实、可用、已部署”必须有可复跑证据和精确范围。
- 不在本目录创建第二套任务状态、权限角色、KPI、知识发布、评测晋级或路线图签发事实。
- 不因参考 WorkBuddy、Claude、Codex、OpenClaw 或 OpenHands 而复制其信任边界；参考的是体验和实现经验，权威语义仍由 FLAi-OS 决定。
- 任何开发从干净、可追溯的基线开始；当前工作树有未知或重叠修改时，先停下盘点并保护用户资产。

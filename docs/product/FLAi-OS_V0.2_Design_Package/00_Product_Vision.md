# FLAi-OS V0.2 产品愿景

> 文档性质：V0.2 产品读模型，不是实现完成声明，也不是新的决策事实源。术语以 [`CONTEXT.md`](../../../CONTEXT.md) 为准，已接受决策以 [`docs/adr/`](../../adr/) 为准；本文件负责把这些事实组织成可供产品、设计与开发共同阅读的产品方向。

## 1. 状态标签

本文只使用以下标签描述能力状态：

| 标签 | 含义 |
|---|---|
| `IMPLEMENTED-VERIFIED` | 当前精确范围、版本与环境有可复跑机械证据，绑定命令、结果引用和日期；不等于生产就绪 |
| `IMPLEMENTED-PARTIAL` | 已有可复用实现，但尚未满足本文件描述的完整目标。 |
| `ACCEPTED-NOT-IMPLEMENTED` | owner 已通过 ADR 接受方向，但尚无实现与验收证据。 |
| `DECLARED-NOT-VERIFIED` | 文档、配置或历史材料中有声明，但本设计包未获得足以复核的当前证据；不得据此点绿或准入。 |
| `OUT-OF-SCOPE` | 当前阶段明确不做；不表示永久否决。 |

标签不能由演示截图、LLM 自评、手工进度或“看起来可用”替代。能力状态变化必须回到代码、契约、评测、签发或运行证据。

## 2. 北极星

FLAi-OS 是面向航空工程组织的**工程智能体协作与治理平台**。它让工程师用自然语言提交完整工作目标，让 Agent 在受控会话内连续规划、执行、验证和恢复；同时把模型、知识、工具、权限、沙箱、并发、证据和最终交付纳入同一控制内核。

它的北极星不是“拥有最多 Agent”，而是：

> 在不降低工程责任和组织安全的前提下，把高频知识工作与工程辅助工作变成可复用、可验证、可追溯的能力发布。

人始终是唯一签发者。AI 可以形成建议、草稿、差异、依据链和待交付动作，但不能把自己的输出晋升为组织事实、工程结论或正式交付。

## 3. 产品定位

### 3.1 双环境、单域单入口

`ACCEPTED-NOT-IMPLEMENTED` FLAi-OS 明确拆成两个不互信环境：

- 外网研发团队以 `FeishuDevelopmentHub + GitHub` 管理 FLAi-OS 产品开发；
- 正式内网用户以完全自托管的 **`FLAiWorkspace`** 作为唯一日常产品入口。

两个环境没有实时同步、共享身份、共享 Secret 或运行控制链，只通过受控、签名、内容寻址的
离线发布准入交换成果。外网飞书不是内网产品依赖，GitHub SHA 在内网也只表示来源 provenance。

内网普通用户默认看到按本人职责与项目范围生成的工作收件箱、一句话 Composer、需要处理的
少量事项和来自权威事实的实质变化，而不是全量项目后台、复杂表格或 Agent 拓扑图。

**工程智能体工作台**仍是首发 Agent 执行主产品，并成为 `FLAiWorkspace` 中的专业执行
Surface。一次任务的主要体验是：

```text
提交目标与材料
    → Agent 连续工作
    → 用户按需查看真实进展、证据与产物
    → 末端查看 Delivery Bundle
    → 具名真人对精确版本签发或退回
```

任务中间不要求用户补填 Agent 已经能够推导的字段，也不以逐命令、逐工具、逐文件确认打断工作。需要不可逆外部效果时，Agent 只能先冻结待交付动作；真人末端授权后，控制内核再提交并记录真实 receipt。

### 3.2 一个内网 FLAi Workspace，多个角色化空间

内网日常 Surface 共用一个 `FLAiWorkspace` Shell，但读取联邦 owner 的权威事实，不把所有
状态复制成聊天、Wiki 或项目表真相：

| 空间／Surface | 主要用户 | 产品职责 | 状态 |
|---|---|---|---|
| FLAi 工作收件箱 | 全体内网认证参与者 | 发起工作、查看本人待办、项目变化与回告 | `ACCEPTED-NOT-IMPLEMENTED` |
| 工程智能体工作台 | 工程师、业务人员 | 连续执行、观察真实进展、核对证据与产物、末端签发 | `IMPLEMENTED-PARTIAL`：已有隔离原型和任务骨架；尚未接入内网 Workspace 与目标 Runtime |
| 项目讨论与知识 | 项目成员 | 通过自托管通讯/Wiki Adapter 协作；正式事实仍由 FLAi/Knowledge owner 拥有 | `CANDIDATE-SELECTION` |
| 治理与运行中心 | 平台管理员、安全人员、Agent Owner、评测维护者 | 在 Workspace 内组织 Agent/Workflow 生命周期、策略、授权、Sandbox、队列预算、异常恢复、审计与 Bench 治理仪式 | `IMPLEMENTED-PARTIAL`：底层注册、评测、晋级和事件骨架存在；Workspace typed intent 与 owner receipt 未闭合 |
| FLAi 共建地图 | 全体参与者 | 在 Workspace 内查看版本、能力、需求来源、里程碑和证据化指标 | `ACCEPTED-NOT-IMPLEMENTED` |
| 智能化指挥中心 | 领导、AI 负责人 | 在 Workspace 内只读聚合真实业务结果、机会组合和风险例外 | `OUT-OF-SCOPE`：Phase 0A 不开放 |

这些空间不是五套应用或五套状态机。“FLAi-OS 智能化指挥中心”可以作为后期领导空间名称，但不能替代产品总名，也不能成为普通用户默认页。

### 3.3 内网 Workspace、控制内核与执行 Ports

`IMPLEMENTED-PARTIAL` 当前仓库已有 FastAPI、SQLite Job Runner、Agent Registry、Task Center、
Agent Runtime、Model Gateway、Tool Registry、File Service、Event Log、评测快照与人工晋级
等基础 Module。它们构成继续演进的本地骨架，但不等于 ADR-0049～0063 的目标状态已经完成。

`ACCEPTED-NOT-IMPLEMENTED` FLAi-OS 将保持唯一控制内核。ExecutionBroker 组合三类不可互换的窄 Port：OpenClaw/OpenHands 只可实现 `AgentRuntimePort`，macOS 隔离实现 `SandboxProviderPort`，Python/Office/CAE/HPC 实现 `ToolExecutionPort`。动态动作逐次取得 Kernel 的短时 ExecutionTicket；任何 Adapter 都不得持有第二套身份、任务、审计、授权或终态真相。移除任一 Adapter，不应改变 FLAi-OS 的权威任务语义。

这个 Seam 的价值在于把复杂执行实现藏在窄 Interface 后面：调用方只学习一次任务、取消、结果、receipt 与失败语义，获得跨后端复用的 Leverage；后端差异与修复集中在 Adapter 内，保持 Locality。

`ACCEPTED-NOT-IMPLEMENTED` 内网 `InternalWorkspaceHub` 以
`open → prepare → commit` 三个入口隐藏自托管通讯、项目、知识创作和 FLAi owner 的差异。
第三方 Surface 只创建权限过滤投影和 typed intent；权威 owner 在提交时重新鉴权并返回
`OwnerCommitReceiptV1`。

外网 `FeishuDevelopmentHub` 只组织研发需求、Codex/Kimi 工作包和 GitHub 交付，不进入内网
身份、知识、Runtime 或发布链。跨域唯一入站是
`OfflineReleaseBundleV1 → AirGapReleaseAdmission`；内网重新验签、扫描、Bench 和具名准入。

`secrets-stackdocker` 当前只作为外网研发普通 App/Connector Secret value 的声明 owner。内网
使用独立 Secret owner/实例、root、namespace、策略和备份；Secret value 与 SecretRef 命名
空间都不跨域。人的安全硬件身份与 Safety receipt-signing key 继续属于独立 Safety Identity /
PKI / HSM 故障域。

## 4. 为谁解决什么问题

| 用户 | 现在的主要痛点 | FLAi-OS 提供的结果 |
|---|---|---|
| 普通工程师与业务人员 | 不知道 Agent 在做什么；流程被反复表单与确认打断；输出缺少来源和差异 | 一个连续任务、一条真实状态线、可核对产物与依据、末端一次签发 |
| 专业工程师 | 模型会猜边界条件、混淆要求与建议；工程目录和结果难以系统检查 | 只读优先、逐项证据、未知显式、权威依据/工程假设/模型建议分离 |
| 业务与领域负责人 | 真实痛点未进入平台规划；代码完成不等于问题解决 | 低门槛需求提交、来源不丢失、路线图回链、试点与验收邀请 |
| 平台与安全人员 | Agent 权限、并发、外联、沙箱、审计和恢复不可见或分散 | 统一控制内核、策略 Seam、可强杀执行、不可变证据与 fail-closed 门 |
| 领导与 AI 负责人 | 看见演示却看不见真实采纳、风险、成本和价值 | 证据派生的共建地图；后期形成只读指挥视图，不手填绿色指标 |

## 5. 首批三条黄金工作流

黄金工作流是用户从 Composer 提交目标到收到 Delivery Bundle 的完整结果，不等同于一个“大而全 Agent”。每条工作流都由深 Module 隐藏文件解析、模型调用、规则检查、知识检索、产物生成和证据装配等实现复杂度，对用户暴露尽可能小的 Interface。

### 5.1 智能办公助手

- `ACCEPTED-NOT-IMPLEMENTED` 首个 tracer bullet：**DOCX 技术报告润色与规范化**。
- 在隔离工作区生成副本，不覆盖原文件。
- 交付修改后的 DOCX、修改摘要、重要差异、待确认问题和执行证据。
- 数字、单位、公式、表格和图片不得被模型静默改变；可能改变技术原意时保留原文并进入末端例外清单。
- 后续可扩展到文档总结、Excel 分析、PPT 材料、规章快查、邮件草拟和基础纪要，但不能把这些范围冒充首版已具备。

### 5.2 CFD 工程助手

- `ACCEPTED-NOT-IMPLEMENTED` 首个 tracer bullet：**已有 OpenFOAM 算例的只读体检**。
- 检查算例完整性、求解器与物理模型、材料与边界条件、网格质量证据、时间步、Courant 数、收敛控制、离散格式、线性求解设置和后处理配置。
- 每条 finding 必须绑定真实文件与字段位置，并区分当前设置、状态、风险、建议和未知前提。
- 首版不修改算例、不启动求解、不自动选择“最佳”模型，不把辅助报告称为工程校核。
- 受控副本修改、已有结果后处理和报告是后续独立增量；全自主 CFD 不在本阶段。

### 5.3 会议行动助手

- `ACCEPTED-NOT-IMPLEMENTED` 首个 tracer bullet：**会后纪要与行动项整理**。
- 输入是会议笔记、既有文字转写、议程和文本附件；首版不做实时录音或自动参会。
- 输出区分议题、决策、共识、未决问题和责任事项，并保留来源锚点。
- 每项责任事项要求预期产出、唯一负责人、截止时间、验收标准和验收人；来源未给出的字段必须保持未知。
- 会议负责人只在末端确认精确版本；AI 不签发正式会议记录，也不代替验收人关闭事项。

`IMPLEMENTED-PARTIAL` 性能盘批处理继续作为内部技术验收样板；它不占 Phase 0A 的三条对外工作流槽，可在真实工具和真实数据验证后进入 Phase 0B 专业能力候选。

## 6. 两个基础信任 Module

### 6.1 权威知识底座

`IMPLEMENTED-PARTIAL` 当前 Knowledge Module 已有 file_dir × document 的 BM25 检索、Knowledge Scope、来源指纹、引用和 default-deny 骨架；目前主要服务 job 模式，尚无权威发布、时间有效性、替代关系和任务时版本快照的完整语义。

`ACCEPTED-NOT-IMPLEMENTED` V0.2 目标是“逻辑统一、物理可联邦”的权威知识底座。Obsidian 可以是策展 Adapter，向量数据库可以是检索 Adapter，但二者都不是权威本身。只有由具名授权人员在 FLAi-OS 中签发、处于当前有效状态的不可变版本，才能支持组织要求或工程依据；受信源系统只能提供可验证的上游签发 `source_system_attestation`，不能成为本平台 signer。缺失、冲突或适用范围不明时，系统必须回答“无法确认”。

### 6.2 FLAi Bench

`IMPLEMENTED-PARTIAL` 当前已有 Eval Runner、eval cases、快照、人工评审和晋级证据骨架，但冻结范围、人工 rubric 和安全治理矩阵尚不足以代表完整“能力发布包”。

`ACCEPTED-NOT-IMPLEMENTED` FLAi Bench 评测冻结的能力发布包，而不是只评模型或 Agent 名称。它采用确定性回归、工程质量、安全治理、运行效率四轨证据矩阵；安全、诚实性、依据链和关键回归是不可抵消门。failed、invalid、skipped、unknown 或无法解析的必测证据都不能被平均分、速度或低 Token 抵消。LLM-as-Judge 只能辅助，不能签发。

## 7. 共建不是装饰

`ACCEPTED-NOT-IMPLEMENTED` FLAi 共建地图采用“战略目标 → 平台地基 → 黄金工作流 → 能力发布包 → 证据”的结构。路线图由具名人员版本化签发，节点状态由发布、评测、人工签发和运行证据派生，不能手工点绿。

需求共创从一段自然语言开始。AI 可以提取痛点、聚类和建议候选验收，但只能形成草稿；需求策展人负责整理，领域与安全评审人提供适用门，路线图负责人对版本作最终具名签发。平台需求池、共建地图承诺和 GitHub Issue 分属发现、承诺与交付三层事实，稳定引用连接但不互相冒充。

公开指标只呈现团队聚合与可复算事实：当前能力、采纳、质量安全、资源消耗和组织价值。Token 是资源成本，不是个人贡献度；节省时间只有在存在版本化基线、有效样本和人工抽样时才报告范围与覆盖率。

## 8. 体验原则

1. **工作台先于后台**：先让用户完成工作，再按角色暴露治理深度。
2. **单一 Composer**：用户表达目标和提供材料，平台负责把复杂度放进深 Module，不把内部 schema 直接变成用户表单。
3. **不中断但不失控**：会话内只运行已获授权的可逆动作；不可逆影响收敛到 Delivery Bundle。
4. **真实状态优先**：正在执行、等待资源、证据不足、受阻、失败、未验证必须可区分；completed 本身不代表工程有效。
5. **渐进披露**：先展示结论、产物和例外，需要时再展开任务图、工具 receipt、模型调用和证据链。
6. **未知是一等结果**：无依据不猜；冲突不由 LLM 决胜；缺口集中呈现而非频繁打断。
7. **一套事实，多种视图**：工作台、治理中心、共建地图和后期指挥中心只投影同一事实源。
8. **中国工程组织语境**：中文优先、正式文件友好、来源与责任清晰、默认不要求终端操作；视觉质量以克制、清晰、可信为目标。

## 9. 试点策略

| 阶段 | 人群与数据 | 目的 | 放大条件 | 当前状态 |
|---|---|---|---|---|
| Phase 0A | 5–8 名具名技术验收人员；macOS 首发；仅 approved synthetic 数据，正常样本用 `fixture_class=canonical` | 验证不中断会话、Sandbox、强杀、并发恢复、证据、真实状态与末端签发；完成三条最小工作流验收 | 本阶段自身门全部有可复核证据 | `ACCEPTED-NOT-IMPLEMENTED` |
| Phase 0B | 20–30 名具名业务用户；按 Agent、项目、数据域和能力清单限范围开放 | 验证真实业务采纳与价值 | Phase 0A 通过，且至少一条工作流接入真实工具与真实数据并完成安全、准确性验收 | `ACCEPTED-NOT-IMPLEMENTED` |

Phase 0A 通过只证明限定机制成立，不证明生产就绪；Phase 0B 有人使用也不等于全面上线。

## 10. 非目标

以下内容当前明确为 `OUT-OF-SCOPE`：

- 用 OpenClaw、OpenHands 或其他框架替换 FLAi-OS 控制内核；
- Phase 0A 建设领导驾驶舱、人员绩效看板或个人 Token 排行榜；
- 首版实现全自主 CFD、自动求解、自动选择工程模型或自动签发结论；
- 实时会议录音、自动参会、自动发信、自动催办和完整行动项闭环；
- 同时铺开 DOCX、PDF 编辑、Excel、PPT、邮件和 Office GUI 自动化；
- Windows 适配与跨平台发布；Phase 0A 先把 macOS 体验和机制做实；
- 因“大模型更强”而省略知识权威、评测、沙箱、权限、审计和证据；
- 用一个综合分抵消安全失败，或用 AI 判分替代真人签发；
- 建设与现有任务、事件、评测、统计、知识并行的第二套事实平台。

## 11. Phase 0A 入场与退出的机械检查

本愿景不能靠口号验收。Phase 0A 的入场准备和退出验收是两组不同证据：入场前先证明候选版本可安全受控运行；Phase 0A 内再由 5–8 名验收人员验证整合旅程、恢复与体验。入场通过不等于 Phase 0A 通过。

### 11.1 Entry readiness：邀请验收人员前

1. clean、可复算的 macOS 候选版本、5–8 人名单、仅含 approved `source_kind=synthetic` 的数据清单（正常样本 `fixture_class=canonical`）、停止条件和回退目标已冻结；
2. 三条黄金工作流各有版本化能力发布包、明确限制、invalid-first fixture 和 Phase 0A eligible QualificationDecision；
3. 统一对象授权、附件 quarantine、Sandbox/强杀、队列/租约、受控出口、审计 outbox、Delivery CAS 的实验室 conformance 与 P0 负例通过；
4. 精确 release digest 有匹配的 Phase 0A DeploymentBinding，未列入人员、数据、能力或动作不能创建任务；
5. 事故联系人、停止/撤权/恢复演练脚本与证据落点已准备。任一入场门 unknown/failed/invalid/skipped 均不得邀请试点用户。

### 11.2 Exit acceptance：Phase 0A 内取得

1. 每条黄金工作流至少一名非开发者验收人员按固定脚本完成全旅程，失败、受阻、取消和撤权路径同样有记录；
2. 相同任务的模型、工具、策略、知识、输入和产物版本可由证据重建；
3. 会话中不存在通用逐动作审批表单，禁止动作不会通过扩大权限偷偷继续；
4. Delivery Bundle 漂移、授权消费、实际 effect receipt 与后置验证语义在整合旅程成立；
5. Sandbox 隔离、限时、限资源、强杀、撤权与恢复在 Phase 0A 实际基线上再次验证；
6. 权威知识冲突、过期、缺失和普通上传越权晋升均 fail-closed，FLAi Bench 不产生假绿；
7. 共建地图节点状态可反查新鲜证据，删除或失效证据后不能继续显示为已验证；
8. Phase 0A 期间没有越出名单、数据/能力清单或测试命名空间，会议工作流只产生 `SYNTHETIC/TEST` receipt；
9. 退出报告明确区分平台机制、工程结果、业务价值与生产就绪，并由具名人员记录通过/不通过和剩余风险。

## 12. 决策追踪

- 控制内核与执行后端：ADR-0049
- 不中断会话与 Delivery Bundle：ADR-0050
- 两级试点：ADR-0051
- 工作台与角色化 Surface：ADR-0052
- 三条黄金工作流及 tracer bullet：ADR-0053～0056
- 权威知识底座：ADR-0057
- FLAi Bench：ADR-0058
- 共建地图与指标：ADR-0059
- 需求共创与决策权：ADR-0060～0061
- 外网飞书研发协作中枢：ADR-0062
- 外网开发、AirGap Exchange 与内网自托管 Workspace：ADR-0063

---

*V0.2 产品读模型 · 2026-07-23 · 未来能力均以状态标签和对应 ADR 为准*

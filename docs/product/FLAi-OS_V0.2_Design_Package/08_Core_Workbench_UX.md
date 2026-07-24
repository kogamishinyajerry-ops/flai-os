# 08｜工程智能体工作台核心 UX

> 文档性质：V0.2 目标体验与原型验收合同，不授权当前仓库实现。
>
> 决策依据：[ADR-0050](../../adr/ADR-0050-uninterrupted-session-and-final-delivery-authorization.md)、[ADR-0052](../../adr/ADR-0052-workbench-first-and-role-specific-governance-surfaces.md)、[ADR-0053](../../adr/ADR-0053-phase-0a-three-golden-workflows.md)、[ADR-0054](../../adr/ADR-0054-office-assistant-first-tracer-bullet.md)、[ADR-0055](../../adr/ADR-0055-cfd-assistant-first-tracer-bullet.md)、[ADR-0056](../../adr/ADR-0056-meeting-assistant-first-tracer-bullet.md)、[ADR-0062](../../adr/ADR-0062-feishu-single-organizational-hub.md)。
>
> 当前设计依据：[UI-PARADIGM](../../design/UI-PARADIGM.md) 与本设计周期的 WorkBuddy 实机录屏分析。录屏分析稿尚未进入本隔离基线，只作外部设计证据；正式验收 Stage C 或申请 Stage D 前必须按精确 digest 导入或登记。

## 1. 状态与范围

| 标签 | 含义 |
|---|---|
| `IMPLEMENTED-VERIFIED` | 当前精确范围、版本与环境有可复跑机械证据，绑定命令、结果引用和日期；不等于生产就绪 |
| `IMPLEMENTED-PARTIAL` | 当前已有可复用交互或实现 Seam，但合同不完整 |
| `ACCEPTED-NOT-IMPLEMENTED` | 目标体验已由 ADR 接受，尚未实现 |
| `DECLARED-NOT-VERIFIED` | 原型候选或外部产品行为，未形成项目证据 |
| `OUT-OF-SCOPE` | Phase 0A 明确冻结 |

本章首先服务 macOS 桌面端受控验收。目标态中，本工作台从当前部署域的 Workspace 内嵌或重新鉴权进入，是专业 Agent 执行 Surface，不是第二个组织管理入口：外网研发域可由飞书承载入口，内网生产域只能由自托管 `FLAiWorkspace` 承载。当前 Stage C 仍是隔离原型，不接真实飞书、内网 Workspace、Runtime 或生产数据。它不宣称 Windows 适配，不改变 Web 技术栈，也不以高保真原型证明 Sandbox、授权或审计存在。

## 2. 一句话体验合同

`ACCEPTED-NOT-IMPLEMENTED`

> 用户在一个 Composer 中说清目标并附上资料；Agent 在同一会话连续计划、执行、验证和恢复；真实状态、产物与依据在原地逐步出现；所有不可逆影响汇总到末端 Delivery Bundle，由有权真人对精确版本一次决定。

这意味着：

- 不出现“规划完成，请重新填写任务创建表单”；
- 不逐工具、逐命令、逐文件弹窗确认；
- 不用“允许完全访问”永久放大权限；
- 不把内部思维链当执行透明度；
- 不把 `completed`、评测通过或人签授权混成同一种成功；
- 不让用户离开会话去寻找进度、产物或失败原因。

## 3. 桌面布局

`ACCEPTED-NOT-IMPLEMENTED`

```text
┌──────────────┬──────────────────────────────────┬─────────────────────────┐
│ ← 项目空间   │ 当前项目 · 范围摘要 · 状态坞     │ 实时观察与产物检查器    │
│              ├──────────────────────────────────┤                         │
│ ＋ 新任务    │ 用户目标                          │ 预览 / 差异 / 检查发现  │
│ 最近工作     │                                  │ 来源 / hash / 验证      │
│              │ 计划摘要                         │ 例外 / 待交付动作       │
│ 共建地图 · 次│ 执行时间线                       │                         │
│              │ 验证与恢复                       │ [按需打开，不抢主轴]    │
│              │ 交付包                           │                         │
│              ├──────────────────────────────────┤                         │
│              │ 单一 Composer                    │                         │
└──────────────┴──────────────────────────────────┴─────────────────────────┘
```

### 3.1 左轨

只负责本执行 Surface 内的新建、切换、搜索和返回当前域项目上下文，不复制项目、需求、治理、知识或领导导航。组织级默认页是当前域工作收件箱；进入工作台后，“新任务/单一 Composer”仍是执行主入口。最近工作按用户能理解的任务名显示，辅以状态、更新时间和工作流类型；不以 Agent ID 或模型名作为主标题。

### 3.2 中央连续叙事

用户目标、计划摘要、真实执行事件、验证、恢复、例外和交付按时间顺序留在同一上下文。并行工作显示为可折叠分支和真实槽位，不展开为满屏多 Agent 组织图。

### 3.3 右侧实时观察与产物检查器

任务开始后，右侧先回答四个问题：Agent 当前在执行哪个**可观察动作**、正在处理哪个工作对象、已经形成什么可见结果、是否有必须关注的阻断或未知。产物首次产生时直接进入同一检查器的预览区；依据、hash、详细验证和审计字段退到按需展开层，不以证据列表占满首屏。

检查器支持工作对象预览、差异、定位来源和查看验证；关闭后中央时间线、最后可信观察和选中产物均不丢失。敏感原始数据按主体与作用域脱敏，secret 永不默认显示。它不得使用“进展显著”、未经校准的百分比或无限旋转来替代真实事件。

### 3.4 状态坞

`IMPLEMENTED-PARTIAL` 当前已有 StatusDock/StatusCenter/peek/full-page 四级披露。V0.2 继续复用这一 Seam，但状态来源要升级到自治会话与 Delivery Bundle，而不是用现有任务列表推断所有目标态语义。

### 3.5 中文主标签

普通用户界面固定使用中文结果词：`交付包`、`版本指纹`、`执行凭证`、`检查发现`、`工具记录`、`待确认事项`。`Delivery Bundle`、`digest`、`receipt`、`findings`、`tool run` 等内核字段只在专家展开、复制字段或审计导出中作为次级标注，不能成为主按钮和首次使用门槛。

## 4. Composer：开始工作而不是配置系统

`ACCEPTED-NOT-IMPLEMENTED`

### 4.1 默认态

Composer 只要求：

- 一段自然语言目标；
- 可选文件或目录；
- 已由当前工作空间带入的上下文。

输入框上方用一行中文摘要说明本次范围，例如：

> 在“气动项目资料”隔离工作区内读取上传内容；不覆盖原件；当前不访问外网；不可逆动作只在最终交付时确认。

“查看范围”可以展开已批准能力、数据域、网络状态、最大资源和策略版本，但不是提交前必填表。

### 4.2 能力推荐

工作流卡片用中国用户熟悉的结果名称：

- 润色技术报告
- 检查 CFD 算例
- 整理会后纪要与行动项

点击卡片只填入可编辑示例目标或筛选附件类型，不代用户提交。Phase 0A 的 Agent、Skill、Workflow、模型、Tool、Schema 与权限全部由冻结 CapabilityReleasePackage 和策略后台推导；包括专家用户在内都没有任务级选择器或覆盖入口。具备职责的治理人员只能在工作台之外通过版本化发布流程形成新 package，不能在一次任务提交时临时改配置。

### 4.3 提交反馈

提交后立即生成不可变输入摘要与本次会话标识，Composer 留在原位。附件 quarantine、同一已验证句柄、scope、classification 与 policy 校验是任何模型、解析器或 Tool 读取输入之前的硬前置门；界面无需逐步打断用户，但执行不得抢跑。运行中补充内容必须形成新的 immutable request/session revision 或明确排入后续轮次，不能注入并改写当前已冻结 run；新 revision 必须重新 quarantine、重编译 CanonicalTaskGraph，并重绑 SessionExecutionGrant，范围扩大不得继承旧授权。若输入不可安全解析，显示具体受阻原因并保留草稿，不把失败表单清空。

### 4.4 禁止态

- 规划完成后弹出几十字段的任务表单；
- 把系统生成的 JSON 要求用户确认后再复制提交；
- 用“高级模式”默认暴露 shell、MCP 或环境变量；
- 用户未提交就自动执行；
- 中文输入法组合状态按 Enter 误提交。

## 5. 自治会话时间线

`ACCEPTED-NOT-IMPLEMENTED`

### 5.1 用户可见阶段

以下是**展示归并**，不是新的持久化状态机。每个展示态必须由控制内核事件派生：

| 展示态 | 用户看到 | 证据要求 |
|---|---|---|
| 已接收 | 输入和范围已冻结，正在排队或准备 | 会话 ID、输入摘要、时间、策略版本 |
| 工作中 | 当前正在解析、检查、调用工具或生成产物 | 最近真实事件、活动开始时间、执行引用 |
| 验证中 | 正在做保真、确定性检查或结果校验 | 验证项、工具或规则版本、结果引用 |
| 正在恢复 | 对可恢复故障执行有界重试或重新规划 | 触发原因、次数、预算、最新事件 |
| 待交付 | 精确交付包已冻结，等待有权真人 | 版本指纹、产物、差异、风险、待交付动作 |
| 已交付 | 人类决定、实际效果与后置验证均有对应事实 | 签发凭证、执行凭证、后置验证 |
| 受阻 | 策略、依据、输入或不可逆影响无法安全处理 | 阻断码、影响、已完成范围、可行下一步 |
| 未知 | 状态或依据无法确认 | 最近成功观察、缺失范围、禁止的推断 |
| 失败 | 真实执行或验证失败 | 失败阶段、错误引用、残余产物、安全重试条件 |
| 已取消 | 用户停止、策略终止或强杀已生效 | 取消主体、原因、停止凭证、保留证据 |

`IMPLEMENTED-PARTIAL` 当前 [任务事件标准](../../05_Task_Event_Standard.md) 使用十态，并以 `waiting_review` + 人工 review 作为既有运行合同。该合同必须如实保留；在 Delivery Bundle、精确授权、CAS 消费与效果 receipt 实现并验证前，不得把 `waiting_review` 改名后宣称目标态已完成。

### 5.2 时间线条目

每条默认显示：人话动作、真实状态、时间与主要对象。例如：

> 已检查 `system/fvSchemes` 的离散格式 · 发现 2 项建议 · 查看依据

展开后才显示文件字段、脱敏参数、tool run、模型调用元数据、策略决策或经授权脱敏的输出证据。不得展示内部思维链、系统提示、隐藏上下文、Secret、未经审查的 stdout/stderr 或原始模型输出；没有证据的自然语言更新不能使用完成式动词。

### 5.3 并行、排队与估时

- 可以显示“2 项并行检查中”“等待 CFD 解析槽位”，前提是队列和并发事实可验证。
- 不显示未经校准的精确剩余时间；可使用范围或“暂无法估计”。
- 排队期间说明原因、已等待时长和可取消范围，不播放假执行动画。
- 恢复必须显示次数与预算，避免无限“正在重试”。

### 5.4 停止

用户始终有一个清晰“停止”入口。停止动作先变为“正在停止”，直到 Sandbox/执行后端返回停止 receipt；不能点击即假装已停止。已经生成的产物与证据保留并标记不完整。

### 5.5 实时工作观察投影

`IMPLEMENTED-VERIFIED` 仅指 2026-07-23 隔离 Stage C 合成原型中的纯前端投影合同与机械测试；生产 Runtime、API、持久化 Schema 和真实心跳仍未实现。

实时观察不是 Agent 自由输出的一段“我正在做什么”，而是从控制内核已验证事件派生的显示 Read Model。当前候选合同 `flai.stage-c.observer.v2` 包含：

| 字段 | 用途 | 不变量 |
|---|---|---|
| `source / contractVersion` | 标明适配来源与版本 | 字段值本身不是认证；生产 Adapter 只能从受信控制内核通道构造 |
| `eventId / sequence` | 去重并选择最近观察 | 同一 sequence 内容冲突时整体降级未知，不任选一条故事 |
| `taskId / taskRevision / executionEpoch` | 绑定精确任务修订与执行世代 | 任一不匹配都停止动态并 fail-closed |
| `observedAt` | 判断观察是否仍新鲜 | 活动态过期或时间超出允许偏差时停止动画并显示未知 |
| `reality` | 区分 `REAL / MOCK / TEST` 执行现实 | 必须有同类型、非空 id 的 `reality-witness`；同一 execution epoch 不得切换 reality |
| `kind / action` | 派生工作、关注、预览、失败、停止等显示语法 | 事件不能直接提交 `motion=true`；动画只由有限 kind 集合派生 |
| `step.current / total / label` | 显示可验证步骤或语义状态 | 禁止百分比、预计剩余时间和模型自报完成度 |
| `preview` | 当前工作对象及可见结果 | 必须是结构化、可验证预览摘要；不是思维链或原始模型输出 |
| `evidenceRefs` | 指向支持本次观察的依据 | 引用缺失不允许把建议升级为结论 |

原型阈值暂定活动观察 30 秒过期、未来时间最大偏差 5 秒，只用于机械验证 fail-closed 行为，不是生产策略。正式 Runtime 接入时必须由控制内核冻结带版本的 freshness policy，并从现有 `task_events`、ExecutionRun、ToolRun、Artifact 与 Knowledge evidence 投影；不能让 Agent Runtime、Tool Adapter 或前端自行声明权威状态，也不能形成第二任务状态机。

#### 5.5.1 只读 Runtime Observer Adapter 候选

`IMPLEMENTED-VERIFIED` 仍只指隔离 Stage C 原型里的纯函数设计与测试夹具，不表示生产 Runtime、统一 `ExecutionRun`、Artifact/Evidence API 或观察心跳已经实现。候选 Adapter 版本为 `flai.stage-c.runtime-observer-adapter.v3`，公开缝隙固定为：

```text
adaptRuntimeFactsToObserver({
  binding,
  readSnapshot,
  taskEvents,
  executionRun,
  artifacts,
  knowledgeEvidence
}) -> { observerEvents, diagnostics }
```

Adapter 不读数据库、不请求网络、不更新任务、不生成签发事实，也不认证 `source="control-kernel"` 这段字符串。未来生产组合根必须先完成主体授权、对象授权、分级门和受信通道验证，再把同一只读快照交给 Adapter；结构校验不能代替来源认证。

| 输入 | 当前可读事实 | Adapter 不变量 |
|---|---|---|
| `binding` | 调用方提供精确 `taskId + taskRevision + executionEpoch` | 三者任一缺失或不匹配，零事件；不得从时间戳或 task id 猜 revision/epoch |
| `readSnapshot` | 不落生产 Schema 的只读组装 envelope：`factSetDigest + capturedAt + task/event/run/artifact/knowledge manifest` | 四组事实必须与 manifest 逐项一致；Execution fact 还冻结 backend/Adapter identity、reality、witness id/phase/verification/time/refs；fact 时间不得晚于 `capturedAt`；缺失、混装或 mutable poll label 均零事件 |
| `taskEvents` | 现有 `/events` 按 SQLite 自增 id 追加顺序分页，但响应不公开 id | 输入必须携带真实页 `offset`；ordinal=`offset+数组位置`，不得按 `created_at` 重排；同 event id 改写即阻断 |
| `executionRun` | 当前 Task + ToolRun 只能组成 `availability=partial`；统一实体和单调 observation revision 尚未实现 | `partial` 永远零活动事件；除精确 run identity、observation、heartbeat 和 current refs 外，还必须提供与状态一致的 backend/reality witness；任一缺失或冲突均零事件 |
| `artifacts` | 内部 `files` 行已有 task id、kind、SHA-256、classification；现有 output-files API 只有 id/name/size/classification | 元数据列表缺 digest 只能诊断，不能成为可验证当前对象；跨 task 产物使整组读取失败；path/uploaded_by 不出 Adapter 输出 |
| `knowledgeEvidence` | `knowledge_search` 已记录 scope 与 `chunk_id/source/fingerprint` | 四钥必须与原 task event 逐项一致；它只能证明“检索过什么”，不能证明 KnowledgeVersion 已生效、适用或获授权，因此保留 `knowledge_authority_unresolved` |

`readSnapshot.factSetDigest` 必须采用 `sha256:<64 hex>` 形式，语义是 canonical **fact membership + trusted capture boundary** 的稳定内容摘要，而不是随机 request id；相同事实集合与相同 `capturedAt` 重放必须得到相同摘要和字节一致的观察事件，`capturedAt` 改变则摘要必须改变。它用于阻断通过提高捕获时间让“未来事实”混入旧摘要。v3 原型只校验摘要格式和 manifest/事实逐项一致性，不自行认证来源或重新实现密码学；未来生产 Snapshot Assembler 必须在同一授权、分级和一致性读取边界内计算并验证摘要，再调用本 Adapter。

Adapter 只使用 task event 的枚举、写入 ordinal 和结构化引用，不采用 `message`、Agent log 或模型自由文本生成右栏标题。活动观察还必须由 verified ExecutionRun 指向一个带 digest、同 task 的只读对象；否则返回 blocking diagnostic，随后既有 `projectObserverEvents()` 只能得到 `unknown + settled`。合法观察的 `evidenceRefs` 首项回指 `read-snapshot:sha256:…`，其后才是 task event、ExecutionRun、Artifact 和 Knowledge refs。

v3 的 backend/reality witness 候选形状为：

```text
backend {
  backend_id, backend_kind=execution-broker|mock|test,
  adapter_id, adapter_version
}
reality_witness {
  witness_id, reality=REAL|MOCK|TEST,
  phase, verification,
  execution_id, execution_epoch, backend_id,
  observed_at, evidence_refs[]
}
```

三类 reality 不能互相借用语义：

- `REAL`：只接受 `execution-broker + verified`，要求 backend receipt、独立 Sandbox witness，以及与状态一致的阶段证据；
- `MOCK`：只接受 `mock + declared + mock-seal`；
- `TEST`：只接受 `test + declared + test-fixture`。

REAL `backend` 表示唯一 ExecutionBroker 的组合身份，不代表 OpenClaw/OpenHands Agent Runtime、macOS Sandbox Provider 或 OpenFOAM/Office Tool Adapter 中任一个 Port，三者的具体身份与摘要应由 production receipt 继续展开。阶段固定为活动态 `activity`、`waiting_review → review-ready`、`completed → result`、`failed → failure`、`cancelled → termination`。REAL 后四态分别还要求 `collect/result/failure/termination-witness`。witness 必须绑定同一 execution id、execution epoch 与 backend，且 `observed_at` 不得晚于 ExecutionRun 观察。`completed` 不会把 MOCK/TEST 升级为 REAL，也不产生真人签发；REAL cancelled 缺 termination evidence 时不能投影“已停止”。

v3 的混装门已经机械覆盖：

- snapshot 声明后又追加 task event；
- ExecutionRun observation revision 超过 manifest；
- ExecutionRun `observed_at` 晚于 `capturedAt`；
- backend/reality/witness id 或 Adapter id/version 与 snapshot manifest 不一致；
- REAL witness 缺失、跨 backend、时间倒挂或缺状态阶段证据；
- MOCK 把 declaration 改成 verified 试图借用 REAL 语义；
- Artifact SHA-256 来自后一次读取；
- task event 与 Knowledge evidence 同时被替换为另一组、彼此仍一致的 citation；
- 相同快照重放保持字节幂等，乱序的不同 observation revision 仍由既有 projector 选择最高 revision。

只读夹具覆盖 `REAL/MOCK/TEST × waiting_review/completed/failed/cancelled` 全矩阵，四态全部 settled。生产 Snapshot Assembler 明确后置：本切片没有修改数据库、API 或生产 Schema，也没有认证 receipt、验证 macOS Sandbox 能力或建立真实一致性读。未来 Assembler 必须在具名主体/对象授权、classification、同一读事务/等价一致性边界和受信 witness resolver 内完成 receipt 验签/内容核对、fact membership + capture boundary 冻结与 digest 计算，再调用该纯函数；字段值或 fixture 绝不能自证 REAL。

当前生产形状的确定结论是：`task_events + Task + ToolRun + output-files metadata + knowledge_search provenance` 可供人工排障，但因缺少权威 `taskRevision / executionEpoch`，按 Production Snapshot Assembler V1 原样必须 `TASK_BINDING_UNAVAILABLE + REJECTED`。只有未来另一个已批准的受信 binding source 提供精确绑定后，这些遗留事实才可能形成 `EXECUTION_FACTS_INCOMPLETE + DIAGNOSTIC_ONLY`；即使如此仍**不足以诚实点亮“正在工作”动画**。解除该限制还需要统一 ExecutionRun 的精确世代、单调观察修订和 heartbeat；本设计没有修改或预埋生产 Schema。

Production Snapshot Assembler 的只读候选合同已单独冻结在 [16_Production_Snapshot_Assembler_Read_Contract.md](16_Production_Snapshot_Assembler_Read_Contract.md)。该文件只供评审，实施门仍关闭；认证通道、对象授权、classification、一致性读、witness resolver、receipt 验签、fact digest 或失败语义未通过具名评审前，不得以 fixture 或 Adapter 结构校验替代生产来源认证。

## 6. 产物与证据检查器

`ACCEPTED-NOT-IMPLEMENTED`

检查器使用统一 Interface，格式差异位于 Adapter：

| 视图 | 默认信息 | 专业展开 |
|---|---|---|
| 产物 | 文件名、类型、版本、状态、预览 | hash、大小、生成步骤、保留期 |
| 差异 | 重要修改、受保护内容是否变化 | 段落／字段级 diff、原始与修改定位 |
| 依据 | 关键来源和覆盖情况 | 精确锚点、知识版本、有效期、冲突 |
| 验证 | 已执行规则与结果 | 规则版本、输入输出、失败或跳过原因 |
| 例外 | 必须由人理解或补充的聚合问题 | 原文、建议、影响、合法处置 |
| 待交付动作 | 将影响何对象、为何、能否恢复 | 主体、能力、对象、有效期、策略与参数摘要 |

预览失败时显示“预览失败，但文件是否存在/是否生成成功分别为……”；不能用空白区冒充没有产物。下载、接受草稿、签发组织事实、发布正式资产和执行外部动作是不同动作，不共用一个含糊“完成”按钮。

## 7. 交付包（Delivery Bundle）末端体验

`ACCEPTED-NOT-IMPLEMENTED`

### 7.1 出现条件

Agent 已完成所有可在受控会话内完成的工作，验证已收口，所有不可逆动作已暂存，例外和残余风险已聚合。Bundle 冻结后中央时间线明确显示“工作已准备交付”，右侧自动定位交付摘要，但不强制打开全屏模态框。

### 7.2 内容顺序

1. **交付什么**：产物、正式记录或待执行动作；
2. **改变什么**：重要差异和影响对象；
3. **依据是什么**：来源、验证和适用范围；
4. **仍不确定什么**：未知、冲突、跳过和残余风险；
5. **你现在决定什么**：接受草稿、退回修改、签发精确版本或执行待交付动作。

默认先展示产物与影响，再显示动作。无权用户只看内容和“联系有权人员”，不能看到可点击但最终 403 的伪动作。

### 7.3 决定与回声

- **退回修改**创建同一会话的后续版本，保留旧 Bundle，不覆盖历史。
- **签发／执行**前重新核验主体、策略、Bundle digest 和有效期；任何漂移 fail-closed。
- 人签成功使用 teal，并显示签发人、时间和精确版本。
- 外部动作执行中回到 clay 工作态；只有真实效果和后置验证到齐才显示相应结果。
- 授权成功但执行失败显示红色真实失败，不能继续保留“已成功”庆祝态。

### 7.4 不使用的模式

- 中途 Action approval 队列；
- 会话级永久 Full Access；
- 全文盲签或每段逐条签；
- 签发按钮藏在原始日志之后；
- AI 给出“建议批准”并自动预选；
- 一个“批准”同时表示接受文件、发布资产和执行外部动作。

## 8. Tracer UX 之一：技术报告润色与规范化

`ACCEPTED-NOT-IMPLEMENTED`，依据 [ADR-0054](../../adr/ADR-0054-office-assistant-first-tracer-bullet.md)。

### 8.1 起手

用户上传一份 DOCX，例如：

> 帮我润色这份技术报告，统一术语和格式，但不要改变数字、单位、公式、表格和图片。

Composer 自动显示：仅处理隔离副本、不覆盖原件、首版只支持 DOCX。若文件类型或大小不支持，提交后给出受阻原因并保留目标；不把用户转去 Office 配置页。

### 8.2 连续时间线

1. 冻结 DOCX 输入与 digest；
2. 安全解析 OOXML 并识别段落、样式和受保护内容；
3. 生成润色副本；
4. 做数字、单位、公式、表格、图片与结构保真检查；
5. 生成重要差异和可能改变技术含义的问题；
6. 冻结 Delivery Bundle。

任何可能改变技术含义的改写保留原文并进入末端例外，不逐段弹窗追问。

### 8.3 右侧检查器

默认标签：

- 修改后的 DOCX；
- 修改摘要；
- 重要差异；
- 保真检查；
- 待确认问题。

差异按“语言优化／格式规范／未采用建议／待确认”分组，数字或公式变化一旦被检测到即阻断该修改并突出证据。不能只显示模型总结而没有可回查 diff。

### 8.4 末端

用户可以接受修改副本、退回进一步润色或下载草稿。若后续要替换正式文档资产，必须作为独立待交付动作进入精确 Bundle；首个 tracer 不自动覆盖原文件、不自动发布知识库。

### 8.5 失败与未知

- 恶意或损坏 OOXML：安全受阻，报告检测项，不尝试绕过解析器；
- 宏、ActiveX、OLE、嵌入包或需要主动访问的外部关系：整份输入稳定拒绝，业务 parser/model/tool 调用为 0；不得用“部分处理”绕过 quarantine；
- 通过 quarantine、确认无活动能力但超出首版保真矩阵的复杂 OOXML 对象：只可在不读取/改写该对象的隔离副本范围继续，明确保护对象、覆盖缩小与 blocked 区域；无法证明安全分割时仍整份拒绝；
- 数字/公式对比不可解析：标记未知并阻断涉及范围的自动交付；
- 预览失败但文件生成成功：分别展示两个事实。

## 9. Tracer UX 之二：CFD 算例体检

`ACCEPTED-NOT-IMPLEMENTED`，依据 [ADR-0055](../../adr/ADR-0055-cfd-assistant-first-tracer-bullet.md)。

### 9.1 起手

用户上传已有 OpenFOAM 算例或压缩包并描述任务目标与工况。Composer 常驻显示：

> 本次只读检查，不修改算例，不启动求解；建议不构成工程校核结论。

平台自动检查包类型、目录穿越、软链接、大小和文件预算。用户不需要先填写求解器、湍流模型和网格质量表；能从算例读取的字段由系统提取，读取不到的成为未知。

### 9.2 连续时间线

1. 冻结只读输入并安全展开；
2. 检查算例完整性与版本适用性；
3. 解析求解器、物理模型、材料、边界条件和数值设置；
4. 读取已有网格质量与运行日志证据；
5. 执行确定性规则；
6. 生成风险解释和修改建议，并区分事实、建议与未知；
7. 冻结体检报告和结构化 findings。

### 9.3 检查发现（findings）Interface

每条 finding 必须含：

- 检查项；
- 当前设置；
- 判断状态；
- 风险等级；
- 文件与字段来源锚点；
- 建议；
- 无法确认的前提。

列表默认按“需要关注／未知／符合已检查规则”组织，不给无证据的“总体健康 92 分”。点击 finding 在右侧定位文件和字段，复制建议时保留其适用前提。

### 9.4 末端

Delivery Bundle 包含辅助体检报告、结构化 findings、输入 digest、检查器/规则版本、未读取或跳过范围及“未启动求解”证据。用户可接受为辅助草案或退回补充分析；此动作不等于工程校核、模型选型批准或求解有效性签发。

### 9.5 失败与未知

- 缺网格质量日志：其他检查继续，相关结论明确未知；
- 版本或求解器未在支持范围：给出已解析事实，阻断不适用规则；
- 压缩包包含危险路径：整体受阻，不在宿主路径展开；
- 某字段存在多处冲突：并列来源，不由模型选择“看起来合理”的值；
- 解析器或观察状态不可用：显示最近成功阶段和未覆盖范围，不写“算例合理”。

## 10. Tracer UX 之三：会后纪要与行动项整理

`ACCEPTED-NOT-IMPLEMENTED`，依据 [ADR-0056](../../adr/ADR-0056-meeting-assistant-first-tracer-bullet.md)。

### 10.1 起手

协调人员上传会议笔记、已有文字转写稿、议程和相关文本附件，并用一句话说明会议。首版不要求实时录音、不自动加入会议，也不要求先填完整参会人和责任矩阵。

### 10.2 连续时间线

1. 冻结各来源材料和 digest；
2. 按材料生成精确来源锚点；
3. 提取议题、决策、共识和未决问题；
4. 提取责任事项的预期产出、唯一负责人、截止时间、验收标准和验收人；
5. 对来源冲突、推断内容和字段缺失形成聚合例外；
6. 生成会议工作包草稿；
7. 会议负责人对精确版本作末端签发；Phase 0A 只产生隔离 `SYNTHETIC/TEST` receipt。

### 10.3 工作包检查器

中央时间线保持工作过程，右侧提供结构化标签：

- 会议概览；
- 决策；
- 共识；
- 未决问题；
- 责任事项；
- 来源与例外。

每个条目显示来源锚点；AI 推断用“推断候选”明确标记。责任事项缺任一必需字段时仍是例外，不能静默填默认负责人或“尽快”。

### 10.4 聚合例外审阅

协调人员只在末端集中处理：来源冲突、发言人不明、责任字段缺失和推断候选。修改形成新的工作包版本并记录修改者与时间，不覆盖原始来源。例外全部消解后，会议负责人一次签发精确工作包；没有签发资格的人不能代签。Phase 0A 的签发只对测试命名空间有效，不能借测试身份激活真实责任。

### 10.5 末端与后续边界

Phase 0A 签发后只形成明确标记的 `SYNTHETIC/TEST` 工作包与 receipt，不创建正式会议记录
ID、不形成生效责任事项、不外发。只有完成 R6 真实路径验证并进入获批 Phase 0B 范围后，真实
材料的具名人签才可由同一 FLAi Meeting & Responsibility Governance owner-local transaction
创建正式会议记录与全部初始责任事项；一个 OwnerCommitReceiptV1 必须绑定正式记录及全部
责任项引用。任一责任项五字段不完整或回执未知时不得称会议闭环。AI 不签发会议结论，也不
替代验收人关闭责任事项。

`OUT-OF-SCOPE` 首版不做自动通知、自动催办、成果提交与验收全生命周期；这些能力未来必须另立 Interface 和权限合同，不能藏在“签发”按钮里顺带执行。

### 10.6 失败与未知

- 来源互相冲突：并列呈现并要求末端消解；
- 负责人只有姓氏或代称：保持未知，不自动匹配组织通讯录；
- 截止时间只有“下周”：显示原文和解析候选，不静默固化日期；
- 多份材料无法建立统一锚点：保留逐来源结果并阻断正式签发；
- 某附件解析失败：工作包明确覆盖范围，不假装全量读取。

## 11. 跨会话状态、错误与恢复体验

`ACCEPTED-NOT-IMPLEMENTED`

### 11.1 网络或页面中断

页面刷新或应用重启后，通过会话稳定标识恢复；先显示“正在恢复已存在会话”，不短暂渲染可提交的新任务空态。无法确认远端状态时显示未知和最后观察时间，不自动创建重复任务。

### 11.2 安全重试

只有 Interface 声明幂等或具备补偿/去重键时显示“重试”。外部不可逆动作执行结果未知时禁止一键重试，必须先核验 receipt 和外部状态。

### 11.3 错误消息

错误常驻在相关阶段和相关对象附近，并包括：发生了什么、影响什么、证据在哪里、系统是否仍在继续、用户是否需要做事。Toast 只作即时回声，不是唯一错误载体。

### 11.4 受阻后的下一步

下一步最多给出当前合法选项，例如补充缺失来源、缩小范围、联系具名治理职责或结束会话。不得建议“开启完全访问”“以管理员重试”或降低安全设置。

## 12. 中文、键盘与无障碍细节

`ACCEPTED-NOT-IMPLEMENTED`

- 默认中文标签；专业字段保留原始英文键时同时给出中文解释和复制入口。
- 支持中文文件名、空格、全角字符和长路径的完整显示与中间省略；hover/focus 可读全名。
- 日期使用 `YYYY-MM-DD` 或中文绝对时间，24 小时制；“刚刚”必须有可展开绝对时间。
- `⌘K` 可搜索会话、产物和有权访问对象；所有快捷键有按钮等价路径。
- `Esc` 按检查器 → 速览 → 状态中心的层级退出，不意外取消任务。
- Composer 支持输入法组合，发送快捷键可配置且可见。
- 状态变化使用文字、图标和形状；屏幕阅读只播报关键阶段与需要处理的例外，不朗读 token 流或每条工具日志。
- 200% 缩放下中央主轴不被右侧检查器压到不可操作；检查器可变为覆盖层并保持焦点圈闭。
- 减少动态效果时禁用位移、粒子和庆祝动画；真实状态仍以静态方式完整表达。

## 13. Module 设计与复用 Seam

`ACCEPTED-NOT-IMPLEMENTED`

| Module | 小 Interface | 隐藏的实现复杂度 | 复用价值 |
|---|---|---|---|
| Composer Module | `目标 + 附件 + 可选上下文 → 会话回执` | 输入快照、能力解析、策略范围、附件检疫、幂等 | 三条 tracer 共享同一起手，无长表单分叉 |
| Execution Timeline Module | `会话事件 + 主体 → 中文时间线` | 状态归并、并行、恢复、脱敏、未知、轮询/推送 | 所有工作流共享真实状态语法 |
| Live Observer Projection Module | `已验证观察事件 + 精确任务身份 → 当前动作/对象/可见结果` | 顺序冲突、Epoch、心跳新鲜度、未知、动画门 | 右侧观察面不读取 Agent 自报状态，也不形成第二状态机 |
| Artifact & Evidence Module | `产物引用 + 主体 → 预览/差异/依据/合法动作` | 文件格式、安全渲染、权限、hash、来源、错误 | DOCX、CFD、会议材料通过 Adapter 扩展 |
| Delivery Bundle Module | `Bundle 引用 + 主体 → 摘要/决定/receipt` | 冻结、CAS、策略重检、过期、执行与后验 | 所有不可逆影响共用一个权威 Seam |
| Status Projection Module | `权威事件 → pill/清单/速览/完整页` | 去重、未读、未知、角色过滤、恢复 | 保持“状态来找人”且不造第二状态机 |
| Hub Entry Context Module | `授权 Hub context → project/session entry` | channel binding、重新鉴权、ACL/classification、稳定返回路由 | 工作台不复制当前域项目管理，也不相信 URL 自报 actor/project；外网 context 不能直接在内网重放 |

Interface 是测试面。每条 tracer 的验收都应从这些相同 Interface 穿过；若为某工作流复制一套时间线、授权或错误系统，就破坏了 Locality。只有 DOCX、OpenFOAM 和会议文本等真实变化格式放到各自 Adapter，保持 Module 的 Depth。

## 14. 原型验收脚本

### 14.1 共通脚本

`ACCEPTED-NOT-IMPLEMENTED`

1. 用户从当前部署域的 FLAi 工作收件箱进入，或在当前 Stage C 隔离入口模拟同一上下文；输入一句目标并附文件，单击一次开始。
2. 会话进入连续时间线；中途不出现泛化审批或长表单。
3. 用户在不离开会话的情况下打开产物、差异和证据。
4. 模拟网络中断、解析失败、缺来源、策略阻断和观察未知，界面不假绿、不丢上下文。
5. Agent 完成自检后出现精确 Delivery Bundle；无权用户无签发动作。
6. 有权真人退回生成新版本，旧 Bundle 仍可追溯。
7. 有权真人签发精确版本；Bundle 漂移或过期时 fail-closed。
8. 授权后模拟真实执行失败，界面显示失败而不是“授权成功=交付成功”。
9. 仅键盘、200% 缩放、减少动态效果和中文输入法各走完一次。

### 14.2 三条 tracer 的最小机械断言

| tracer | 必须为真 | 篡改后必须失败 |
|---|---|---|
| DOCX 润色 | 原件未覆盖；受保护内容差异为零或明确阻断；修改副本、diff、例外和证据齐全 | 静默改数字/公式、预览空白冒充无产物 |
| CFD 体检 | 不启动求解、不写输入；每条 finding 有字段锚点；缺证据为未知 | 输出无来源“总体合理”、危险压缩包在宿主展开 |
| 会后整理 | 每条责任事项五字段齐全或进入例外；签发者具名且版本精确 | AI 补默认负责人并当事实、无来源仍可正式签发 |

## 15. 与当前实现的迁移诚实线

`IMPLEMENTED-PARTIAL`

可复用：对话主轴、状态坞、状态中心、任务速览、完整深链页、真实轮询、信任色锁、reduced-motion 基础、产物列表和人签现有路径。

尚缺且不得用文案伪装：统一自治会话、CanonicalTaskGraph、SessionExecutionGrant、可强杀 Sandbox、不可变 Delivery Bundle、精确授权 CAS、待交付动作、效果 receipt、完整证据检查器、三条 tracer Adapter、分域 Hub Entry Context、内网自托管 Workspace Adapter、角色化治理投影与 invalid-first 验收。

实施前必须先完成架构评审与 MVP 合同；不得直接把现有 `waiting_review` 按钮改名为“交付授权”，也不得先做漂亮右栏再宣称安全闭环成立。

## 16. Phase 0A 非目标

`OUT-OF-SCOPE`

- Word 以外的 Office 全家桶、Office GUI 自动控制与邮件自动发送；
- CFD 自动求解、自动优化、覆盖原算例与工程校核签发；
- 实时录音转写、自动入会、自动通知催办与完整责任事项验收；
- Windows 专项适配；
- 个人 Token／任务量排行榜、领导驾驶舱和手填平台完成率；
- 通过展示内部思维链制造“透明度”。
- 真实飞书 tenant/app 接入、内网自托管 Workspace、AirGapExchange、组织身份签发或任一 Secret Owner 的运行时解析；它们分别属于 ADR-0062 F1～F5 与 ADR-0063 A1～A5 后续切片。

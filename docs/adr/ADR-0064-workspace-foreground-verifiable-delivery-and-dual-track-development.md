# ADR-0064：Workspace 前景体验、隐性可验证交付与双线程研发章程

- 状态：`confirmed_in_design_session`
- 实现状态：`ACCEPTED-NOT-IMPLEMENTED`
- 日期：2026-07-24
- 正式签发主体：`UNRESOLVED`
- 实施授权：仅授权收敛设计文档；不授权生产实现
- 生产 Schema 变更：否
- 生产准入影响：无；当前仍为 `NO-GO`
- 取代关系：部分澄清并取代 ADR-0052 的“工程智能体工作台是默认首页”表述；保留其
  “工程智能体工作台是首发 Agent 执行主产品”和角色化治理 Surface 决定
- 关联：ADR-0050、ADR-0052、ADR-0053、ADR-0057、ADR-0058、ADR-0059、ADR-0060、
  ADR-0061、ADR-0062、ADR-0063

## 背景

FLAi-OS 已确定以可追溯依据、受控执行、真实产物、验证证据和真人最终决定构成可信工作闭环。
但如果这些治理对象直接成为普通用户的首页、一级导航和前置表单，平台即使专业，也会因为启动
成本、认知负担和过程不可见而失去采用。

委托人在本次设计会话中进一步确认：

1. 可验证工作交付是平台价值内核，但必须对普通用户保持隐性；
2. 用户首先选择的是一个流畅、熟悉、达到成熟 Agent 工作台水准的 Workspace；
3. FLAiWorkspace 必须拥有完整前台体验，第三方自托管产品不能把产品切成拼盘；
4. 北极星必须同时证明真实采用和真实交付，不能用 MAU、Token 或 `completed` 冒充价值；
5. 蓝图冻结后，Codex 与 Kimi-K3 需要在不重叠责任域中并行开发。

本 ADR 收束这些相互依赖的产品、架构和研发组织决定。它不推翻既有控制内核、安全、知识、
Bench、AirGap 或真人签发合同。

### 规范归属

本 ADR 负责跨域优先级、前景体验、唯一北极星指标和当前双线程责任 profile。既有领域合同仍
分别由 ADR-0049（控制内核/Runtime）、ADR-0050（自治会话/交付）、ADR-0053～0056（黄金
工作流）、ADR-0057（权威知识）、ADR-0058（FLAi Bench）、ADR-0059（指标通则）和
ADR-0063（部署信任域/AirGap）规范。本 ADR 对它们的摘要用于说明组合关系，不另造持久对象、
状态机或第二套技术合同；除本 ADR 明确新增或收窄的条款外，细节冲突以对应领域 ADR 为准。

## 决定

### 1. 隐性价值对象与显性产品对象分离

FLAi-OS 的隐性核心价值对象是 `VerifiableWorkDelivery`：

```text
自然语言目标
  -> 获准上下文与依据
  -> 受控自治执行
  -> 可观察过程
  -> 可检查真实产物
  -> 验证证据
  -> 具名真人最终决定
```

它不是普通用户需要学习的产品术语、一级导航、治理表单或审批流程。用户前台感知的产品对象是
`WorkspaceForegroundExperience`：在一个统一工作空间中自然开始工作、持续观察、检查产物，
只在确有本人决定需要时介入。

产品北极星表述冻结为：

> 让一名普通工程师只用一句目标，就能在受控权限内连续完成一项真实工作，并在同一处获得
> 可检查的过程、可追溯的依据、可交付的产物，以及由真人作出的最终决定。

治理复杂度必须由系统编译进默认路径。只有来源不足、权限例外、风险中断或最终交付决定确需
本人参与时，治理信息才渐进披露。

### 2. 冻结 Workspace landing 与会话执行态工作范式

`FLAiWorkspace` 的组织级 landing 仍是工作收件箱：以低门槛 Composer、本人待处理、项目实质
变化和最近产物承接“开始、处理、回看”。工程智能体工作台是首发 Agent 执行主产品，但不是
第二组织首页。

用户提交目标或进入既有自治会话后，无缝进入采用 `SessionArtifactWorkspacePattern` 的桌面
默认执行态：

| 区域 | 默认职责 |
|---|---|
| 左侧 | 项目、空间、最近工作、历史会话与获准知识上下文 |
| 中央 | 一句话 Composer、连续 Agent 执行叙事、异常和恢复 |
| 右侧 | 此刻最值得追踪、监控、渲染或预览的真实对象 |

右侧不是固定依据栏。文档、表格、幻灯片、图片、CFD 状态、差异、异常、来源和最终产物按当前
真实状态切换；没有可验证对象时必须诚实显示缺口。会议、知识和 CFD 可以替换右侧专业工作台，
但不能分裂统一入口。

界面不得以纯聊天页、统计驾驶舱、传统表单后台或不可观察的“正在思考”作为默认体验。动效只能
由真实 observer state 驱动，terminal、unknown 或 stale 状态必须停止工作动画。

### 3. FLAiWorkspace 拥有体验主权

`FLAiWorkspace` 对导航、会话中心、动态执行流、Artifact 工作台、工作收件箱和统一视觉语言
承担完整产品责任。Mattermost、Rocket.Chat、Wiki.js、Outline、Open WebUI 或其他自托管产品
只能通过稳定 Adapter 提供可替换能力，或在不暴露产品接缝的前提下受控嵌入。

第三方 Surface 不得拥有 Agent 任务、授权、知识权威、交付、Bench 或审计真相。用户不需要
理解第三方产品边界，也不应在多套导航和状态模型之间切换。

### 4. 冻结唯一产品北极星指标

唯一北极星指标是 `WeeklyVerifiedValueUserRate`：

```text
一个冻结统计周内至少获得一项 REAL 可验证工作交付的去重目标用户数
-----------------------------------------------------------------
该周开始前由适用 `status=active` DeploymentBinding 冻结、具备真实工作流权限的目标用户数
```

计入的交付必须绑定真实产物、证据摘要和具名有权真人的有效正向最终决定；若包含外部效果，
还必须解析到成功且后置验证成立的 ActionReceipt。以下信号均不得计入分子：

- 仅有 `completed`；
- MOCK、TEST 或合成 fixture；
- 页面访问、消息、Agent 数量或 Token 消耗；
- 无冻结分母的活跃比例；
- LLM 自评或无法复核的节省时间；
- rejected、returned、cancelled、failed、effect_unknown 或仍待对账的结果。

该比率必须同时展示分子、分母和 cohort/DeploymentBinding digest；指标维护者不能通过临时
缩小目标用户集合制造增长。

Metric definition、cohort selection policy、cohort digest 或 DeploymentBinding digest 任一
变化都会形成统计断点。该周可以报告新口径值和 cohort delta/reason，但不得与上一周直接
计算或宣称环比增长。

只有 synthetic fixture 的 Phase 0A 受控验收阶段返回 `not_applicable`，不能把北极星显示为
零、REAL 或增长。

首个可见产物时间、验收率、返工率、证据完整率、单位成本、抽样节省时间、需求采纳率和路线图
进展属于诊断指标。越权、安全和假绿事件是独立护栏，目标必须为零，不能被北极星增长抵消。

### 5. 新旧系统采用渐进信息吸收

FLAiWorkspace 与老 OA、邮件、eSpace、UME 和文件系统遵循：

> 新增先收口、存量只读吸收、写回逐项准入。

获准黄金工作流产生的新工作事实优先从 Workspace 进入。历史信息只通过保留原 ACL、密级、
版本、来源、摘要和时间的只读 Adapter 渐进接入。“内网可读取”不等于当前主体有权把内容
交给模型。

向旧系统写回必须逐系统证明认证、授权、幂等、效果回执和审计。不得用账号模拟、脆弱爬虫或
一个通用写回开关作为长期架构。

### 6. 真相知识采用逻辑统一、物理联邦

权威知识底座采用 Truth Knowledge Plane：

1. 原始内容保留在受控源系统或不可变来源库；
2. 登记层统一记录 owner、ACL、密级、版本、摘要、有效期和发布状态；
3. 知识项与结论保存精确来源锚点；
4. 全文、向量和关系索引是可重建投影，不是权威本身；
5. 每次 Agent 上下文装配按当前主体、任务、密级和用途重新授权；
6. 权威知识、工作草稿、来源材料与 Agent 推断严格分层。

Obsidian、Wiki、DMS 和向量数据库只是创作、阅读、存储或检索 Adapter，不能因物理集中、
同步成功或相似度高而获得权威性。

### 7. FLAi Bench 是硬证据门，不是自动签发者

FLAi Bench 复用生产执行链，对冻结 `CapabilityReleasePackage` 运行确定性回归、工程质量、
安全治理与运行效率四条独立证据轨道。任何强制 Gate 失败均不得被综合分数抵消；REAL、MOCK
与 TEST 必须分开。

Bench 通过只表示精确发布包满足冻结标准。具名真人只能在全部强制 Gate 通过后签发适用资格，
Bench 不能自动发布，人的批准也不能覆盖红线失败。

### 8. 首发范围冻结为共同地基加三条黄金薄切片

首发承诺：

1. 技术报告润色与规范化；
2. CFD 算例体检；
3. 会后纪要与行动项整理；
4. 三者共用的 Workspace、Truth Knowledge Plane、执行观察、Artifact 渲染、Sandbox、
   权限审计与 FLAi Bench 地基。

性能盘后处理是首个 Fast Follow，不阻塞首发。Office 全家桶、自动外发消息、完整自主 CFD、
实时会议伴随、OA 替换和 Agent 市场不进入首发承诺。

首轮只能作为 Phase 0A 受控验收：由 5–8 名具名技术验收人员在 approved
`source_kind=synthetic` 数据和冻结能力范围内验证平台机制。它不证明真实业务价值、真实数据
授权、业务试点、生产就绪或组织全面采用；Phase 0B 和生产仍受各自独立准入门约束。

### 9. OpenClaw 是受约束 Runtime Adapter

FLAi Control Kernel 永久拥有身份、权限、任务、队列、预算、ReleaseKnowledgeBinding、
TaskKnowledgeSnapshot、Sandbox 准入、ExecutionTicket、Artifact、Evidence、Receipt、Bench、
审计和真人交付决定。

Built-in Runtime 是简单、确定、可做合同测试和回退的参考实现；OpenClaw 是重点吸收成熟
Agent Loop、上下文、Skill 和协作策略的 `AgentRuntimePort` Adapter。两者通过同一合同测试。
首发和 Phase 0A 可以只使用 Built-in Runtime；OpenClaw 接入是独立、可拒绝的后续切片，
不是入场依赖。

OpenClaw 不得持有企业长期凭据、绕过 FLAi 调用工具、读取未经任务时装配的知识、写权威状态
或决定业务完成。FLAi-OS 不是 OpenClaw 的定制发行版，OpenClaw 也不是第二控制面。

### 10. 冻结 Codex 与 Kimi-K3 双线程研发责任

在 `EXTERNAL_DEVELOPMENT` 域采用当前责任章程：

| 责任域 | 当前负责人 | 拥有的主要工作 |
|---|---|---|
| Platform & Integration Lead | Codex | 控制内核、领域/API 合同、后端、安全、Runtime/Sandbox/Tool Adapter、Knowledge、Bench、测试、CI、部署与集成 |
| Workspace Experience Lead | Kimi-K3 | IA/交互细化、三栏工作范式、视觉与动效系统、Artifact 右侧工作台、前端体验、响应式/无障碍、视觉回归 |

责任名称不授予系统权限，也不替代版本化 executor qualification。具体工作仍必须具有具名人类
owner、冻结 base SHA、独立 branch/worktree、不重叠文件与 Interface scope、预算、密级、
egress、验证命令和 `DevelopmentHandoffV1`。

Codex 先冻结版本化事实合同和合成 fixture；Kimi 依合同实现前台体验。Kimi 可以提出合同变更，
但不能直接修改生产 Schema、安全策略、状态机或审计语义。Codex 不得以集成为由无证据覆盖
已评审的视觉方案。

GitHub 拥有代码、PR、CI、review 和 merge 事实；飞书是外网研发工作收件箱与协作中枢。两类
AI 可以互审，但都不能成为 CODEOWNER、批准者、merge owner、安全签发者或发布 signer。
Kimi 仅处理获准源码、合成 fixture 和非敏感参考，不成为内网运行依赖。

## 关键不变量

1. 人是唯一签发者；AI 不进入正式判决链。
2. FLAi Control Kernel 是唯一运行和治理控制面。
3. 专业控制默认下沉，但不能被隐藏到无法观察或无法审计。
4. 用户体验质量与运行真实性共同构成采用门槛，二者不能互相抵消。
5. completed 不等于业务通过，Bench 通过不等于发布，GitHub merge 不等于内网准入。
6. 第三方 Workspace Adapter、OpenClaw、Codex 和 Kimi 均可替换，不拥有 FLAi 权威事实。
7. 本 ADR 不修改生产 Schema、API、数据库、状态机或依赖，不授权真实数据接入、试点或部署。

## 后果

### 正面

- 用户获得接近成熟 Agent 工作台的低门槛体验，同时保留企业级证据与安全；
- 产品成功标准从功能数量和活跃度转向真实、被人认可的工作价值；
- 自托管协作产品与 OpenClaw 可以被深度利用，但不锁定控制内核和产品体验；
- 首发范围、知识可信度、评测门和双线程责任形成同一套可执行合同；
- Codex 与 Kimi 可以并行工作，而不会争夺 Schema、状态机或同一前端文件。

### 代价

- FLAiWorkspace 必须承担更多一体化前端和 Adapter 集成工作；
- 真实价值指标形成较慢，不能靠早期演示数据快速点绿；
- 旧系统写回和知识发布需要逐来源、逐权限、逐回执治理；
- 双线程并行需要严格的 base SHA、文件所有权、合同 fixture 和集成纪律。

## 被拒绝的方案

### 把治理对象直接做成产品首页

拒绝。它会把控制内核复杂度转嫁给普通用户，形成表单后台和审批驱动体验。

### 以第三方开源产品拼成 Workspace

拒绝。通讯、Wiki 和项目系统可以提供能力，但多套导航、状态和视觉边界会破坏统一体验，并
诱发第二事实源。

### 用 MAU、Token 或 completed 作为北极星

拒绝。它们分别衡量访问、成本或技术终态，不能证明用户获得了真实、可验收的价值。

### 将所有企业数据复制进一个向量库

拒绝。物理集中不产生权威，反而可能丢失 ACL、密级、版本、有效性和责任归属。

### 基于 OpenClaw 分叉建设全部平台

拒绝。它会把身份、权限、状态、发布和供应链边界绑定到单一开源 Runtime。

### 让 Codex 和 Kimi 在同一分支自由协作

拒绝。缺少冻结 scope、独立 worktree 和权威合同会导致覆盖修改、状态漂移和不可复核交付。

## 下一阶段门

1. 将本 ADR、CONTEXT 和 V0.2 读模型收敛到一个 clean Git SHA；
2. 为 Kimi UI/UX 工作冻结独立 work item、base SHA、写范围和合成 fixture；
3. Codex 继续拥有 observer/runtime/security/API 合同并完成集成复核；
4. 两条线程各自提交机械验证与 `DevelopmentHandoffV1`，由具名人类决定是否接受；
5. 任何生产实现仍受 ADR-0063 七责任域评审、Stage D 精确授权和现行生产门约束。

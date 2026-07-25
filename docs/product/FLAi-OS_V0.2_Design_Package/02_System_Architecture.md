# FLAi-OS V0.2 系统架构

> 文档性质：V0.2 产品与开发读模型，不是新的架构事实源，也不授权修改运行时代码。
> 术语以 [`CONTEXT.md`](../../../CONTEXT.md) 为准；已接受决策以
> [`ADR-0033`](../../adr/ADR-0033-flai-control-kernel-and-replaceable-execution-backends.md)
> 至 [`ADR-0045`](../../adr/ADR-0045-demand-decision-rights-and-roadmap-signoff.md) 为准；
> 当前实现仍以代码、契约和现行标准为准；完整基线索引见本包 [`README`](README.md#7-现行基线与诚实边界)。

## 1. 状态标签

| 标签 | 本文含义 |
|---|---|
| `IMPLEMENTED-VERIFIED` | 当前精确范围、版本与环境有可复跑机械证据，绑定命令、结果引用和日期；不等于生产就绪 |
| `IMPLEMENTED-PARTIAL` | 已有真实实现，但能力面、生产证据或目标合同尚未闭合 |
| `ACCEPTED-NOT-IMPLEMENTED` | 已在设计会话中确认目标方向，但未正式组织签发、实现或验收 |
| `DECLARED-NOT-VERIFIED` | 文档或配置已有声明，但缺当前目标机或精确版本验证 |
| `OUT-OF-SCOPE` | 明确不进入本阶段 |

除非另有精确证据，本文件不把任何目标模块标为 `IMPLEMENTED-VERIFIED`。当前混合工作树、历史截图、旧测试记录和环境变量存在都不能单独证明生产就绪。

## 2. 架构结论

FLAi-OS V0.2 采用一个权威控制内核，由 Execution Broker 组合三类语义不同、分别可替换的执行 Port：

```text
用户 / 治理角色
      │
      ▼
工程智能体工作台（Vue 3）
      │  authenticated request / read model
      ▼
FastAPI Application API
      │
      ▼
FLAi Control Kernel（唯一权威控制面）
  ├─ Identity & Resource Authorization
  ├─ Intent Compiler & Canonical TaskGraph
  ├─ SessionExecutionGrant Lifecycle
  ├─ Durable Queue / Budget / Lease
  ├─ Execution Broker
  ├─ Artifact / Evidence / Delivery
  ├─ Knowledge Authority & FLAi Bench
  └─ Audit Outbox / Read Projections
      │
      ▼
Execution Broker（组合层，不持有第二状态机）
  ├─ AgentRuntimePort
  │    ├─ Built-in Runtime Adapter
  │    ├─ OpenClaw Adapter（候选）
  │    └─ OpenHands Adapter（候选）
  ├─ SandboxProviderPort
  │    ├─ MacSandboxAdapter（Phase 0A 候选）
  │    └─ InMemorySandboxAdapter（仅测试、非 REAL）
  └─ ToolExecutionPort
       ├─ Python / Office Tool Adapter
       └─ CAE / HPC Adapter
      │  every dynamic action requires ExecutionTicket
      ▼
Model Gateway / Knowledge / Approved Connector / Tool Registry
```

`FLAi Control Kernel` 是身份、策略、任务图、队列、状态、审计、证据与交付决定的唯一事实源。OpenClaw/OpenHands 只实现 `AgentRuntimePort`，macOS 隔离只实现 `SandboxProviderPort`，CAE/HPC 只实现 `ToolExecutionPort`；它们不是彼此可替换的同类 Adapter。Agent Runtime 只能提出 replan/step proposal，不能直接调用 Tool、Model、Knowledge 或 Connector；每个动态动作必须返回 Kernel 取得短时 `ExecutionTicket`。任何 Adapter 都不能签发、授权、改变权威终态、持有第二套恢复语义或建立第二本审计账簿。这一所有权由 [ADR-0033](../../adr/ADR-0033-flai-control-kernel-and-replaceable-execution-backends.md) 固定。

## 3. 现状基线

| 当前模块 | 状态 | 已有深度 | 诚实边界 |
|---|---|---|---|
| FastAPI + Python 3.10+ 后端 | `IMPLEMENTED-PARTIAL` | API、Registry、Runtime、Gateway、任务与治理已有真实代码 | 未以本设计包重新跑全量验证；不能外推为生产发布候选 |
| Vue 3 + Vite + Element Plus 前端 | `IMPLEMENTED-PARTIAL` | 工作台、任务详情、事件与治理页面已有实现 | 现有页面不证明目标授权、Sandbox 或指标事实已存在 |
| SQLite 仓储层 | `IMPLEMENTED-PARTIAL` | 无 ORM 仓储、任务表、事件及多类运行证据已存在 | 目标对象级授权、租约、审计 outbox、交付包等合同未闭合 |
| SQLite Job Runner | `IMPLEMENTED-PARTIAL` | 持久任务、轮询 claim 与恢复基础存在 | 当前不是统一 lane/budget/lease 调度；运行中 kill 与副作用对账未闭合 |
| Agent / Tool Package | `IMPLEMENTED-PARTIAL` | Schema、版本、白名单、limitations、Registry seam 已形成 | 包签名、SBOM、quarantine、运行隔离与能力发布包摘要未闭合 |
| Model Gateway | `IMPLEMENTED-PARTIAL` | profile 路由、调用归因和 Token 记录已有实现 | 统一 task-aware egress、SecretRef、短时凭据与目标 witness 未闭合 |
| Knowledge Service | `IMPLEMENTED-PARTIAL` | `file_dir × document` 的 BM25、scope 白名单已有实现 | 不是权威知识底座；interactive 挂载、有效期、发布/撤销和精确锚点未闭合 |
| Eval Runner | `IMPLEMENTED-PARTIAL` | eval case、snapshot、人工评审、promotion seam 已存在 | 尚未冻结完整能力发布包，仍需消除晚写翻绿等假绿路径 |
| 文件与任务分级 | `IMPLEMENTED-PARTIAL` | `internal|sensitive`、任务级 CAS-on-NULL 与部分读取门已有实现 | 当前标签不等于完整企业授权；附件引用旁路仍是 P0 缺口 |
| 真正的执行 Sandbox | `ACCEPTED-NOT-IMPLEMENTED` | 只有 subprocess/工作目录等局部 containment 先例 | 未证明 OS 强制文件、网络、资源与进程树隔离，不得称“已沙箱化” |
| 离线正式发布链 | `DECLARED-NOT-VERIFIED` | 有规划、校验脚本与局部备份能力 | 完整制品 hash、SBOM、组织签名、断网安装与全资产恢复尚未闭合 |

当前分层基线见 [总体架构](../../01_Overall_Architecture.md)、[Agent Package 标准](../../02_Agent_Package_Standard.md)、[Tool Package 标准](../../03_Tool_Package_Standard.md)、[Model Gateway 标准](../../04_Model_Gateway_Standard.md) 和 [Task/Event 标准](../../05_Task_Event_Standard.md)。

## 4. 目标 Modules、Interfaces 与 Seams

### 4.1 工程智能体工作台

- **状态**：`IMPLEMENTED-PARTIAL`（现有工作台）＋ `ACCEPTED-NOT-IMPLEMENTED`（V0.2 完整体验）。
- **Module 责任**：接收自然语言目标，展示执行事实、证据、产物与末端交付；不求解权限、不拼装权威状态、不生成“漂亮的假绿”。
- **Interface**：只调用 Application API；所有按钮可见性与后端授权都来自同一 effective policy 投影，前端隐藏按钮不是安全控制。
- **Depth**：正常路径只有“提交目标 → 连续执行 → 检查产物/证据 → 末端交付授权”。Schema 求解、计划修补和策略判定留在后台。
- **Locality**：产品交互变化应收敛在前端视图与稳定 read model，不把执行框架特性泄漏给普通用户。

### 4.2 Application API

- **状态**：`IMPLEMENTED-PARTIAL`。
- **Module 责任**：认证请求、输入边界校验、调用 Control Kernel、返回角色适配的 read model。
- **Interface**：任何 task、conversation、file、feedback、eval、promotion、knowledge 或 delivery 资源动作都必须进入统一 `authorize(actor, action, resource, context, policy_version)` seam。
- **禁止**：路由函数直接 import 第三方 workflow、执行 shell、在 UI 参数中信任 owner/project/classification、绕过 Kernel 写终态。

### 4.3 Identity & Resource Authorization

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`；现有认证与粗粒度角色仅为 `IMPLEMENTED-PARTIAL`。
- **Module 责任**：把认证主体、项目成员关系、对象 owner、数据分级、Agent 可见性、职责委派和动作类型编译为确定性决策。
- **Interface**：唯一入口为 `authorize(actor, action, resource, context, policy_version)` 与 commit-time `recheck(...)`，结果为 `DENY | DEFER_TO_DELIVERY | AUTO_EXECUTE`。只有 `AUTO_EXECUTE` 才可进一步签发短时 `ExecutionTicket`；`DENY` 永不可被 Delivery 覆盖，下层策略只可继续收紧。
- **Seam**：API 入口、后台恢复、附件装配、模型上下文渲染、治理写入和不可逆提交共用同一 Policy seam，并在事务提交前重检活跃身份与授权。
- **Locality**：策略规则集中；业务 Module 只传 actor/action/resource，不自行发明 `is_admin` 分支。

### 4.4 Intent Compiler & Canonical TaskGraph

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **Module 责任**：把用户目标、项目策略、附件 envelope、权威知识和能力目录编译成具名来源的 DAG。
- **Interface**：

  ```text
  compile_intent(request_envelope, project_context, capability_catalog)
    -> READY(task_graph, provenance, assumptions)
     | BLOCKED(missing_facts, policy_conflicts, evidence)
  ```

- **Depth**：内部允许发现、重规划、Schema 验证和保守默认；外部不暴露 `prefilled_inputs` 搬运、逐 Agent 建任务或重复填表。
- **不变量**：LLM 可以提候选图，只有确定性编译器能解析来源、验证类型、生成 canonical digest；无法推导且会改变安全边界的事实聚合为一次 `blocked`。

### 4.5 SessionExecutionGrant Lifecycle

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **Module 责任**：在用户提交目标时后台建立、版本化、撤销和关闭受控会话范围；它提出逐步授权请求，但不拥有 Policy 判定或 Delivery 写入。
- **Interface**：`open_session`、`request_step_authorization`、`revoke_session`、`close_session`。`request_step_authorization` 只是调用 Authorization Module 的 façade；唯一 Policy 决策仍由 4.3 产生。
- **Depth**：用户不填写授权表。Grant 从认证主体、项目策略、工作区、Agent/Tool 版本、输入摘要、网络策略、资源预算和期限派生。
- **不变量**：Grant 不授权永久访问；它只冻结 Identity/Authorization/Supply-chain owner 的 `credential_epoch + authorization_epoch_snapshot[] + trust_policy_epoch/digest`，自身永不改写。策略/输入/能力漂移形成新 digest；不可逆动作只进入 Delivery Bundle。对应 owner 撤权时以 CAS 提升 epoch、同事务写 invalidation outbox、停止新 claim，并把所有绑定旧快照的 active lease 送入 Broker 强制终止；不能只等下一步或提交阶段再拒绝。见 [ADR-0034](../../adr/ADR-0034-uninterrupted-session-and-final-delivery-authorization.md)。

### 4.6 Durable Queue / Budget / Lease

- **状态**：现有 SQLite 队列 `IMPLEMENTED-PARTIAL`；V0.2 合同 `ACCEPTED-NOT-IMPLEMENTED`。
- **Module 责任**：在接纳前执行 lane、预算、并发、背压和恢复判定；持有执行租约而不是依赖进程内内存队列。
- **Interface**：`admit`、`claim_lease`、`heartbeat`、`request_cancel`、`finish_if_lease_matches`、`reconcile`。
- **Seam**：保持 SQLite Job Runner；不引入 Redis/Celery，也不采用 OpenClaw 进程内 Promise 队列作为企业任务事实源。
- **不变量**：每会话最多一个 active run；终态 CAS；租约 generation 匹配；非幂等/未知副作用不得自动重放。

### 4.7 Execution Broker

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **Module 责任**：把已授权的 canonical plan 变成可隔离、可停止、可收集证据的执行，而不是让主应用直接执行第三方代码。
- **Interface**：

  ```text
  prepare(task_graph_digest, grant_digest, policy_digest, epoch_snapshot_digest, lease_generation)
    -> execution_handle
  start(execution_handle) -> running_witness
  observe(execution_handle, since_sequence) -> observations
  reattach(execution_handle, lease_generation) -> running_witness | reconcile_required
  reconcile(execution_handle, observed_side_effects) -> reconciliation_decision
  cancel(execution_handle, cancellation_token_digest) -> termination_witness
  revoke(execution_handle, revocation_token_digest) -> revocation_witness(process, credential, connection)
  collect(execution_handle) -> result + resource_usage + evidence_refs
  destroy(execution_handle) -> cleanup_witness
  ```

- **逐步控制协议**：Agent Runtime 的动态 replan/step 只能形成 `StepProposal`。Kernel 对 proposal 的 canonical step digest、Grant、policy、`credential_epoch + authorization_epoch_snapshot[] + trust_policy_epoch/digest`、lease id/generation、调用能力/目标、预算、有效期和 nonce 做确定性验证后签发短时 `ExecutionTicket`。Tool/Model/Knowledge/Connector 与 Sandbox 启动边界一律无票拒绝；ticket 使用结果必须返回 receipt，不能由 Runtime 自报完成。
- **Depth**：调用方不理解 macOS 隔离、进程组或 OpenClaw 会话细节，只理解稳定 Broker Interface 和明确失败；Adapter 私有 session 只能是可重建缓存，不能成为恢复事实源。
- **撤权耦合**：每个 `execution_handle` 必须绑定 `grant_id + epoch_snapshot_digest + lease id/generation`。Identity、Authorization 或 Supply-chain owner 的撤权事务必须原子写 epoch bump、`revocation_id`、受影响 lease selector、CancellationToken 与 invalidation outbox。Broker 终止进程树，Secret Broker 吊销步骤凭据，Egress Gateway 关闭或失效既有连接；RevocationAttempt 绑定冻结 SLA/deadline，只有 termination/credential/connection witness 均明确成功才可记为 `revocation_complete`，否则进入 `revocation_incomplete/needs_reconciliation` 并禁止交付、恢复和重试。
- **故障归属**：Broker 负责“是否按快照启动/停止/收集”；Backend 负责隔离机制；Tool 负责领域结果；Kernel 负责权威状态。任何一层证据缺失都不得由上一层猜成成功。

### 4.8 Broker 内部 Ports 与 Adapters

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **AgentRuntimePort**：接受冻结上下文并输出 `StepProposal/ReplanProposal/Observation`。Built-in、OpenClaw、OpenHands 是此 Port 的候选 Adapter；不得持有有效授权、直接访问工具或写权威状态。
- **SandboxProviderPort**：创建隔离单元、启动/观察/强杀进程树、计量资源并销毁。`MacSandboxAdapter` 是 Phase 0A 受控验收候选；`InMemorySandboxAdapter` 仅供测试，所有结果标记非 REAL。
- **ToolExecutionPort**：只凭有效 `ExecutionTicket` 调用已注册 Tool。Python/Office 与 CAE/HPC Adapter 实现该 Port；未知外部副作用必须返回 reconciliation 状态。
- **组合不变量**：Agent Runtime 必须在 Sandbox Provider 所建隔离单元内运行，Tool/Model/Connector 调用必须经过 ticket-gated host callback；不能把 OpenClaw 自带沙箱、macOS sandbox 或 CAE 进程当成同一种实现互相替代。
- **Adapter 合同**：三类 Port 各有独立 conformance suite，Broker 另有组合套件覆盖逐步授权、replan、观察/重连、取消、超时、进程树、越界访问、网络拒绝、stale lease、证据收集和清理；缺能力即拒绝装配，不降级宿主执行。

### 4.9 Tool Registry、Model Gateway、Knowledge 与 Connector

- **状态**：Tool Registry/Model Gateway/部分 Knowledge 为 `IMPLEMENTED-PARTIAL`；统一 egress、权威知识、Connector 治理为 `ACCEPTED-NOT-IMPLEMENTED`。
- **Tool Interface**：保持“先注册、Schema 校验、白名单、再调用”；每次执行还必须校验 `ExecutionTicket` 与 step/tool/input digest，禁止 Runtime 直接调用 adapter。
- **Model Interface**：Agent 只声明 profile；Model Gateway 只接受绑定 step/model/profile/budget 的有效 ticket，resolved model、参数、重试和外联目标进入执行快照与 `model_calls`。
- **Knowledge Interface**：普通检索命中不能冒充权威依据；知识项版本、有效性、精确锚点与冲突必须由权威知识底座提供。见 [ADR-0041](../../adr/ADR-0041-authoritative-knowledge-foundation.md)。
- **Connector Interface**：只开放已批准动作和目标；个人凭据不能自动流入共享项目。

### 4.10 Artifact, Evidence & Delivery

- **状态**：文件 hash 与任务产物为 `IMPLEMENTED-PARTIAL`；完整 Delivery Bundle 为 `ACCEPTED-NOT-IMPLEMENTED`。
- **Module 责任**：唯一登记输入、输出、差异、验证、来源与残余风险；唯一冻结 Delivery Bundle、消费真人授权、提交一次性动作、记录动作级 receipt 与后置验证。Session/Policy/UI 只能调用此 Module，不能另建交付写路径。
- **Interface**：`register_artifact`、`freeze_bundle`、`authorize_bundle`、`commit_once`、`verify_receipt`。
- **不变量**：Bundle 内容摘要、策略、授权主体或待交付动作任一漂移都使授权失效；授权成功不等于外部效果成功，必须有执行 receipt 与后置验证。

### 4.11 Knowledge Authority、FLAi Bench 与共建地图

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`，复用既有 Knowledge/Eval/Stats seams。
- **Knowledge Authority**：逻辑统一、物理联邦，索引技术不赋予权威性。
- **FLAi Bench**：冻结能力发布包，四轨评测，不可抵消门不允许 `failed/invalid/skipped/unknown` 通过。见 [ADR-0042](../../adr/ADR-0042-flai-bench-evaluation-foundation.md)。
- **共建地图**：只读投影，状态来自发布、评测、签发和准备证据，不能手工点绿。见 [ADR-0043](../../adr/ADR-0043-co-building-map-and-evidence-derived-metrics.md)。

### 4.12 Audit Ledger & Read Projections

- **状态**：`task_events/tool_runs/model_calls` 为 `IMPLEMENTED-PARTIAL`；防篡改账本、可靠 outbox 与 WORM 为 `ACCEPTED-NOT-IMPLEMENTED`。
- **Module 责任**：权威写入与审计 outbox 同事务；生成追加式、可校验、可导出的安全证据；为工作台、治理中心和共建地图提供权限过滤后的只读投影。
- **禁止**：保存或展示完整内部思维链；用应用日志替代授权、执行、交付和撤销证据；展示层改写事实状态。

## 5. 关键执行流

### 5.1 不中断自治会话

```text
认证用户提交目标
  → Intent Compiler 生成 TaskGraph + provenance
  → 后台生成 SessionExecutionGrant
  → task-level Policy Decision + effective_callability
      AUTO_EXECUTE       → AdmissionDecision → Queue → claim lease → Broker prepare
                           → StepProposal → step-level Policy Decision → ExecutionTicket
                           → Sandbox/Tool/Model/Knowledge/Connector → receipt → 观察/验证/恢复
      DEFER_TO_DELIVERY  → 暂存待交付动作，自治工作继续
      DENY               → 记录原因；能继续的安全工作继续
  → 聚合产物、差异、验证、未知项与残余风险
  → 冻结 Delivery Bundle
  → 具名真人一次性授权精确 Bundle
  → 执行外部效果并验证 receipt
```

一般用户不在过程中审批命令、文件或工具。真正无法推导且会改变安全边界的事实只形成一次聚合 `blocked`；系统不能通过扩大宿主权限继续。

“能继续的安全工作”按 TaskGraph 依赖闭包判定：只有其全部传递依赖都不包含 `DENY` 或未决 `DEFER_TO_DELIVERY` 的独立节点才可继续。不得换成更弱 Tool、模型、权限、知识 scope、网络目标或宿主路径绕过原决定；被跳过、未覆盖和未决范围必须进入最终交付包/blocked 证据，不能从叙事中消失。

### 5.2 CFD 算例体检首切片

首期只读检查已有 OpenFOAM case：输入进入任务级隔离副本或只读挂载；所有判断定位到文件与字段；权威依据、工程师确认假设、模型建议分栏；不得覆盖原算例或启动求解。目标是验证 Control Kernel、Evidence、Knowledge 和 Sandbox seams，而不是宣称全自主 CFD。

### 5.3 能力发布

```text
Agent/Prompt/Workflow/Schema/Model/Tool/Sandbox/Policy/Knowledge/Eval
  → freeze Capability Release Package
  → FLAi Bench 四轨运行
  → 不可抵消门
  → 具名人工评审/晋级
  → 发布范围与限制
  → 共建地图只读投影
```

LLM-as-Judge 只能提供诊断，不能晋级、签发或把未知门写成通过。

## 6. 故障归属矩阵

| 故障 | 首要归属 Module | 必须产生的事实 | 禁止行为 |
|---|---|---|---|
| 身份/对象越权 | Authorization | deny reason + actor/resource/policy ref | 仅靠前端隐藏；返回对象存在性的敏感细节 |
| 意图无法编译 | Intent Compiler | 聚合 missing/conflict/provenance | 循环表单；LLM 静默猜工程事实 |
| 队列超预算 | Queue/Budget | admission decision + budget snapshot | 接受后无限排队；用 500 掩盖容量事实 |
| worker 丢失 | Lease/Recovery | lease expiry + reconciliation decision | 无 lease 重跑未知副作用 |
| Sandbox 不可用 | Broker/Backend | capability failure witness | 自动降级 host exec |
| 工具超时 | Backend + Tool | termination witness + tool failure | 线程标失败后让子进程继续写 |
| 模型不可用 | Model Gateway/Egress | resolved profile、attempt、失败原因 | 静默换模型并沿用旧 provenance |
| 审计写入失败 | Audit Outbox | outbox/ledger health | 高风险写继续但不留证 |
| 交付提交漂移 | Delivery | CAS failure + stale bundle | 把旧授权应用到新产物/参数 |
| 评测晚写 | Eval/Repository | terminal CAS reject | `error/failed → completed` 翻绿 |

## 7. Locality 与演进纪律

1. **控制语义只在 Kernel**：身份、授权、任务状态、队列、审计和交付不散落到 Agent workflow、Broker 内部 Port 或 Adapter。
2. **业务能力只在 Package**：新增 Agent/Tool 优先新增包，不做顺手内核分支；公共合同真实缺口才进入 Kernel 设计。
3. **Adapter 隔离技术差异**：OpenClaw、OpenHands、macOS Sandbox、未来 Windows 或 HPC 的差异收敛在 Adapter；上层不出现其私有 session/state 名称。
4. **现有 seam 增量演进**：复用 SQLite、Repository、Task/Event、Registry、Gateway、Stats 和 Eval；不创建第二数据库、第二任务中心、第二评测平台或第二 KPI 平台。
5. **契约先行**：公开 Schema、状态机、持久格式和 Interface 变更必须另获实现授权，并先有 invalid-first fixture、迁移/回滚和 tamper witness。

## 8. 部署拓扑

### 8.1 macOS 首发目标

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- 工作台/API、控制内核与执行平面逻辑分离；即便首期同机部署，也不能共享不受控执行权限。
- `MacSandboxAdapter` 是 Phase 0A 受控验收候选，不是正式生产声明；必须在选定 macOS/Apple Silicon 基线上验证睡眠唤醒、异常退出、进程树强杀、网络拒绝、资源限制、升级回退和断网安装。
- Windows Adapter 明确 `OUT-OF-SCOPE`，不要求本阶段同步 `.ps1`；公共 Broker Interface 与 `SandboxProviderPort` 不得把 macOS 私有语义泄漏给 Kernel。后续正式内网平台目标另经具名决策，不由 Phase 0A 自动外推。

### 8.2 规模演进

Phase 0A 面向 5–8 名具名技术验收人员，只用 canonical/synthetic 数据验证机制；Phase 0B 才向 20–30 名业务用户开放至少一条真实工具和真实数据工作流。多节点 HA、跨部门 execution cell 和 Windows 适配为 `OUT-OF-SCOPE`，不得用架构图暗示已具备。

## 9. 明确不做

- 不以 OpenClaw/OpenHands 替换 FLAi Control Kernel。
- 不引入 Next.js、PostgreSQL、Redis、Celery、ORM 或新的编排平台。
- 不建立双任务状态、双审计账本、双评测平台或第二控制面。
- 不让 LLM 进入授权、工程判决、评测晋级、路线图签发或最终交付签发链。
- 不保存 chain-of-thought，不用自由文本“推理轨迹”冒充可审计证据。
- 不把工作目录、线程 timeout 或 subprocess 本身称为真正 Sandbox。
- 不用逐命令批准或长表单把后台策略求解责任转嫁给用户。

## 10. 架构评审与 MVP 定义的产出门

下列不是“开始架构评审前就已完成”的循环前提，而是 R0 架构评审与 R1 MVP 定义必须产出的机械证据。只读现状勘察和评审可以立即开始；这些门全部闭合后才可授权原型或运行时实现。

1. 三个黄金工作流的 MVP 范围、非目标和验收 fixture 版本化冻结。
2. `ActorContext/Resource/Action`、TaskGraph、SessionExecutionGrant、PolicyDecision/ExecutionTicket、Broker Interface、三类执行 Port 与 Delivery Bundle 合同通过架构评审。
3. 统一授权 P0 负例先红，覆盖 BOLA/IDOR、治理写入口、附件旁路和 commit-time 撤权。
4. Sandbox threat model 与一个低副作用 Tool 的 Broker 迁移计划获批；能强杀且无 host fallback。
5. Queue lane/budget/lease、terminal CAS、side-effect-aware recovery 和 audit outbox 不变量冻结。
6. 能力发布包、FLAi Bench 四轨 envelope 和不可抵消门冻结。
7. macOS 目标基线、身份源、审计留存/WORM、出站域、离线签名和部署规模由具名责任人裁决。
8. 只有上述 R0/R1 产出门完成后，才进入“原型 → 经明确授权的实现”；本文件本身不等于完成任何门。

## 11. 关联依据

- [系统宪法](../../00_FLAi-OS_Constitution.md)
- [总体架构](../../01_Overall_Architecture.md)
- [生产就绪纲领](../../PRODUCTION-READINESS-PROGRAM.md)
- [OpenClaw / WorkBuddy / 安全治理研究](../../research/2026-07-23-openclaw-workbuddy-security-governance-study.md)
- [OpenClaw Runtime 安全参考](../../research/openclaw-runtime-security-reference-2026-07-23.md)
- [ADR-0033：控制内核与执行后端](../../adr/ADR-0033-flai-control-kernel-and-replaceable-execution-backends.md)
- [ADR-0034：自治会话与末端授权](../../adr/ADR-0034-uninterrupted-session-and-final-delivery-authorization.md)
- [ADR-0035：两级试点](../../adr/ADR-0035-two-stage-controlled-and-business-pilots.md)
- [ADR-0036：工作台优先与角色化治理面](../../adr/ADR-0036-workbench-first-and-role-specific-governance-surfaces.md)
- [ADR-0037：Phase 0A 三条黄金工作流](../../adr/ADR-0037-phase-0a-three-golden-workflows.md)
- [ADR-0038：智能办公首切片](../../adr/ADR-0038-office-assistant-first-tracer-bullet.md)
- [ADR-0039：CFD 助手首切片](../../adr/ADR-0039-cfd-assistant-first-tracer-bullet.md)
- [ADR-0040：会议行动首切片](../../adr/ADR-0040-meeting-assistant-first-tracer-bullet.md)
- [ADR-0041：权威知识底座](../../adr/ADR-0041-authoritative-knowledge-foundation.md)
- [ADR-0042：FLAi Bench](../../adr/ADR-0042-flai-bench-evaluation-foundation.md)
- [ADR-0043：共建地图与证据指标](../../adr/ADR-0043-co-building-map-and-evidence-derived-metrics.md)
- [ADR-0044：需求共创闭环](../../adr/ADR-0044-demand-co-creation-loop.md)
- [ADR-0045：需求决策权](../../adr/ADR-0045-demand-decision-rights-and-roadmap-signoff.md)

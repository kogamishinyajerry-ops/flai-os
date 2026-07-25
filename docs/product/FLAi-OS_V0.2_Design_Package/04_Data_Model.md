# FLAi-OS V0.2 逻辑数据模型

> 文档性质：V0.2 逻辑模型与不变量设计，不是数据库迁移脚本或已实现 Schema。
> 当前持久化契约仍以仓库代码、`contracts/`、[Task/Event 标准](../../05_Task_Event_Standard.md)
> 和已接受 ADR 为准。本文中的目标实体不得被解释为“数据库已经存在这些表”。

## 1. 状态标签

| 标签 | 本文含义 |
|---|---|
| `IMPLEMENTED-VERIFIED` | 当前精确范围、版本与环境有可复跑机械证据，绑定命令、结果引用和日期；不等于生产就绪 |
| `IMPLEMENTED-PARTIAL` | 已有表或仓储 seam，但不满足完整目标语义 |
| `ACCEPTED-NOT-IMPLEMENTED` | 目标逻辑已接受，本阶段未授权 Schema/API 实现 |
| `DECLARED-NOT-VERIFIED` | 文档/配置存在，缺当前数据或目标机验证 |
| `OUT-OF-SCOPE` | 本阶段不建模或不落库 |

## 2. 建模原则

1. **一项事实只有一个权威 owner**：任务、执行、评测、知识、需求和路线图各自有明确 Module，不靠跨表复制状态“保持大致同步”。
2. **标识与展示分离**：授权、关联与审计使用不可变 ID；姓名、标题和显示名不是权威键。
3. **不可变优先**：输入快照、策略摘要、执行摘要、知识版本、能力发布包、交付包和审计事件一经冻结不原位修改。
4. **追加式修正**：事件、评审、需求处理、路线图变更和知识撤销以新记录表达；禁止覆盖历史。
5. **CAS-on-NULL / CAS-on-version**：首次写入的分级、摘要、授权消费、终态和版本签发必须使用条件更新；未命中就是冲突，不猜。
6. **严格布尔门**：安全、诚实性、依据链、人工签发等门只接受明确 `true` 或 `false`；缺失、`null`、未知字符串都不能通过。
7. **unknown ≠ null ≠ zero**：未知事实、字段不适用和数值为零必须可区分。
8. **分类污点单调不降级**：派生数据至少继承所有输入中最严格的有效分级；摘要、引用、导出或模型处理不能自动降级。
9. **状态与审计同事务**：强治理写入与 audit outbox 原子提交；业务状态已变但审计证据不存在属于失败。
10. **SQLite 继续是 SSOT**：V0.2 不引入 PostgreSQL、ORM、Redis 或 Celery；演进通过仓储层、迁移和窄 Interface 完成。

## 3. 当前事实层

| 现有事实 | 状态 | V0.2 复用方式 | 当前不足 |
|---|---|---|---|
| `tasks` | `IMPLEMENTED-PARTIAL` | 继续作为任务实例和状态事实 | 尚无 Canonical TaskGraph、Grant、统一 lane/lease、Delivery Bundle |
| `task_events` | `IMPLEMENTED-PARTIAL` | 继续作为任务运行事件事实 | 不是不可抗抵赖账本，部分状态/事件原子性仍需收口 |
| `tool_runs` | `IMPLEMENTED-PARTIAL` | 工具调用事实与资源统计来源 | 尚未统一绑定 Broker handle、policy/plan digest、termination witness |
| `model_calls` | `IMPLEMENTED-PARTIAL` | resolved model、Token、调用状态事实 | 尚未统一绑定 egress decision、SecretRef identity 和尝试序列 |
| `files` / task output | `IMPLEMENTED-PARTIAL` | 产物注册与 hash seam | 对象授权、附件引用门、Bundle 冻结与全链 classification 未闭合 |
| `samples` / `feedback` | `IMPLEMENTED-PARTIAL` | 失败回流、人工采用和需求来源 | feedback 当前任务绑定、字段有限，不能承担完整需求池 |
| Knowledge scope / BM25 index | `IMPLEMENTED-PARTIAL` | 作为检索 Adapter 和 scope seam | scope 不是权威性；无 authority class/effective lifecycle/version snapshot |
| eval cases / runs / snapshots / promotions | `IMPLEMENTED-PARTIAL` | 扩展为 FLAi Bench 的事实源 | Snapshot 尚未覆盖完整能力发布包，终态晚写假绿须封闭 |
| users / sessions / coarse roles | `IMPLEMENTED-PARTIAL` | 当前本地认证与会话事实；未来可由 LDAP/OIDC/本地身份 Adapter 向统一 Identity Interface 提供主体 | 不等于对象级、项目级和职责级授权模型 |

## 4. 逻辑实体关系

```text
Actor ──member/delegated──> Project / ResponsibilityScope
  │                              │
  └──submits──> Conversation ──opens──> AutonomousSession
                                      │
RequestEnvelope ──compiled_to──> CanonicalTaskGraph
                                      │
                           SessionExecutionGrant
                                      │
                    PolicyDecision ──constrains──> AdmissionDecision ──admits──> QueueLease
                                                                        │
                                                                  ExecutionRun
                                                                        │
                                   StepProposal ──checked_by──> PolicyDecision(step)
                                                                        │
                                                                 ExecutionTicket
                                                    ┌───────────────────┼───────────────────┐
                                                    ▼                   ▼                   ▼
                                                 ToolRun            ModelCall            Artifact
                                                    │                   │                   │
                                                    └──────────── EvidenceReference ────────┘
                                      │
TaskKnowledgeSnapshot ────────────────┤
                                      ▼
                                DeliveryBundle
                                      │
                          DeliveryAuthorization
                                     │
                               DeliveryAttempt
                                      │
                                ActionReceipt

CapabilityReleasePackage ──evaluated_by──> BenchRun
BenchRun ──supports──> QualificationDecision ──authorizes──> DeploymentBinding
DemandSignal ──processed_by──> CurationEvent ──forms──> DemandCandidate
DemandCandidate ──reviewed_by──> DomainReview / SecurityReview
DomainReview / SecurityReview ──supports──> RoadmapDecision / HumanSignoff
RoadmapDecision ──accepted_as──> RoadmapCommitment ──delivered_as──> CapabilityReleasePackage
所有强治理变化 ──atomic outbox──> AuditLedgerEvent ──projects_to──> Read Models
```

## 5. 身份、项目与资源授权

### 5.1 Actor

- **状态**：当前认证 `IMPLEMENTED-PARTIAL`；目标字段 `ACCEPTED-NOT-IMPLEMENTED`。
- **最小字段**：`actor_id`、`identity_provider`、`subject_id`、`status`、`authenticated_at`、`credential_epoch`。
- **不变量**：`display_name` 只展示；Identity Module 是 `credential_epoch` 的唯一 owner，并以 CAS 提升 epoch、同事务写 invalidation outbox。停用、会话撤销或 epoch 漂移不仅在提交阶段 fail-closed，还必须停止新 claim，并终止绑定旧快照的活动执行。
- **非目标**：本文不拍板 AD/LDAP/OIDC Adapter、MFA 或离线账户策略。

### 5.2 Project / OrganizationalScope

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **事实 owner**：Control Kernel 内的 Project Directory Module；外部项目系统只能作为 Adapter 同步来源，不能让任意业务对象自报 `project_id`。
- **最小字段**：`project_id`、`department_id`、`data_domain_ids`、`owner_actor_id`、`status`、`classification_ceiling`、`source_ref`、`version`。
- **不变量**：project 不是唯一组织边界；Authorization 同时评估 tenant/组织、部门、数据域、项目和对象 predicate，未知层级 fail-closed。

### 5.3 ProjectMembership / ResponsibilityDelegation

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **职责**：表达某主体在项目、部门、数据域、Agent 或治理动作上的有限职责，而不是把全部能力压进全局 `admin`。
- **字段**：`delegation_id`、`actor_id`、`responsibility_code`、`scope_type`、`scope_id`、`valid_from`、`valid_until`、`granted_by`、`revoked_at`、`version`。
- **不变量**：授权必须有作用域和有效期；撤销追加记录并提升版本；策略提交时重读当前版本。

### 5.4 ResourceEnvelope

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **字段**：`resource_type`、`resource_id`、`owner_actor_id`、`tenant/department/data_domain/project` scope、`policy_predicates`、`data_classification`、`visibility`、`version`、`status`。
- **用途**：所有持久资源共用的授权输入，包括 request、AutonomousSession、TaskGraph、task、conversation、file/Artifact、feedback、Grant、QueueLease、ExecutionRun、DeliveryBundle/Authorization/Attempt/Receipt、eval/Bench、sample、typed promotion/qualification、CapabilityRelease、DeploymentBinding、knowledge、demand、roadmap 和 audit view；不强迫所有对象继承同一物理表。
- **机械门**：上述每类资源都必须有跨主体、跨项目/数据域、已知 ID 深链、list/search/export/aggregate 与撤权后的 invalid-first fixture；缺 envelope 或 predicate 的资源默认不可读写。

### 5.5 AuthorizationRevocationState / ExecutionEpochSnapshot

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **事实 owner**：Identity Module 独占 actor/session 的 `credential_epoch`；Authorization Module 独占每个 `revocation_partition_type + revocation_partition_ref` 的 `authorization_epoch`；Supply-chain Module 独占 trust domain 的 `trust_policy_epoch + trust_policy_digest`。Grant、Ticket、Lease 或 Adapter 均不得提升这些值。
- **状态字段**：`partition_type/ref`、当前 epoch/digest、`version`、`updated_by`、`updated_at`、`reason_code`。一次执行冻结 `ExecutionEpochSnapshot`，显式列出 actor credential epoch、所有适用 authorization partition/epoch，以及 trust-policy epoch/digest。
- **撤权事务**：对应 owner 以 CAS 提升 epoch，并在同一事务写 `revocation_id`、invalidation outbox、受影响 lease selector/快照与 CancellationToken；worker/Broker 只消费事件，不自行猜测撤权范围。
- **不变量**：Grant、ExecutionTicket、QueueLease、ExecutionRun/execution handle 都携带同一 epoch snapshot 或其不可碰撞 digest；任一当前值不等、快照缺失、多头或无法解析均 `unknown → deny`。旧 snapshot 永不原位改写。

## 6. 请求、会话与任务图

### 6.1 RequestEnvelope

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **不可变字段**：认证主体快照、原始用户文本摘要、会话版本、附件引用与 hash/owner/classification、项目策略版本、提交时间、actor-scoped `idempotency_key`、payload digest 与重放有效期。
- **不变量**：同 actor/scope/key 只接受相同 payload digest，并返回已记录结果；digest 不同即冲突。附件不是裸 file ID；以 `open-no-follow` 打开的同一已验证句柄完成 owner/project/classification/capability、祖先与 hash 校验后直接交给解析器，禁止校验后按路径重开。

### 6.2 AutonomousSession

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **字段**：`session_id`、`conversation_id`、`actor_id`、`project_id`、`request_digest`、`status`、`opened_at`、`expires_at`、`active_run_id`、`version`。
- **状态建议**：`open | executing | blocked | delivery_ready | delivery_committed | failed | cancelled | expired`。
- **不变量**：同一会话最多一个 active run；新用户输入不会隐式修改已冻结 run，必须形成新 request/session version。

### 6.3 CanonicalTaskGraph / TaskNode / DependencyEdge

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **TaskGraph 不可变字段**：`graph_id`、`graph_version`、`request_digest`、`compiler_version`、`policy_context_digest`、`graph_digest`。
- **TaskNode 字段**：`node_id`、Agent/Tool/Schema 版本、typed input、source refs、effect class、预算、验收条件。
- **Edge 字段**：有限 `dependency_type`、上游输出引用、转换合同。
- **不变量**：图通过确定性 Schema 校验后才冻结；依赖无环；所有必填字段有来源；LLM 推断与权威事实分开；图变更产生新版本和 digest。

### 6.4 Task

- **状态**：`IMPLEMENTED-PARTIAL`。
- **当前语义**：沿用 [Task/Event 标准](../../05_Task_Event_Standard.md) 的状态事实，任何状态变化必须有事件见证。
- **V0.2 增量引用**：`graph_id/node_id`、`session_id`、`origin`、`project_id`、`grant_digest`、`policy_digest`、`lease_id`、`effect_class`、`data_classification`、`terminal_version`。
- **不变量**：
  - `data_classification` 使用 CAS-on-NULL 首写不可变；
  - 终态使用 CAS-on-expected-state/version；
  - `failed/error/cancelled` 不得被晚到 writer 改回 `completed`；
  - `completed` 不表示工程签发或外部效果成功。

## 7. 授权、策略与交付

### 7.1 SessionExecutionGrant

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **不可变字段**：`grant_id`、`session_id`、`actor/project` 快照、请求/输入 digest、Agent Package digest、工作空间范围、能力集合、目标类别、网络策略、资源预算、有效期、`credential_epoch`、`authorization_epoch_snapshot[]`、`trust_policy_epoch/digest`、`epoch_snapshot_digest`、`grant_digest`。
- **不变量**：Grant 由后台推导，不要求用户填写；不授予不可逆外部效果。Grant 只冻结 owner Module 的 epoch 快照，永不被“提升”。撤权或策略漂移由对应 owner CAS 提升当前 epoch 并写 invalidation outbox，使旧 Grant 立即失效、停止新 claim，并把所有绑定旧快照的活动执行送入强杀与凭据/连接吊销；不能只让“后续步骤拒绝”。

### 7.2 PolicyDecision / ExecutionTicket

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **Decision 字段**：`decision_id`、`actor_id`、`action`、`resource_ref`、`canonical_step_digest`、`policy_version/digest`、`epoch_snapshot_digest`、`result`、`reason_codes[]`、`decided_at`。
- **Ticket 不可变字段**：`ticket_id`、`decision_id`、`canonical_step_digest`、`grant_id/digest`、`credential_epoch`、`authorization_epoch_snapshot[]`、`trust_policy_epoch/digest`、`lease_id/generation`、能力/目标/input digest、预算、`issued_at/expires_at`、nonce 与 ticket digest。
- **结果枚举**：`DENY | DEFER_TO_DELIVERY | AUTO_EXECUTE`。
- **不变量**：有限枚举；不得以自由文本理由替代结果；下层策略不能把 DENY 变为允许；提交前重新判定。Ticket 只为已领取当前 lease 的具体步骤签发；epoch、lease、step、target 或时效任一不匹配即无票处理并拒绝。

### 7.3 PendingDeliveryAction

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **字段**：规范化 action、目标、参数摘要、影响范围、回滚/补偿说明、所需职责、准备证据。
- **不变量**：不得在 DeliveryAuthorization 之前执行；参数或目标变化产生新 action digest。

### 7.4 DeliveryBundle

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **不可变字段**：`bundle_id/version`、`session_id`、输入/图/策略摘要、产物清单与 hash、diff、验证证据、权威依据快照、假设与未知项、残余风险、待交付动作、`bundle_digest`、`frozen_at`。
- **不变量**：冻结后不可修改；任何内容变化新建版本；“准备完成”不等于“已签发”或“已提交”。

### 7.5 DeliveryAuthorization / DeliveryAttempt / ActionReceipt

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **Authorization 字段**：`authorization_id`、`bundle_digest`、具名 `actor_id`、职责/作用域、决定、时间、过期时间、单次消费状态。
- **Attempt 字段**：`attempt_id`、`authorization_id`、actor/scope-scoped request idempotency key、开始/结束时间、overall state、每个 action 的 ordinal/digest、稳定 `effect_idempotency_key` 与当前状态。
- **ActionReceipt 字段**：`attempt_id`、action ordinal/digest、执行者/Adapter、开始结束时间、结果、外部 reference、后置验证、错误、幂等回放与 reconciliation 状态。
- **事务与唯一性**：消费 Authorization、创建唯一 Attempt（`UNIQUE(authorization_id)`）及全部 ActionIntent 必须同一 SQLite 事务完成；ActionIntent 以 `(attempt_id, ordinal, action_digest)` 唯一，effect key 在目标 Adapter 的副作用域内稳定且跨重试/重新授权保持一致。同 actor/scope/request key 只返回原 Attempt；不同 payload digest 冲突。
- **动作状态机**：每个 action 以 CAS 执行 `prepared → executing → succeeded|failed|effect_unknown`；`effect_unknown` 只能经外部查询/receipt 对账进入 `succeeded|failed|needs_reconciliation`。在外部效果成功后、receipt 落库前崩溃或 stale `executing` 时一律进入 `effect_unknown`，不得盲重放；重新授权不能生成新的 effect key 绕过未知效果。
- **不变量**：只有真人可授权；CAS 单次消费；审批人无权、Bundle 漂移或过期均拒绝；授权不能冒充 receipt。多动作部分成功必须保持 `partially_applied/needs_reconciliation` 并逐动作展示，只有全部动作及后置验证成功才能形成整体“已交付”。

## 8. 队列、租约、执行与恢复

### 8.1 AdmissionDecision / LaneBudget

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **Lane 维度**：project、user、session、Agent、Tool、provider/egress；实际组合在实现 ADR 中冻结。
- **Budget 字段**：`max_queued`、`max_running`、CPU/内存/墙钟/输出/外部调用预算、版本和有效期。
- **不变量**：接纳前检查；`unknown` 预算不等于无限；拒绝或延迟有稳定 reason code；不以 API 接收成功冒充已获执行容量。

### 8.2 QueueLease

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **字段**：`lease_id`、`task_id/run_id`、`owner_worker_id`、`generation`、`grant_id`、`credential_epoch`、`authorization_epoch_snapshot[]`、`trust_policy_epoch/digest`、`epoch_snapshot_digest`、`execution_handle_id`、`acquired_at`、`heartbeat_at`、`expires_at`、`lease_version`、`revocation_state`。
- **不变量**：claim 与状态变化同事务；心跳只可由匹配 owner/generation 更新；finish/cancel 必须匹配 active lease；过期后旧 writer 永久失去终态写权。

### 8.3 CancellationToken / RevocationAttempt / RevocationWitness

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **Cancellation 字段**：请求人、原因、请求时间、目标 lease/generation 与 epoch snapshot、被 Broker 观察时间。
- **Attempt 字段**：`revocation_id/attempt_id`、撤权 commit 时间、目标新旧 epoch、受影响 lease、`sla_policy_digest`、deadline、状态与 reconciliation owner。
- **Witness 字段**：分别记录 `process_tree_termination`、`credential_invalidation`、`connection_invalidation` 的 `succeeded|failed|unknown`、开始/完成时间、执行者、目标摘要、最后可能副作用时间和 evidence digest；普通 cancel 仍产生 termination witness。
- **不变量**：`cancel requested` 不等于 `terminated`；只有三类撤权 witness 都在冻结 SLA 内明确成功，Attempt 才可 CAS 为 `revocation_complete`。超时、缺失、unknown 或 target epoch 不匹配统一为 `revocation_incomplete/needs_reconciliation`，任务不得声明安全停止、交付、恢复或重试。

### 8.4 ExecutionRun

- **状态**：现有 task/tool 执行为 `IMPLEMENTED-PARTIAL`；统一实体 `ACCEPTED-NOT-IMPLEMENTED`。
- **字段**：`execution_id`、`plan/policy/grant digest`、`credential_epoch`、`authorization_epoch_snapshot[]`、`trust_policy_epoch/digest`、`epoch_snapshot_digest`、lease/generation、Backend/镜像/工具摘要、workspace、网络策略、SecretRef identities、资源上限、running/termination/revocation witness、result digest。
- **不变量**：Sandbox 能力无法证明时不创建 REAL execution；Mock/Test backend 明确标记；Backend 私有状态不成为 Control Kernel 权威状态。

### 8.5 RecoveryDecision

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **结果**：`retry_safe | needs_reconciliation | terminal_fail | cancelled`。
- **不变量**：只有无副作用或可证明幂等且 receipt 可核对的步骤允许自动重试；未知/外部副作用必须 `needs_reconciliation`，不得在新 lease 下盲重放。

## 9. 运行证据与产物

### 9.1 ToolRun / ModelCall

- **状态**：`IMPLEMENTED-PARTIAL`。
- **V0.2 增量**：绑定 `execution_id`、attempt、canonical step、grant/policy digest、resolved Adapter/模型、egress decision、资源统计和证据 refs。
- **不变量**：错误也必须落事实；日志不得记录秘密；模型 fallback 改变 provenance，不能静默沿用旧能力评测。

### 9.2 Artifact

- **状态**：`IMPLEMENTED-PARTIAL`。
- **字段**：`artifact_id`、`task/execution`、类型、内容摘要、大小、创建者、来源 refs、classification、状态、存储引用。
- **状态建议**：`workspace_draft | delivery_candidate | authorized_release | revoked | quarantined`。
- **不变量**：原始输入不被覆盖；输出只写任务目录；正式资产必须经精确 Bundle/Receipt；文件存在不等于内容可信。

### 9.3 EvidenceReference

- **状态**：局部 refs `IMPLEMENTED-PARTIAL`；统一合同 `ACCEPTED-NOT-IMPLEMENTED`。
- **字段**：`ref_type`、`ref_id/version`、content digest、精确 anchor、captured_at、classification。
- **不变量**：ref 必须可解析到已存在事实；无来源内容不能作为工程或组织依据；不存在的 ref 使承载记录 invalid。

## 10. 权威知识模型

### 10.1 KnowledgeAuthority / KnowledgeItem / KnowledgeVersion

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **Authority 字段**：权威类别、issuer、owner、批准要求、适用域、状态。
- **Item 字段**：稳定 `knowledge_id`、标题、分类、范围、当前版本引用。
- **Version 不可变字段**：版本、内容摘要、发布/批准证据、生效/失效时间、supersedes、存储引用、精确锚点策略、classification。
- **生命周期语义**：`draft | in_review | published | future_effective | effective | expired | superseded | revoked`。`published` 只说明发布动作成立；只有任务时刻处于 `effective` 且适用范围匹配的版本，才能支撑当前组织要求或工程依据。
- **不变量**：只有具名授权人员可以签发发布/撤销；受信源系统只能附加 `source_system_attestation`（上游签发身份、来源版本、内容 digest 与验证结果），不能成为本平台 `human_signer`。普通上传、会议草稿、AI 输出不能自动晋升；过期/撤销内容只作历史证据。

### 10.2 ReleaseKnowledgeBinding / TaskKnowledgeSnapshot / Citation

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **ReleaseKnowledgeBinding**：运行前冻结进能力发布包的知识合同，包含允许的 authority/scope、必需/禁止集合、版本选择策略、目录根摘要、检索/锚点策略和外部活态模式；它参与 release digest，但不包含 actor、任务时刻或实际命中。
- **TaskKnowledgeSnapshot**：运行时按 Binding、actor、task、`as_of` 与当前授权解析出的实际知识版本、索引版本、使用锚点、缺失/冲突和整体 digest；它绑定 task/Bench run，但不反向改变 release 身份。
- **Citation**：知识版本、精确位置、任务时有效状态和引用语义。
- **不变量**：Task Snapshot 必须机械证明符合 Release Binding；索引命中不决定权威；缺失/冲突返回“无法确认”；知识密级传播到任务、模型调用、产物与审计。

### 10.3 EngineeringClaimLedger

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **用途**：CFD 等工作流把每个需求、边界条件、模型选择和建议标为 `authoritative_basis | engineer_confirmed_assumption | model_suggestion | unresolved`。
- **不变量**：模型建议不能改写成既有要求；未决事实可以聚合进 Delivery Bundle，但依赖它的不可逆动作不得执行。

## 11. 能力发布与 FLAi Bench

### 11.1 CapabilityReleasePackage、QualificationDecision 与 DeploymentBinding

- **状态**：当前 eval snapshot `IMPLEMENTED-PARTIAL`；完整对象 `ACCEPTED-NOT-IMPLEMENTED`。
- **不可变 Manifest**：Agent、Prompt、Workflow、Schema、resolved model/profile、Tool/Adapter、Sandbox/镜像、权限/出站策略、ReleaseKnowledgeBinding、Eval Suite/Rubric 及各自摘要；运行时 TaskKnowledgeSnapshot 不参与 release 身份。
- **Package lifecycle**：`assembling | frozen | superseded | retired`，只回答包是否仍可被引用；冻结后不可改字节，评测失败不回写包内容。
- **QualificationDecision**：追加式记录 `target_class=phase_0a|phase_0b|released`、`outcome=eligible|ineligible|expired`、release/bench digest、范围、限制、签发主体与证据；评测运行状态不塞进 package lifecycle。决定分区键固定为 `release_digest + target_class + qualification_scope_digest`；每个分区使用单调 `decision_epoch`、`supersedes_decision_id` 和 head CAS，任何多头、断链、旧 epoch 或不可判定 head 都归为 `unknown → deny`。只有唯一 current head 为未过期 `eligible` 才满足资格条件。
- **DeploymentBinding**：把精确 release digest 暴露给具名人群/项目/数据域/动作/时间窗，字段含 `deployment_class` 与 `status=draft|active|suspended|revoked|expired`；Phase 0A、Phase 0B 和正式服务是绑定类别，不是包状态。
- **不变量**：任一关键成分变化形成新 release digest；外部活态必须显式列出；不可重建且影响准入时不得形成 eligible decision。包 lifecycle、qualification、deployment binding、现有 `agent.status` 与 L0–L3 各有唯一 owner，禁止互相自动推导。
- **唯一 effective_callability**：Kernel 只在 package=`frozen`、Agent 非 `disabled` 且对主体可见、目标 class 有当前明确 eligible decision、精确 release 有匹配且 active 的 DeploymentBinding、授权与 Session Grant 有效、依赖健康并可签发 ExecutionTicket 时返回 true；`suspended/revoked/expired/unknown` 任一命中都硬否决。L0–L3 仅为成熟度信息，不授予调用权。

### 11.2 BenchSuite / BenchCase / BenchRun

- **状态**：现有 Eval `IMPLEMENTED-PARTIAL`；四轨合同 `ACCEPTED-NOT-IMPLEMENTED`。
- **轨道**：`deterministic_regression | engineering_quality | safety_governance | efficiency`。
- **Case 生命周期**：`draft | approved | retired`；真实/synthetic 与 classification 明确。
- **Run 结果**：逐 case `passed | failed | invalid | skipped | unknown`，加环境、任务和证据 refs；沿用现有 `passed` 拼写，若未来改枚举必须有显式 Schema 迁移/兼容 Adapter。
- **不可抵消门**：安全、诚实性、依据链和关键回归任一非明确 `passed`，release 不能晋级；没有单一加权总分。

### 11.3 HumanReview / Typed Qualification and Promotion

- **状态**：`IMPLEMENTED-PARTIAL`。
- **不变量**：评审主体来自认证身份；LLM judge 只作建议；`honesty`、`traceability` 严格布尔。`AgentLifecyclePromotion` 只改变现有 Agent 生命周期/成熟度事实；`CapabilityQualificationDecision` 与 `DeploymentSignoff` 分别绑定精确 release/bench digest 和暴露范围。三类 typed command 带 `target_type + target_digest`，不得自动互推，且终态 CAS 防止晚写翻绿。

## 12. 需求共创、路线图与指标

### 12.1 DemandSignal / DemandEvent / Candidate

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **Signal 不可变字段**：原始文字、提出者、时间、来源类型、关联任务/文件/证据、classification、公开姓名偏好。
- **Event**：补充、合并、拆分、分类、脱敏、状态变化、理由和操作者，全部追加式。
- **不变量**：合并不删除来源；AI 摘要与原文分开；“我也遇到”是独立信号而非自动优先级。

### 12.2 RoadmapVersion / RoadmapCommitment / Signoff

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **不变量**：需求池、路线图承诺和工程 Issue 是三层事实；只有具名路线图负责人可签发版本；领域/安全门缺失或 false 时不能采纳；交付负责人不能以合并代码自证需求已解决。

### 12.3 MetricDefinition / MetricObservation

- **状态**：当前 stats `IMPLEMENTED-PARTIAL`；证据化指标合同 `ACCEPTED-NOT-IMPLEMENTED`。
- **Definition**：`definition_version`、事实源、窗口、分子/分母或公式、排除规则、隐私阈值、价格表/节时基线引用。
- **Observation**：`since/until`、`sample_count`、numerator/denominator、value/range、coverage、quality flags、evidence refs。
- **不变量**：Token 只表示资源；无价格表不算成本；无基线不报节时；eval-origin 不污染真实用户采纳；共建地图不能手工改值。

## 13. 数据分级与传播

### 13.1 当前分级

`internal | sensitive` 当前已有执行语义，状态为 `IMPLEMENTED-PARTIAL`。在组织正式密级、授权矩阵和改级流程裁决前，不增加只有名称没有行为的更多枚举。

### 13.2 派生规则

```text
effective_classification = max(
  request.classification,
  attachment.classification,
  task_knowledge_snapshot.classification,
  tool_output_classification,
  connector_response_classification,
  explicit_policy_floor
)
```

- 计算结果在执行产生内容前 CAS-on-NULL 写入任务级事实。
- 所有 file/sample/event/tool/model/audit 派生内容继承，不允许摘要降级。
- 存量未知或 Adapter/Tool 无法识别时 fail-closed，不能因为“当前 registry 不认识”判 internal。
- 降级只能由具名治理动作产生新版本和证据，不原位覆盖历史分类。

## 14. 事务与 CAS 不变量

| 写入 | 条件 | 同事务内容 | 失败语义 |
|---|---|---|---|
| 首次任务分级 | `classification IS NULL` | 分级 + 必要派生子行一致化 | 读取既有持久值，不覆盖 |
| 队列 claim | expected state + 无 active lease | 状态 + lease + event/outbox | 未命中即未获得执行权 |
| lease heartbeat | owner + generation + version 匹配 | heartbeat/version | 旧 worker 失权 |
| terminal finish | active lease + expected state/version | terminal state + result digest + event/outbox | 晚 writer 被拒，不能翻绿 |
| Delivery commit start | authorization 未消费 + digest/actor/policy 有效 + 无既有 Attempt | 消费 authorization + 建立唯一 Attempt + 全部 ActionIntent + outbox | 返回既有 Attempt 或拒绝冲突；不存在只消费授权的独立路径 |
| ActionIntent claim/finish | expected action state/version + effect key 匹配 | action state + receipt/outbox | 边界崩溃转 `effect_unknown`，未经对账不重放 |
| epoch 撤权 | expected owner/version/epoch | epoch bump + revocation attempt + affected-lease selector + cancel/invalidation outbox | 竞态/缺 witness 为 incomplete，不宣称撤权完成 |
| 路线图签发 | expected version + 所有门 `is True` | 新版本 + signoff + event/outbox | 缺门/竞态不采纳 |
| Knowledge 发布/撤销 | expected lifecycle/version | 新 immutable version/status event | 不原位修改 |
| Typed qualification / promotion | target type/digest 匹配 + applicable gates `is True` | 对应 decision + event/outbox | 跨类型推导、unknown/skipped/invalid 拒绝 |

SQLite 实现必须使用短事务和仓储层封装；长时间模型/工具调用不得持有数据库事务。外部动作采用 prepare/receipt/reconcile，不可能与 SQLite 事务伪装成一个分布式原子提交。

## 15. 删除、留存与恢复

- **逻辑撤销优先**：知识、能力包、交付、需求和路线图历史不可物理覆盖；撤销通过状态/事件表达。
- **敏感正文与审计元数据分离**：分别定义访问、留存、导出和删除责任；审计不得因为脱敏而丢失主体、动作、对象、结果与摘要。
- **备份范围**：DB、uploads、outputs/task_runs、知识版本/索引重建清单、审计/outbox、配置和 SecretRef/签名引用必须进入全资产恢复合同。
- **恢复证据**：备份文件存在不等于可恢复；目标机 restore drill、完整性检查、对象数对账和截断 tamper 必须有机器证据。

## 16. Schema 实现前置门

1. 对每个目标实体回答：权威 Module、消费者、稳定 ID、版本、classification、留存、授权动作和失败归属。
2. 冻结最小 Schema；未知字段 fail-closed，避免先建万能 JSON 垃圾桶。
3. invalid-first fixtures 至少覆盖：缺 actor、跨项目对象、附件旁路、未知分级、旧 lease 晚写、failed 翻 completed、授权重复消费、知识版本冲突、Bench skipped 冒充通过、AI 自签路线图。
4. 迁移必须有旧库 fixture、幂等运行、回滚/前滚策略与备份恢复演练。
5. 公开 API 或持久格式变化另立实施 ADR；本文件不授权创建上述表。

## 17. 关联依据

- [系统宪法](../../00_FLAi-OS_Constitution.md)
- [Task/Event 标准](../../05_Task_Event_Standard.md)
- [知识与记忆标准](../../06_Knowledge_Memory_Standard.md)
- [Eval 标准](../../07_Eval_Standard.md)
- [ADR-0025：不可变任务级分级与 CAS-on-NULL](../../adr/ADR-0025-immutable-task-classification.md)
- [ADR-0033：唯一控制内核](../../adr/ADR-0033-flai-control-kernel-and-replaceable-execution-backends.md)
- [ADR-0034：交付包与末端授权](../../adr/ADR-0034-uninterrupted-session-and-final-delivery-authorization.md)
- [ADR-0041：权威知识底座](../../adr/ADR-0041-authoritative-knowledge-foundation.md)
- [ADR-0042：能力发布包与 FLAi Bench](../../adr/ADR-0042-flai-bench-evaluation-foundation.md)
- [ADR-0043：证据化指标](../../adr/ADR-0043-co-building-map-and-evidence-derived-metrics.md)
- [ADR-0044：需求共创闭环](../../adr/ADR-0044-demand-co-creation-loop.md)
- [ADR-0045：需求决策权](../../adr/ADR-0045-demand-decision-rights-and-roadmap-signoff.md)

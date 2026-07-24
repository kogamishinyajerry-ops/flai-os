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
10. **SQLite 继续承载 FLAi 本地事实**：V0.2 不引入 PostgreSQL、ORM、Redis 或 Celery；FLAi 自有任务、运行、授权、证据与审计通过仓储层、迁移和窄 Interface 演进。它不是 GitHub、飞书协作域或 `secrets-stackdocker` 的全局 SSOT。

## 3. 当前事实层

| 现有事实 | 状态 | V0.2 复用方式 | 当前不足 |
|---|---|---|---|
| `tasks` | `IMPLEMENTED-PARTIAL` | 继续作为任务实例和状态事实 | 尚无 CanonicalTaskGraph、Grant、统一 lane/lease、Delivery Bundle |
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

CapabilityReleasePackage ──bound_by──> EvaluationAdmission ──permits──> BenchRun
BenchRun ──produces──> qualification evidence matrix ──supports──> QualificationDecision
QualificationDecision ──prerequisite_for──> human-signed DeploymentBinding
DemandSignal ──processed_by──> CurationEvent ──forms──> DemandCandidate
DemandCandidate ──reviewed_by──> DomainReview / SecurityReview
DomainReview / SecurityReview ──supports──> RoadmapDecision / HumanSignoff
RoadmapDecision ──accepted_as──> RoadmapCommitment ──delivered_as──> CapabilityReleasePackage
所有强治理变化 ──atomic outbox──> AuditLedgerEvent ──projects_to──> Read Models

FeishuChannelAttestation ──binds──> ExternalIdentityBinding ──maps_to──> Actor
SourceOwnershipRegistryHeadV1 ──selects──> SourceOwnershipRegistryV1 ──resolves_as──> SourceOwnershipResolutionV1
HubIntent ──prepared_with_resolution_as──> PreparedCommandV1 / ReviewChallengeV1
ReviewChallengeV1 + ConfirmationProofV1 ──committed_by_owner──> OwnerCommitReceiptV1 | EffectUnknownV1
FederatedFactRef ──materializes_as──> ProjectionManifest
EffectUnknownV1 / source gap / projection drift ──may_open──> ReconciliationCase
SecretRef ──resolved_only_at_connector──> OpaqueSecretLease
SafetyPrepareAdmissionSubjectV1 / SafetyChallengeV1 / SafetyPolicyPublicationChallengeV1 ──bound_by──> EmergencyActorAdmissionV1[2]
EmergencyActorAdmissionV1[2] + subject nonce ──CAS_reserved_as──> SafetyAuthorizationReservationV1
SafetyAuthorizationReservationV1 ──anchors──> EmergencyAdmissionConsumptionV1[2] / SafetySubjectNonceConsumptionV1
SafetyAuthorizationReservationV1 ──prepares──> SafetyPreparedCommandV1 ──challenges_as──> SafetyChallengeV1
SafetyChallengeV1 ──tracked_by──> SafetyChallengeStateRevisionV1 / SafetyChallengeStateHeadV1
SafetyAuthorizationReservationV1 ──reserves_as──> SafetyCommitAttemptV1
SafetyTrustedTimeEpochTransitionV1 ──authorizes_epoch──> SafetyTrustedTimeAttestationV1
SafetyTrustedTimeAttestationV1 ──leased_for_commit_as──> SafetyTrustedTimeCommitLeaseV1 ──linearized_as──> SafetyTrustedTimeCommitFreshnessProofV1 ──CAS_advances──> SafetyTrustedTimeCheckpointV1
SafetyOwnerWorkloadAttestationV1 ──verified_as──> SafetyOwnerWorkloadAttestationVerificationV1
SafetyCoordinatorReservationVerificationSubjectV1 ──attested_by──> SafetyOwnerWorkloadAttestationV1
SafetyTargetOwnerSigningSubjectV1 / SafetyPolicyAliasTransitionSubjectV1 ──attested_by──> SafetyOwnerWorkloadAttestationV1
SafetyCommitAttemptV1 ──authorizes──> SafetyProviderMutationRequestV1 ──frozen_by──> SafetyCommitDispatchClaimV1 ──freezes_subject_for──> SafetyProviderMutationCapabilityV1
SafetyProviderMutationCapabilityV1 ──consumed_once_as──> SafetyProviderMutationCapabilityConsumptionV1 ──anchors_with──> SafetyEgressBoundaryAttestationV1 / SafetyProviderCallAttemptV1
SafetyProviderMutationRequestV1 ──compared_with──> SafetyProviderWireBytesEvidenceV1 ──attested_as──> SafetyProviderWireRequestAttestationV1 ──bound_by──> SafetyProviderCallAttemptV1
SafetyEgressBoundaryAttestationV1 / SafetyProviderWireRequestAttestationV1 ──verified_as──> SafetyEgressWorkloadAttestationVerificationV1
SafetyProviderCallAttemptV1 ──may_receive──> SafetyProviderRawSendReceiptV1 ──verified_as──> SafetyProviderSendReceiptVerificationV1 ──sealed_as──> SafetyProviderSendReceiptV1
SafetyCommitAttemptV1 ──resolves_as──> SafetyOwnerReceiptPayloadV1 | SafetyEffectUnknownV1
SafetyOwnerReceiptPayloadV1 ──requested_for_signing_as──> SafetySigningRequestV1
SafetyOwnerReceiptPayloadV1 ──wrapped_as──> SafetyOwnerReceiptV1
SafetySigningRequestV1 ──frozen_for_fence_as──> SafetySignatureEnvelopeCoreV1 ──signed_and_wrapped_as──> SafetySignatureEnvelopeV1
SafetyOwnerReceiptV1 ──signed_with──> SafetySignatureEnvelopeV1
SafetyPolicyPublicationChallengeV1 ──reserved_by_two_admissions_as──> SafetyAuthorizationReservationV1 ──consumed_by_policy_owner_as──> SafetyPolicyPublicationReceiptV1
SafetyPolicyPublicationReceiptV1 ──appends──> SafetyIssuancePolicyHeadV1 / SafetyVerificationPolicyHeadV1 ──selected_by──> SafetyPolicyHeadPointerRevisionV1
SafetyPolicyAliasTransitionRequestV1 ──committed_by──> SafetyPolicyAliasCommitResultV1 ──atomic_CAS_advances──> SafetyPolicyHeadCurrentAliasV1
SafetyPolicyHeadCurrentAliasV1 ──atomic_CAS_resolves_to──> SafetyPolicyHeadPointerRevisionV1 + SafetyPolicyFenceWitnessV1(ALIAS_COMMIT)
SafetySigningRequestV1 ──fenced_by──> SafetyPolicyFenceWitnessV1(SIGN_PRE/SIGN_POST)
SafetyIssuancePolicyHeadV1 ──selects──> SafetyIssuancePolicyBundleV1 ──governs──> SafetyPreparedCommandV1 / SafetyChallengeV1 / SafetyOwnerReceiptPayloadV1 / SafetySigningRequestV1 / SafetySignatureEnvelopeV1
SafetyVerificationPolicyHeadV1 ──selects──> SafetyVerificationPolicyBundleV1 ──governs──> SafetyReceiptVerificationV1
SafetyOwnerReceiptV1 ──verified_as──> SafetyReceiptVerificationV1
SafetyReceiptVerificationV1 ──factory_yields──> FullSafetyEffectVerifiedV1 | LocalFenceVerifiedExternalPendingV1 | SafetyResultInvalidatedV1 | SafetyResultInconclusiveV1
FullSafetyEffectVerifiedV1 / LocalFenceVerifiedExternalPendingV1 / SafetyResultInvalidatedV1 / SafetyResultInconclusiveV1 ──CAS_advances──> SafetyResultHeadV1
LocalFenceVerifiedExternalPendingV1 ──queried_as──> SafetyEffectObservationV1
SafetyEffectObservationV1 ──append_only_reconciles──> successor SafetyOwnerReceiptPayloadV1
```

## 5. 身份、项目与资源授权

### 5.1 Actor

- **状态**：当前认证 `IMPLEMENTED-PARTIAL`；目标字段 `ACCEPTED-NOT-IMPLEMENTED`。
- **最小字段**：`actor_id`、`identity_provider`、`subject_id`、`status`、`authenticated_at`、`credential_epoch`。
- **不变量**：`display_name` 只展示；普通协作/工作负载 Identity Module 是其 `credential_epoch` 的唯一 owner，并以 CAS 提升 epoch、同事务写 invalidation outbox。独立 Safety Identity / PKI / HSM 另行拥有 EmergencyActorAdmission 的 credential/key epoch；普通 Identity 不得提升、覆盖或解析它。停用、会话撤销或 epoch 漂移不仅在提交阶段 fail-closed，还必须停止新 claim，并终止绑定旧快照的活动执行。
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
- **用途**：所有持久资源共用的授权输入，包括 request、AutonomousSession、CanonicalTaskGraph、task、conversation、file/Artifact、feedback、Grant、QueueLease、ExecutionRun、DeliveryBundle/Authorization/Attempt/Receipt、eval/Bench、sample、typed promotion/qualification、CapabilityReleasePackage、DeploymentBinding、knowledge、demand、roadmap 和 audit view；不强迫所有对象继承同一物理表。
- **机械门**：上述每类资源都必须有跨主体、跨项目/数据域、已知 ID 深链、list/search/export/aggregate 与撤权后的 invalid-first fixture；缺 envelope 或 predicate 的资源默认不可读写。

### 5.5 AuthorizationRevocationState / ExecutionEpochSnapshot

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **事实 owner**：普通协作/工作负载 Identity Module 独占普通 actor/session 的 `credential_epoch`；Authorization Module 独占每个 `revocation_partition_type + revocation_partition_ref` 的 `authorization_epoch`；Supply-chain Module 独占 trust domain 的 `trust_policy_epoch + trust_policy_digest`。独立 Safety Identity / Admission 独占 Emergency actor 的 credential/key epoch，并通过 `EmergencyActorAdmissionV1` 单独绑定精确 Safety prepare/commit/policy-publication subject；普通 `ExecutionEpochSnapshot` 不得吞并或改写它。Grant、Ticket、Lease、Kernel 或 Adapter 均不得跨 owner 提升这些值。
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
- **CanonicalTaskGraph 不可变字段**：`graph_id`、`graph_version`、`request_digest`、`compiler_version`、`policy_context_digest`、`graph_digest`。
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
- **结果枚举**：`deny | defer_to_delivery | auto_execute`。
- **不变量**：有限枚举；不得以自由文本理由替代结果；下层策略不能把 `deny` 变为允许；提交前重新判定。Ticket 只为已领取当前 lease 的具体步骤签发；epoch、lease、step、target 或时效任一不匹配即无票处理并拒绝。

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
- **ReleaseKnowledgeBinding**：运行前冻结进能力发布包的知识合同，包含允许的 authority/scope、必需/禁止集合、版本选择策略、目录根摘要、检索/锚点策略和外部活态模式；完整 canonical 内容形成 `binding_digest` 并参与 release digest，任一组成变化都使两个摘要变化，但它不包含 actor、任务时刻或实际命中。
- **TaskKnowledgeSnapshot**：运行时按 Binding、actor、task、`as_of` 与当前授权解析出的实际知识版本、索引版本、使用锚点、缺失/冲突和整体 digest；它绑定 task/Bench run，但不反向改变 release 身份。
- **Citation**：知识版本、精确位置、任务时有效状态和引用语义。
- **不变量**：Task Snapshot 必须机械证明符合 Release Binding；索引命中不决定权威；缺失/冲突返回“无法确认”；知识密级传播到任务、模型调用、产物与审计。

### 10.3 EngineeringClaimLedger

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- **用途**：CFD 等工作流把每个需求、边界条件、模型选择和建议标为 `authoritative_basis | engineer_confirmed_assumption | model_suggestion | unresolved`。
- **不变量**：模型建议不能改写成既有要求；未决事实可以聚合进 Delivery Bundle，但依赖它的不可逆动作不得执行。

## 11. 能力发布与 FLAi Bench

### 11.1 CapabilityReleasePackage、EvaluationAdmission、QualificationDecision 与 DeploymentBinding

- **状态**：当前 eval snapshot `IMPLEMENTED-PARTIAL`；完整对象 `ACCEPTED-NOT-IMPLEMENTED`。
- **不可变 Manifest**：Agent、Prompt、Workflow、Schema、resolved model endpoint/route/trust bundle/parameter profile/tokenizer、Tool/Adapter、Sandbox/镜像/资源策略、预算、权限/出站策略、完整 ReleaseKnowledgeBinding `binding_digest`、Eval Suite/Rubric、Gate Policy、environment profile 及各自摘要；运行时 TaskKnowledgeSnapshot 不参与 release 身份。
- **Package lifecycle**：`assembling | frozen | superseded | retired`，只回答包是否仍可被引用；冻结后不可改字节，评测失败不回写包内容。
- **EvaluationAdmission**：由具备职责的 Eval maintainer 签发并版本化，绑定 evaluator/service actor 与 scope、精确 release、approved synthetic fixture/pack/rubric/Gate Policy/environment digest、允许动作、`external_effects=none`、资源/Token 预算、TTL 和 ExecutionEpochSnapshot；状态为 `active|suspended|revoked|expired`。它不进入 release digest、不授予普通用户调用权，也不产生资格决定。
- **QualificationDecision**：追加式记录 `target_class=phase_0a|phase_0b|released`、`outcome=eligible|ineligible|expired`、release/bench digest、范围、限制、签发主体与证据；评测运行状态不塞进 package lifecycle。决定分区键固定为 `release_digest + target_class + qualification_scope_digest`；每个分区使用单调 `decision_epoch`、`supersedes_decision_id` 和 head CAS，任何多头、断链、旧 epoch 或不可判定 head 都归为 `unknown → deny`。只有唯一 current head 为未过期 `eligible` 才满足资格条件。
- **DeploymentBinding**：把精确 release digest 暴露给具名人群/项目/数据域/动作/时间窗，字段含 `deployment_class` 与 `status=draft|active|suspended|revoked|expired`；Phase 0A、Phase 0B 和正式服务是绑定类别，不是包状态。
- **不变量**：任一关键成分变化形成新 release digest；外部活态必须显式列出；不可重建且影响准入时不得形成 eligible decision。包 lifecycle、qualification、deployment binding、现有 `agent.status` 与 L0–L3 各有唯一 owner，禁止互相自动推导。
- **唯一 effective_callability**：Kernel 先要求 package=`frozen`、Agent 非 `disabled`、授权/依赖健康且可派生 Session Grant，再只允许两条互斥路径：实验室评测必须有精确匹配且 active 的 EvaluationAdmission，并且 actor/scope、approved synthetic fixture/pack、预算、TTL、epoch 与零外部效果全部匹配；用户/业务调用必须同时有目标 class 的 current eligible QualificationDecision 和精确 release 的 active DeploymentBinding。`origin=eval` 只由前一事实派生，不能作为输入；`suspended/revoked/expired/unknown` 任一命中都硬否决。L0–L3 仅为成熟度信息，不授予调用权。

### 11.2 BenchSuite / BenchCase / BenchRun

- **状态**：现有 Eval `IMPLEMENTED-PARTIAL`；四轨合同 `ACCEPTED-NOT-IMPLEMENTED`。
- **轨道**：`deterministic_regression | engineering_quality | safety_governance | efficiency`。
- **Case 生命周期**：`draft | approved | retired`；真实/synthetic 与 classification 明确。
- **Run 结果**：逐 case `passed | failed | invalid | skipped | unknown`，加环境、任务和证据 refs；沿用现有 `passed` 拼写，若未来改枚举必须有显式 Schema 迁移/兼容 Adapter。
- **不可抵消门**：安全、诚实性、依据链和关键回归任一非明确 `passed`，release 不能晋级；没有单一加权总分。

### 11.3 HumanReview / Typed Qualification and Promotion

- **状态**：`IMPLEMENTED-PARTIAL`。
- **不变量**：评审主体来自认证身份；LLM judge 只作建议；`honesty`、`traceability` 严格布尔。`AgentLifecyclePromotion` 只改变现有 Agent 生命周期/成熟度事实；`QualificationDecision` 与 `DeploymentBinding` 分别绑定精确 release/bench digest 和暴露范围。对应 typed command 使用 `IssueQualificationDecision` 与 `SignDeploymentBinding`，三类命令都带 `target_type + target_digest`，不得自动互推，且终态 CAS 防止晚写翻绿。

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

### 12.4 飞书中枢逻辑实体

以下对象是 `ACCEPTED-NOT-IMPLEMENTED` 的逻辑合同，不授权创建生产表：

| 逻辑实体 | 最小语义 | 权威 owner |
|---|---|---|
| `FeishuChannelAttestation` | tenant/app/channel/subject、事件或免登证据、时间窗、nonce、防重放结果 | 受信 Feishu ingress |
| `ActorAttestationV1` | verified channel admission、内部 actor/binding version、responsibility/scope digest、credential/authz epoch、assurance、audience/purpose | FLAi Identity / Admission |
| `ExternalIdentityBinding` | 外部 subject 到内部 Actor 的版本化绑定、职责、scope、clearance、credential epoch 与有效期 | FLAi Identity |
| `HubIntent` | tagged type、target ref/version/digest、payload ref/version/digest/classification、作用域、原因、幂等键、过期时间 | Feishu Organizational Hub |
| `PreparedCommandV1` | intent/payload/target digest、prepare ActorAttestation、binding/epoch/assurance、required commit assurance profile、policy/review/gate digest、nonce/TTL/idempotency | Feishu Organizational Hub |
| `ReviewChallengeV1` | prepared command digest、规范化 challenge digest、精确对象、具名职责、required commit assurance、classification、一次性 nonce 与 TTL | 对应治理 owner |
| `OwnerCommitReceiptV1` | intent/challenge/actor/target/effect key、fresh commit ActorAttestation/assurance/credential+authz epoch、expected/result fact、owner sequence、验证方法/策略、evidence 与规范化 receipt digest；outcome 仅 `COMMITTED` | 对应事实 owner |
| `EffectUnknownV1` | intent/target/effect key、显式可空的 owner effect-attempt ref+digest、last-known owner fact、ReconciliationCase、`DO_NOT_REPLAY` | Hub Reconciliation Module |
| `FederatedFactRef` | source system、resource、revision、digest、classification、freshness 与 source evidence ref；治理变迁可另带 owner receipt | 来源 owner |
| `ProjectionManifest` | 目标 Surface/record、来源 revision/digest、classification lattice/policy、space ceiling、audience digest、redaction、adapter version、适用 receipt 与投影 digest | Hub Projection Module |
| `ProjectContextBinding` | collaboration project 到 FLAi authorized project scope 的单向版本化映射；不携带 membership 写权 | FLAi Project Directory |
| `DeliveryWorkItem` | 人类 owner、项目/密级、frozen SHA、文件/Interface scope、executor/budget、dispatch/handoff/integration 状态 | FLAi Delivery Governance |
| `DevelopmentHandoffV1` | work item/run/runtime receipt、base/final SHA、commit/diff、变更 scope、验证结果、证据、风险/未决项与 domain-separated canonical digest | FLAi Delivery Governance |
| `F0ReviewManifestV1` | frozen Git commit/tree、生成主体/工具摘要、规范文件 path/hash/role 集、review/receipt/seal schema、supersedes 与 canonical digest；不含 review records | FLAi Architecture / Governance |
| `F0ManifestGenerationReceiptV1` | 精确 manifest、生成主体/工具、受控 channel/event、attestation evidence、外部验证 receipt 与 generation digest | 组织批准的 manifest-generation verifier |
| `F0NamedReviewV1` | reviewer actor/scope/decision、精确 manifest 与 generation receipt、任命、design evidence、后续 witness gate、残余风险与 review core digest | 对应七个责任域 |
| `F0NamedReviewSealV1` | review core、manifest/generation receipt、reviewer ActorBinding、签名或不可变审计证据、trust policy/verifier receipt 与 seal digest | 对应七个责任域的组织信任 verifier |
| `SourceOwnershipRegistryV1` | `(intent_type, schema_version, resource_kind)` 到 owner Module/Port、receipt type/schema 与 verifier ref/version/digest 的具名签发映射；epoch/effective range、canonical digest | FLAi Architecture / Governance Policy owner |
| `SourceOwnershipRegistryHeadV1` | owner、generation、current registry ref+digest、publication receipt 与独立 head digest | FLAi Architecture / Governance Policy owner |
| `SourceOwnershipResolutionV1` | observed Head/Registry/Entry ref+digest 与确定性 resolution digest；零/多匹配都不是 resolution | SourceOwnershipRegistryPort |
| `ConfirmationProofV1` | 精确 challenge/prepared/nonce digest、confirmation mode、actor/channel/audience/purpose、显式确认时间与 canonical digest | FLAi Admission |
| `ReconciliationCase` | effect unknown、source gap、projection drift、auth change 或冲突及具名处置 | Hub Reconciliation Module |
| `SecretRef` | 运行时 App/Connector 的 provider/scope/name/version selector/purpose 非秘密引用 | `secrets-stackdocker` |
| `OpaqueSecretLease` | concrete version ref、lease ref、TTL、workload/purpose 和 audit ref；不含可序列化 value | SecretProviderPort |
| `SafetySigningMaterialRef` | 独立 HSM key handle/epoch、hardware identity ref 与 public trust anchor ref；不含私钥材料 | Safety Identity / PKI / HSM |
| `SafetyOwnerWorkloadAttestationMaterialRefV1` | owner/workload/operation/purpose-bound 的不可导出 workload attestation key handle/epoch、policy、failure domain、trust anchor、revocation 与有效期；Coordinator/target owner/Policy owner 分别实例化且不得互相代签 | 独立 Safety Owner Workload Identity / PKI / HSM |
| `SafetyEgressWorkloadAttestationMaterialRefV1` | egress boundary identity / wire-buffer 两类 operation-bound material ref、短时不可导出 key/epoch、policy/failure-domain/trust/revocation；不得用 App/Connector credential、自签进程 key 或跨 operation 代签 | Safety Egress Workload Identity / TPM / TEE / KMS |
| `SafetyPolicyFenceMaterialRefV1` | Policy Fence Authority 的不可导出 key handle/epoch、role、trust anchor 与 revocation | 独立 Safety Policy Fence Authority / PKI / HSM |
| `SafetyTrustedTimeMaterialRefV1` | Time Authority 的 TIME_INTERVAL_ATTEST 或 EPOCH_TRANSITION_CONTINUITY operation-bound 不可导出 key handle/epoch、time policy、failure domain、trust anchor 与 revocation；两类 material identity 不得相同 | 独立 Safety Trusted Time Authority / continuity root / PKI / HSM |
| `SafetyTrustedTimeCommitGuardMaterialRefV1` | consumer/storage-profile-bound 的 precommit guard、受信 monotonic elapsed source、不可导出 key/epoch、failure domain、trust/revocation；不是普通 workload credential | 独立 Safety Trusted Time Commit Guard |
| `SafetyTrustedTimeEpochTransitionV1` | Genesis 或 epoch+1 的 predecessor attestation/counter、前后 source/key/trust、counter 初值、transition policy/reason/nonce 与 continuity-root 签名的 canonical record | 独立 Safety Trusted Time Continuity owner |
| `SafetyTrustedTimeAttestationV1` | request nonce/subject/purpose、authority epoch+严格单调 counter/predecessor、exact epoch-transition、UTC lower/upper bound、uncertainty、validity、key/trust/signature 与 canonical ref+digest | 独立 Safety Trusted Time Authority |
| `SafetyTrustedTimeCommitLeaseV1` | consumer/transaction nonce/commit subject/purpose、TimeAttestation、可信 elapsed acceptance/deadline tick、最大提交预算与 storage profile 的一次性签名 lease | consumer-local Safety Trusted Time Commit Guard |
| `SafetyTrustedTimeCommitFreshnessProofV1` | Guard 在 owner-store 线性化点形成的签名 proof；绑定 lease、前序 checkpoint、线性化 token/tick、elapsed upper bound 与 FRESH outcome | consumer-local Safety Trusted Time Commit Guard |
| `SafetyTrustedTimeCheckpointV1` | consumer owner 已接受的 epoch/counter/attestation high-water，以及 exact commit lease/proof、transaction nonce/subject、store token 与唯一 consumption key；与 anchor owner-local CAS 防回拨、重放和陈旧事务 | 各 Safety consumer owner |
| `SafetyOwnerWorkloadAttestationV1` | Coordinator、target owner、Policy owner 复用的 owner/workload/build/failure-domain/operation-subject/audience/purpose/TTL/key/trust/signature 不可变 envelope | 对应 Safety owner workload / 独立 Safety Identity |
| `SafetyOwnerWorkloadAttestationVerificationV1` | 对 attestation 的 canonical、owner/workload/build/failure-domain/operation subject/key/revocation/trust/signature/time 三态验证，并冻结 exact TrustedTimeAttestation + verifier-local Checkpoint ref/digest；False 优先 Invalid，Unknown fail-closed | 独立 Safety Owner Workload Attestation Verifier |
| `SafetyCoordinatorReservationVerificationSubjectV1` | Coordinator store commit/sequence、Reservation、两条 AdmissionConsumption、一条 SubjectNonceConsumption、expected ACTIVE、audience/purpose 的 canonical operation subject | Safety Admission Coordinator |
| `SafetyTargetOwnerSigningSubjectV1` | payload/command/challenge/effect/target、Issuance Head+Bundle、audience/purpose/TTL 的 canonical target-owner signing subject | 被处置的 target owner Module |
| `SafetyPolicyAliasTransitionSubjectV1` | publication receipt、expected alias/pointer/fence 与 successor PointerRevision/Head/Bundle、idempotency/TTL 的 canonical policy-owner operation subject | 对应 Safety Policy owner |
| `SafetyPrepareAdmissionSubjectV1` | 精确 typed command/target/effect、Issuance Head+PointerRevision+Bundle、audience/purpose、TTL 与一次性 nonce 的 immutable subject | Safety Survival Module |
| `EmergencyActorAdmissionV1` | 独立安全身份、admission kind、精确 subject ref+digest/nonce、职责/scope、credential/authz epoch、fresh assurance、hardware/PKI evidence、audience/purpose 与 canonical/replay-domain digest | Safety Identity / Admission |
| `SafetyAuthorizationReservationV1` | 精确 subject/projection、双人 admission/replay-domain、subject nonce、requested owner、idempotency/effect key 与 commit state revision 的 immutable 跨 owner 续作凭证 | Safety Admission Coordinator |
| `SafetyAuthorizationReservationVerificationV1` | Coordinator 权威 Store 中 Reservation+双 AdmissionConsumption+SubjectNonceConsumption 的原子存在、binding、attested-time TTL、独立 Coordinator workload attestation/failure-domain 验证；False/Unknown/Expired 均拒绝 | Safety Admission Coordinator / independent verifier |
| `SafetySubjectNonceConsumptionV1` | subject type/ref/digest + nonce 的唯一键及其唯一 Reservation；CAS-on-NULL | Safety Admission Coordinator |
| `EmergencyAdmissionConsumptionV1` | admission digest 唯一键、精确 subject/replay domain、actor 与同事务 Reservation anchor；CAS-on-NULL，一生只消费一次 | Safety Admission Coordinator |
| `SafetyCommitAttemptV1` | challenge/prepared/command/target/effect key、双人 commit admission、nonce 与 projection digest 的 immutable 本地执行 journal；最终 receipt/unknown 追加引用它 | 被处置的 target owner Module |
| `SafetyProviderWireCanonicalizationProfileV1` | method/path/query/header/credential exclusion/body/media/redirect/Unicode 的版本化唯一规范化规则与 canonical digest；unknown profile fail-closed | Safety Provider Protocol Policy owner |
| `SafetyProviderMutationRequestV1` | provider method/route/path/query、非秘密 headers、content-addressed body bytes、effect-key carrier 与 credential-injection profile 的 canonical ref/digest；凭据值不入对象 | 被处置的 target owner Module |
| `SafetyCommitDispatchClaimV1` | CommitAttempt/effect key、worker/lease/provider/request/route、无环 `provider_mutation_subject_digest` 与 attested-time deadline 的短时领取；不含未来 Capability ref/digest，不证明已发送 | 被处置的 target owner Module |
| `SafetyProviderMutationCapabilityV1` | 单向引用 claim/subject，并绑定 attempt/effect/request/provider/route/policy epoch/lease/deadline/audience/nonce 的一次性发送能力；同 Claim CAS-on-NULL 只签发一个，不是 SecretLease | 唯一 Safety Provider Mutation/Egress owner |
| `SafetyProviderMutationCapabilityConsumptionV1` | capability/subject/claim/effect/egress/time 的 owner-local CAS-on-NULL 消费记录；`capability_consumption_key_digest` 唯一 | 唯一 Safety Provider Mutation/Egress owner |
| `SafetyEgressBoundaryAttestationV1` | egress workload 身份/build/failure-domain、provider route、network policy、policy epoch、TTL、独立 key/trust/签名的不可变 attestation | Safety Egress Identity / Attestation owner |
| `SafetyProviderWireBytesEvidenceV1` | send 前 sealed buffer 的实际 method/path/query/非秘密 headers/body bytes/effect-key carrier、classification 与 generation 的 typed immutable evidence；显式排除 credential values | 唯一 Safety Provider Mutation/Egress owner |
| `SafetyProviderWireRequestAttestationV1` | 实际待发缓冲区的业务 wire projection、immutable wire-bytes evidence、request/effect/provider/boundary、凭据字段名集合与 SecretLease ref/digest 的签名证明；不保存凭据值 | 唯一 Safety Provider Mutation/Egress owner |
| `SafetyEgressWorkloadAttestationVerificationV1` | 独立解析 Boundary/Wire attestation material、operation、workload/build/failure-domain、provider/route/request/capability、policy/key/revocation/trust/time 的三态结果；冻结 exact TrustedTimeAttestation + verifier-local Checkpoint ref/digest | Safety Egress Workload Attestation Verifier |
| `SafetyProviderCallAttemptV1` | 唯一 egress boundary 在实际 send primitive 前重验时间并 CAS 消费 capability 后形成的不可变 attempt；复制 Boundary/Wire verification 的 exact time/checkpoint 绑定，不宣称字节已发送 | 唯一 Safety Provider Mutation/Egress owner |
| `SafetyProviderRawSendReceiptV1` | provider/transport 原始 call-attempt/request/effect handoff claim；未验证、不能证明 handoff | provider / Safety Egress owner |
| `SafetyProviderSendReceiptVerificationV1` | 独立验证 Raw、CallAttempt、CapabilityConsumption、EgressAttestation、request/effect/provider/trust 的三态记录；`False > Unknown > True` | Safety Provider Send Receipt Verifier |
| `SafetyProviderSendReceiptV1` | 只在 verification VALID 且 raw claim CONFIRMED 时形成的单向 verified wrapper；缺失时只能 effect unknown/query/no replay | Safety Provider Send Receipt Verifier |
| `SafetyPreparedCommandV1` | typed subtractive command、精确 prepare Reservation/subject/projection、target digest/generation、required Issuance Policy Bundle ref+digest、policy、commit nonce/TTL/idempotency/effect key 与 command digest | Safety Survival Module |
| `SafetyChallengeV1` | immutable commit admission subject：prepared command、同一双人 actor set、required commit assurance、required Issuance Policy Bundle ref+digest、target、nonce、TTL 与 projection digest；不含可变 state | Safety Survival Module |
| `SafetyChallengeStateRevisionV1` / `SafetyChallengeStateHeadV1` | append-only state revision 与 current CAS head；generation/predecessor 严格连续，commit reservation 只能从 PREPARED 推进 COMMITTING | Safety Admission Coordinator |
| `LocalSafetyEvidenceV1` | receipt signer 故障时的双人硬件签名、command/challenge digest 与本地 fence witness；不是最终成功 receipt | Local Safety Evidence Spool |
| `SafetyEffectObservationV1` | 原 command/challenge/effect key/target、认证 provider query receipt+digest、`CONFIRMED|CONFIRMED_NO_EFFECT|UNKNOWN`、freshness 与 observation digest | 被查询 provider/source owner；Query Adapter 只形成可验证 attestation |
| `SafetyOwnerReceiptPayloadV1` | 精确 CommitAttempt、显式可空且成对绑定的 DispatchClaim/ProviderCallAttempt/verified SendReceipt、command/challenge/effect key、required Issuance Policy Bundle、双人 admission、target owner sequence、local fence、provider state、observation/query receipt、supersedes/head CAS 与预先存在 evidence；字段分支按 `CONFIRMED / NOT_APPLICABLE / EFFECT_UNKNOWN` fail-closed | 被处置的 target owner Module |
| `SafetyOwnerReceiptV1` | payload ref/digest、固定 canonical profile/domain separator、不可变 signature envelope ref/digest 与 receipt digest | 被处置的 target owner Module |
| `SafetySigningRequestV1` | target owner attestation、payload/command/challenge/effect/target digest、issuance Policy Head/Bundle、audience/purpose/TTL 与 canonical digest | 被处置的 target owner Module |
| `SafetySignatureEnvelopeCoreV1` | SigningRequest、HSM material ref/key epoch/算法/signed digest、trust/policy、Issuance Head/Bundle 与 signer operation 的不可变可解析 core ref+digest；先于 PRE 形成 | 独立 Safety Receipt Signer / PKI / HSM |
| `SafetySignatureEnvelopeV1` | immutable envelope-core ref+digest、HSM 签名、共同 policy fence epoch 下的 SIGN_PRE/SIGN_POST witness 与 final digest | 独立 Safety Receipt Signer / PKI / HSM |
| `SafetyIssuancePolicyBundleV1` | command/admission/signing/failure-domain policy、allowed algorithms、epoch/有效期、独立 domain separator 与 canonical digest | Safety Identity / PKI / HSM Policy owner |
| `SafetyVerificationPolicyBundleV1` | verifier/factory/issuance-acceptance policy、明确 accepted issuance digest 集、allowed algorithms、trust snapshot、epoch/有效期与独立 canonical digest | 独立 Safety Receipt Verifier / Policy owner |
| `SafetyPolicyPublicationChallengeV1` | role/mode、expected Head+PointerRevision、new/supersedes bundle、rollback tuple、scope/audience/purpose、TTL 与 publication nonce 的 immutable 双人确认主题 | 对应 Safety Policy owner |
| `SafetyPolicyPublicationReceiptV1` | 精确 publication Reservation/challenge/projection、policy role/mode/owner、两个不同真人 subject-bound admission、expected Head+PointerRevision、new/supersedes bundle、rollback reason/incident、effective time、owner signature 与 canonical digest | 对应 Safety Policy owner |
| `SafetyIssuancePolicyHeadV1` | immutable role+generation content-addressed ref、predecessor、issuance bundle、publication receipt 与 head digest | Safety Identity / PKI / HSM Policy owner |
| `SafetyVerificationPolicyHeadV1` | immutable role+generation content-addressed ref、predecessor、verification bundle、publication receipt 与 head digest | 独立 Safety Receipt Verifier / Policy owner |
| `SafetyPolicyHeadPointerRevisionV1` | content-addressed append-only revision、前序 revision、当前 immutable Head/Bundle、publication receipt 与 canonical digest | 对应 Safety Policy owner |
| `SafetyPolicyAliasTransitionRequestV1` | Policy owner 对 publication receipt、expected alias/pointer/fence 与 successor PointerRevision/Head/Bundle 的不可变、具名 attestation 请求；proposal 本身不生效 | 对应 Safety Policy owner |
| `SafetyPolicyAliasCommitResultV1` | Fence Authority 对 transition request、已提交 alias-state generation/digest 与 ALIAS_COMMIT witness 的不可变结果 | Safety Policy Fence Authority |
| `SafetyPolicyFenceWitnessV1` | 单调 fence epoch 下的 ALIAS_COMMIT 或 SIGN_PRE/SIGN_POST witness，绑定 PointerRevision/Head/Bundle/receipt、SigningRequest/envelope core、exact TimeAttestation/CommitLease/FreshnessProof/Checkpoint 与独立签名 | Safety Policy Fence Authority |
| `SafetyPolicyHeadCurrentAliasV1` | 固定 role URI，由唯一 Fence Authority 在自身事务以 alias-state generation/digest CAS 解析当前 PointerRevision 与 ALIAS_COMMIT fence epoch/witness；不是历史证据 | Safety Policy Fence Authority |
| `SafetyReceiptVerificationV1` | owner receipt/digest、SigningRequest/target-owner attestation、signature envelope/digest、issuance 与 required verification Policy Head/PointerRevision/Bundle 两组 ref+generation+digest、publication/acceptance、verifier policy、trust snapshot、key revocation、anchor、signature、canonical digest，以及 DispatchClaim/CallAttempt/SendReceipt/external effect evidence 的独立三态验证结果 | 独立 Safety Receipt Verifier |
| `FullSafetyEffectVerifiedV1` | owner receipt 与 verification 的不可变引用/digest；只允许 external effect `CONFIRMED|NOT_APPLICABLE`，outcome 为 `FULL_EFFECT_VERIFIED` | Safety Receipt Verifier |
| `LocalFenceVerifiedExternalPendingV1` | 已验证本地 fence、external effect `EFFECT_UNKNOWN`、ReconciliationCase 与 amber 展示合同 | Safety Receipt Verifier |
| `SafetyResultInvalidatedV1` | 已知验证无效、红色、reason codes、前序 result 与同 chain generation | Safety Receipt Verifier |
| `SafetyResultInconclusiveV1` | 验证 unknown/stale/unavailable、amber、reverify disposition、前序 result 与同 chain generation | Safety Receipt Verifier |
| `SafetyResultHeadV1` | command/effect/target 稳定 chain key、generation、当前 result/receipt/verification ref+digest、outcome 与独立 head digest | Safety Receipt Verifier Result Store |
| `SafetyEffectUnknownV1` | 原 CommitAttempt、仅在实际形成时出现的 DispatchClaim/CallAttempt/SendReceipt ref+digest、last-known fence/provider state、稳定 idempotency/effect key、ReconciliationCase 与 `DO_NOT_REPLAY`；不存在的可空对必须显式为 null | Safety Reconciliation |

不变量：

- Bitable row、卡片 payload、projection cache 和通知不是来源事实；
- actor/role/clearance/classification 不接受客户端自报；
- 一个 HubIntent 只提交给一个权威 owner；跨 owner 流程由多个 receipt 串联；
- Source Ownership Registry 是 FLAi Governance owner 的具名签发事实，不是 Hub 配置；
  prepare 冻结 Head/Registry/Entry/expected verifier，commit 在消费 nonce 前重解并逐字比较。
  receipt 自报 owner/type/schema 只能与冻结 Entry 比对，绝不能驱动 verifier dispatch；
- commit 必须传精确 ReviewChallengeV1 ref 与 ConfirmationProofV1；commit ActorAttestation/proof
  绑定 challenge id/digest、prepared digest、nonce、confirmation mode、audience/purpose，
  nonce 只由该 challenge CAS 单次消费；
- Safety prepare/commit/policy publication admission 必须是 domain-separated typed immutable
  对象，绑定精确 subject ref+digest、一次性 nonce、actor/scope/epoch/assurance/channel/
  audience/purpose；`EmergencyAdmissionConsumptionV1` 以 admission digest 为唯一键
  CAS-on-NULL。唯一 Safety Admission Coordinator 先在自己的事务中原子消费两份 admission +
  subject nonce并签发 `SafetyAuthorizationReservationV1`；Safety Survival、target owner 与
  Policy owner 再分别在各自 owner-local transaction 中凭 Reservation 创建
  Prepared/Challenge、CommitAttempt 或 publication receipt/Head/PointerRevision/alias。
  不承诺跨 owner 原子提交；崩溃保持 consumed+reserved 并按同 reservation/idempotency/effect
  key 对账，不释放为可复用授权。ChallengeState 全链只由 Coordinator 的
  `SafetyChallengeStatePort` 写；不同 phase、subject 或 replay domain 不得复用；
- Reservation digest 只证明内容，不证明 CAS provenance。每个下游 owner 首次 anchor 前必须
  从 Coordinator 权威 Store resolve，验证 Reservation、两条 AdmissionConsumption、一条
  SubjectNonceConsumption、owner sequence/store commit 与 workload attestation；所有 gate
  必须 `is True` 且 status `ACTIVE`。owner-local commit 内必须消费独立
  `SafetyTrustedTimeAttestationV1 ref+digest`，按保守 UTC upper bound 与
  `min(reservation expiry, verification freshness, attestation validity)` 比较，并 CAS
  `SafetyTrustedTimeCheckpointV1`；Checkpoint 必须由 transaction-nonce/commit-subject-bound
  CommitLease 与受信 monotonic elapsed 的线性化 FreshnessProof 形成，并和 anchor 在同一
  owner-local transaction；epoch transition 具名签名、Genesis/counter 初值、epoch+1 连续性
  必须可验证。epoch/counter/predecessor 回拨或 gap、陈旧 lease、超 elapsed budget、
  skew/uncertainty 超限、source/key/revocation outage/Unknown 一律拒绝，禁止
  host-clock/cache fallback；
  expiry 前未形成 anchor 时禁止首次 effect。outbox enqueue 和
  `SafetyCommitDispatchClaimV1` 都不算 provider send；唯一受控 egress boundary 必须在第一
  mutating send primitive 前重新验 attested time/deadline、CAS 消费一次性
  `SafetyProviderMutationCapabilityV1` 并创建 `SafetyProviderCallAttemptV1`。缺 verified
  `SafetyProviderSendReceiptV1` 一律 effect unknown + DO_NOT_REPLAY，只可原键查询/对账；
- subject ref/digest 存在不等于生成对象获授权；PrepareSubject↔PreparedCommand、
  Challenge↔CommitAttempt、PublicationChallenge↔PublicationReceipt 必须分别从冻结字段独立
  重算同一个 domain-separated projection digest 并逐字相等，任何重复字段漂移都在消费前拒绝；
- 适用的治理变迁无有效 OwnerCommitReceiptV1 不显示生效；运行 witness、GitHub verified
  provider state 等只读证据不伪造治理 receipt；响应丢失进入 EffectUnknownV1，不换幂等键重放；
- 普通运行时 `SecretRef` 与全部 Safety material（Signer、3 类 owner-workload、2 类
  egress operation、Policy Fence、Trusted Time/Commit Guard）属于不同 owner/failure
  domain；Safety key
  不得由 `SecretProviderPort`、
  `secrets-stackdocker`、普通 workload identity 或应用进程解析。各类引用可以进入配置与审计，
  Secret/private-key value 不能进入上述任何实体、digest 或日志；F0 必须冻结每类 Safety
  owner/failure-domain/key/revocation/trust 合同与 fixture/drill 规格，任一合同未决即阻断；
  真实 material/runtime/outage witness 保持 `DECLARED-NOT-VERIFIED` 并在 D6/D7/D8 + F4 闭合；
- target owner 只签发自己的 Safety effect receipt，独立 signer 只签 canonical digest，
  verifier 只验证且不得生成或补写 owner receipt；verified 结果只能由
  SafetyResultFactory 构造。factory 先要求 verification 自身 key/digest/schema、调用者指定
  Verification Policy Bundle、factory policy 与 Head CAS 等 meta-integrity gate 全部
  `is True`；再按 `INVALID > UNKNOWN > VALID` 矩阵生成 Invalidated/Inconclusive 或
  Full/Pending，不能用 VALID 的 subject gate 阻断 fail-closed successor；
  external effect unknown 只能形成 amber 的 LocalFenceVerifiedExternalPendingV1，只有
  FullSafetyEffectVerifiedV1 可投影完整处置成功；
- Safety receipt 使用固定 RFC8785/JCS UTF-8 NFC、SHA-256 和类型 domain separator；payload、
  envelope、wrapper 分层排除自身 digest 并逐层重算，禁止 detached digest；
- pending→confirmed 只允许原 effect key 的认证查询、expected-head CAS 与新 owner sequence 的
  追加 successor receipt；signed payload 必须绑定 observation/query receipt ref+digest，
  前序不可改、已消费 challenge 不得再次执行、历史不可覆盖；
- PreparedCommand、Challenge、receipt payload、envelope 与 signer 显式绑定同一个 immutable
  Issuance Policy Head generation+digest 及其 Bundle ref+digest；verifier、factory、
  Verification、Result 与 Head 显式绑定具名 Verification Policy Head generation+digest 及
  其 Bundle ref+digest，不得隐式解析“当前策略”；
- 两类 bundle、policy publication challenge/receipt、两类 Policy Head 与 PointerRevision
  都有精确 RFC8785/JCS、type domain、self-exclusion/ref 规则；数组严格排序并拒绝重复。
  Head 只能由双人 subject-bound admission 签发 publication receipt（两个不同真人、相同
  scope/audience/purpose）追加 immutable version，再以 expected
  generation/head/PointerRevision digest 与 expected policy fence epoch/witness 向唯一
  Fence Authority 提交 AliasTransitionRequest；Authority 在自身 single-writer 原子提交中
  CAS current alias 到该 role 从未发布过的新 bundle digest，把 fence epoch 严格
  `E→E+1` 并形成绑定 successor PointerRevision/Head/Bundle/receipt 的 ALIAS_COMMIT
  witness 与 alias-state digest；
  genesis 只能从 null/generation 0 到 generation 1；后继 Head/PointerRevision generation
  必须严格 +1、predecessor/role/owner/bundle/receipt 逐字连续，并对
  `(role,generation)` 唯一；
  同/历史 digest 不得产生新 Head，回滚必须铸造新 epoch/trust/validity/digest；未签/多头/
  unknown fail-closed；
- 历史 Policy Head version、PointerRevision、bundle、publication challenge/receipt、
  Reservation 与 Admission/SubjectNonce consumption 按 ref/digest 在线 append-only 可解析；固定 URI 只作为 current
  alias 并解析当前 revision，不能充当历史证据；WORM 是下游镜像，不能替代验证源；
- signer 只接受 target owner 的 immutable SafetySigningRequest，不接受裸 digest/key handle；
  request 绑定 payload、用途、TTL 与 current issuance Head/PointerRevision/Bundle/fence，
  防止 signing oracle；HSM 调用前后必须从同一 Policy Fence Authority 取得 SIGN_PRE/
  SIGN_POST witness。两者绑定同一 fence/Pointer/Head/Bundle/SigningRequest/envelope-core，
  POST 引用 PRE 与 signature-bytes digest，Envelope 覆盖两份 witness；任一漂移/Unknown 时
  签名字节不形成 Envelope；
- Verification 同时记录两对 bundle ref+digest；只有 issuance 链逐字一致、digest 可重算且
  明确出现在 required verification bundle 的 accepted issuance digest 集中才可继续。
  acceptance `False` 产生 INVALID，`Unknown` 产生 UNKNOWN，不得改写旧 receipt；
- verification key 固定绑定 receipt/envelope 与完整 immutable Verification Policy Bundle；
  receipt/envelope digest 已间接绑定 immutable Issuance Policy Bundle。verification
  digest 使用独立 canonical profile/domain；result key 只由 receipt+verification digest
  直接确定。factory policy 不是 result key 的直接字段，但通过 Policy Bundle →
  verification digest 间接参与结果身份；
- result chain key 固定绑定 command/effect key/target；Result 与 Head Store 在一个
  owner-local 事务内同时比较 current Verification Policy Head 与 Result Head，再做 result
  CAS-on-NULL + expected generation/head digest CAS，历史 result
  只引用 predecessor，Head 单向引用当前 result，禁止分叉和摘要自循环；
- command/admission/signing policy 由 immutable Issuance Policy Bundle 绑定并随 receipt
  永久冻结；verifier/factory/issuance-acceptance policy 与 trust snapshot 由 immutable
  Verification Policy Bundle 绑定。verification bundle 漂移产生新 verification，旧 issuance
  bundle 不变。新 verification bundle 下 reverify 为 INVALID/UNKNOWN 时必须把红色
  Invalidated/amber Inconclusive successor CAS 为当前 Head，不能继续沿用旧 Full；
- 同一 Verification Policy Bundle replay 永远返回首次 verification/result。既有 freshness 到期仅由读取
  门立即派生 amber/unknown，不在旧 bundle 下写第二个 Inconclusive；持久 reverify 必须用
  新 trust snapshot/freshness window 签发新 Verification Policy Bundle，再以 current Head
  CAS 追加结果；
- 读取完整成功必须重验 Head outcome、当前 required Verification Policy Bundle、
  具名 Verification Policy Head/Bundle、verification freshness 与
  全部 digest；任一 unknown/stale/unavailable 立即 fail-closed，不等待后台 reverify；
- Audit/WORM 对 receipt/result 的 seal 是只引用既有 digest 的下游追加镜像，不反向进入签名
  payload 或事实裁决，不形成摘要循环或第二状态 owner；
- 本节不改变现有生产 Schema，实施前必须另立迁移、回滚与 invalid-first 合同。

## 13. 数据分级与传播

### 13.1 当前分级

`internal | sensitive` 当前已有执行语义，状态为 `IMPLEMENTED-PARTIAL`。在组织正式密级、授权矩阵和改级流程裁决前，不增加只有名称没有行为的更多枚举。

### 13.2 派生规则

```text
effective_classification = classification_lattice.join(
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
| 会议记录签发与初始责任发行 | exact MeetingWorkPackage digest + 全部责任项五字段齐全 + expected owner version | 同一 FLAi Meeting & Responsibility owner-local transaction 创建 OfficialMeetingRecord + 全部初始 ResponsibilityItem + OwnerCommitReceiptV1 + audit outbox | 任一缺失/竞态则全部不生效；响应不明先对账，不把部分结果称会议闭环 |
| Knowledge 发布/撤销 | expected lifecycle/version | 新 immutable version/status event | 不原位修改 |
| Typed qualification / promotion | target type/digest 匹配 + applicable gates `is True` | 对应 decision + event/outbox | 跨类型推导、unknown/skipped/invalid 拒绝 |
| Hub prepare/commit bookkeeping | challenge 未消费 + fresh attestation + expected owner version/digest + policy/epoch 有效 | 仅 Hub 本地 intent/challenge/effect-attempt/outbox | 不把远端 owner 或飞书投影伪装进同一事务；stale/撤权/缺门拒绝 |
| Owner fact commit | owner 本地 expected version/digest + owner policy/epoch 有效 | 仅该 owner 本地 fact + owner receipt + owner outbox | 远端响应不明转 `effect_unknown`；Hub 不直接写 owner 数据库 |
| Remote effect dispatch | stable idempotency/effect key + frozen request digest | 仅本地 dispatch attempt + outbox | 通过 owner receipt/authenticated postcondition query 对账；禁止分布式事务幻觉 |
| Projection apply | owner revision 连续 + destination audience/classification 允许 | manifest + projection/outbox | source gap、drift 或目标不允许时 stale/suppressed，不反写 owner |

SQLite 实现必须使用短事务和仓储层封装；长时间模型/工具调用不得持有数据库事务。外部动作采用 prepare/receipt/reconcile，不可能与 SQLite 事务伪装成一个分布式原子提交。

## 15. 删除、留存与恢复

- **逻辑撤销优先**：知识、能力包、交付、需求和路线图历史不可物理覆盖；撤销通过状态/事件表达。
- **敏感正文与审计元数据分离**：分别定义访问、留存、导出和删除责任；审计不得因为脱敏而丢失主体、动作、对象、结果与摘要。
- **备份范围**：DB、uploads、outputs/task_runs、知识版本/索引重建清单、审计/outbox、配置和 SecretRef/签名引用必须进入全资产恢复合同。
- **恢复证据**：备份文件存在不等于可恢复；目标机 restore drill、完整性检查、对象数对账和截断 tamper 必须有机器证据。

## 16. Schema 实现前置门

1. 对每个目标实体回答：权威 Module、消费者、稳定 ID、版本、classification、留存、授权动作和失败归属。
2. 冻结最小 Schema；未知字段 fail-closed，避免先建万能 JSON 垃圾桶。
3. invalid-first fixtures 至少覆盖：缺 actor、跨项目对象、附件旁路、未知分级、旧 lease 晚写、failed 翻 completed、授权重复消费、知识版本冲突、Bench skipped 冒充通过、AI 自签路线图、伪造 `open_id`、旧 challenge、Bitable 改绿、receipt invalid、effect unknown 换键重放和 Secret fallback。
4. 迁移必须有旧库 fixture、幂等运行、回滚/前滚策略与备份恢复演练。
5. 公开 API 或持久格式变化另立实施 ADR；本文件不授权创建上述表。

## 17. 关联依据

- [系统宪法](../../00_FLAi-OS_Constitution.md)
- [Task/Event 标准](../../05_Task_Event_Standard.md)
- [知识与记忆标准](../../06_Knowledge_Memory_Standard.md)
- [Eval 标准](../../07_Eval_Standard.md)
- [ADR-0025：不可变任务级分级与 CAS-on-NULL](../../adr/ADR-0025-immutable-task-classification.md)
- [ADR-0049：唯一控制内核](../../adr/ADR-0049-flai-control-kernel-and-replaceable-execution-backends.md)
- [ADR-0050：交付包与末端授权](../../adr/ADR-0050-uninterrupted-session-and-final-delivery-authorization.md)
- [ADR-0057：权威知识底座](../../adr/ADR-0057-authoritative-knowledge-foundation.md)
- [ADR-0058：能力发布包与 FLAi Bench](../../adr/ADR-0058-flai-bench-evaluation-foundation.md)
- [ADR-0059：证据化指标](../../adr/ADR-0059-co-building-map-and-evidence-derived-metrics.md)
- [ADR-0060：需求共创闭环](../../adr/ADR-0060-demand-co-creation-loop.md)
- [ADR-0061：需求决策权](../../adr/ADR-0061-demand-decision-rights-and-roadmap-signoff.md)
- [ADR-0062：飞书唯一日常组织协作与治理中枢](../../adr/ADR-0062-feishu-single-organizational-hub.md)
- [飞书中枢详细设计](17_Feishu_Organizational_Hub.md)

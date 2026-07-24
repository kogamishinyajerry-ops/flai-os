# 17｜飞书唯一组织协作与治理中枢

> 决策依据：
> [ADR-0062](../../adr/ADR-0062-feishu-single-organizational-hub.md)
>
> 状态：`ACCEPTED-NOT-IMPLEMENTED`
>
> 本文只完成产品、架构、Interface、Seam、治理与迁移设计。它不修改生产 Schema、公开
> Interface、任务状态机、飞书应用、GitHub、`secrets-stackdocker` 或任何真实数据。

## 1. 结论

飞书可以承担 FLAi-OS 全部日常管理与治理的**唯一组织落点、工作收件箱和编排 Surface**，
但需要精确定义：

> 飞书是唯一日常 `System of Engagement`；FLAi Control Kernel、GitHub、Knowledge
> Authority、Audit/WORM 与 `secrets-stackdocker` 继续分别拥有自己的权威事实。

这意味着用户都从飞书发起、组织、跟踪并接收回告：

- 团队与项目协作；
- 需求提交、策展、领域/安全评审与路线图签发；
- 开发任务编排、Codex/Kimi-K3 协作和 GitHub 交付跟踪；代码 diff review、PR approval、
  branch protection 与 merge 仍通过重新鉴权深链进入 GitHub 原生专业 Surface；
- 会议工作包、正式会议记录、责任事项和验收；
- 知识起草、会签、发布意图、查询和依据链查看；
- Agent 生命周期、FLAi Bench、QualificationDecision 和 DeploymentBinding 治理；
- 运行异常、安全处置、审计协作、指标与领导简报；
- ExecutionRun、Artifact、Knowledge evidence 和 DeliveryBundle 的观察与末端人签。

“唯一”不承诺每个专业操作都物理留在飞书客户端。FLAi 专业执行工作台、GitHub 原生代码评审/
合并和密封安全生存通道仍是权威专业 Surface，但它们不再拥有第二套组织首页、工作收件箱或
项目治理看板。用户在飞书中发起动作，也不代表飞书可以自行决定动作成立；所有高影响动作都
必须由事实 owner 重新鉴权、检查精确版本并返回可验证 receipt。

若“唯一中枢”被解释为“所有数据、状态、权限和审计都落进飞书”，结论是 **NO**；那会形成
第二控制面、双写冲突和不可验证的人签。正确形态是**单一人机中枢、联邦事实所有权**。

### 1.1 方案比选

| 方案 | 优点 | 致命代价 | 结论 |
|---|---|---|---|
| A：Bitable/Docs 作为所有对象的总数据库 | 快、看起来统一、低代码 | 单元格可篡改运行/签发事实；双写和 last-write-wins；无法证明 receipt/ACL/classification | 拒绝 |
| B：飞书只做导航，所有管理仍回 FLAi 独立后台 | 安全边界简单 | 用户仍学习多个入口；会议、项目、需求与 Agent 上下文割裂 | 不作为目标 |
| C：飞书唯一日常 Shell + 深 Hub Module + 联邦事实 | 用户只学一个入口；owner 边界、证据和安全仍成立 | 需要 ActorBinding、outbox、receipt、reconciliation 与最终一致性 | 采用 |
| D：飞书与 FLAi 两套完整管理中心双活 | 任一侧故障仍能操作 | 两套角色、状态和审批；冲突时无法裁决；治理成本最高 | 拒绝 |

采用方案 C，但吸收 B 的安全优点：FLAi 保留专业执行 Surface 与密封、只减权的安全生存通道，
不保留第二个日常管理中心。

## 2. 状态与诚实边界

| 能力 | 当前状态 | 已有基础 | 未证范围 |
|---|---|---|---|
| 飞书机器人、长连接、卡片、Bitable 与项目协作骨架 | `IMPLEMENTED-PARTIAL` | 独立 `feishu-assistant` 已有真实代码和测试 | 不能证明与 FLAi 身份、ACL、receipt 或生产密级闭合 |
| 飞书工作空间作为唯一组织入口 | `ACCEPTED-NOT-IMPLEMENTED` | 飞书支持网页应用、工作台能力和消息事件 | 未完成租户配置、IA、组织验收和正式发布 |
| FLAi/GitHub/飞书联邦事实图 | `ACCEPTED-NOT-IMPLEMENTED` | 当前已有稳定对象和部分读 Interface | 无 Source Ownership Registry、FactRef、outbox 与 reconciliation |
| 飞书内完成正式治理动作 | `ACCEPTED-NOT-IMPLEMENTED` | 当前卡片已有部分人工动作 | 无 ActorBinding、prepare/commit、commit recheck 和 owner receipt |
| `secrets-stackdocker` 作为运行时 App/Connector Secret value 的唯一 owner | `DECLARED-NOT-VERIFIED` | 用户已说明现有 key 已迁移 | 本轮未读取 Secret、未验证最小挂载、轮换、撤销和故障行为；不含尚未实现的全部 Safety material（Signer、3 类 owner-workload、2 类 egress operation、Fence、Trusted Time Authority/Commit Guard） |
| 飞书承载目标密级正文 | `DECLARED-NOT-VERIFIED` | 可做 ACL/脱敏投影 | 取决于组织对租户、应用和数据域的正式批准 |

任何“配置存在”“变量存在”“卡片能点”“表格已更新”都不能提升上述状态。

## 3. 单中枢不等于单数据库

### 3.1 事实 owner

| 领域 | 权威 owner | 飞书中枢拥有 | 飞书中枢不拥有 |
|---|---|---|---|
| 人员协作 | 飞书组织与协作域 | 群聊、评论、协作文档、工作空间布局、协作草稿 | FLAi capability、工程签发资格 |
| 项目协作 | Feishu Organizational Hub 协作域 | 项目计划草稿、路线图草案、关注和回告编排 | FLAi Project/OrganizationalScope、正式路线图承诺、GitHub/FLAi 结果 |
| 需求与路线图 | FLAi Demand / Roadmap Governance owner Modules | 自然语言输入与 owner 事实投影 | DemandSignal、策展事件、RoadmapVersion 与签发事实 |
| 开发工作编排 | FLAi Delivery Governance owner Module | 协作草稿、工作收件箱与 owner 事实投影 | DeliveryWorkItem 生命周期、dispatch/handoff/accept 事实 |
| 工程交付 | GitHub | 稳定引用、负责人协调、请求评审、状态解释 | commit、branch、PR approval、merge、CI 结果 |
| 正式会议与责任事项 | FLAi Meeting & Responsibility Governance owner Module | 群聊/妙记/文档来源、工作包草稿与 typed intent | OfficialMeetingRecord、ResponsibilityItem、Acceptance、Correction/Addendum |
| Agent 运行 | FLAi Control Kernel | 权限过滤后的状态、Artifact、证据和人类意图 | ExecutionRun、状态机、witness、DeliveryAttempt |
| Agent 治理 | FLAi Release/Bench/Authorization owner Module | 评审工作包、待处理事项、typed intent | QualificationDecision、DeploymentBinding、Bench gate |
| 权威知识 | Knowledge Authority；内容可来自飞书 Wiki/Docs | 起草、协作、阅读、来源版本与发布意图 | authority、effective、supersession、任务时快照判定 |
| 安全审计 | FLAi Audit / WORM | 事故协作、指派、处置说明和受限深链 | 不可变事件、审计链和执行 witness |
| 运行时 App/Connector Secret | `secrets-stackdocker` | health、可用性、版本别名和错误状态 | Secret value、轮换和撤销真相 |
| Safety 身份、时间、Fence 与签名材料 | 分离的 Safety Identity / PKI / HSM / Time owners | admission、time/fence/signing/attestation 能力健康和 receipt 验证投影 | 人的硬件私钥、Safety receipt-signing、3 类 owner-workload attestation、2 类 egress operation attestation、Policy-fence、Trusted-Time Authority/Commit-Guard material；public trust anchor 不是 Secret |
| 指标 | Metric Registry 与各事实 owner | 版本化定义的投影、解释和领导简报 | 手填完成率、个人 Token 绩效 |

### 3.2 稳定引用

跨系统只交换稳定引用、digest、source stamp 和 receipt，不复制并争夺状态：

```text
github://organization/repository/issue/143
github://organization/repository/pr/88@commit-sha

flai://demand/DEM-127@v3
flai://roadmap/RM-2026Q3@v5
flai://meeting-record/MTG-0723@official-v2
flai://execution-run/RUN-771@fact-digest
flai://capability-release/REL-019@release-digest
flai://bench-run/BENCH-224@evidence-digest
flai://deployment-binding/DB-031@version
```

真实组织名、仓库名、tenant、table、record、message 和 SecretRef 不写死在领域对象中，由
Adapter 和部署配置解析。

## 4. 产品信息架构

### 4.1 唯一顶层入口

飞书工作台只固定一个应用：**FLAi 工作空间**。

```text
FLAi 工作空间
├── 工作收件箱（默认）
├── 我的项目
│   ├── 本周目标与实质变化
│   ├── 责任事项
│   ├── GitHub 交付
│   ├── 决策与风险
│   ├── Agent 运行与产物
│   └── 会议工作包
├── 需求共创
├── FLAi 共建地图
├── 真相知识
├── 能力与 FLAi Bench
├── 治理与运行中心
├── 安全与审计
└── 指标与领导简报
```

### 4.2 工作收件箱

默认首页不展示全量项目表或管理驾驶舱，只展示：

1. 一句话 Composer：“告诉 FLAi 你想推进什么”；
2. 当前用户确实需要处理的 3–7 项；
3. 少量正在推进的项目；
4. 今日来自权威事实的实质变化；
5. 最近可查看的产物、运行、风险和人签 receipt。

输入自然语言后，Hub 可以提出候选意图：

- 发起自治会话；
- 提交需求信号；
- 导入会议工作包；
- 补充项目事实或证据；
- 查询真相知识；
- 提交成果或请求验收。

AI 只能起草候选意图。系统无法安全区分时，只问一次最小澄清，不把 PRD、责任矩阵、权限
JSON 或 Agent 配置退给普通用户填写。

### 4.3 飞书原生与内嵌 Surface

| Surface | 首选实现 | 使用场景 |
|---|---|---|
| Bot / 私聊卡片 | 简短提醒、低影响动作、回告 | 待办、异常、补证据、接收确认 |
| 工作台网页应用 | FLAi 工作空间主界面 | 工作收件箱、项目、治理、共建地图 |
| Bitable | 结构化协作草稿和高级视图 | 需求、责任事项、风险、项目关系 |
| Wiki / Docs | 叙事、知识创作和会议来源 | 规范、纪要、方案、正式内容来源 |
| 内嵌工程智能体工作台 | 专业执行 Surface | ExecutionRun、Artifact、Evidence、DeliveryBundle |
| 重新鉴权的 GitHub 深链 | 权威代码专业 Surface | diff review、PR approval、branch protection、merge |
| 工作台小组件 | 少量摘要 | 今日待办、受阻项目、关键风险 |

Bitable 不作为普通用户的默认导航，也不允许人工编辑受控状态字段。GitHub 深链不是第二组织
中枢：飞书仍承接工作发现、分派、上下文和结果回告，GitHub 只承接其权威代码操作。

## 5. 深 Module 与 Interface

### 5.1 `FeishuOrganizationalHub`

```text
interface FeishuOrganizationalHub {
  open(
    actor_attestation,
    view_request
  ) -> AuthorizedWorkspaceProjection | Rejection

  prepare(
    actor_attestation,
    typed_intent
  ) -> ReviewChallengeV1 | Rejection

  commit(
    commit_actor_attestation,
    review_challenge_ref,
    confirmation_proof_ref
  ) -> OwnerCommitReceiptV1 | EffectUnknownV1 | Rejection
}
```

这三个入口形成高 Depth：

- 调用方不学习 Feishu Card、Bitable、Docs、Wiki、Bot 和工作台差异；
- 调用方不学习 GitHub webhook、ETag、PR/CI 字段和限流；
- 调用方不学习 FLAi 的任务、Bench、Knowledge、Authorization 和审计内部表；
- actor 映射、ACL、classification、digest、幂等、receipt 和 reconciliation 集中在
  Implementation 内，保持 Locality。

HubStateStore 只保存 ingress admission、collaboration draft、inbox/outbox、projection manifest、
intent/challenge/receipt 引用和 ReconciliationCase。它不保存可独立改写的 DemandSignal、
RoadmapVersion、ExecutionRun、QualificationDecision、DeploymentBinding、KnowledgeVersion 或
GitHub delivery state。

### 5.2 `open`

`open` 返回：

```text
AuthorizedWorkspaceProjection {
  view_id
  generated_at
  projection_version
  items[]
  source_freshness[]
  source_gaps[]
  unknowns[]
  suppressed_fields[]
  next_cursor
}

ProjectionItem {
  canonical_ref
  title
  display_state
  source_owner
  source_version
  fact_digest
  reality              REAL | MOCK | TEST | UNKNOWN
  value_state          measured | unknown | suppressed | stale
  classification
  observed_at
  allowed_intents[]
  evidence_refs[]
}
```

不变量：

- `allowed_intents` 仅用于显示；`prepare/commit` 仍重新授权；
- source freshness 不足时显示 stale/unknown，不沿用旧绿；
- ACL 或 classification 无法解析时收容、脱敏或拒绝；
- 普通群卡片不发送敏感正文；
- 深链每次重新鉴权，知道对象 ID 不赋予读取权。

### 5.3 `prepare`

`typed_intent` 是版本化 tagged union：

```text
HubIntent {
  intent_id
  intent_type
  schema_version
  resource_kind
  target_ref
  expected_source_version
  expected_digest
  payload_ref
  payload_version
  payload_digest
  payload_classification
  project_scope
  reason
  idempotency_key
  expires_at
}
```

`actor_attestation` 不是客户端可填写对象，而是 admission layer 验证后生成的 opaque
`ActorAttestationV1` 引用。其规范化记录绑定：

```text
tenant_ref + app_ref + feishu_subject_ref + internal_actor_ref
+ actor_binding_version + responsibility_scope_digest
+ credential_epoch + authorization_epoch_snapshot
+ assurance_profile + assurance_evidence_ref + authenticated_at
+ audience + purpose + channel_binding + admission_ref
+ challenge_id_if_commit + challenge_digest_if_commit
+ prepared_command_digest_if_commit + nonce_digest_if_commit
+ confirmation_proof_ref_if_commit + confirmation_proof_digest_if_commit
+ confirmation_mode_if_commit
```

HubIntent 中的 `payload_ref` 只能指向不可变内容；prepare 必须重读 payload 并验证 version、
digest 和 classification，不能相信卡片回传正文。`resource_kind` 由 server-side target
resolver 从 `target_ref` 得到并与 intent schema 交叉验证，客户端自报值不能参与 owner 路由。

允许的意图包括：

```text
Demand
  SubmitDemandSignal
  AppendDemandEvidence
  CurateDemandCandidate
  MergeDemandCandidate
  SplitDemandCandidate

Roadmap
  PrepareRoadmapVersion
  RecordDomainReview
  RecordSecurityReview
  SignRoadmapVersion
  DeferDemandCandidate

ProjectGovernance
  BindCollaborationProject
  SuspendProjectContextBinding

Development
  CreateDeliveryWorkItem
  FreezeDeliveryWorkScope
  DispatchDeveloperAssistant
  PauseDeveloperAssistantRun
  ResumeDeveloperAssistantRun
  CancelDeveloperAssistantRun
  ReconcileDeveloperAssistantRun
  SubmitDevelopmentHandoff
  RequestDevelopmentRework
  AcceptDevelopmentHandoff
  CreateIssueFromCommitment
  LinkExistingIssue
  AssignDeliveryOwner
  RequestCodeReview
  ReconcileDeliveryStatus

Meeting
  CreateMeetingPackage
  ResolveReviewException
  SignMeetingRecordAndIssueResponsibilities
  AcknowledgeResponsibilityItem
  SubmitResponsibilityResult
  RequestResponsibilityRework
  AcceptResponsibilityResult
  SubmitCorrectionOrAddendum

Knowledge
  ProposeKnowledgeVersion
  RecordPublicationReview
  SignKnowledgeVersion
  RevokeOrSupersedeKnowledgeVersion

AgentGovernance
  RequestReleaseReview
  SignQualificationDecision
  SignDeploymentBinding
  SuspendDeploymentBinding
  RequestRetirement

Security
  AcknowledgeIncident
  AssignInvestigation
  RequestRevocation
  AttachRemediationEvidence
  RequestIncidentClosure

Delivery
  AuthorizeDeliveryBundle
  RejectDeliveryBundle
```

禁止：

- `approve(object)`；
- `set_status("completed")`；
- `run_shell(command)`；
- `call_api(url, body)`；
- 客户端自报 actor、role、reviewer、signer 或 classification；
- 一个 intent 同时要求两个权威 owner 原子提交。

跨 owner 工作流拆成多个带 receipt 的 intent，不能伪装分布式原子事务。

#### Source Ownership Registry

Source ownership 不是 Hub 内部可随意改的路由表，而是由 **FLAi Architecture / Governance
Policy owner** 具名签发的权威治理事实：

```text
SourceOwnershipEntryV1 {
  entry_ref
  intent_type
  intent_schema_version
  resource_kind
  source_owner_module
  owner_port
  required_receipt_type
  required_receipt_schema_version
  receipt_verifier_ref
  receipt_verifier_version
  receipt_verifier_digest
  effect_query_port_if_external
  valid_from
  valid_until
  entry_digest
}

SourceOwnershipRegistryV1 {
  registry_schema_version
  registry_ref
  registry_epoch
  entries[]
  effective_from
  effective_until
  supersedes_registry_ref
  supersedes_registry_digest
  registry_digest
}

SourceOwnershipRegistryHeadV1 {
  head_ref                  flai://source-ownership-registry-head/main
  owner_module
  generation
  current_registry_ref
  current_registry_digest
  publication_receipt_ref
  publication_receipt_digest
  updated_at
  head_digest
}

SourceOwnershipResolutionV1 {
  observed_head_generation
  observed_head_digest
  registry_ref
  registry_digest
  entry_ref
  entry_digest
  resolution_digest
}
```

Registry publication receipt 由具备该 scope 的具名真人通过 FLAi Governance owner 签发，绑定
registry digest、epoch、effective range、supersedes 与 Head expected generation/digest；
GitHub 文件、Hub 配置、飞书 Bitable 和 Adapter 默认值都不能发布或改写它。entry key 固定为
`(intent_type, intent_schema_version, resource_kind)`；未知、零匹配、多匹配、区间重叠、
重复 key、过期、publication receipt 无效、Head 多头或任一 digest unknown 都 fail-closed。

Entry、Registry、Head 与 Resolution 均使用 `RFC8785-JCS-UTF8-NFC + SHA-256` 及独立 type
domain separator；未知字段拒绝，字符串为 NFC、时间为 UTC RFC3339、禁止浮点。entries 按上述
key 的规范化 UTF-8 byte tuple 严格升序并拒绝重复/重叠。精确规则：

```text
entry_digest = SHA-256(
  UTF8("flai.source-ownership.entry.v1\0")
  || RFC8785_JCS_UTF8(SourceOwnershipEntryV1
       excluding exactly entry_ref and entry_digest)
)
entry_ref = "flai://source-ownership-entry/" + entry_digest

registry_digest = SHA-256(
  UTF8("flai.source-ownership.registry.v1\0")
  || RFC8785_JCS_UTF8(SourceOwnershipRegistryV1
       excluding exactly registry_ref and registry_digest)
)
registry_ref = "flai://source-ownership-registry/" + registry_digest

head_digest = SHA-256(
  UTF8("flai.source-ownership.registry-head.v1\0")
  || RFC8785_JCS_UTF8(SourceOwnershipRegistryHeadV1
       excluding exactly head_digest)
)

resolution_digest = SHA-256(
  UTF8("flai.source-ownership.resolution.v1\0")
  || RFC8785_JCS_UTF8(SourceOwnershipResolutionV1
       excluding exactly resolution_digest)
)
```

`head_ref` 是固定 URI 并进入 Head digest。publication receipt 在 registry digest 形成后签发，
绑定 expected Head generation/digest 与新 registry ref/digest；它不反向进入 registry content
digest，Head 再引用该 receipt，避免摘要循环。Adapter 必须从 ref 解析并重算每层 digest，
禁止信任 detached digest。

prepare 必须从签发的 Registry Head 取得一个确定性 Resolution，并把 Head、Registry、Entry
和 expected owner/Port/receipt/verifier 全部冻结进 PreparedCommand/Challenge。commit 在消费
challenge nonce 前重读同一 Registry Head；generation/digest 或 resolution 任一漂移都使
challenge 失效并要求重新 prepare。owner receipt 只用于验证其自报字段是否等于被冻结映射：
**receipt 的 `source_owner/receipt_type/schema_version` 绝不能驱动 verifier dispatch**。

### 5.4 `ReviewChallengeV1`

低影响动作可在一次显式用户动作内完成 prepare/commit。路线图、知识、能力、部署、交付和
安全处置必须先形成不可变 `PreparedCommandV1`，再返回：

```text
PreparedCommandV1 {
  prepared_command_ref
  prepared_command_digest
  intent_id
  intent_type
  intent_schema_version
  resource_kind
  intent_digest
  payload_ref
  payload_version
  payload_digest
  payload_classification
  target_ref
  target_owner
  source_ownership_registry_head_ref
  source_ownership_registry_ref
  source_ownership_registry_digest
  source_ownership_registry_head_generation
  source_ownership_registry_head_digest
  source_ownership_entry_ref
  source_ownership_entry_digest
  expected_owner_port
  expected_receipt_type
  expected_receipt_schema_version
  expected_receipt_verifier_ref
  expected_receipt_verifier_digest
  expected_source_version
  expected_source_digest
  actor_attestation_ref
  actor_ref
  actor_binding_version
  responsibility_scope_digest
  credential_epoch
  authorization_epoch_snapshot
  authentication_assurance
  required_commit_assurance_profile_ref
  required_commit_authentication_age_max
  authorization_policy_digest
  required_reviews_digest
  gate_set_digest
  idempotency_key_digest
  nonce_digest
  prepared_at
  expires_at
}
```

`intent_digest` 覆盖整个 tagged-union intent、payload digest、target、预期 owner
version/digest 和幂等键；`prepared_command_digest` 再覆盖 prepare 时的身份、认证、授权、策略、
评审、gate、nonce 和 TTL 快照。

```text
ReviewChallengeV1 {
  challenge_id
  prepared_command_ref
  prepared_command_digest
  intent_digest
  payload_digest
  subject_ref
  target_ref
  target_owner
  source_ownership_registry_head_ref
  source_ownership_registry_ref
  source_ownership_registry_digest
  source_ownership_registry_head_generation
  source_ownership_registry_head_digest
  source_ownership_entry_ref
  source_ownership_entry_digest
  expected_receipt_type
  expected_receipt_schema_version
  expected_receipt_verifier_ref
  expected_receipt_verifier_digest
  expected_source_version
  expected_source_digest
  actor_ref
  actor_binding_version
  responsibility_scope_digest
  credential_epoch
  authorization_epoch_snapshot
  authentication_assurance
  required_commit_assurance_profile_ref
  required_commit_authentication_age_max
  authorization_policy_digest
  required_reviews_digest
  gate_set_digest
  required_responsibility
  satisfied_reviews[]
  missing_gates[]
  classification
  expires_at
  nonce_digest
  one_time_nonce
  confirmation_mode
  challenge_digest
}

ConfirmationProofV1 {
  confirmation_proof_ref
  challenge_id
  challenge_digest
  prepared_command_digest
  actor_ref
  channel_binding
  audience
  purpose
  nonce_digest
  confirmation_mode
  explicitly_confirmed_at
  expires_at
  confirmation_proof_digest
}
```

飞书内嵌页必须展示精确对象、版本、适用范围、证据、缺口、风险和动作结果，不能只显示
“是否批准”。`challenge_id + one_time_nonce` 绑定上述全部字段；任何字段、epoch、认证
assurance、对象版本、payload 或 Registry/Entry digest 漂移都使挑战失效，不能局部更新后
继续消费。

`challenge_digest` 使用
`RFC8785-JCS-UTF8-NFC + SHA-256 + "flai.hub.review-challenge.v1\0"`，覆盖
`ReviewChallengeV1` 除 `challenge_digest` 与 raw `one_time_nonce` 外的全部字段；raw nonce
只以 `nonce_digest` 进入 identity，未知字段拒绝。`ConfirmationProofV1` 使用独立
`"flai.hub.confirmation-proof.v1\0"` 覆盖除 `confirmation_proof_ref/digest` 外的全部字段，
ref 由 digest 派生。`required_commit_assurance_profile_ref` 是版本化认证政策引用，不使用
布尔 `required_step_up`；commit attestation 与 `ConfirmationProofV1` 都必须在 challenge
生成并由真人显式确认后取得，逐字绑定 challenge id/digest、prepared digest、nonce digest、
confirmation mode、actor、channel、audience 与 purpose，并满足 required profile 与 maximum
authentication age。`commit` 只能接收精确 `review_challenge_ref`，不得凭
`prepared_command_ref` 隐式选择“当前 challenge”；proof 是 admission layer 形成的 opaque
引用，不接受客户端自报字段。

挑战状态使用 `PREPARED → COMMITTING → COMMITTED | EFFECT_UNKNOWN | REJECTED | EXPIRED`
的 CAS 白名单。首次 commit 原子消费 nonce；重复提交仅当 tenant、app、actor、scope、
audience、purpose、idempotency key 和 request digest 全部相同且重新授权通过时，才返回同一
脱敏终态或 ReconciliationCase。其余重放一律拒绝，不能产生第二次 owner effect。低影响动作
即使在同一次用户手势中完成，也必须遵守相同的绑定和单次消费规则。

### 5.5 `commit`

强制顺序：

```text
验证飞书 channel attestation、tenant/app、时间窗和防重放
→ 映射 Feishu subject 到内部 ActorBinding
→ 从 owner 重读对象，禁止相信卡片回传正文
→ ACL/classification/read scope
→ 从签发的 SourceOwnershipRegistry Head 重解 intent owner/verifier
→ 与 PreparedCommand 冻结的 Head/Registry/Entry/owner/verifier 逐字比较
→ 冻结 challenge digest
→ 真人检查精确内容
→ fresh attestation + commit-time 再认证/再授权/再检查 epoch
→ 验证同一 actor、review challenge、confirmation proof、prepared/intent/payload digest、
  nonce 与要求的 step-up assurance
→ CAS 单次消费该精确 challenge nonce
→ owner 内部事实使用 owner 本地 CAS/追加式事务
→ 外部 owner 使用稳定 effect key 调度，再做 authenticated postcondition query
→ receipt 验证或 effect_unknown
→ 异步更新飞书投影
```

返回：

```text
OwnerCommitReceiptV1 {
  receipt_type
  receipt_schema_version
  source_owner
  attesting_adapter_or_workload
  attesting_adapter_version
  verification_method
  verification_policy_digest
  intent_id
  intent_digest
  prepared_command_digest
  challenge_id
  challenge_digest
  confirmation_proof_ref
  confirmation_proof_digest
  source_ownership_registry_head_ref
  source_ownership_registry_ref
  source_ownership_registry_digest
  source_ownership_registry_head_generation
  source_ownership_registry_head_digest
  source_ownership_entry_ref
  source_ownership_entry_digest
  expected_receipt_verifier_ref
  expected_receipt_verifier_digest
  actor_ref
  actor_binding_version
  responsibility_scope_digest
  commit_actor_attestation_ref
  commit_actor_attestation_digest
  commit_assurance_profile_ref
  commit_assurance_evidence_ref
  commit_authenticated_at
  commit_audience
  commit_purpose
  credential_epoch
  authorization_decision_ref
  authorization_epoch_snapshot_digest
  target_ref
  expected_before_version
  expected_before_digest
  result_fact_ref
  result_fact_version
  result_fact_digest
  idempotency_key_digest
  effect_key_digest
  outcome                 COMMITTED
  owner_sequence
  trusted_observed_at
  evidence_refs[]
  owner_receipt_ref
  owner_receipt_digest
  normalized_receipt_digest
}

EffectUnknownV1 {
  intent_id
  intent_digest
  prepared_command_digest
  challenge_id
  challenge_digest
  confirmation_proof_digest
  actor_ref
  target_ref
  owner_system
  source_ownership_registry_head_ref
  source_ownership_registry_ref
  source_ownership_registry_digest
  source_ownership_registry_head_generation
  source_ownership_registry_head_digest
  source_ownership_entry_ref
  source_ownership_entry_digest
  expected_receipt_verifier_ref
  expected_receipt_verifier_digest
  idempotency_key_digest
  effect_key_digest
  owner_effect_attempt_ref_if_any
  owner_effect_attempt_digest_if_any
  last_known_owner_fact_ref
  reconciliation_case_ref
  reason_code
  outcome                 EFFECT_UNKNOWN
  retry_disposition       DO_NOT_REPLAY
  observed_at
}
```

Receipt Verifier 必须先按 PreparedCommand 冻结的 Registry Head/Registry/Entry 选择
`expected_receipt_verifier_ref + digest`，再要求 receipt 的
`source_owner + receipt_type + schema_version` 与该 Entry 逐字相等；绝不按 receipt 自报字段
选择验证器。它验证上述全部绑定，包括 commit attestation 的 actor 与 prepare actor 完全相同、
attestation 与 confirmation proof 都绑定精确 challenge/digest/nonce/confirmation mode，
attestation 的 audience/purpose 指向该 owner commit、认证发生在 challenge 之后、assurance
满足 required profile、credential/authorization epoch snapshot 当前有效。外部 owner 没有原生可验签 receipt 时，证据必须诚实标注为
“受信 Adapter attestation + authenticated postcondition query”，不能冒充 owner
cryptographic signature。`projection_state` 属于 Hub ProjectionManifest，不属于 owner
receipt。飞书“已点击”、HTTP 2xx、Bitable 更新或通知送达都不是 OwnerCommitReceipt；
无法证明 `COMMITTED` 时只能返回 `EffectUnknownV1` 或 Rejection。

## 6. 内部 Modules、Ports 与 Adapters

```text
Feishu Bot / Card / Web App / Bitable / Docs / Wiki
                         │
                         ▼
             FeishuOrganizationalHub
                         │
      ┌──────────────────┼──────────────────┐
      ▼                  ▼                  ▼
Intent Router     Projection Composer  Fact Explainer
      │                  │                  │
      ├─ ActorBinding / Channel Attestation│
      ├─ SourceOwnershipRegistryPort       │
      ├─ Authorization / Classification    │
      ├─ Idempotency / Outbox              │
      ├─ Receipt Verifier                  │
      ├─ Reconciliation Engine             │
      └─ Federated Fact Link Graph ────────┘
              │             │             │
              ▼             ▼             ▼
       FLAi Kernel Port  GitHub Port  Feishu Projection Port
              │
       SecretProviderPort
              │
       secrets-stackdocker Adapter
```

### 6.1 依赖分类

| 分类 | 依赖 | 设计 |
|---|---|---|
| In-process | intent 校验、FactRef、digest、已签发 ownership resolution 校验、classification taint、状态派生 | 收入 Hub Implementation，不额外暴露 Seam |
| Local-substitutable | 协作事件、outbox、cursor、projection cache、fact link、reconciliation case | 生产使用仓储层，测试用临时 SQLite；只通过 Hub Interface 测试 |
| Remote but owned | FLAi Kernel、Source Ownership Registry、Knowledge、Metric、Bench、`secrets-stackdocker` | 定义窄 Port；生产 Adapter 与 in-memory Adapter 构成真实 Seam |
| True external | Feishu Open Platform、GitHub、外部 WORM/SIEM | 注入 Adapter；测试使用签名 fixture 或 mock Adapter |

### 6.2 主要 Ports

```text
FLAiGovernancePort
FLAiProjectionPort
SourceOwnershipRegistryPort
DevelopmentWorkCoordinatorPort
DeveloperAssistantPort
GitHubDeliveryPort
FeishuSurfacePort
FeishuEventPort
KnowledgeSourcePort
AuditReadPort
SecretProviderPort
```

每个 Port 都必须有生产与测试 Adapter。Feishu SDK 对象、GitHub 字段和 Secret value 不得穿过
这些 Seam 进入领域 Module。

```text
interface SourceOwnershipRegistryPort {
  get_published_head()
    -> SourceOwnershipRegistryHeadV1 | RegistryUnavailable | Rejection

  resolve(
    source_ownership_registry_head_ref,
    source_ownership_registry_head_digest,
    intent_type,
    intent_schema_version,
    resource_kind
  ) -> SourceOwnershipResolutionV1 | NoMatch | Ambiguous | Rejection
}
```

Port 只读取 FLAi Governance owner 已签发的 Head/Registry，不允许 Hub/Adapter 临时添加
fallback mapping。prepare 与 commit 都验证 publication receipt、Head/Registry/Entry digest；
返回 `NoMatch/Ambiguous/Unavailable` 时不调度 owner。

## 7. 身份、ACL 与 classification

### 7.1 ActorBinding

```text
ActorBinding {
  tenant_ref
  app_ref
  feishu_subject_ref
  internal_actor_ref
  binding_version
  responsibilities[]
  scopes[]
  clearance
  credential_epoch
  valid_from
  valid_until
  status
}
```

约束：

- `open_id` 对应用有作用域，不能脱离 tenant/app 使用；
- display name 不作为身份；
- 管理员白名单不能代替职责、对象 scope 和 clearance；
- 成员离职、停用、职责变更或应用权限撤销必须提升 epoch 并使旧 challenge 失效；
- 群成员关系不是项目授权；
- 同一人兼任多个职责时，每次 intent 仍记录其当前职责和作用域。

### 7.2 Classification Projection

```text
effective_content_classification =
  join(source_classification, derived_taint, projection_policy_floor)

projection_allowed =
  flows_to(effective_content_classification, target_space_ceiling) is True
  and audience_policy_allows(source_acl, target_audience) is True
  and projection_policy_allows(content_kind, target_space, target_audience) is True
```

`target_space_ceiling` 是承载上限，不参与内容密级 join。实际规则不能用数值 `max` 猜测，
必须由版本化 classification lattice 与独立 `can_project` 判定实现；三个条件都必须显式为
`True`，`False` 或 `Unknown` 都不得投影正文。ProjectionManifest 必须记录 lattice/policy
version、target audience digest 和 target space ceiling。标题、计数、对象存在性与聚合结果
也要分别分类；redaction 不能替代 source authorization。若：

- source classification unknown；
- 飞书空间 ceiling 不足；
- ACL 不能映射；
- 内容可能反推受限对象存在；

则正文不得进入飞书。允许的结果是：

- 脱敏摘要；
- 仅稳定引用；
- `suppressed` 占位；
- 对无权主体返回不泄露存在性的拒绝。

“所有管理都在飞书”只承诺交互入口；在正式密级批准前，不承诺所有正文复制到飞书。

### 7.3 协作项目与授权 Project 的单向映射

飞书项目、群或 Bitable 记录是协作容器；对象授权只认 FLAi Project Directory 拥有的
`Project/OrganizationalScope/ProjectMembership/ProjectContextBinding`。Hub 只有只读解析
Port，不拥有或直接写 binding：

```text
interface ProjectDirectoryPort {
  resolve_context_binding(
    collaboration_project_ref,
    actor_ref,
    as_of
  ) -> AuthorizedProjectContext | Stale | Rejection
}
```

`BindCollaborationProject` 与 `SuspendProjectContextBinding` 虽可从飞书提交 typed intent，
仍必须由 FLAi Project Directory 的具名职责、prepare/commit 和 OwnerCommitReceiptV1 形成
新版本。两者通过版本化单向绑定连接：

```text
ProjectContextBinding {
  binding_id
  binding_version
  collaboration_project_ref
  collaboration_project_version
  authorized_project_scope_ref
  authorized_project_scope_version
  authorized_project_scope_digest
  source_acl_digest
  mapping_policy_digest
  status
  verified_at
  expires_at
}
```

约束：

- 创建飞书群、项目、表格行或加入群聊，绝不创建或修改 `ProjectMembership`；
- 飞书项目改名只更新显示名，不改变 `authorized_project_scope_ref`；
- 飞书项目归档会停止该协作入口的新 intent，但不删除、撤销或重写 FLAi/GitHub 历史事实；
- 成员、ACL 或 scope 漂移时 binding 立即 stale，`allowed_intents=[]`，重新从 Project
  Directory 验证后才可恢复；
- 一个协作项目不能用手工字段改绑到更高权限 scope；目标映射变更必须形成新的 binding
  version、FLAi Project Directory owner receipt 和审计证据；
- open/prepare/commit 都重新解析 binding；知道 collaboration ref 不赋予底层对象权限。

## 8. 核心工作流

### 8.1 需求到交付

```text
飞书自然语言需求
→ 不可变 DemandSignal
→ AI draft 预处理
→ Demand Curator 在工作收件箱策展
→ Domain/Security Reviewer 提交具名评审
→ Roadmap Owner 签发精确 RoadmapVersion
→ Delivery Owner 发起 CreateIssueFromCommitment
→ GitHub receipt
→ PR/CI/commit 投影
→ CapabilityReleasePackage + FLAi Bench
→ 具名验收与结果回告
```

GitHub Issue 关闭不等于需求解决；只有适用发布、Bench 和人类验收 receipt 完整，需求状态才能
进入已解决范围。

### 8.2 Codex、Kimi-K3 与多人开发

`DeliveryWorkItem` 由 FLAi Delivery Governance owner Module 拥有；飞书只承接工作输入、工作
收件箱、typed intent 和权威投影，GitHub 继续拥有代码事实。`DevelopmentWorkCoordinator`
组合 `DeveloperAssistantPort` 与 `GitHubDeliveryPort`，但不能写 GitHub 状态或代替人类集成
决定。

```text
interface DeveloperAssistantPort {
  dispatch(assistant_execution_envelope)
    -> AssistantDispatchReceiptV1 | EffectUnknownV1 | Rejection
  observe(assistant_run_ref)
    -> AssistantRunObservation
  pause(assistant_run_ref, expected_generation)
    -> AssistantControlReceiptV1 | EffectUnknownV1 | Rejection
  resume(assistant_run_ref, expected_generation)
    -> AssistantControlReceiptV1 | EffectUnknownV1 | Rejection
  cancel(assistant_run_ref, expected_generation)
    -> AssistantControlReceiptV1 | EffectUnknownV1 | Rejection
  query_effect(effect_key_digest)
    -> AssistantRunObservation | ConfirmedNoEffect | EffectUnknownV1
  collect_handoff(assistant_run_ref)
    -> DevelopmentHandoffV1 | Rejection
}
```

```text
AssistantDispatchReceiptV1 {
  work_item_ref
  work_item_digest
  assistant_run_ref
  versioned_executor_ref
  workload_identity_ref
  executor_adapter_version
  actual_runtime_ref
  actual_provider_model_ref_if_applicable
  repository_ref
  base_sha
  branch_worktree
  owned_scope_digest
  budget_digest
  execution_generation
  idempotency_key_digest
  effect_key_digest
  started_at
  receipt_digest
}

AssistantControlReceiptV1 {
  assistant_run_ref
  operation                PAUSE | RESUME | CANCEL
  expected_generation
  resulting_generation
  before_state
  after_state
  idempotency_key_digest
  effect_key_digest
  runtime_control_receipt_ref
  termination_or_pause_witness_ref
  observed_at
  receipt_digest
}
```

`AssistantRunObservation` 必须引用 dispatch/control receipt 与 backend/reality witness；只有 work
item 上的展示标签、模型配置或自然语言自报时，状态保持 `UNKNOWN`。

`DeliveryWorkItemV1` 至少包含：

```text
work_item_id
work_item_version
work_item_digest
human_owner
authorized_project_scope_ref
classification
source_commitment_ref
outcome_contract_ref
owned_file_scope
owned_interface_scope
frozen_sha
branch_worktree
issue_ref
pr_ref
required_checks[]
required_reviewer
concurrency_budget
time_budget
token_or_cost_budget
allowed_tools
allowed_egress
current_blocker
integration_status
```

状态机采用 CAS 白名单：

```text
DRAFT
  → READY
READY
  → DISPATCHING
DISPATCHING
  → RUNNING | EFFECT_UNKNOWN | FAILED
RUNNING
  → PAUSING | CANCELLING | HANDOFF_SUBMITTED | FAILED
PAUSING
  → PAUSED | EFFECT_UNKNOWN
PAUSED
  → RESUMING | CANCELLING
RESUMING
  → RUNNING | EFFECT_UNKNOWN
CANCELLING
  → CANCELLED | EFFECT_UNKNOWN
EFFECT_UNKNOWN
  → RECONCILING
RECONCILING
  → RUNNING | PAUSED | CANCELLED | HANDOFF_SUBMITTED | FAILED | EFFECT_UNKNOWN
HANDOFF_SUBMITTED
  → NEEDS_REWORK | ACCEPTED
NEEDS_REWORK
  → READY
ACCEPTED
  → INTEGRATION_PENDING
INTEGRATION_PENDING
  → INTEGRATED | NEEDS_REWORK | REJECTED
FAILED
  → NEEDS_REWORK | CANCELLED
REJECTED
  → NEEDS_REWORK | CANCELLED
```

未列转换默认拒绝。`ACCEPTED` 只表示具名人类 owner 接受 handoff 内容，不等于 PR approval、
merge、CI 通过、CapabilityRelease 或需求解决；`INTEGRATED` 必须回读 GitHub 权威事实。
resume 只能由 `ResumeDeveloperAssistantRun` 从已确认 PAUSED 状态发起；`EFFECT_UNKNOWN`
必须先用原 effect key 对账，不能重新 dispatch。返工形成新的 work item version/digest 和
新的 dispatch effect key，但保留原 run/handoff 证据。

每次 dispatch 冻结：

```text
versioned_executor_ref
executor_adapter_version
workload_identity_ref
repository_ref
base_sha
branch_worktree
owned_file_and_interface_scope
classification_and_data_scope
allowed_tool_action_and_egress_scope
concurrency_time_token_or_cost_budget
expected_work_item_digest
idempotency_key_digest
effect_key_digest
execution_generation
```

`versioned_executor_ref` 可以解析为 Codex、Kimi-K3 或未来执行器，但展示字段
`assistant_model=codex|kimi-k3` 不是权威事实。实际执行必须回传 workload identity、Adapter、
runtime、provider/model（适用时）、generation 和 receipt/witness；配置标签不能自证“由
Kimi-K3 完成”或“由 Codex 验证”。

`DevelopmentHandoffV1` 必须包含：

```text
handoff_schema_version = DevelopmentHandoffV1
work_item_ref + work_item_digest
assistant_run_ref + actual_runtime_receipt
base_sha
final_sha_if_committed
commit_refs[]
patch_or_diff_digest
changed_files[]
changed_interfaces[]
verification_commands[]
verification_results[]
artifact_and_evidence_refs[]
risks[]
unresolved_issues[]
recommended_next_step
handoff_digest
```

`DevelopmentHandoffV1` 是不可变 handoff core。`final_sha_if_committed` 可以为 `null`，数组顺序
按执行器提交的证据顺序保留；不得在摘要前排序、去重或丢弃失败/unknown。canonical projection
从完整对象中**仅删除** `handoff_digest`；所有字符串必须为 NFC，禁止浮点数与非有限数，再
执行 RFC 8785 JCS。摘要规则固定为：

```text
handoff_digest =
  lowercase_hex(
    SHA-256(
      ASCII("flai.development-handoff.v1") || 0x00
      || RFC8785_JCS_UTF8(
           DevelopmentHandoffV1 excluding exactly handoff_digest
         )
    )
  )
```

verifier 必须从 raw object 删除精确字段后重算，不信任执行器或客户端自报 digest。
`handoff_schema_version`、work item/run/runtime receipt、base/final SHA、commit/diff、变更
scope、验证命令与结果、证据、风险、未决项和下一步全部进入摘要。handoff 任一字段变化都
生成新 core/digest；旧 core 保留，不得原地改写。该无钥摘要只证明内容绑定，不证明执行器
身份、runtime 真实性、人类接受、GitHub approval 或 merge；这些仍分别依赖 dispatch/runtime
receipt、reality witness、具名人类决定和 GitHub 权威回读。

提交 handoff 不授予集成权。具名人类 owner 在飞书工作收件箱接收摘要与证据，可以请求返工或
接受 handoff；代码 diff review、PR approval 和 merge 仍进入 GitHub 原生 Surface，由
CODEOWNERS、branch protection 和 CI 裁决。GitHub 回读后，Coordinator 才更新
`INTEGRATION_PENDING → INTEGRATED | REJECTED`。

运行规则：

- 每个交付项只有一个具名人类 owner；
- 每个 Assistant run 使用独立 branch/worktree；并发 scheduler 对文件与 Interface scope
  做冲突检测，不允许两个活动 run 同时拥有重叠写范围；
- “Codex 主实现、Kimi-K3 偏 UI/UX”只是可编辑的推荐分工，不是模型名驱动的授权规则；实际
  eligibility 由版本化 executor qualification、项目 scope、密级、egress 和预算共同决定；
- AI 可以互审，但不能成为 CODEOWNER、批准者、merge owner 或发布 signer；
- dispatch、pause、resume、cancel、reconcile、handoff、rework 与 accept 都是 typed
  intent，绑定幂等键、epoch 和 work item digest；任何 dispatch/control 远端响应不明均进入
  `EFFECT_UNKNOWN`，未经原 effect key 对账不得恢复、取消或换键重派；
- 飞书可以发起认领、请求评审和生成工作包，但 commit、PR、CI、approval 和 merge 事实只
  回读 GitHub；
- 共享 Interface 漂移后，依赖工作必须重新冻结 SHA。

### 8.3 Agent 运行与交付

ExecutionRun 卡片只投影冻结观察合同：

- 当前实际 backend；
- `REAL/MOCK/TEST/UNKNOWN` witness；
- `waiting_review/completed/failed/cancelled` 的权威事实；
- 当前最值得观察的 Artifact、工具结果或知识依据；
- 取消、恢复和缺证据状态；
- DeliveryBundle 与待交付动作。

卡片、Bot 或 Bitable 不得根据自然语言声称“进展显著”“已完成”或显示假百分比。

### 8.4 会议工作包

```text
群聊／妙记／文档来源
→ 会后导入
→ 会议工作包草稿
→ 例外审阅
→ 会议负责人签发精确工作包
→ 同一 owner-local transaction 创建正式会议记录与全部初始责任事项
→ 接收确认
→ 成果提交
→ 责任事项验收
```

全流程从飞书编排。`SignMeetingRecordAndIssueResponsibilities` 只提交给同一个 FLAi
Meeting & Responsibility Governance owner Module；该 owner 在一个本地事务中创建
OfficialMeetingRecord、全部具备五个必需字段的初始 ResponsibilityItem、Audit outbox 与
OwnerCommitReceiptV1。任一责任项不完整、CAS 失败或 owner receipt 未验证时，全部不生效，
Hub 保持 `EFFECT_UNKNOWN/REJECTED`，不得宣称“会议闭环”。通知失败只影响送达并进入对账，
不回滚已确认的 owner 事实。接收确认、成果提交、返工与验收使用后续独立 typed intent。
AI 推断仍是推断候选。

### 8.5 权威知识

飞书 Wiki/Docs 是 `KnowledgeSourceAdapter`：

```text
source document version
+ immutable content digest
+ source ACL/classification
+ authority class
+ effective scope/time
+ named signer
+ publication receipt
```

已签版本再次编辑时，新内容自动成为草稿候选，不能覆盖原 KnowledgeItem。可信回答只引用当前
有效且适用的版本和精确来源锚点。

### 8.6 Agent 治理

治理人员在飞书完成评审仪式，但 FLAi owner Module 决定事实是否成立：

```text
release review work package
→ qualification intent
→ FLAi re-auth / exact release + Bench digest / role separation
→ QualificationDecision receipt
→ deployment binding intent
→ FLAi scope / actor / project / data / action / TTL recheck
→ DeploymentBinding receipt
```

Bitable 状态、卡片点击和 Bench 综合分均不能代替这些 receipt。

## 9. Bitable、Wiki 与受控字段

### 9.1 字段分类

每个飞书工作对象字段必须属于以下一类：

| 类别 | 可编辑者 | 例子 |
|---|---|---|
| `collaboration_input` | 有权用户 | 需求输入草稿/source payload、说明、评论、附件、候选责任人 |
| `draft_assistance` | AI 或用户 | 摘要、聚类建议、候选验收标准 |
| `governed_command_input` | 具名职责者 | 签发理由、适用范围、退回说明 |
| `authoritative_projection` | 仅 Projection Module | GitHub、ExecutionRun、Bench、发布、签发状态 |
| `derived_metric` | 仅 Metric Projection | 版本化指标、freshness、coverage |

`authoritative_projection` 和 `derived_metric` 即使在 Bitable UI 中出现，也不能直接编辑。
`SubmitDemandSignal` 成功后，FLAi Demand owner 生成新的不可变 DemandSignal 与 receipt；
之后继续编辑飞书草稿只会形成新 source revision，不会改写既有 DemandSignal。

### 9.2 投影最小元数据

```text
canonical_ref
source_owner
source_version
source_digest
classification
projection_policy_version
classification_lattice_version
target_audience_digest
target_space_ceiling
observed_at
freshness_deadline
source_evidence_ref
owner_receipt_ref_if_applicable
projection_state
```

所有投影都必须有 `source_evidence_ref`。只有治理状态变迁需要
`owner_receipt_ref_if_applicable`；ExecutionRun 使用 witness，GitHub 只读事实使用 verified
provider state/receipt，知识使用 source/version/authority evidence。缺少不适用的 owner
receipt 不会自动变 stale；缺少该类事实必需的 transition receipt 时，该变迁不得显示生效。

## 10. SecretProviderPort

### 10.1 普通运行时 Secret Owner 与独立 Safety 签名域

`secrets-stackdocker` 是运行时 App/Connector Secret value 的唯一 owner。Hub、Feishu
Adapter、GitHub Adapter 和 FLAi Connector 仅声明：

```text
SecretRef {
  provider
  scope
  name
  version_selector
  purpose
}
```

文档中的 `secret://provider/scope/name@version` 只是序列化形态示例，不代表真实名称。

### 10.2 Safety 控制材料引用

Safety signing、三类 Owner workload attestation、两类 Egress workload attestation、
Policy fence attestation、Trusted Time Authority signing 与 consumer-local Trusted
Time Commit Guard material 均不经
`SecretProviderPort`，只以不可导出 key handle 和公共验证材料引用进入 sealed Safety
composition root：

```text
SafetySigningMaterialRef {
  owner                     SAFETY_IDENTITY_PKI_HSM
  key_handle_ref
  key_epoch
  purpose                   SAFETY_RECEIPT_SIGNING
  algorithm_policy_ref
  trust_anchor_ref
  trust_anchor_epoch
  revocation_status_ref
  not_before
  not_after
}

SafetyOwnerWorkloadAttestationMaterialRefV1 {
  material_ref
  material_digest
  owner_ref
  workload_identity_ref
  operation_code            COORDINATOR_RESERVATION_VERIFY
                          | TARGET_OWNER_SIGNING_REQUEST
                          | POLICY_ALIAS_TRANSITION
  key_handle_ref
  key_epoch
  audience
  purpose
  attestation_policy_ref
  attestation_policy_digest
  key_failure_domain
  trust_anchor_ref
  trust_anchor_epoch
  revocation_status_ref
  not_before
  not_after
}

SafetyEgressWorkloadAttestationMaterialRefV1 {
  material_ref
  material_digest
  owner                     SAFETY_EGRESS_WORKLOAD_IDENTITY
  workload_identity_ref
  egress_boundary_ref
  operation_code            EGRESS_BOUNDARY_IDENTITY
                          | EGRESS_WIRE_REQUEST_BUFFER
  key_handle_ref
  key_epoch
  audience                  SAFETY_PROVIDER_SEND_BOUNDARY
  purpose
  attestation_policy_ref
  attestation_policy_digest
  key_failure_domain
  trust_anchor_ref
  trust_anchor_epoch
  trust_anchor_digest
  revocation_status_ref
  not_before
  not_after
}

SafetyPolicyFenceMaterialRefV1 {
  owner                     SAFETY_POLICY_FENCE_AUTHORITY
  key_handle_ref
  key_epoch
  purpose                   SAFETY_POLICY_FENCE_WITNESS
  policy_role
  trust_anchor_ref
  revocation_status_ref
}

SafetyTrustedTimeMaterialRefV1 {
  material_ref
  material_digest
  owner                     SAFETY_TRUSTED_TIME_AUTHORITY
  operation_code            TIME_INTERVAL_ATTEST | EPOCH_TRANSITION_CONTINUITY
  key_handle_ref
  key_epoch
  purpose                   SAFETY_TRUSTED_TIME_ATTEST
                          | SAFETY_TRUSTED_TIME_EPOCH_TRANSITION
  time_policy_ref
  time_policy_digest
  key_failure_domain
  trust_anchor_ref
  trust_anchor_epoch
  trust_anchor_digest
  revocation_status_ref
  not_before
  not_after
}

SafetyTrustedTimeCommitGuardMaterialRefV1 {
  material_ref
  material_digest
  owner                     SAFETY_TRUSTED_TIME_COMMIT_GUARD
  consumer_owner_ref
  storage_commit_profile_ref
  storage_commit_profile_digest
  trusted_elapsed_source_ref
  trusted_elapsed_source_digest
  trusted_elapsed_source_epoch
  operation_code            TRUSTED_TIME_PRECOMMIT_CONSUME
  key_handle_ref
  key_epoch
  purpose                   PROVE_TRUSTED_TIME_FRESH_AT_LINEARIZATION
  key_failure_domain
  trust_anchor_ref
  trust_anchor_epoch
  trust_anchor_digest
  revocation_status_ref
  not_before
  not_after
}
```

`SafetyOwnerWorkloadAttestationMaterialRefV1.material_digest` 使用
`SHA-256("flai.safety.owner-workload-attestation-material.v1\0" ||
RFC8785_JCS_UTF8(object excluding material_ref/material_digest))`，`material_ref` 由 digest
派生；同一 owner/workload 只能为声明的 operation/audience/purpose 使用。Coordinator、
target owner 与 Policy owner 必须是三个不同 material identity/failure-domain 实例，
verifier 对 owner、operation 与 subject 做精确匹配，不能仅因共用 trust anchor 而允许跨域
代签。每份 `SafetyOwnerWorkloadAttestationV1` 的 canonical identity 必须包含 material
ref+digest；Verifier Port 接收 expected material、解析并重算 policy/failure-domain/
key-epoch/revocation/trust/validity，`material_binding_valid` 非 `True` 一律 fail-closed。

`SafetyEgressWorkloadAttestationMaterialRefV1.material_digest` 使用
`SHA-256("flai.safety.egress-workload-attestation-material.v1\0" ||
RFC8785_JCS_UTF8(object excluding material_ref/material_digest))`，ref 由 digest 派生；
Boundary identity 与 Wire-buffer 两个 operation 必须是不同
material identity，不能跨 operation 代签。它不强制使用独立 HSM，但必须按组织政策使用
短时、不可导出、可撤销并可远程验证的 workload identity/TPM/TEE/KMS key，且与普通
App/Connector credential 分离。

`SafetyTrustedTimeCommitGuardMaterialRefV1.material_digest` 使用
`SHA-256("flai.safety.trusted-time-commit-guard-material.v1\0" ||
RFC8785_JCS_UTF8(object excluding material_ref/material_digest))`，ref 由 digest 派生。
Commit Guard 是 consumer owner 的 privileged storage-commit participant；它以独立、短期、
不可导出并可撤销的 identity 访问受信 monotonic elapsed source，只为一个
`consumer_owner_ref + storage_commit_profile + TRUSTED_TIME_PRECOMMIT_CONSUME` operation
工作。它不是普通 workload credential，也不能被业务代码调用为任意签名 oracle。无法把
Guard 检查与 owner-local store 的线性化点绑定时，该 owner 的 Safety commit 必须
`NOT-IMPLEMENTED/NO-GO`，不得退化为“调用前看一次时间”。

`SafetyTrustedTimeMaterialRefV1.material_digest` 使用
`SHA-256("flai.safety.trusted-time-material.v1\0" ||
RFC8785_JCS_UTF8(object excluding material_ref/material_digest))`，ref 由 digest 派生。
`TIME_INTERVAL_ATTEST` 与 `EPOCH_TRANSITION_CONTINUITY` 必须使用不同 material identity 与
failure domain；在线 time-signing key 无权自行批准自己的 epoch/key/source/trust 迁移。
EpochTransition 只能由预置 continuity material 签名，且 verifier 必须精确匹配 material
operation/purpose/policy/epoch/revocation/trust。

两个 workload-attestation verifier 都是 Trusted Time 的独立 consumer。每次验证必须消费
调用参数中 exact `SafetyTrustedTimeAttestationV1 ref+digest`，在 verifier 自己的 durable
store 以 CAS 更新 `SafetyTrustedTimeCheckpointV1`，并把该 time attestation 与 checkpoint
的 exact ref+digest 冻结进 verification；不能只留下 `trusted_time_valid=True`、本机
`verified_at` 或一个可由调用者填写的 freshness deadline。后续 signer、Fence Authority、
Reservation verifier、egress owner 与 SendReceipt verifier 必须解析 verification 内冻结
的 exact time/checkpoint，逐字匹配 verifier owner、authority epoch/counter、trust snapshot
与 freshness；不得用另一份时间证明替换、重放旧 checkpoint 或用 host clock 补齐。

这些引用都不含 private key。key handle、epoch、用途、有效期或吊销状态任一不匹配均拒绝；
trust anchor 的分发、轮换和回滚必须形成版本化、可离线验证的证据。上述高保障 key 可在满足
组织隔离政策的独立 HSM 分区/设备中实现；所有 Safety material 都不得来自普通 workload
identity、应用进程自签 key、Coordinator/Policy 数据库、`SecretProviderPort` 或
`secrets-stackdocker`，也不得互相代签。

### 10.3 不变量

- 不读取、复制、展示或记录 Secret value；
- App ID 若被组织定义为非 Secret，也仍按敏感配置处理；
- Secret 只在最终 Connector 边界按最小 scope 注入；
- Adapter 不得把 Secret 传给 Agent Runtime、LLM prompt、Tool stdout 或前端；
- resolution 失败、版本 unknown、provider 不可达或 Secret revoked 时 fail-closed；
- 禁止回退到旧 `.env`、硬编码值、Git 历史值或全局 Keychain；
- 轮换后 token cache、长连接、旧凭据和 authorization epoch 必须失效；
- 审计只记录 SecretRef identity/version、purpose、result 和 witness，不记录值；
- bootstrap、unseal 和 recovery 凭据必须与运行时 Connector Secret 分离。
- 上述 Safety material 不得由普通 SecretProviderPort 解析，Safety
  Coordinator/Time/Fence/Signer/Verifier 不得回退 App/Connector key 或共享其 failure
  domain。F0 必须具名冻结每类 owner、failure-domain、key epoch/吊销/trust policy 与
  fixture/drill 规格；任一合同仍未决即阻断 F0。真实 key、runtime 和 stack-outage witness
  保持 `DECLARED-NOT-VERIFIED`，在对应 D6/D7/D8 + F4 前闭合，不用实现冒充 F0 设计评审。

### 10.4 仍需验证

“key 已迁移”解决了存放位置，但正式准入还需要证明：

1. 旧值已撤销或确认不再有效；
2. 每个 Adapter 只有最小 SecretRef；
3. Secret 不进入容器环境转储、日志、crash dump 或子进程；
4. 轮换和吊销在冻结 SLA 内生效；
5. provider 不可用时无明文 fallback；
6. 访问、拒绝和轮换有不可变审计；
7. backup/restore 不导出明文 Secret。

## 11. 失败、对账与安全生存

### 11.1 稳定失败码

| 错误码 | 语义 | 默认行为 |
|---|---|---|
| `HUB_CHANNEL_ATTESTATION_INVALID` | 飞书事件、tenant、app 或时间窗无效 | 拒绝并审计 |
| `HUB_REPLAY_DETECTED` | event/nonce 已消费 | 仅关联维度完全相同且重新授权通过时返回脱敏原终态；否则拒绝/冲突 |
| `HUB_ACTOR_UNBOUND` | 飞书身份未绑定内部 actor | 禁止治理动作 |
| `HUB_REAUTH_REQUIRED` | 高影响动作认证 assurance 不足 | 重新确认 |
| `HUB_POLICY_DENIED` | 当前主体、职责或 scope 不允许 | fail-closed |
| `HUB_CLASSIFICATION_UNKNOWN` | 分类或 space ceiling 无法确定 | 写入拒绝；读取收容 |
| `HUB_SOURCE_VERSION_CONFLICT` | expected version/digest 漂移 | 刷新后重新 prepare |
| `HUB_PREPARED_BINDING_STALE` | actor binding、epoch、assurance、policy/gate 或 payload digest 漂移 | challenge 失效，完整重新 prepare |
| `HUB_REQUIRED_REVIEW_MISSING` | 领域、安全或职责分离门不满足 | 拒绝 commit |
| `HUB_SOURCE_UNAVAILABLE` | owner 明确未执行且不可达 | 同键安全重试 |
| `HUB_RECEIPT_INVALID` | receipt 缺失、验签失败或不匹配 | 不投影成功 |
| `HUB_EFFECT_UNKNOWN` | 外部效果可能发生但无法确认 | 禁止重放，进入对账 |
| `HUB_EVENT_GAP` | source sequence 存在缺口 | 标 stale，启动 reconcile |
| `HUB_PROJECTION_STALE` | 投影超过 freshness | amber/unknown；禁止依赖其签发 |
| `HUB_IDEMPOTENCY_CONFLICT` | 同键对应不同 intent digest | 拒绝并安全审计 |
| `HUB_SECRET_REF_UNAVAILABLE` | Secret provider 无法解析 | 外部调用 fail-closed |
| `HUB_RECONCILIATION_REQUIRED` | Hub 与 owner 事实冲突 | 不自动选择最新值 |
| `HUB_PRIVACY_SUPPRESSED` | 聚合可能反推个人或受限对象 | 返回抑制语义 |
| `SAFETY_ADMISSION_SUBJECT_MISMATCH` | admission kind/subject/nonce/replay domain 与当前动作不一致 | 拒绝且不消费目标 nonce |
| `SAFETY_ADMISSION_ALREADY_CONSUMED` | admission digest 已绑定另一 subject 或 reservation | 冲突；禁止换键或跨 phase 重试 |
| `SAFETY_RESERVATION_INVALID` | Reservation provenance/三条 consumption/attestation/binding 任一非 True | 拒绝；孤儿或伪造对象不得形成 anchor |
| `SAFETY_RESERVATION_EXPIRED` | 首次 owner anchor 时 Reservation/verification 已过期 | 不启动 effect；保持 consumed 并对账 |
| `SAFETY_TRUSTED_TIME_UNAVAILABLE` | Time Authority、签名、source/head/key/revocation、区间或 freshness 任一 Unknown | 禁止 TTL-sensitive anchor/send；禁止 host-clock/cache fallback |
| `SAFETY_TIME_ROLLBACK` | authority epoch/counter/predecessor/checkpoint 回拨、gap、fork 或无签 epoch transition | 拒绝并安全审计；不得签发新时间证据 |
| `SAFETY_DISPATCH_DEADLINE_EXPIRED` | Claim 后进入唯一 provider send boundary 时 attested upper bound 已到期 | `EXPIRED_NOT_SENT`，provider call 为 0；重新授权需新 subject |
| `SAFETY_PROVIDER_SEND_UNKNOWN` | CallAttempt 已落账但无 verified ProviderSendReceipt | `effect_unknown + DO_NOT_REPLAY`；只按原 effect key 查询 |
| `CHALLENGE_STATE_NOT_READY` | Challenge 已创建但唯一 Coordinator 尚未初始化/解析 current state revision | fail-closed；只按原 reservation 补 genesis 或对账 |
| `SAFETY_POLICY_POINTER_HISTORY_GAP` | expected/observed PointerRevision 无法按 ref+digest 重算 | fail-closed；不得信任 current alias 猜测历史 |
| `SAFETY_POLICY_DRIFT` | alias CAS/fence epoch/witness 或 signer PRE/POST PointerRevision/Head/Bundle 不一致 | 不发布 Envelope；受限封存/销毁签名字节并重新 prepare |

### 11.2 Reconciliation

每个外部 effect 使用稳定幂等键。若请求可能成功但 receipt 丢失：

1. 记录 `effect_unknown`；
2. 禁止用户重复点击产生新键；
3. 通过 owner 的查询 Interface 对账；
4. 找到匹配 effect 后补 receipt；
5. 仅在该 owner 的 typed policy 明确允许、且不存在 SafetyProviderCallAttempt 或其他
   “可能已发送” witness 时才可原键重试；Safety CallAttempt 无 receipt 永不重发；
6. 冲突时进入具名 ReconciliationCase，不以最后写入时间自动裁决。

### 11.3 安全生存通道

安全生存通道是独立于 `FeishuOrganizationalHub` 的窄 Interface，使用 sealed composition
root，不经过 Bot、卡片、Bitable、HubStateStore、普通飞书 SSO 或正常 Connector Secret：

```text
interface SafetyAdmissionReservationPort {
  reserve_prepare(
    prepare_admission_subject_ref,
    prepare_admission_subject_digest,
    prepare_actor_admission_refs[2],
    prepare_actor_admission_digests[2]
  ) -> SafetyAuthorizationReservationV1 | Rejection

  reserve_commit(
    safety_challenge_ref,
    safety_challenge_digest,
    expected_challenge_state_revision_ref,
    expected_challenge_state_revision_generation,
    expected_challenge_state_revision_digest,
    expected_challenge_state_head_digest,
    commit_actor_admission_refs[2],
    commit_actor_admission_digests[2]
  ) -> SafetyAuthorizationReservationV1 | Rejection

  reserve_policy_publication(
    policy_publication_challenge_ref,
    policy_publication_challenge_digest,
    policy_actor_admission_refs[2],
    policy_actor_admission_digests[2]
  ) -> SafetyAuthorizationReservationV1 | Rejection

  resolve_and_verify_reservation(
    safety_authorization_reservation_ref,
    safety_authorization_reservation_digest,
    expected_reservation_kind,
    expected_subject_ref,
    expected_subject_digest,
    expected_action_projection_digest,
    expected_owner_ref,
    expected_idempotency_key_digest,
    expected_effect_key_digest_if_applicable,
    trusted_time_attestation_ref,
    trusted_time_attestation_digest
  ) -> SafetyAuthorizationReservationVerificationV1 | Rejection
}

interface SafetyTrustedTimeAuthorityPort {
  read_and_attest(
    request_nonce_digest,
    subject_ref,
    subject_digest,
    purpose,
    required_time_policy_ref,
    required_time_policy_digest
  ) -> SafetyTrustedTimeAttestationV1 | TimeUnavailable | Rejection

  resolve_and_verify(
    trusted_time_attestation_ref,
    trusted_time_attestation_digest,
    expected_subject_ref,
    expected_subject_digest,
    expected_purpose
  ) -> SafetyTrustedTimeAttestationV1 | Rejection

  resolve_and_verify_epoch_transition(
    epoch_transition_ref,
    epoch_transition_digest,
    expected_time_authority_ref,
    expected_predecessor_epoch_or_null,
    expected_successor_epoch
  ) -> SafetyTrustedTimeEpochTransitionV1 | Rejection
}

interface SafetyTrustedTimeCommitGuardPort {
  begin_commit_guard(
    commit_guard_material_ref,
    commit_guard_material_digest,
    consumer_owner_ref,
    owner_transaction_nonce_digest,
    commit_subject_type,
    commit_subject_ref,
    commit_subject_digest,
    expected_purpose,
    trusted_time_attestation_ref,
    trusted_time_attestation_digest
  ) -> SafetyTrustedTimeCommitLeaseV1 | Rejection

  consume_at_commit(
    owner_local_transaction_context,
    commit_lease_ref,
    commit_lease_digest,
    expected_predecessor_checkpoint_ref_or_null,
    expected_predecessor_checkpoint_digest_or_null
  ) -> SafetyTrustedTimeCheckpointV1 | Rejection
}

interface SafetyOwnerWorkloadAttestationVerifierPort {
  verify_owner_workload_attestation(
    owner_workload_attestation_ref,
    owner_workload_attestation_digest,
    expected_owner_ref,
    expected_material_ref,
    expected_material_digest,
    expected_operation_code,
    expected_subject_ref,
    expected_subject_digest,
    expected_audience,
    expected_purpose,
    trusted_time_attestation_ref,
    trusted_time_attestation_digest
  ) -> SafetyOwnerWorkloadAttestationVerificationV1 | Rejection
}

interface SafetyEgressWorkloadAttestationVerifierPort {
  verify_egress_workload_attestation(
    attestation_type,
    attestation_ref,
    attestation_digest,
    expected_material_ref,
    expected_material_digest,
    expected_operation_code,
    expected_egress_boundary_ref,
    expected_provider_ref,
    expected_provider_route_digest,
    expected_provider_request_ref_if_wire,
    expected_provider_request_digest_if_wire,
    expected_provider_mutation_capability_ref_if_wire,
    expected_provider_mutation_capability_digest_if_wire,
    expected_boundary_attestation_ref_if_wire,
    expected_boundary_attestation_digest_if_wire,
    expected_boundary_attestation_verification_ref_if_wire,
    expected_boundary_attestation_verification_digest_if_wire,
    trusted_time_attestation_ref,
    trusted_time_attestation_digest
  ) -> SafetyEgressWorkloadAttestationVerificationV1 | Rejection
}

interface SafetyProviderMutationPort {
  prepare_send_once(
    dispatch_claim_ref,
    dispatch_claim_digest,
    expected_provider_mutation_subject_digest,
    provider_request_ref,
    provider_request_digest,
    expected_effect_key_digest,
    expected_provider_ref,
    expected_provider_route_digest
  ) -> SafetyProviderMutationCapabilityV1 | Rejection

  send_once(
    provider_mutation_capability_ref,
    provider_mutation_capability_digest,
    trusted_time_attestation_ref,
    trusted_time_attestation_digest
  ) -> SafetyProviderRawSendReceiptV1 | SafetyEffectUnknownV1 | Rejection
}

interface SafetyProviderSendReceiptVerifierPort {
  verify_raw_send_receipt(
    raw_send_receipt_ref,
    raw_send_receipt_digest,
    expected_provider_call_attempt_ref,
    expected_provider_call_attempt_digest,
    expected_provider_request_ref,
    expected_provider_request_digest,
    expected_effect_key_digest,
    expected_provider_ref
  ) -> SafetyProviderSendReceiptVerificationV1 | Rejection

  seal_verified_send_receipt(
    raw_send_receipt_ref,
    raw_send_receipt_digest,
    send_receipt_verification_ref,
    send_receipt_verification_digest
  ) -> SafetyProviderSendReceiptV1 | Rejection
}

interface SafetyPolicyFenceAuthorityPort {
  commit_alias_transition(
    alias_transition_request_ref,
    alias_transition_request_digest,
    trusted_time_attestation_ref,
    trusted_time_attestation_digest
  ) -> SafetyPolicyAliasCommitResultV1 | Rejection

  begin_signing_fence(
    policy_role,
    signing_request_ref,
    signing_request_digest,
    envelope_core_ref,
    envelope_core_digest,
    expected_signer_operation_ref,
    expected_signer_operation_digest,
    expected_current_alias_state_generation,
    expected_current_alias_state_digest,
    expected_alias_commit_fence_witness_ref,
    expected_alias_commit_fence_witness_digest,
    trusted_time_attestation_ref,
    trusted_time_attestation_digest
  ) -> SafetyPolicyFenceWitnessV1(SIGN_PRE) | Rejection

  complete_signing_fence(
    sign_pre_fence_witness_ref,
    sign_pre_fence_witness_digest,
    signing_request_ref,
    signing_request_digest,
    envelope_core_ref,
    envelope_core_digest,
    expected_signer_operation_ref,
    expected_signer_operation_digest,
    signature_bytes_digest,
    trusted_time_attestation_ref,
    trusted_time_attestation_digest
  ) -> SafetyPolicyFenceWitnessV1(SIGN_POST) | Rejection

  resolve_and_verify_witness(
    fence_witness_ref,
    fence_witness_digest,
    expected_policy_role,
    expected_witness_kind
  ) -> SafetyPolicyFenceWitnessV1 | Rejection
}

interface SafetyChallengeStatePort {
  initialize_prepared(
    prepare_reservation_ref,
    prepare_reservation_digest,
    safety_challenge_ref,
    safety_challenge_digest
  ) -> SafetyChallengeStateHeadV1 | Rejection

  advance(
    safety_challenge_ref,
    safety_challenge_digest,
    expected_state_revision_ref,
    expected_state_revision_generation,
    expected_state_revision_digest,
    expected_state_head_digest,
    transition_evidence_ref,
    transition_evidence_digest
  ) -> SafetyChallengeStateHeadV1 | Rejection
}

interface SafetySurvivalPort {
  prepare_admission_subject(
    typed_safety_command,
    expected_issuance_policy_head_ref,
    expected_issuance_policy_head_generation,
    expected_issuance_policy_head_digest,
    expected_issuance_policy_head_pointer_revision_ref,
    expected_issuance_policy_head_pointer_revision_generation,
    expected_issuance_policy_head_pointer_revision_digest,
    expected_issuance_policy_fence_epoch,
    expected_alias_commit_fence_witness_ref,
    expected_alias_commit_fence_witness_digest
  ) -> SafetyPrepareAdmissionSubjectV1 | Rejection

  prepare_safety_command(
    safety_authorization_reservation_ref,
    safety_authorization_reservation_digest,
    prepare_admission_subject_ref,
    prepare_admission_subject_digest,
    typed_safety_command
  ) -> SafetyChallengeV1 | Rejection

  commit_safety_command(
    safety_authorization_reservation_ref,
    safety_authorization_reservation_digest,
    safety_challenge_ref,
    safety_challenge_digest
  ) -> FullSafetyEffectVerifiedV1
     | LocalFenceVerifiedExternalPendingV1
     | SafetyResultInvalidatedV1
     | SafetyResultInconclusiveV1
     | SafetyEffectUnknownV1
     | Rejection
}

interface SafetyReceiptSignerPort {
  sign_owner_receipt(
    safety_signing_request_ref,
    safety_signing_request_digest,
    expected_issuance_policy_head_ref,
    expected_issuance_policy_head_generation,
    expected_issuance_policy_head_digest,
    expected_issuance_policy_head_pointer_revision_ref,
    expected_issuance_policy_head_pointer_revision_generation,
    expected_issuance_policy_head_pointer_revision_digest
  ) -> SafetySignatureEnvelopeV1 | SignerUnavailable | Rejection
}

interface SafetyReceiptVerifierPort {
  verify_owner_receipt(
    safety_owner_receipt_payload,
    safety_owner_receipt,
    safety_signature_envelope,
    required_verification_policy_bundle_ref,
    required_verification_policy_bundle_digest,
    observed_verification_policy_head_ref,
    observed_verification_policy_head_generation,
    observed_verification_policy_head_digest,
    observed_verification_policy_head_pointer_revision_ref,
    observed_verification_policy_head_pointer_revision_generation,
    observed_verification_policy_head_pointer_revision_digest
  ) -> SafetyReceiptVerificationV1 | Rejection
}

interface SafetyResultFactory {
  construct(
    safety_owner_receipt_payload,
    safety_owner_receipt,
    safety_receipt_verification,
    required_verification_policy_bundle_ref,
    required_verification_policy_bundle_digest,
    expected_verification_policy_head_ref,
    expected_verification_policy_head_generation,
    expected_verification_policy_head_digest,
    expected_verification_policy_head_pointer_revision_ref,
    expected_verification_policy_head_pointer_revision_generation,
    expected_verification_policy_head_pointer_revision_digest,
    trusted_time_attestation_ref,
    trusted_time_attestation_digest,
    expected_result_head_generation,
    expected_result_head_digest
  ) -> FullSafetyEffectVerifiedV1
     | LocalFenceVerifiedExternalPendingV1
     | SafetyResultInvalidatedV1
     | SafetyResultInconclusiveV1
     | SafetyEffectUnknownV1
     | Rejection
}

interface SafetyEffectQueryPort {
  query_original_effect(
    command_digest,
    challenge_digest,
    effect_key_digest,
    target_ref
  ) -> SafetyEffectObservationV1 | EffectSourceUnavailable | Rejection
}

interface SafetyReconciliationPort {
  reconcile_external_pending(
    pending_result_ref,
    expected_result_head_generation,
    expected_result_head_digest,
    effect_observation_ref,
    effect_observation_digest,
    authenticated_query_receipt_ref,
    authenticated_query_receipt_digest
  ) -> FullSafetyEffectVerifiedV1
     | LocalFenceVerifiedExternalPendingV1
     | SafetyResultInvalidatedV1
     | SafetyResultInconclusiveV1
     | SafetyEffectUnknownV1
     | Rejection

  reverify_active_result(
    result_chain_key_digest,
    expected_result_head_generation,
    expected_result_head_digest,
    required_verification_policy_bundle_ref,
    required_verification_policy_bundle_digest,
    expected_verification_policy_head_ref,
    expected_verification_policy_head_generation,
    expected_verification_policy_head_digest,
    expected_verification_policy_head_pointer_revision_ref,
    expected_verification_policy_head_pointer_revision_generation,
    expected_verification_policy_head_pointer_revision_digest
  ) -> FullSafetyEffectVerifiedV1
     | LocalFenceVerifiedExternalPendingV1
     | SafetyResultInvalidatedV1
     | SafetyResultInconclusiveV1
     | SafetyEffectUnknownV1
     | Rejection
}

TypedSafetyCommand =
  KillExecution(execution_ref, expected_generation)
  | RevokeSession(session_ref, expected_epoch)
  | RevokeGrant(grant_ref, expected_digest)
  | SuspendDeploymentBinding(binding_ref, expected_digest)
  | DenySecretRef(secret_ref, expected_epoch)
  | IsolateArtifact(artifact_ref, expected_digest)
  | IsolateLane(lane_ref, expected_generation)
  | OpenReconciliationCase(target_ref, expected_digest)
  | SealIncidentEvidence(incident_ref, preapproved_evidence_scope)
  | StageRecoveryValidation(recovery_ref, expected_digest)
```

```text
SafetyPrepareAdmissionSubjectV1 {
  subject_ref
  subject_digest
  subject_schema_version
  subject_type              SAFETY_PREPARE
  subject_owner_ref
  command_schema_version
  command_type
  command_digest
  target_owner
  target_ref
  expected_target_version
  expected_target_digest
  expected_target_generation
  requested_effect
  issuance_policy_head_ref
  issuance_policy_head_generation
  issuance_policy_head_digest
  issuance_policy_head_pointer_revision_ref
  issuance_policy_head_pointer_revision_generation
  issuance_policy_head_pointer_revision_digest
  required_issuance_policy_bundle_ref
  required_issuance_policy_bundle_digest
  audience                  SAFETY_SURVIVAL
  purpose                   SAFETY_COMMAND_PREPARE
  idempotency_key_digest
  effect_key_digest
  issued_at
  expires_at
  one_time_nonce_digest
  prepare_projection_digest
}

EmergencyActorAdmissionV1 {
  admission_ref
  admission_digest
  admission_schema_version
  admission_kind            SAFETY_PREPARE | SAFETY_COMMIT | POLICY_PUBLICATION
  admission_subject_type    SafetyPrepareAdmissionSubjectV1
                          | SafetyChallengeV1
                          | SafetyPolicyPublicationChallengeV1
  admission_subject_ref
  admission_subject_digest
  subject_one_time_nonce_digest
  actor_ref
  responsibility_scope_digest
  credential_epoch
  authorization_epoch_snapshot_digest
  assurance_profile_ref
  hardware_or_pki_evidence_ref
  authenticated_at
  audience                  SAFETY_SURVIVAL
  purpose
  channel_binding
  issued_at
  expires_at
  replay_domain_digest
}

SafetyAuthorizationReservationV1 {
  reservation_ref
  reservation_digest
  reservation_schema_version
  reservation_kind         SAFETY_PREPARE | SAFETY_COMMIT | POLICY_PUBLICATION
  subject_type
  subject_ref
  subject_digest
  subject_one_time_nonce_digest
  subject_nonce_key_digest
  action_projection_digest
  actor_refs[2]
  admission_refs[2]
  admission_digests[2]
  admission_replay_domain_digests[2]
  requested_owner_ref
  idempotency_key_digest
  effect_key_digest_if_applicable
  challenge_state_revision_ref_if_commit
  challenge_state_revision_generation_if_commit
  challenge_state_revision_digest_if_commit
  challenge_state_head_digest_if_commit
  coordinator_owner_ref
  coordinator_sequence
  reserved_at
  expires_at
}

SafetySubjectNonceConsumptionV1 {
  nonce_consumption_ref
  nonce_consumption_digest
  subject_nonce_key_digest
  subject_type
  subject_ref
  subject_digest
  subject_one_time_nonce_digest
  reservation_ref
  reservation_digest
  consumed_at
}

SafetyTrustedTimeEpochTransitionV1 {
  epoch_transition_ref
  epoch_transition_digest
  transition_schema_version
  time_authority_ref
  transition_kind          GENESIS | KEY_ROTATION | TRUST_ANCHOR_ROTATION
                         | SOURCE_SET_CHANGE | AUTHORITY_RECOVERY
  predecessor_time_authority_epoch_or_null
  successor_time_authority_epoch
  predecessor_attestation_ref_or_null
  predecessor_attestation_digest_or_null
  predecessor_authority_monotonic_counter_or_null
  successor_initial_authority_monotonic_counter 1
  predecessor_source_set_ref_or_null
  predecessor_source_set_digest_or_null
  successor_source_set_ref
  successor_source_set_digest
  predecessor_time_signing_key_ref_or_null
  predecessor_time_signing_key_epoch_or_null
  successor_time_signing_key_ref
  successor_time_signing_key_epoch
  predecessor_time_trust_anchor_ref_or_null
  predecessor_time_trust_anchor_digest_or_null
  successor_time_trust_anchor_ref
  successor_time_trust_anchor_digest
  transition_policy_ref
  transition_policy_digest
  transition_reason_code
  incident_ref_or_null
  incident_digest_or_null
  transition_nonce_digest
  authorized_lower_bound_utc
  authorized_upper_bound_utc
  continuity_material_ref
  continuity_material_digest
  continuity_signing_key_ref
  continuity_signing_key_epoch
  continuity_trust_anchor_ref
  continuity_trust_anchor_epoch
  continuity_trust_anchor_digest
  revocation_snapshot_ref
  revocation_snapshot_digest
  signature_algorithm
  signature
}

SafetyTrustedTimeAttestationV1 {
  trusted_time_attestation_ref
  trusted_time_attestation_digest
  attestation_schema_version
  time_authority_ref
  time_authority_epoch
  authority_monotonic_counter
  source_set_ref
  source_set_digest
  time_policy_ref
  time_policy_digest
  predecessor_attestation_ref_or_null
  predecessor_attestation_digest_or_null
  epoch_transition_ref
  epoch_transition_digest
  request_nonce_digest
  subject_ref
  subject_digest
  audience                  SAFETY_CONTROL
  purpose
  lower_bound_utc
  upper_bound_utc
  maximum_uncertainty_ms
  observed_local_skew_ms
  issued_at_utc
  expires_at_utc
  time_material_ref
  time_material_digest
  time_signing_key_ref
  time_signing_key_epoch
  time_trust_anchor_ref
  time_trust_anchor_digest
  signature_algorithm
  signature
}

SafetyTrustedTimeCommitLeaseV1 {
  commit_lease_ref
  commit_lease_digest
  commit_lease_schema_version
  commit_guard_material_ref
  commit_guard_material_digest
  consumer_owner_ref
  owner_transaction_nonce_digest
  commit_subject_type
  commit_subject_ref
  commit_subject_digest
  purpose
  trusted_time_attestation_ref
  trusted_time_attestation_digest
  time_authority_ref
  time_authority_epoch
  authority_monotonic_counter
  time_policy_ref
  time_policy_digest
  trusted_elapsed_source_ref
  trusted_elapsed_source_digest
  trusted_elapsed_source_epoch
  acceptance_monotonic_tick
  commit_deadline_monotonic_tick
  tick_resolution_ns
  maximum_commit_elapsed_budget_ms
  storage_commit_profile_ref
  storage_commit_profile_digest
  lease_nonce_digest
  issued_at_upper_bound_utc
  commit_guard_key_ref
  commit_guard_key_epoch
  commit_guard_trust_anchor_ref
  commit_guard_trust_anchor_epoch
  commit_guard_trust_anchor_digest
  revocation_snapshot_ref
  revocation_snapshot_digest
  signature_algorithm
  signature
}

SafetyTrustedTimeCommitFreshnessProofV1 {
  commit_freshness_proof_ref
  commit_freshness_proof_digest
  commit_freshness_proof_schema_version
  commit_guard_material_ref
  commit_guard_material_digest
  commit_lease_ref
  commit_lease_digest
  consumer_owner_ref
  owner_transaction_nonce_digest
  commit_subject_type
  commit_subject_ref
  commit_subject_digest
  purpose
  trusted_time_attestation_ref
  trusted_time_attestation_digest
  time_authority_ref
  time_authority_epoch
  authority_monotonic_counter
  trusted_elapsed_source_ref
  trusted_elapsed_source_digest
  trusted_elapsed_source_epoch
  acceptance_monotonic_tick
  commit_linearization_monotonic_tick
  commit_deadline_monotonic_tick
  elapsed_upper_bound_ms
  maximum_commit_elapsed_budget_ms
  storage_commit_profile_ref
  storage_commit_profile_digest
  store_linearization_token_digest
  predecessor_checkpoint_ref_or_null
  predecessor_checkpoint_digest_or_null
  checked_at_upper_bound_utc
  freshness_outcome       FRESH_AT_OWNER_STORE_LINEARIZATION
  commit_guard_key_ref
  commit_guard_key_epoch
  commit_guard_trust_anchor_ref
  commit_guard_trust_anchor_epoch
  commit_guard_trust_anchor_digest
  revocation_snapshot_ref
  revocation_snapshot_digest
  signature_algorithm
  signature
}

SafetyTrustedTimeCheckpointV1 {
  checkpoint_ref
  checkpoint_digest
  checkpoint_schema_version
  consumer_owner_ref
  time_authority_ref
  accepted_time_authority_epoch
  accepted_authority_monotonic_counter
  accepted_attestation_ref
  accepted_attestation_digest
  commit_lease_ref
  commit_lease_digest
  commit_freshness_proof_ref
  commit_freshness_proof_digest
  owner_transaction_nonce_digest
  commit_subject_type
  commit_subject_ref
  commit_subject_digest
  purpose
  time_consumption_key_digest
  store_linearization_token_digest
  predecessor_checkpoint_ref_or_null
  predecessor_checkpoint_digest_or_null
  updated_at_upper_bound_utc
}

SafetyOwnerWorkloadAttestationV1 {
  owner_workload_attestation_ref
  owner_workload_attestation_digest
  attestation_schema_version
  owner_workload_attestation_material_ref
  owner_workload_attestation_material_digest
  attesting_owner_ref
  attesting_workload_identity_ref
  attesting_workload_build_digest
  attesting_workload_failure_domain
  operation_code           COORDINATOR_RESERVATION_VERIFY
                         | TARGET_OWNER_SIGNING_REQUEST
                         | POLICY_ALIAS_TRANSITION
  operation_subject_type   SafetyCoordinatorReservationVerificationSubjectV1
                         | SafetyTargetOwnerSigningSubjectV1
                         | SafetyPolicyAliasTransitionSubjectV1
  operation_subject_ref
  operation_subject_digest
  audience
  purpose
  authorization_policy_digest
  request_nonce_digest
  issued_at
  expires_at
  attestation_key_ref
  attestation_key_epoch
  attestation_trust_anchor_ref
  attestation_trust_anchor_digest
  signature_algorithm
  signature
}

SafetyOwnerWorkloadAttestationVerificationV1 {
  owner_workload_attestation_verification_ref
  owner_workload_attestation_verification_digest
  owner_workload_attestation_ref
  owner_workload_attestation_digest
  expected_owner_ref
  expected_material_ref
  expected_material_digest
  expected_operation_code
  expected_subject_ref
  expected_subject_digest
  expected_audience
  expected_purpose
  trusted_time_attestation_ref
  trusted_time_attestation_digest
  trusted_time_checkpoint_ref
  trusted_time_checkpoint_digest
  trust_snapshot_ref
  trust_snapshot_digest
  canonical_digest_valid       True | False | Unknown
  material_binding_valid       True | False | Unknown
  owner_binding_valid          True | False | Unknown
  workload_identity_valid      True | False | Unknown
  workload_build_valid         True | False | Unknown
  failure_domain_valid         True | False | Unknown
  operation_subject_valid      True | False | Unknown
  audience_purpose_valid       True | False | Unknown
  key_epoch_valid              True | False | Unknown
  key_not_revoked              True | False | Unknown
  trust_anchor_valid           True | False | Unknown
  signature_valid              True | False | Unknown
  trusted_time_valid           True | False | Unknown
  verification_outcome         VALID | INVALID | UNKNOWN
  verified_at
  freshness_deadline
}

SafetyCoordinatorReservationVerificationSubjectV1 {
  coordinator_operation_subject_ref
  coordinator_operation_subject_digest
  coordinator_owner_ref
  coordinator_sequence
  coordinator_store_commit_ref
  coordinator_store_commit_digest
  reservation_ref
  reservation_digest
  admission_consumption_refs[2]
  admission_consumption_digests[2]
  subject_nonce_consumption_ref
  subject_nonce_consumption_digest
  expected_reservation_status ACTIVE
  audience                 SAFETY_CONTROL
  purpose                  VERIFY_SAFETY_ADMISSION_RESERVATION
}

SafetyAuthorizationReservationVerificationV1 {
  reservation_verification_ref
  reservation_verification_digest
  reservation_ref
  reservation_digest
  coordinator_owner_ref
  coordinator_sequence
  coordinator_store_commit_ref
  coordinator_store_commit_digest
  admission_consumption_refs[2]
  admission_consumption_digests[2]
  subject_nonce_consumption_ref
  subject_nonce_consumption_digest
  coordinator_operation_subject_ref
  coordinator_operation_subject_digest
  reservation_canonical_valid        True | False | Unknown
  coordinator_provenance_valid       True | False | Unknown
  atomic_consumption_set_valid       True | False | Unknown
  subject_binding_valid              True | False | Unknown
  action_projection_binding_valid    True | False | Unknown
  owner_binding_valid                True | False | Unknown
  idempotency_effect_binding_valid   True | False | Unknown
  admission_fresh_at_reservation     True | False | Unknown
  subject_fresh_at_reservation       True | False | Unknown
  reservation_status                ACTIVE | EXPIRED | UNKNOWN
  trusted_time_attestation_ref
  trusted_time_attestation_digest
  trusted_time_checkpoint_ref
  trusted_time_checkpoint_digest
  trusted_time_upper_bound_utc
  verified_at_upper_bound_utc
  freshness_deadline
  coordinator_attestation_policy_ref
  coordinator_attestation_policy_digest
  coordinator_signing_key_ref
  coordinator_signing_key_epoch
  coordinator_trust_anchor_ref
  coordinator_trust_anchor_digest
  coordinator_key_failure_domain_valid True | False | Unknown
  coordinator_key_not_revoked          True | False | Unknown
  coordinator_signature_valid          True | False | Unknown
  trusted_time_authority_valid          True | False | Unknown
  trusted_time_monotonic_valid          True | False | Unknown
  trusted_time_interval_valid           True | False | Unknown
  coordinator_owner_workload_attestation_ref
  coordinator_owner_workload_attestation_digest
  coordinator_owner_workload_attestation_verification_ref
  coordinator_owner_workload_attestation_verification_digest
}

EmergencyAdmissionConsumptionV1 {
  consumption_ref
  consumption_digest
  consumption_key_digest
  admission_ref
  admission_digest
  admission_kind
  admission_subject_ref
  admission_subject_digest
  subject_one_time_nonce_digest
  actor_ref
  replay_domain_digest
  atomic_anchor_record_type SafetyAuthorizationReservationV1
  atomic_anchor_record_ref
  atomic_anchor_record_digest
  consumed_at
}

SafetyPreparedCommandV1 {
  prepared_command_ref
  command_schema_version
  command_type
  command_id
  command_digest
  incident_ref
  reason_digest
  target_owner
  target_ref
  expected_target_version
  expected_target_digest
  expected_target_generation
  requested_effect
  policy_version
  policy_digest
  issuance_policy_head_ref
  issuance_policy_head_generation
  issuance_policy_head_digest
  issuance_policy_head_pointer_revision_ref
  issuance_policy_head_pointer_revision_generation
  issuance_policy_head_pointer_revision_digest
  required_issuance_policy_bundle_ref
  required_issuance_policy_bundle_digest
  prepare_admission_subject_ref
  prepare_admission_subject_digest
  prepare_projection_digest
  safety_authorization_reservation_ref
  safety_authorization_reservation_digest
  reservation_verification_ref
  reservation_verification_digest
  reservation_checked_at_upper_bound_utc
  reservation_trusted_time_attestation_ref
  reservation_trusted_time_attestation_digest
  reservation_trusted_time_checkpoint_ref
  reservation_trusted_time_checkpoint_digest
  prepare_admission_refs[2]
  prepare_admission_digests[2]
  distinct_actor_refs[2]
  issued_at
  expires_at
  nonce_digest
  idempotency_key_digest
  effect_key_digest
  prepared_command_digest
}

SafetyChallengeV1 {
  challenge_ref
  challenge_digest
  prepared_command_ref
  prepared_command_digest
  command_digest
  distinct_actor_refs[2]
  required_commit_assurance_profile_ref
  issuance_policy_head_ref
  issuance_policy_head_generation
  issuance_policy_head_digest
  issuance_policy_head_pointer_revision_ref
  issuance_policy_head_pointer_revision_generation
  issuance_policy_head_pointer_revision_digest
  required_issuance_policy_bundle_ref
  required_issuance_policy_bundle_digest
  target_owner
  target_ref
  expected_target_digest
  expected_target_generation
  expires_at
  nonce_digest
  idempotency_key_digest
  effect_key_digest
  commit_projection_digest
}

SafetyChallengeStateRevisionV1 {
  state_revision_ref
  state_revision_digest
  challenge_ref
  challenge_digest
  generation
  predecessor_state_revision_ref
  predecessor_state_revision_digest
  state                      PREPARED
                           | COMMITTING
                           | LOCAL_FENCE_CONFIRMED
                           | LOCAL_FENCE_CONFIRMED_EXTERNAL_PENDING
                           | EFFECT_UNKNOWN
                           | REJECTED
                           | EXPIRED
  authorization_reservation_ref_if_commit
  authorization_reservation_digest_if_commit
  commit_attempt_ref_if_known
  commit_attempt_digest_if_known
  owner_record_ref_if_terminal
  owner_record_digest_if_terminal
  updated_at
}

SafetyChallengeStateHeadV1 {
  challenge_ref
  challenge_digest
  current_state_revision_ref
  current_state_revision_generation
  current_state_revision_digest
  head_digest
}

SafetyCommitAttemptV1 {
  commit_attempt_ref
  commit_attempt_digest
  challenge_ref
  challenge_digest
  safety_authorization_reservation_ref
  safety_authorization_reservation_digest
  reservation_verification_ref
  reservation_verification_digest
  reservation_checked_at_upper_bound_utc
  reservation_trusted_time_attestation_ref
  reservation_trusted_time_attestation_digest
  reservation_trusted_time_checkpoint_ref
  reservation_trusted_time_checkpoint_digest
  prepared_command_ref
  prepared_command_digest
  command_digest
  target_owner
  target_ref
  expected_target_digest
  expected_target_generation
  idempotency_key_digest
  effect_key_digest
  commit_admission_refs[2]
  commit_admission_digests[2]
  distinct_actor_refs[2]
  challenge_nonce_digest
  commit_projection_digest
  target_owner_journal_generation
  dispatch_authorized_until
  created_at
  dispatch_state            RESERVED
}

SafetyProviderWireCanonicalizationProfileV1 {
  provider_wire_canonicalization_profile_ref
  provider_wire_canonicalization_profile_digest
  profile_schema_version
  method_rule
  path_rule
  query_rule
  nonsecret_header_rule
  credential_field_exclusion_rule
  body_octet_rule
  media_type_rule
  redirect_rule
  unicode_rule
  invalid_input_disposition REJECT
}

SafetyProviderMutationRequestV1 {
  provider_request_ref
  provider_request_digest
  provider_request_schema_version
  commit_attempt_ref
  commit_attempt_digest
  effect_key_digest
  target_ref
  provider_ref
  provider_route_digest
  provider_wire_canonicalization_profile_ref
  provider_wire_canonicalization_profile_digest
  operation_code
  http_method
  normalized_path
  canonical_query_items[]
  canonical_nonsecret_header_items[]
  canonical_body_blob_ref
  canonical_body_bytes_digest
  canonical_body_length
  canonical_media_type
  idempotency_carrier_name
  idempotency_effect_key_value_digest
  credential_injection_profile_ref
  credential_injection_profile_digest
  authorized_business_wire_projection_digest
  created_at
}

SafetyCommitDispatchClaimV1 {
  dispatch_claim_ref
  dispatch_claim_digest
  commit_attempt_ref
  commit_attempt_digest
  reservation_ref
  reservation_digest
  effect_key_digest
  target_owner_ref
  target_owner_sequence
  worker_ref
  lease_generation
  provider_ref
  provider_route_digest
  provider_request_ref
  provider_request_digest
  provider_mutation_subject_digest
  trusted_time_attestation_ref
  trusted_time_attestation_digest
  trusted_time_checkpoint_ref
  trusted_time_checkpoint_digest
  trusted_time_upper_bound_utc
  dispatch_authorized_until
  claimed_at_upper_bound_utc
}

SafetyProviderMutationCapabilityV1 {
  provider_mutation_capability_ref
  provider_mutation_capability_digest
  dispatch_claim_ref
  dispatch_claim_digest
  provider_mutation_subject_digest
  commit_attempt_ref
  commit_attempt_digest
  effect_key_digest
  provider_request_ref
  provider_request_digest
  provider_ref
  provider_route_digest
  egress_boundary_ref
  policy_epoch_digest
  lease_generation
  dispatch_authorized_until
  audience                 SAFETY_PROVIDER_SEND_BOUNDARY
  purpose                  SEND_MUTATING_SAFETY_EFFECT_ONCE
  capability_nonce_digest
  capability_consumption_key_digest
  issued_at_upper_bound_utc
  expires_at
}

SafetyProviderCallAttemptV1 {
  provider_call_attempt_ref
  provider_call_attempt_digest
  dispatch_claim_ref
  dispatch_claim_digest
  provider_mutation_capability_ref
  provider_mutation_capability_digest
  capability_consumption_ref
  capability_consumption_digest
  commit_attempt_ref
  commit_attempt_digest
  effect_key_digest
  provider_request_ref
  provider_request_digest
  provider_ref
  provider_route_digest
  egress_boundary_ref
  egress_boundary_attestation_ref
  egress_boundary_attestation_digest
  egress_boundary_attestation_verification_ref
  egress_boundary_attestation_verification_digest
  wire_request_attestation_ref
  wire_request_attestation_digest
  wire_request_attestation_verification_ref
  wire_request_attestation_verification_digest
  boundary_verification_trusted_time_attestation_ref
  boundary_verification_trusted_time_attestation_digest
  boundary_verification_trusted_time_checkpoint_ref
  boundary_verification_trusted_time_checkpoint_digest
  wire_verification_trusted_time_attestation_ref
  wire_verification_trusted_time_attestation_digest
  wire_verification_trusted_time_checkpoint_ref
  wire_verification_trusted_time_checkpoint_digest
  trusted_time_attestation_ref
  trusted_time_attestation_digest
  trusted_time_checkpoint_ref
  trusted_time_checkpoint_digest
  trusted_time_upper_bound_utc
  dispatch_authorized_until
  send_boundary_entered_at_upper_bound_utc
  attempt_state            SEND_BOUNDARY_ENTERED
}

SafetyProviderMutationCapabilityConsumptionV1 {
  capability_consumption_ref
  capability_consumption_digest
  capability_consumption_key_digest
  provider_mutation_capability_ref
  provider_mutation_capability_digest
  provider_mutation_subject_digest
  dispatch_claim_ref
  dispatch_claim_digest
  effect_key_digest
  egress_boundary_ref
  trusted_time_attestation_ref
  trusted_time_attestation_digest
  trusted_time_checkpoint_ref
  trusted_time_checkpoint_digest
  consumed_at_upper_bound_utc
  owner_sequence
  consumption_state        CONSUMED
}

SafetyEgressBoundaryAttestationV1 {
  egress_boundary_attestation_ref
  egress_boundary_attestation_digest
  egress_attestation_material_ref
  egress_attestation_material_digest
  operation_code            EGRESS_BOUNDARY_IDENTITY
  audience                  SAFETY_PROVIDER_SEND_BOUNDARY
  purpose                   ATTEST_EGRESS_BOUNDARY_IDENTITY
  egress_boundary_ref
  egress_workload_identity_ref
  egress_workload_build_digest
  egress_workload_failure_domain
  provider_ref
  provider_route_digest
  policy_epoch_digest
  network_path_policy_digest
  attestation_policy_ref
  attestation_policy_digest
  attestation_key_failure_domain
  attested_at
  expires_at
  attestation_key_ref
  attestation_key_epoch
  attestation_trust_anchor_ref
  attestation_trust_anchor_epoch
  attestation_trust_anchor_digest
  revocation_snapshot_ref
  revocation_snapshot_digest
  signature_algorithm
  signature
}

SafetyProviderWireBytesEvidenceV1 {
  wire_bytes_evidence_ref
  wire_bytes_evidence_digest
  provider_request_ref
  provider_request_digest
  provider_mutation_capability_ref
  provider_mutation_capability_digest
  provider_ref
  provider_route_digest
  provider_wire_canonicalization_profile_ref
  provider_wire_canonicalization_profile_digest
  egress_boundary_ref
  actual_http_method
  actual_normalized_path
  actual_canonical_query_items[]
  actual_canonical_nonsecret_header_items[]
  actual_body_blob_ref
  actual_body_bytes_digest
  actual_body_length
  actual_media_type
  actual_idempotency_carrier_name
  actual_idempotency_effect_key_value_digest
  injected_credential_field_names_digest
  credential_values_included False
  classification
  sealed_buffer_generation
  captured_before_send_at_upper_bound_utc
}

SafetyProviderWireRequestAttestationV1 {
  wire_request_attestation_ref
  wire_request_attestation_digest
  egress_attestation_material_ref
  egress_attestation_material_digest
  wire_egress_workload_identity_ref
  wire_egress_workload_build_digest
  wire_egress_workload_failure_domain
  operation_code            EGRESS_WIRE_REQUEST_BUFFER
  audience                  SAFETY_PROVIDER_SEND_BOUNDARY
  purpose                   ATTEST_WIRE_REQUEST_BUFFER
  provider_mutation_capability_ref
  provider_mutation_capability_digest
  provider_request_ref
  provider_request_digest
  effect_key_digest
  provider_ref
  provider_route_digest
  provider_wire_canonicalization_profile_ref
  provider_wire_canonicalization_profile_digest
  egress_boundary_ref
  egress_boundary_attestation_ref
  egress_boundary_attestation_digest
  egress_boundary_attestation_verification_ref
  egress_boundary_attestation_verification_digest
  wire_bytes_evidence_ref
  wire_bytes_evidence_digest
  actual_business_wire_projection_digest
  injected_credential_field_names_digest
  credential_lease_ref
  credential_lease_digest
  credential_values_persisted False
  attestation_policy_ref
  attestation_policy_digest
  attestation_key_failure_domain
  attested_at_upper_bound_utc
  expires_at
  attestation_key_ref
  attestation_key_epoch
  attestation_trust_anchor_ref
  attestation_trust_anchor_epoch
  attestation_trust_anchor_digest
  revocation_snapshot_ref
  revocation_snapshot_digest
  signature_algorithm
  signature
}

SafetyEgressWorkloadAttestationVerificationV1 {
  egress_attestation_verification_ref
  egress_attestation_verification_digest
  attestation_type          EGRESS_BOUNDARY_IDENTITY
                          | EGRESS_WIRE_REQUEST_BUFFER
  attestation_ref
  attestation_digest
  material_ref
  material_digest
  expected_operation_code
  expected_egress_boundary_ref
  expected_provider_ref
  expected_provider_route_digest
  expected_provider_request_ref_if_wire
  expected_provider_request_digest_if_wire
  expected_provider_mutation_capability_ref_if_wire
  expected_provider_mutation_capability_digest_if_wire
  expected_boundary_attestation_ref_if_wire
  expected_boundary_attestation_digest_if_wire
  expected_boundary_attestation_verification_ref_if_wire
  expected_boundary_attestation_verification_digest_if_wire
  trusted_time_attestation_ref
  trusted_time_attestation_digest
  trusted_time_checkpoint_ref
  trusted_time_checkpoint_digest
  trust_snapshot_ref
  trust_snapshot_digest
  canonical_digest_valid       True | False | Unknown
  material_binding_valid       True | False | Unknown
  operation_binding_valid      True | False | Unknown
  workload_identity_valid      True | False | Unknown
  workload_build_valid         True | False | Unknown
  failure_domain_valid         True | False | Unknown
  boundary_provider_route_valid True | False | Unknown
  request_capability_binding_valid True | False | Unknown | NOT_APPLICABLE
  boundary_attestation_chain_valid True | False | Unknown | NOT_APPLICABLE
  boundary_workload_identity_match_valid True | False | Unknown | NOT_APPLICABLE
  boundary_workload_build_match_valid True | False | Unknown | NOT_APPLICABLE
  boundary_failure_domain_match_valid True | False | Unknown | NOT_APPLICABLE
  policy_purpose_valid         True | False | Unknown
  key_epoch_valid              True | False | Unknown
  key_not_revoked              True | False | Unknown
  trust_anchor_valid           True | False | Unknown
  signature_valid              True | False | Unknown
  trusted_time_valid           True | False | Unknown
  verification_outcome         VALID | INVALID | UNKNOWN
  verified_at
  freshness_deadline
}

SafetyProviderRawSendReceiptV1 {
  raw_send_receipt_ref
  raw_send_receipt_digest
  provider_call_attempt_ref
  provider_call_attempt_digest
  provider_ref
  provider_request_ref
  provider_request_digest
  transport_receipt_ref
  transport_receipt_digest
  idempotency_effect_key_echo_digest
  handoff_claim             CONFIRMED | UNKNOWN
  received_at_upper_bound_utc
}

SafetyProviderSendReceiptVerificationV1 {
  send_receipt_verification_ref
  send_receipt_verification_digest
  raw_send_receipt_ref
  raw_send_receipt_digest
  provider_call_attempt_ref
  provider_call_attempt_digest
  capability_consumption_ref
  capability_consumption_digest
  egress_boundary_attestation_ref
  egress_boundary_attestation_digest
  egress_boundary_attestation_verification_ref
  egress_boundary_attestation_verification_digest
  wire_request_attestation_ref
  wire_request_attestation_digest
  wire_request_attestation_verification_ref
  wire_request_attestation_verification_digest
  expected_provider_ref
  expected_provider_request_ref
  expected_provider_request_digest
  expected_effect_key_digest
  trust_snapshot_ref
  trust_snapshot_digest
  raw_receipt_digest_valid          True | False | Unknown
  provider_call_attempt_binding_valid True | False | Unknown
  capability_consumption_binding_valid True | False | Unknown
  egress_boundary_binding_valid        True | False | Unknown
  egress_attestation_material_valid    True | False | Unknown
  egress_boundary_attestation_valid True | False | Unknown
  wire_attestation_material_valid      True | False | Unknown
  wire_request_attestation_valid       True | False | Unknown
  authorized_wire_projection_match     True | False | Unknown
  wire_canonicalization_profile_valid  True | False | Unknown
  provider_identity_valid           True | False | Unknown
  transport_receipt_valid           True | False | Unknown
  request_binding_valid             True | False | Unknown
  effect_key_echo_valid             True | False | Unknown
  trusted_time_valid                True | False | Unknown
  verification_outcome              VALID | INVALID | UNKNOWN
  verified_at
  freshness_deadline
}

SafetyProviderSendReceiptV1 {
  provider_send_receipt_ref
  provider_send_receipt_digest
  raw_send_receipt_ref
  raw_send_receipt_digest
  send_receipt_verification_ref
  send_receipt_verification_digest
  provider_call_attempt_ref
  provider_call_attempt_digest
  provider_ref
  provider_request_ref
  provider_request_digest
  effect_key_digest
  handoff_state                     CONFIRMED
  verified_at
}
```

`effect_key_digest` 在 SafetyPrepareAdmissionSubject 形成时一次确定：

```text
SHA-256(
  UTF8("flai.safety.effect-key.v1\0")
  || RFC8785_JCS_UTF8({
       command_digest,
       target_ref,
       idempotency_key_digest
     })
)
```

它必须逐字复制进 PreparedCommand、Challenge、CommitAttempt、OwnerReceiptPayload、
SafetyEffectUnknown、EffectObservation 和全部 reconcile/query；响应丢失或 signer
不可用时也不得重算、换键或只保留普通 request id。

安全准入不是“刚完成过一次强认证”的通用会话属性，而是对一个精确不可变 subject 的
一次性授权。所有 subject、admission 与 consumption 都使用
`RFC8785-JCS-UTF8-NFC + SHA-256`、拒绝未知字段、禁止浮点数、UTC RFC3339 时间和小写
64 位十六进制 digest；ref/digest 自身只按下列规则排除：

```text
prepare_subject_digest = SHA-256(
  UTF8("flai.safety.prepare-admission-subject.v1\0")
  || RFC8785_JCS_UTF8(SafetyPrepareAdmissionSubjectV1
       excluding exactly subject_ref and subject_digest)
)
prepare_subject_ref =
  "flai://safety-prepare-admission-subject/" + prepare_subject_digest

prepare_projection_digest = SHA-256(
  UTF8("flai.safety.prepare-authorized-projection.v1\0")
  || RFC8785_JCS_UTF8({
       command_schema_version,
       command_type,
       command_digest,
       target_owner,
       target_ref,
       expected_target_version,
       expected_target_digest,
       expected_target_generation,
       requested_effect,
       issuance_policy_head_ref,
       issuance_policy_head_generation,
       issuance_policy_head_digest,
       issuance_policy_head_pointer_revision_ref,
       issuance_policy_head_pointer_revision_generation,
       issuance_policy_head_pointer_revision_digest,
       required_issuance_policy_bundle_ref,
       required_issuance_policy_bundle_digest,
       idempotency_key_digest,
       effect_key_digest
     })
)

safety_challenge_digest = SHA-256(
  UTF8("flai.safety.command-commit-challenge.v1\0")
  || RFC8785_JCS_UTF8(SafetyChallengeV1
       excluding exactly challenge_ref and challenge_digest)
)
safety_challenge_ref =
  "flai://safety-command-commit-challenge/" + safety_challenge_digest

commit_projection_digest = SHA-256(
  UTF8("flai.safety.commit-authorized-projection.v1\0")
  || RFC8785_JCS_UTF8({
       prepared_command_ref,
       prepared_command_digest,
       command_digest,
       target_owner,
       target_ref,
       expected_target_digest,
       expected_target_generation,
       nonce_digest,
       idempotency_key_digest,
       effect_key_digest
     })
)

commit_attempt_digest = SHA-256(
  UTF8("flai.safety.commit-attempt.v1\0")
  || RFC8785_JCS_UTF8(SafetyCommitAttemptV1
       excluding exactly commit_attempt_ref and commit_attempt_digest)
)
commit_attempt_ref =
  "flai://safety-commit-attempt/" + commit_attempt_digest

provider_wire_canonicalization_profile_digest = SHA-256(
  UTF8("flai.safety.provider-wire-canonicalization-profile.v1\0")
  || RFC8785_JCS_UTF8(SafetyProviderWireCanonicalizationProfileV1
       excluding exactly provider_wire_canonicalization_profile_ref
                         and provider_wire_canonicalization_profile_digest)
)
provider_wire_canonicalization_profile_ref =
  "flai://safety-provider-wire-canonicalization-profile/"
  + provider_wire_canonicalization_profile_digest

authorized_business_wire_projection_digest = SHA-256(
  UTF8("flai.safety.provider-business-wire-projection.v1\0")
  || RFC8785_JCS_UTF8({
       provider_ref,
       provider_route_digest,
       provider_wire_canonicalization_profile_ref,
       provider_wire_canonicalization_profile_digest,
       http_method,
       normalized_path,
       canonical_query_items,
       canonical_nonsecret_header_items,
       canonical_body_blob_ref,
       canonical_body_bytes_digest,
       canonical_body_length,
       canonical_media_type,
       idempotency_carrier_name,
       idempotency_effect_key_value_digest
     })
)

provider_request_digest = SHA-256(
  UTF8("flai.safety.provider-mutation-request.v1\0")
  || RFC8785_JCS_UTF8(SafetyProviderMutationRequestV1
       excluding exactly provider_request_ref and provider_request_digest)
)
provider_request_ref =
  "flai://safety-provider-mutation-request/" + provider_request_digest

trusted_time_epoch_transition_digest = SHA-256(
  UTF8("flai.safety.trusted-time-epoch-transition.v1\0")
  || RFC8785_JCS_UTF8(SafetyTrustedTimeEpochTransitionV1
       excluding exactly epoch_transition_ref,
                         epoch_transition_digest,
                         signature)
)
trusted_time_epoch_transition_ref =
  "flai://safety-trusted-time-epoch-transition/"
  + trusted_time_epoch_transition_digest

trusted_time_epoch_transition_signature_input =
  UTF8("flai.safety.trusted-time-epoch-transition-signature.v1\0")
  || RFC8785_JCS_UTF8(SafetyTrustedTimeEpochTransitionV1
       excluding exactly epoch_transition_ref,
                         epoch_transition_digest,
                         signature)

trusted_time_attestation_digest = SHA-256(
  UTF8("flai.safety.trusted-time-attestation.v1\0")
  || RFC8785_JCS_UTF8(SafetyTrustedTimeAttestationV1
       excluding exactly trusted_time_attestation_ref,
                         trusted_time_attestation_digest,
                         signature)
)
trusted_time_attestation_ref =
  "flai://safety-trusted-time-attestation/" + trusted_time_attestation_digest

trusted_time_signature_input =
  UTF8("flai.safety.trusted-time-signature.v1\0")
  || RFC8785_JCS_UTF8(SafetyTrustedTimeAttestationV1
       excluding exactly trusted_time_attestation_ref,
                         trusted_time_attestation_digest,
                         signature)

trusted_time_checkpoint_digest = SHA-256(
  UTF8("flai.safety.trusted-time-checkpoint.v1\0")
  || RFC8785_JCS_UTF8(SafetyTrustedTimeCheckpointV1
       excluding exactly checkpoint_ref and checkpoint_digest)
)
trusted_time_checkpoint_ref =
  "flai://safety-trusted-time-checkpoint/" + trusted_time_checkpoint_digest

trusted_time_commit_lease_digest = SHA-256(
  UTF8("flai.safety.trusted-time-commit-lease.v1\0")
  || RFC8785_JCS_UTF8(SafetyTrustedTimeCommitLeaseV1
       excluding exactly commit_lease_ref,
                         commit_lease_digest,
                         signature)
)
trusted_time_commit_lease_ref =
  "flai://safety-trusted-time-commit-lease/"
  + trusted_time_commit_lease_digest
trusted_time_commit_lease_signature_input =
  UTF8("flai.safety.trusted-time-commit-lease-signature.v1\0")
  || RFC8785_JCS_UTF8(SafetyTrustedTimeCommitLeaseV1
       excluding exactly commit_lease_ref,
                         commit_lease_digest,
                         signature)

trusted_time_commit_freshness_proof_digest = SHA-256(
  UTF8("flai.safety.trusted-time-commit-freshness-proof.v1\0")
  || RFC8785_JCS_UTF8(SafetyTrustedTimeCommitFreshnessProofV1
       excluding exactly commit_freshness_proof_ref,
                         commit_freshness_proof_digest,
                         signature)
)
trusted_time_commit_freshness_proof_ref =
  "flai://safety-trusted-time-commit-freshness-proof/"
  + trusted_time_commit_freshness_proof_digest
trusted_time_commit_freshness_proof_signature_input =
  UTF8("flai.safety.trusted-time-commit-freshness-proof-signature.v1\0")
  || RFC8785_JCS_UTF8(SafetyTrustedTimeCommitFreshnessProofV1
       excluding exactly commit_freshness_proof_ref,
                         commit_freshness_proof_digest,
                         signature)

time_consumption_key_digest = SHA-256(
  UTF8("flai.safety.trusted-time-consumption-key.v1\0")
  || RFC8785_JCS_UTF8({
       consumer_owner_ref,
       owner_transaction_nonce_digest,
       commit_subject_type,
       commit_subject_ref,
       commit_subject_digest,
       purpose,
       trusted_time_attestation_digest,
       commit_lease_digest
     })
)

owner_workload_attestation_digest = SHA-256(
  UTF8("flai.safety.owner-workload-attestation.v1\0")
  || RFC8785_JCS_UTF8(SafetyOwnerWorkloadAttestationV1
       excluding exactly owner_workload_attestation_ref,
                         owner_workload_attestation_digest,
                         signature)
)
owner_workload_attestation_ref =
  "flai://safety-owner-workload-attestation/"
  + owner_workload_attestation_digest

owner_workload_attestation_signature_input =
  UTF8("flai.safety.owner-workload-attestation-signature.v1\0")
  || RFC8785_JCS_UTF8(SafetyOwnerWorkloadAttestationV1
       excluding exactly owner_workload_attestation_ref,
                         owner_workload_attestation_digest,
                         signature)

owner_workload_attestation_verification_digest = SHA-256(
  UTF8("flai.safety.owner-workload-attestation-verification.v1\0")
  || RFC8785_JCS_UTF8(SafetyOwnerWorkloadAttestationVerificationV1
       excluding exactly owner_workload_attestation_verification_ref,
                         owner_workload_attestation_verification_digest)
)
owner_workload_attestation_verification_ref =
  "flai://safety-owner-workload-attestation-verification/"
  + owner_workload_attestation_verification_digest

dispatch_claim_digest = SHA-256(
  UTF8("flai.safety.commit-dispatch-claim.v1\0")
  || RFC8785_JCS_UTF8(SafetyCommitDispatchClaimV1
       excluding exactly dispatch_claim_ref and dispatch_claim_digest)
)
dispatch_claim_ref =
  "flai://safety-commit-dispatch-claim/" + dispatch_claim_digest

provider_mutation_subject_digest = SHA-256(
  UTF8("flai.safety.provider-mutation-subject.v1\0")
  || RFC8785_JCS_UTF8({
       commit_attempt_digest,
       effect_key_digest,
       provider_request_digest,
       provider_ref,
       provider_route_digest,
       provider_wire_canonicalization_profile_ref,
       provider_wire_canonicalization_profile_digest,
       lease_generation,
       dispatch_authorized_until
     })
)

provider_mutation_capability_digest = SHA-256(
  UTF8("flai.safety.provider-mutation-capability.v1\0")
  || RFC8785_JCS_UTF8(SafetyProviderMutationCapabilityV1
       excluding exactly provider_mutation_capability_ref
                         and provider_mutation_capability_digest)
)
provider_mutation_capability_ref =
  "flai://safety-provider-mutation-capability/"
  + provider_mutation_capability_digest

provider_call_attempt_digest = SHA-256(
  UTF8("flai.safety.provider-call-attempt.v1\0")
  || RFC8785_JCS_UTF8(SafetyProviderCallAttemptV1
       excluding exactly provider_call_attempt_ref
                         and provider_call_attempt_digest)
)
provider_call_attempt_ref =
  "flai://safety-provider-call-attempt/" + provider_call_attempt_digest

capability_consumption_key_digest = SHA-256(
  UTF8("flai.safety.provider-capability-consumption-key.v1\0")
  || RFC8785_JCS_UTF8({
       dispatch_claim_digest,
       provider_mutation_subject_digest,
       capability_nonce_digest
     })
)

capability_consumption_digest = SHA-256(
  UTF8("flai.safety.provider-capability-consumption.v1\0")
  || RFC8785_JCS_UTF8(SafetyProviderMutationCapabilityConsumptionV1
       excluding exactly capability_consumption_ref
                         and capability_consumption_digest)
)
capability_consumption_ref =
  "flai://safety-provider-capability-consumption/"
  + capability_consumption_digest

egress_boundary_attestation_digest = SHA-256(
  UTF8("flai.safety.egress-boundary-attestation.v1\0")
  || RFC8785_JCS_UTF8(SafetyEgressBoundaryAttestationV1
       excluding exactly egress_boundary_attestation_ref,
                         egress_boundary_attestation_digest,
                         signature)
)
egress_boundary_attestation_ref =
  "flai://safety-egress-boundary-attestation/"
  + egress_boundary_attestation_digest

egress_boundary_attestation_signature_input =
  UTF8("flai.safety.egress-boundary-attestation-signature.v1\0")
  || RFC8785_JCS_UTF8(SafetyEgressBoundaryAttestationV1
       excluding exactly egress_boundary_attestation_ref,
                         egress_boundary_attestation_digest,
                         signature)

wire_bytes_evidence_digest = SHA-256(
  UTF8("flai.safety.provider-wire-bytes-evidence.v1\0")
  || RFC8785_JCS_UTF8(SafetyProviderWireBytesEvidenceV1
       excluding exactly wire_bytes_evidence_ref and wire_bytes_evidence_digest)
)
wire_bytes_evidence_ref =
  "flai://safety-provider-wire-bytes-evidence/" + wire_bytes_evidence_digest

actual_business_wire_projection_digest = SHA-256(
  UTF8("flai.safety.provider-business-wire-projection.v1\0")
  || RFC8785_JCS_UTF8({
       provider_ref,
       provider_route_digest,
       provider_wire_canonicalization_profile_ref,
       provider_wire_canonicalization_profile_digest,
       http_method: actual_http_method,
       normalized_path: actual_normalized_path,
       canonical_query_items: actual_canonical_query_items,
       canonical_nonsecret_header_items:
         actual_canonical_nonsecret_header_items,
       canonical_body_blob_ref: actual_body_blob_ref,
       canonical_body_bytes_digest: actual_body_bytes_digest,
       canonical_body_length: actual_body_length,
       canonical_media_type: actual_media_type,
       idempotency_carrier_name: actual_idempotency_carrier_name,
       idempotency_effect_key_value_digest:
         actual_idempotency_effect_key_value_digest
     })
)

wire_request_attestation_digest = SHA-256(
  UTF8("flai.safety.provider-wire-request-attestation.v1\0")
  || RFC8785_JCS_UTF8(SafetyProviderWireRequestAttestationV1
       excluding exactly wire_request_attestation_ref,
                         wire_request_attestation_digest,
                         signature)
)
wire_request_attestation_ref =
  "flai://safety-provider-wire-request-attestation/"
  + wire_request_attestation_digest

wire_request_attestation_signature_input =
  UTF8("flai.safety.provider-wire-request-attestation-signature.v1\0")
  || RFC8785_JCS_UTF8(SafetyProviderWireRequestAttestationV1
       excluding exactly wire_request_attestation_ref,
                         wire_request_attestation_digest,
                         signature)

egress_attestation_verification_digest = SHA-256(
  UTF8("flai.safety.egress-workload-attestation-verification.v1\0")
  || RFC8785_JCS_UTF8(SafetyEgressWorkloadAttestationVerificationV1
       excluding exactly egress_attestation_verification_ref,
                         egress_attestation_verification_digest)
)
egress_attestation_verification_ref =
  "flai://safety-egress-workload-attestation-verification/"
  + egress_attestation_verification_digest

raw_send_receipt_digest = SHA-256(
  UTF8("flai.safety.provider-raw-send-receipt.v1\0")
  || RFC8785_JCS_UTF8(SafetyProviderRawSendReceiptV1
       excluding exactly raw_send_receipt_ref and raw_send_receipt_digest)
)
raw_send_receipt_ref =
  "flai://safety-provider-raw-send-receipt/" + raw_send_receipt_digest

send_receipt_verification_digest = SHA-256(
  UTF8("flai.safety.provider-send-receipt-verification.v1\0")
  || RFC8785_JCS_UTF8(SafetyProviderSendReceiptVerificationV1
       excluding exactly send_receipt_verification_ref
                         and send_receipt_verification_digest)
)
send_receipt_verification_ref =
  "flai://safety-provider-send-receipt-verification/"
  + send_receipt_verification_digest

provider_send_receipt_digest = SHA-256(
  UTF8("flai.safety.provider-send-receipt.v1\0")
  || RFC8785_JCS_UTF8(SafetyProviderSendReceiptV1
       excluding exactly provider_send_receipt_ref
                         and provider_send_receipt_digest)
)
provider_send_receipt_ref =
  "flai://safety-provider-send-receipt/" + provider_send_receipt_digest

challenge_state_revision_digest = SHA-256(
  UTF8("flai.safety.challenge-state-revision.v1\0")
  || RFC8785_JCS_UTF8(SafetyChallengeStateRevisionV1
       excluding exactly state_revision_ref and state_revision_digest)
)
challenge_state_revision_ref =
  "flai://safety-challenge-state-revision/"
  + challenge_digest + "/"
  + decimal(generation) + "/"
  + challenge_state_revision_digest

challenge_state_head_digest = SHA-256(
  UTF8("flai.safety.challenge-state-head.v1\0")
  || RFC8785_JCS_UTF8(SafetyChallengeStateHeadV1
       excluding exactly head_digest)
)

emergency_admission_digest = SHA-256(
  UTF8("flai.safety.emergency-actor-admission.v1\0")
  || RFC8785_JCS_UTF8(EmergencyActorAdmissionV1
       excluding exactly admission_ref and admission_digest)
)
emergency_admission_ref =
  "flai://safety-emergency-admission/" + emergency_admission_digest

replay_domain_digest = SHA-256(
  UTF8("flai.safety.admission-replay-domain.v1\0")
  || RFC8785_JCS_UTF8({
       admission_kind,
       admission_subject_type,
       admission_subject_ref,
       admission_subject_digest,
       subject_one_time_nonce_digest,
       actor_ref,
       responsibility_scope_digest,
       credential_epoch,
       authorization_epoch_snapshot_digest,
       assurance_profile_ref,
       audience,
       purpose,
       channel_binding
     })
)

subject_nonce_key_digest = SHA-256(
  UTF8("flai.safety.subject-nonce-key.v1\0")
  || RFC8785_JCS_UTF8({
       subject_type,
       subject_ref,
       subject_digest,
       subject_one_time_nonce_digest
     })
)

reservation_digest = SHA-256(
  UTF8("flai.safety.authorization-reservation.v1\0")
  || RFC8785_JCS_UTF8(SafetyAuthorizationReservationV1
       excluding exactly reservation_ref and reservation_digest)
)
reservation_ref =
  "flai://safety-authorization-reservation/" + reservation_digest

coordinator_operation_subject_digest = SHA-256(
  UTF8("flai.safety.coordinator-reservation-verification-subject.v1\0")
  || RFC8785_JCS_UTF8(SafetyCoordinatorReservationVerificationSubjectV1
       excluding exactly coordinator_operation_subject_ref
                         and coordinator_operation_subject_digest)
)
coordinator_operation_subject_ref =
  "flai://safety-coordinator-reservation-verification-subject/"
  + coordinator_operation_subject_digest

reservation_verification_digest = SHA-256(
  UTF8("flai.safety.authorization-reservation-verification.v1\0")
  || RFC8785_JCS_UTF8(SafetyAuthorizationReservationVerificationV1
       excluding exactly reservation_verification_ref,
                         reservation_verification_digest)
)
reservation_verification_ref =
  "flai://safety-authorization-reservation-verification/"
  + reservation_verification_digest

consumption_key_digest = SHA-256(
  UTF8("flai.safety.admission-consumption-key.v1\0")
  || RFC8785_JCS_UTF8({
       admission_ref,
       admission_digest
     })
)
consumption_digest = SHA-256(
  UTF8("flai.safety.admission-consumption.v1\0")
  || RFC8785_JCS_UTF8(EmergencyAdmissionConsumptionV1
       excluding exactly consumption_ref and consumption_digest)
)
consumption_ref =
  "flai://safety-admission-consumption/" + consumption_digest

nonce_consumption_digest = SHA-256(
  UTF8("flai.safety.subject-nonce-consumption.v1\0")
  || RFC8785_JCS_UTF8(SafetySubjectNonceConsumptionV1
       excluding exactly nonce_consumption_ref and nonce_consumption_digest)
)
nonce_consumption_ref =
  "flai://safety-subject-nonce-consumption/" + nonce_consumption_digest
```

时间验证顺序固定为：ref/digest → canonical/schema → authority/key usage/current key epoch/
revocation/trust anchor → signature → audience/purpose/subject/nonce → time policy/source set →
predecessor/epoch/counter/consumer checkpoint → uncertainty/skew → TTL。任一步不是显式 `True`
即拒绝。TTL 使用区间而不是点值：

```text
deadline = min(
  reservation.expires_at,
  reservation_verification.freshness_deadline,
  trusted_time_attestation.expires_at_utc
)

VALID   iff trusted_time_attestation.upper_bound_utc <= deadline
EXPIRED iff trusted_time_attestation.lower_bound_utc > deadline
UNKNOWN otherwise
```

`UNKNOWN` 与 `EXPIRED` 都不得创建首次 anchor 或进入 provider send boundary。Time Authority
outage 时不签新 attestation、不延长缓存、不回退 host clock；已进入原 send boundary 的 effect
仍只能按原 key 查询/收尾/对账。

`prepare_projection_digest` 必须由 Subject 与 PreparedCommand 各自的上列字段独立重算且
逐字相等；`commit_projection_digest` 必须由 Challenge 与 CommitAttempt 独立重算，其中
CommitAttempt 的 `challenge_nonce_digest` 按上式映射为 `nonce_digest`。Subject/Challenge
ref+digest 正确但任一重复字段或 projection digest 不等，仍是
`SAFETY_ADMISSION_SUBJECT_MISMATCH`，不得消费 admission/nonce。
Coordinator 必须从实际 subject/challenge 重算 Reservation 的
`action_projection_digest`、`subject_nonce_key_digest`、`idempotency_key_digest` 与适用
`effect_key_digest`；requested owner 必须等于 subject 的 target/policy owner。调用方不能
通过 Reservation payload 改写这些派生值。

content-addressed Reservation 只证明内容未变，不证明 Coordinator 的 CAS 真发生。任何下游
owner 在创建**首个**本地 anchor 前都必须调用唯一
`SafetyAdmissionReservationPort.resolve_and_verify_reservation`，从 Coordinator 权威 Store
重读同一 local commit 中的 Reservation、两条 AdmissionConsumption 和一条
SubjectNonceConsumption，并验证 Coordinator owner/sequence/store-commit/attestation。
`reservation_canonical_valid`、`coordinator_provenance_valid`、
`atomic_consumption_set_valid`、subject/projection/owner/idempotency/effect binding 与
reservation-time freshness、`coordinator_key_not_revoked` 与
`coordinator_signature_valid` 全部必须 `is True`，`reservation_status` 必须为 `ACTIVE`；
任一 False/Unknown、孤儿/伪造 Reservation、缺消费记录或 freshness 超限都拒绝。Prepared、
CommitAttempt 与 PolicyPublicationReceipt 必须冻结这次 fresh
ReservationVerification ref+digest，不能只保存 detached Reservation。

Coordinator attestation 是 workload provenance，不是人类签发或治理批准。它必须由
`coordinator_attestation_policy_ref+digest` 允许的、purpose-bound、不可导出
与 operation `COORDINATOR_RESERVATION_VERIFY` 精确匹配的
`SafetyOwnerWorkloadAttestationMaterialRefV1` 对
具名、可解析的 `SafetyCoordinatorReservationVerificationSubjectV1 ref+digest` 签发
`SafetyOwnerWorkloadAttestationV1`。该 subject 规范化绑定
Coordinator store commit/sequence、Reservation、两条 AdmissionConsumption、一条
SubjectNonceConsumption、expected ACTIVE、audience 与 purpose，并绑定
operation `COORDINATOR_RESERVATION_VERIFY`、key epoch、trust anchor 与 purpose
`VERIFY_SAFETY_ADMISSION_RESERVATION`。独立
`SafetyOwnerWorkloadAttestationVerifierPort` 先生成 attestation verification，随后
Reservation verifier 才把二者 ref+digest 纳入
`SafetyAuthorizationReservationVerificationV1`；因此不存在 attestation 反向签
ReservationVerification 的摘要环。任一 Unknown/False 都不得接受 Reservation。该 key
由独立 Safety Identity / PKI / HSM owner 生成、轮换、吊销和证明，不得来自 Coordinator
进程或数据库、普通 workload identity、`SecretProviderPort` 或
`secrets-stackdocker`。

Reservation `expires_at` 必须是 subject/challenge expiry、两份 admission expiry、适用 Policy
Head/Bundle validity 与配置最大 TTL 的最早值。所有 TTL 判断只能使用独立
`SafetyTrustedTimeAuthorityPort` 返回的 `SafetyTrustedTimeAttestationV1`，不能使用调用方、
进程、数据库或 provider 自报的时间。每份 attestation 精确绑定 request nonce、
subject ref+digest、purpose、time-authority epoch、严格单调 counter、前序 attestation、
UTC lower/upper bound、最大不确定度、有效期、签名 key epoch 与 trust anchor。
Time Authority 是该证明的唯一 owner，以 durable CAS 独占
`(time_authority_epoch, authority_monotonic_counter, attestation_head_digest)`：同 epoch
counter 必须严格 `+1` 且 predecessor 精确匹配；恢复、source set 或 key continuity 改变时
epoch 只能 `+1` 并携带已验证 transition，新的 UTC lower bound 不得回退到前序 lower bound
之前。无法证明 head continuity 时 Authority 自身也不得签新 attestation。

所谓“已验证 transition”只能是具名、可解析且 canonical/signature 可重算的
`SafetyTrustedTimeEpochTransitionV1 ref+digest`。Genesis 固定
`successor_time_authority_epoch=1`、`successor_initial_authority_monotonic_counter=1`，所有
predecessor 字段均为 `null`，并由离线预置信任的 continuity root 签名；非 Genesis 固定
`successor_epoch=predecessor_epoch+1`、新 epoch counter 从 `1` 开始，逐字绑定上一 epoch
最后一份 attestation/counter、前后 source set、time-signing key 与 trust anchor。每一份
TimeAttestation 都必须引用本 epoch 的 exact transition ref+digest：同 epoch 后续
attestation 继续引用同一 transition，不允许只有首条持有、后续靠缓存猜测。
`SafetyTrustedTimeAuthorityPort.resolve_and_verify_epoch_transition` 必须验证 canonical digest、
continuity-root key epoch/吊销/trust、transition policy、epoch/counter 初值、predecessor、
source/key/anchor tuple 与 UTC lower-bound continuity；任何缺失、fork、Unknown 或普通
time-signing key 自批 transition 都 fail-closed。

consumer owner 在本地事务中以 `SafetyTrustedTimeCheckpointV1` CAS 推进已接受的
authority epoch/counter；回拨、重复 counter、chain gap/fork、epoch transition 无签名、
`upper_bound - lower_bound` 超政策、过期、吊销或任一解析/验证 Unknown 都返回
`SAFETY_TRUSTED_TIME_UNAVAILABLE` 或 `SAFETY_TIME_ROLLBACK` 并拒绝。首次 owner-local anchor
只有在 attested `upper_bound_utc <= expires_at` 且**实际 owner-store 线性化点**仍处于可信
elapsed budget 内才能形成。仅在事务开始前取得 attestation、比较一次 UTC、随后任意久地
持有事务不合规。

机械流程固定为：

1. owner 为本次不可变 commit subject 生成一次性 `owner_transaction_nonce_digest`；
2. `SafetyTrustedTimeCommitGuardPort.begin_commit_guard` 解析 exact TimeAttestation、
   epoch transition 与 time policy，由受信 monotonic elapsed source 记录 acceptance tick，
   签发一次性 `SafetyTrustedTimeCommitLeaseV1`，冻结 deadline tick、最大 elapsed budget、
   consumer、subject、purpose、storage profile 与 transaction nonce；
3. owner-local store 的最终 precommit/linearization hook 调用
   `consume_at_commit`。Guard 使用同一受信 elapsed source 读取线性化 tick；超过 lease
   deadline、elapsed upper bound 超预算、material/key/revocation/profile 漂移、nonce/subject
   不同或 lease replay 均中止整个事务；
4. 通过时，Guard 在同一 owner-local 原子提交中形成签名的
   `SafetyTrustedTimeCommitFreshnessProofV1`，并 CAS 写
   `SafetyTrustedTimeCheckpointV1`。Proof 绑定 lease、前序 checkpoint、store
   linearization token、acceptance/linearization/deadline ticks 与 outcome
   `FRESH_AT_OWNER_STORE_LINEARIZATION`；Checkpoint 冻结 proof/lease、commit subject、
   transaction nonce 与唯一 `time_consumption_key_digest`；
5. anchor 冻结该 checkpoint ref+digest；checkpoint 再单向解析 proof→lease→attestation→
   epoch transition。任一对象不可解析、签名/吊销/高水位为 Unknown 或不能证明与 anchor
   同一 owner-local transaction，均 fail-closed。

`owner_local_transaction_context` 是受控 storage implementation 提供的不可序列化 capability，
不能来自 Hub、Adapter、业务 payload 或网络调用。若 SQLite/未来 store 不能实现“Guard
线性化检查 + checkpoint + anchor 同事务”，真实实现保持 `NOT-IMPLEMENTED`，不能用 host
clock、sleep、缓存 attestation 或调用前日志冒充。Policy publication 的
receipt/Head/PointerRevision/fence/alias 事务也必须在同一门内完成。通用 anchor 至少冻结
exact attestation + checkpoint ref/digest 和用于比较的 upper bound，checkpoint 必须再冻结
exact commit lease/proof；Fence witness 额外直接复制 attestation/lease/proof/checkpoint
四组 ref+digest 以便 PRE/POST/ALIAS_COMMIT 逐字段比较。裸 `trusted_time_ref`、仅记录自报
`checked_at` 或未绑定 transaction nonce 的 proof 不构成证据。

resolver 返回 ACTIVE 不能消除其后 TOCTOU：各 owner 必须在**写入本地事务内部**消费一份
fresh attestation 并 CAS checkpoint，要求 attested upper bound 不晚于
`min(reservation.expires_at, reservation_verification.freshness_deadline)`。
CommitAttempt 创建时同时冻结
`dispatch_authorized_until = reservation.expires_at`；进入 outbox 和创建
`SafetyCommitDispatchClaimV1` 都只是领取，不证明已经调用 provider，也不延长 deadline。

Provider 业务请求不是一个 detached digest。target owner 必须先发布不可变
`SafetyProviderMutationRequestV1 ref+digest`：method/path、规范化 query、非秘密 header、
content-addressed body bytes、media type、route、effect-key carrier 与 credential injection
profile 都进入 canonical identity。正文和非秘密 header 必须可由 verifier 从 immutable blob
重读；凭据值不得进入该对象，只允许 opaque `SecretLease ref+digest` 在 egress boundary
注入。Claim、Capability、CallAttempt、Raw receipt、verification 与 final receipt 必须复制并
重算同一 request ref+digest，禁止在层间把它缩成来源不明的 `canonical_request_digest`。

Request 与 WireBytesEvidence 必须逐字绑定同一
`SafetyProviderWireCanonicalizationProfileV1 ref+digest`。V1 profile 至少冻结以下规则，
Adapter 不能各自解释：

- method 只能是 allowlist 内 ASCII token，identity 使用大写；大小写或 token 非法直接拒绝；
- path 必须是以 `/` 开头的 UTF-8 NFC 绝对路径；反斜杠、控制字符、非法 UTF-8/percent
  escape、解码后 `.`/`..` segment、编码斜杠/反斜杠均拒绝；只解码 unreserved octet，
  其余 percent hex 统一大写，不折叠连续 `/`；
- query 由 typed name/value multiset 构造，不接受调用者拼接的 raw query；字符串 NFC，
  只保留 RFC3986 unreserved，space 编码 `%20` 而非 `+`，按编码后 name/value bytes 排序，
  重复项保留且空值与缺值区分；
- 非秘密 header name 使用小写 ASCII，值去除首尾 OWS；obs-fold、控制字符、未 allowlist
  header 拒绝。重复 header 不做隐式逗号合并，按 name/value bytes 排序且重复保留；认证/
  credential 字段由 versioned injection profile 枚举，只记录字段名与 SecretLease ref/digest，
  其值不得进入 canonical nonsecret headers、body 或 evidence；
- body identity 是 send buffer 的精确 octets ref+SHA-256+length；不做 JSON 重排、换行、
  charset 或压缩的隐式转换。media type 使用注册的 canonical token；Content-Encoding 或
  redirect 未在 profile 明示允许时一律拒绝，安全变更 V1 禁止 redirect；
- 任一 profile ref/digest 不可解析、两端 profile 不同、字段无法按规则唯一规范化或实际
  buffer 在 attestation 后变化，均在首字节前 fail-closed。

进入 send primitive 前，egress owner 必须对实际待发缓冲区形成签名的
`SafetyProviderWireRequestAttestationV1`。它引用不可变 request、Capability、边界 attestation
与具名可解析的 `SafetyProviderWireBytesEvidenceV1 ref+digest`；后者在首次 send 前从 sealed
buffer 冻结实际 method/route/path/query/非秘密 headers/body bytes/effect-key carrier，并
明确 `credential_values_included=False`。Verifier 从该 evidence 的 typed fields 自行重算与
authorized request 相同 domain/field-name projection，不能信任 attestation 自报
`actual_business_wire_projection_digest`。认证 header 值永不落账，只记录被注入字段名集合
digest 与 SecretLease ref+digest。Verifier 要求
`actual_business_wire_projection_digest == authorized_business_wire_projection_digest`、
request/effect/provider/boundary 全部逐字相等且两份 attestation 签名/TTL/trust 都为
`True`；否则不得进入 send，不能以 TLS、HTTP 2xx 或日志字符串代替 byte-bound equality。
Boundary 与 Wire attestation 还必须分别经独立
`SafetyEgressWorkloadAttestationVerifierPort` 解析 material/policy/purpose/key epoch/
revocation/trust/time，生成两份
`SafetyEgressWorkloadAttestationVerificationV1 ref+digest`。最终
`SafetyProviderSendReceiptVerificationV1` 必须冻结两份 exact verification，要求都为
`VALID`、fresh、使用同一受信 trust snapshot，且各自 material operation 精确匹配；任一
`False` 使 send verification 为 INVALID，任一 `Unknown`（且无 False）使其为 UNKNOWN。
自签进程 key、普通 App/Connector credential、不可撤销长期 key 或只有裸 signature 的对象
一律不合规。

Wire verification 还必须沿 Wire attestation 内冻结的
`egress_boundary_attestation ref+digest` 与
`egress_boundary_attestation_verification ref+digest` 解析原始 Boundary attestation 及其
独立验证记录，不能只相信 Wire attestation 自报“来自同一边界”。Boundary verification
必须为 `VALID` 且 fresh；两条链的 `egress_boundary_ref/provider_ref/provider_route_digest`
必须逐字相等；Wire attestation 的 `wire_egress_workload_identity_ref`、
`wire_egress_workload_build_digest`、`wire_egress_workload_failure_domain` 必须分别等于
Boundary attestation 的 workload identity/build/failure-domain，并与两份 material 所允许
的 workload、build 与 failure-domain projection 相符。对应
`boundary_attestation_chain_valid`、`boundary_workload_identity_match_valid`、
`boundary_workload_build_match_valid`、`boundary_failure_domain_match_valid` 任一为
`False` 时 INVALID，任一为 `Unknown`（且无 False）时 UNKNOWN；缺 ref/digest、过期记录、
跨 workload、跨 build 或跨 failure-domain 拼接均在首字节前 fail-closed。

Claim 不得包含未来 Capability 的 ref/digest；它只冻结由
`commit_attempt_digest + effect_key_digest + provider_request_digest + provider_ref +
provider_route_digest + lease_generation + dispatch_authorized_until` 计算的 domain-separated
`provider_mutation_subject_digest`。唯一 `SafetyProviderMutationPort` 重算该 projection 并
逐字匹配 Claim 后，以 `dispatch_claim_digest` 为唯一 issuance key 做 CAS-on-NULL：
同 claim/subject replay 只返回同一 Capability，同 claim 不同 subject 或第二个 Capability
一律拒绝。随后它签发单向引用 Claim、subject、attempt/effect/request/provider/route/policy
epoch/lease/deadline 的 `SafetyProviderMutationCapabilityV1`，因此不存在 Claim↔Capability
摘要环，也不能在崩溃后换 nonce 重铸发送权。在进入第一次 mutating send primitive 的边界，
它必须：

1. 重新取得并验证 fresh `SafetyTrustedTimeAttestationV1`，要求 attested
   `upper_bound_utc < dispatch_authorized_until`；
2. 预写 content-addressed WireBytesEvidence、Boundary/Wire attestations；这些对象本身不授予
   发送权。独立 verifier 形成两份 immutable verification；
3. egress owner 在自己的 durable single-writer transaction 中重验 trusted time、两份
   verification 均 `VALID`/fresh、相同 trust snapshot、profile、sealed-buffer generation 与
   material operation，并解析、逐字匹配两份 verification 内冻结的 Trusted Time
   attestation/checkpoint ref+digest；CallAttempt 同时复制这两组 time/checkpoint
   ref+digest，禁止换证或只信布尔值。然后以
   `capability_consumption_key_digest` 唯一约束 CAS-on-NULL 写入
   `SafetyProviderMutationCapabilityConsumptionV1`，并创建绑定两份 raw attestation 与
   verification ref+digest 的 `SafetyProviderCallAttemptV1`。这是 owner-local 事务，不虚构
   与独立 verifier 跨 owner 同事务。consumption key 只由 Claim/subject/capability nonce
   派生，不含可变 boundary；Consumption、CallAttempt 与 attestation 的
   `egress_boundary_ref` 必须逐字等于 Capability；
4. 随即以同一 sealed buffer、canonical request 与 effect key 进入不可重入 send primitive；
   worker、
   target owner 和普通 Adapter 均无直连 provider 的网络路径。

`SafetyProviderCallAttemptV1` 只证明 egress send boundary 已进入，不宣称字节已发送或 effect
已发生。send primitive 只能先产生不受信的 `SafetyProviderRawSendReceiptV1`；独立
`SafetyProviderSendReceiptVerifierPort` 重算 raw/CallAttempt/Consumption/EgressAttestation/
request/effect/provider/trust 绑定后形成
`SafetyProviderSendReceiptVerificationV1`。其中任一 gate 为 `False` 时 outcome 必须为
`INVALID`，无 False 但存在 `Unknown` 时为 `UNKNOWN`，全部 `is True` 且 raw
`handoff_claim=CONFIRMED` 时才为 `VALID`。只有 VALID verification 才能单向封装为
`handoff_state=CONFIRMED` 的 `SafetyProviderSendReceiptV1`；verification 只引用 Raw，
最终 SendReceipt 再引用 verification，因此无摘要环和“先验后生”倒置。HTTP 2xx、raw claim、
capability consumption、worker 退出或 DispatchClaim 都不能冒充 verified handoff。若在
Capability 消费/CallAttempt 落账后没有最终 verified SendReceipt，无论崩溃发生在 socket write
前、中或后，结果一律为 `effect_unknown + DO_NOT_REPLAY + ReconciliationCase`；不得重发、
换 effect key 或新发 capability，只能按原 key 做认证查询。若 provider 不能原生支持
idempotency/effect query，或 deadline-critical 请求无法在 provider 边界校验 deadline，
该 Adapter 对该安全动作不合规并 fail-closed。到期前只有 Claim 而尚未进入 send boundary，
或 egress 在边界重验时已到期，必须生成 `EXPIRED_NOT_SENT` evidence，provider call 数为 0；
再次执行必须新建 subject 并重新双人 admission。

“首个 anchor”机械定义为：PREPARE 是同一 Safety Survival owner-local transaction 中的
PreparedCommand + Challenge；COMMIT 是同一 target-owner transaction 中的 CommitAttempt +
唯一 effect-key outbox reservation（它只保留授权，实际调用仍必须经过 DispatchClaim、
一次性 ProviderMutationCapability 与 ProviderCallAttempt/verified SendReceipt）；
POLICY_PUBLICATION 是 Policy owner 已形成的 immutable PublicationReceipt + successor
Head + PointerRevision 被唯一 Fence Authority 在同一 alias-owner transaction 中以
ALIAS_COMMIT witness + `alias_state_generation/digest` CAS 激活。只有这些 anchor
在 TTL 门内成立后，后续才可按原键查询/收尾/对账；消息、resolver 200、Reservation digest
或单独草稿都不算 anchor。

`EmergencyAdmissionConsumptionV1` 对 `consumption_key_digest` 做全局 CAS-on-NULL，一个
admission digest 一生只能绑定一个 subject 和一个
`SafetyAuthorizationReservationV1` atomic anchor。`SafetySubjectNonceConsumptionV1`
同时对 `subject_nonce_key_digest` CAS-on-NULL；因此同一 subject/nonce 即使换成两份新的
真人 admission 也不能再取得第二个 reservation。完全相同的
`admission_digest + subject_digest + replay_domain_digest` 重试只返回首次 consumption 与
同一 reservation 当前关联的脱敏终态；下游 owner record 尚未形成时返回
`RESERVED/RECONCILIATION_REQUIRED`，不得另开 effect。任何 kind、subject、nonce、actor、
scope、epoch、channel、audience、purpose 或 reservation 差异均返回冲突，
`SAFETY_PREPARE`、`SAFETY_COMMIT` 与
`POLICY_PUBLICATION` 绝不跨 phase 复用。

所有 `[2]` actor/admission 组合必须把
`actor_ref + admission_ref + admission_digest + replay_domain_digest` 作为不可拆分 tuple，
按 `actor_ref` 的规范化 UTF-8 bytes 严格升序；actor、admission、subject 或 replay-domain
重复、数组错序、长度不为 2、两个 subject digest 不同一律拒绝，不做静默排序或去重。

不得把 Safety Admission、target owner 与 Policy owner 写成一个虚构的分布式事务。
`SafetyAdmissionReservationPort` 的唯一 owner（Safety Admission Coordinator）先在自己的
serializable transaction 中校验两个不同真人的 subject-bound admission，并原子完成：

1. 对两个 `consumption_key_digest` CAS-on-NULL；
2. 对一个 `subject_nonce_key_digest` CAS-on-NULL；
3. 插入一个 immutable `SafetyAuthorizationReservationV1`；
4. 插入两条 AdmissionConsumption 与一条 SubjectNonceConsumption，三者都只指向该
   reservation；
5. `SAFETY_COMMIT` 还以 expected revision CAS ChallengeStateHead，从 PREPARED 追加
   COMMITTING revision；其他 state 不可 reserve。

随后各事实 owner 只在**自己的**事务内消费 reservation：Safety Survival owner 以
reservation ref/digest + prepare projection 唯一创建 PreparedCommand/Challenge；
Safety Admission Coordinator 在其后独立验证二者，再由唯一
`SafetyChallengeStatePort` 幂等初始化 PREPARED revision/head；target owner 以
reservation ref/digest + commit projection +
effect key 唯一创建 immutable `SafetyCommitAttemptV1`；Policy owner 以 reservation
ref/digest + publication projection 更新自己的 receipt/Head/PointerRevision/alias。
Coordinator 与下游 owner 之间不存在原子提交；任一崩溃都保留“admission/nonce 已消费 +
reservation 待对账”，精确 replay 只按 reservation/idempotency/effect key 查询或续作，永不
释放 admission/nonce，也不换键创建第二次动作。
Reservation 到期只禁止尚未开始的下游 effect，并形成拒绝/对账证据；不会删除 Consumption
或释放 admission/nonce。确需再次授权时必须创建新的 subject/nonce 并重新取得两份 admission。

ChallengeState 全链唯一 owner/写者是 Safety Admission Coordinator 的
`SafetyChallengeStatePort`；Safety Survival、target owner、signer、verifier 和 Policy owner
只能提交已验真的 transition evidence，不能直接创建、覆盖或 CAS state revision/head。
Prepared/Challenge 已创建但 PREPARED revision 尚未初始化时，commit fail-closed 为
`CHALLENGE_STATE_NOT_READY`，对账只补同一 genesis，不重做 prepare effect。

外部 provider 不可纳入 target-owner 本地事务时只经 CommitAttempt journal/outbox 使用原
effect key，响应不确定进入 `SafetyEffectUnknownV1`；最终 OwnerReceipt/EffectUnknown 都必须
追加引用原 CommitAttempt ref+digest。独立 signer 不参与 target-owner 本地事务。

`OpenReconciliationCase` 只开案不裁决；`SealIncidentEvidence` 只写入预批准的本地 WORM；
`StageRecoveryValidation` 只验证候选恢复条件，不能重新启用权限、连接或业务执行。任意对外证据
导出、恢复启用、正常签发或权限扩展仍走常规治理/Delivery。

`SafetyChallengeV1` 是 immutable admission subject，摘要**不包含任何可变 state**。状态只由
append-only `SafetyChallengeStateRevisionV1` 与单行
`SafetyChallengeStateHeadV1` 的 expected generation/revision/head digest CAS 管理。初始
revision 必须为 generation 1、predecessor null、state PREPARED；后续 generation 必须
严格 +1 并引用当前 revision，`(challenge_digest, generation)` 唯一。允许转换只有：

```text
PREPARED
  → COMMITTING | REJECTED | EXPIRED

COMMITTING
  → LOCAL_FENCE_CONFIRMED
  | LOCAL_FENCE_CONFIRMED_EXTERNAL_PENDING
  | EFFECT_UNKNOWN
  | REJECTED
```

target owner 不直接改 ChallengeStateHead；Coordinator 只在验证 reservation、
CommitAttempt 与 owner record ref+digest 后追加 successor revision。回告丢失时保持
COMMITTING 并按 reservation/effect key 对账，不猜 terminal state。

commit 的两个 admission 必须来自 prepare 时**同一组两个不同真人**，但都是 challenge 产生后
重新取得的 fresh strong-auth admission；`admission_kind=SAFETY_COMMIT`，
`admission_subject_type=SafetyChallengeV1`，且两者逐字绑定同一
command/prepared/challenge digest、subject nonce、audience、purpose、effect key 和 target。
credential/authorization epoch、职责、scope 或 assurance 任一漂移都使 challenge 失效；
nonce 与 admission consumption 均由 commit reservation 按上文 CAS 单次消费；target owner
只接受该 reservation，不再次解释通用 admission。

```text
SafetyEffectObservationV1 {
  observation_ref
  command_digest
  challenge_digest
  effect_key_digest
  target_owner
  target_ref
  provider_ref
  authenticated_query_receipt_ref
  authenticated_query_receipt_digest
  provider_effect_state      CONFIRMED | CONFIRMED_NO_EFFECT | UNKNOWN
  provider_effect_receipt_ref
  provider_effect_receipt_digest
  observed_at
  freshness_deadline
  observation_digest
}

SafetyOwnerReceiptPayloadV1 {
  payload_schema_version
  issuer_owner_ref
  commit_attempt_ref
  commit_attempt_digest
  dispatch_claim_ref_if_applicable
  dispatch_claim_digest_if_applicable
  provider_call_attempt_ref_if_applicable
  provider_call_attempt_digest_if_applicable
  provider_send_receipt_ref_if_confirmed
  provider_send_receipt_digest_if_confirmed
  command_ref
  command_digest
  prepared_command_digest
  challenge_ref
  challenge_digest
  issuance_policy_head_ref
  issuance_policy_head_generation
  issuance_policy_head_digest
  issuance_policy_head_pointer_revision_ref
  issuance_policy_head_pointer_revision_generation
  issuance_policy_head_pointer_revision_digest
  required_issuance_policy_bundle_ref
  required_issuance_policy_bundle_digest
  prepare_admission_digests[2]
  commit_admission_digests[2]
  distinct_actor_refs[2]
  idempotency_key_digest
  effect_key_digest
  target_owner
  target_ref
  target_owner_sequence
  before_digest
  after_digest
  local_credential_epoch_after
  local_authorization_epoch_after
  lease_admission_closed_witness
  egress_deny_witness
  kill_or_isolate_witness
  local_fence_outcome        CONFIRMED
  external_provider_effect   CONFIRMED | NOT_APPLICABLE | EFFECT_UNKNOWN
  external_provider_receipt_ref_if_applicable
  external_provider_receipt_digest_if_applicable
  reconciliation_case_ref_if_unknown
  supersedes_owner_receipt_ref_if_reconciled
  expected_reconciliation_head_generation
  expected_reconciliation_head_digest
  reconciliation_effect_observation_ref_if_applicable
  reconciliation_effect_observation_digest_if_applicable
  authenticated_query_receipt_ref_if_applicable
  authenticated_query_receipt_digest_if_applicable
  preexisting_local_evidence_refs[]
  effect_observed_at
  receipt_signer_failure_domain
  issued_at
  trusted_time_attestation_ref
  trusted_time_attestation_digest
}

SafetyTargetOwnerSigningSubjectV1 {
  target_owner_signing_subject_ref
  target_owner_signing_subject_digest
  target_owner_ref
  payload_ref
  canonical_receipt_payload_digest
  command_digest
  challenge_digest
  effect_key_digest
  target_ref
  issuance_policy_head_ref
  issuance_policy_head_generation
  issuance_policy_head_digest
  issuance_policy_head_pointer_revision_ref
  issuance_policy_head_pointer_revision_generation
  issuance_policy_head_pointer_revision_digest
  issuance_policy_fence_epoch
  issuance_alias_commit_fence_witness_ref
  issuance_alias_commit_fence_witness_digest
  issuance_policy_bundle_ref
  issuance_policy_bundle_digest
  audience
  purpose
  issued_at
  expires_at
}

SafetySigningRequestV1 {
  signing_request_ref
  signing_request_schema_version
  target_owner_ref
  target_owner_signing_subject_ref
  target_owner_signing_subject_digest
  target_owner_attestation_ref
  target_owner_attestation_digest
  target_owner_attestation_verification_ref
  target_owner_attestation_verification_digest
  payload_ref
  canonical_receipt_payload_digest
  command_digest
  challenge_digest
  effect_key_digest
  target_ref
  issuance_policy_head_ref
  issuance_policy_head_generation
  issuance_policy_head_digest
  issuance_policy_head_pointer_revision_ref
  issuance_policy_head_pointer_revision_generation
  issuance_policy_head_pointer_revision_digest
  issuance_policy_fence_epoch
  issuance_alias_commit_fence_witness_ref
  issuance_alias_commit_fence_witness_digest
  issuance_policy_bundle_ref
  issuance_policy_bundle_digest
  audience
  purpose
  issued_at
  expires_at
  signing_request_canonicalization_profile RFC8785-JCS-UTF8-NFC
  signing_request_digest_algorithm SHA-256
  signing_request_domain_separator flai.safety.signing-request.v1\0
  signing_request_digest
}

SafetySignatureEnvelopeCoreV1 {
  envelope_core_ref
  envelope_core_digest
  envelope_core_schema_version
  signing_request_ref
  signing_request_digest
  safety_signing_material_ref
  signer_key_epoch
  signature_algorithm
  signed_digest
  trust_anchor_ref
  trust_anchor_epoch
  signature_policy_digest
  issuance_policy_head_ref
  issuance_policy_head_generation
  issuance_policy_head_digest
  issuance_policy_head_pointer_revision_ref
  issuance_policy_head_pointer_revision_generation
  issuance_policy_head_pointer_revision_digest
  issuance_policy_fence_epoch
  issuance_alias_commit_fence_witness_ref
  issuance_alias_commit_fence_witness_digest
  issuance_policy_bundle_ref
  issuance_policy_bundle_digest
  signer_operation_ref
  signer_operation_digest
}

SafetySignatureEnvelopeV1 {
  signature_envelope_ref
  signature_envelope_digest
  envelope_core_ref
  envelope_core_digest
  signature
  pre_hsm_fence_witness_ref
  pre_hsm_fence_witness_digest
  post_hsm_fence_witness_ref
  post_hsm_fence_witness_digest
  envelope_canonicalization_profile RFC8785-JCS-UTF8-NFC
  envelope_digest_algorithm SHA-256
  envelope_domain_separator flai.safety.signature-envelope.v1\0
}

SafetyOwnerReceiptV1 {
  owner_receipt_ref
  receipt_schema_version
  payload_ref
  payload_canonicalization_profile RFC8785-JCS-UTF8-NFC
  payload_digest_algorithm  SHA-256
  payload_digest_domain_separator flai.safety.owner-receipt-payload.v1\0
  canonical_receipt_payload_digest
  signature_envelope_ref
  signature_envelope_digest
  receipt_canonicalization_profile RFC8785-JCS-UTF8-NFC
  receipt_digest_algorithm  SHA-256
  receipt_digest_domain_separator flai.safety.owner-receipt.v1\0
  receipt_digest
}

SafetyIssuancePolicyBundleV1 {
  issuance_policy_bundle_ref
  issuance_policy_bundle_epoch
  command_policy_ref
  command_policy_digest
  admission_policy_ref
  admission_policy_digest
  signing_policy_ref
  signing_policy_digest
  signer_failure_domain_policy_ref
  signer_failure_domain_policy_digest
  allowed_signature_algorithms[]
  valid_from
  valid_until
  bundle_canonicalization_profile RFC8785-JCS-UTF8-NFC
  bundle_digest_algorithm    SHA-256
  bundle_digest_domain_separator flai.safety.issuance-policy-bundle.v1\0
  issuance_policy_bundle_digest
}

SafetyVerificationPolicyBundleV1 {
  verification_policy_bundle_ref
  verification_policy_bundle_epoch
  verifier_policy_ref
  verifier_policy_digest
  factory_policy_ref
  factory_policy_digest
  issuance_acceptance_policy_ref
  issuance_acceptance_policy_digest
  accepted_issuance_policy_bundle_digests[]
  allowed_signature_algorithms[]
  trust_snapshot_ref
  trust_snapshot_digest
  valid_from
  valid_until
  bundle_canonicalization_profile RFC8785-JCS-UTF8-NFC
  bundle_digest_algorithm    SHA-256
  bundle_digest_domain_separator flai.safety.verification-policy-bundle.v1\0
  verification_policy_bundle_digest
}

SafetyPolicyPublicationChallengeV1 {
  publication_challenge_ref
  publication_challenge_digest
  challenge_schema_version
  subject_type              POLICY_PUBLICATION
  policy_role               ISSUANCE | VERIFICATION
  publication_mode          ADVANCE | ROLLBACK
  policy_owner_ref
  required_publication_assurance_profile_ref
  required_publication_scope_digest
  publication_audience
  publication_purpose
  expected_policy_head_ref
  expected_policy_head_generation
  expected_policy_head_digest
  expected_policy_head_pointer_revision_ref
  expected_policy_head_pointer_revision_generation
  expected_policy_head_pointer_revision_digest
  expected_policy_fence_epoch
  expected_alias_commit_fence_witness_ref
  expected_alias_commit_fence_witness_digest
  new_policy_bundle_ref
  new_policy_bundle_digest
  supersedes_policy_bundle_ref
  supersedes_policy_bundle_digest
  rollback_reason_digest
  rollback_incident_ref
  rollback_incident_digest
  effective_from
  issued_at
  expires_at
  one_time_nonce_digest
  publication_idempotency_key_digest
  publication_projection_digest
}

SafetyPolicyPublicationReceiptV1 {
  publication_receipt_ref
  safety_authorization_reservation_ref
  safety_authorization_reservation_digest
  reservation_verification_ref
  reservation_verification_digest
  reservation_checked_at_upper_bound_utc
  reservation_trusted_time_attestation_ref
  reservation_trusted_time_attestation_digest
  reservation_trusted_time_checkpoint_ref
  reservation_trusted_time_checkpoint_digest
  publication_challenge_ref
  publication_challenge_digest
  publication_one_time_nonce_digest
  publication_idempotency_key_digest
  publication_projection_digest
  policy_role               ISSUANCE | VERIFICATION
  publication_mode          ADVANCE | ROLLBACK
  policy_owner_ref
  policy_owner_sequence
  human_policy_admission_refs[2]
  human_policy_admission_digests[2]
  distinct_actor_refs[2]
  required_publication_assurance_profile_ref
  required_publication_scope_digest
  publication_audience
  publication_purpose
  expected_policy_head_ref
  expected_policy_head_generation
  expected_policy_head_digest
  expected_policy_head_pointer_revision_ref
  expected_policy_head_pointer_revision_generation
  expected_policy_head_pointer_revision_digest
  expected_policy_fence_epoch
  expected_alias_commit_fence_witness_ref
  expected_alias_commit_fence_witness_digest
  new_policy_bundle_ref
  new_policy_bundle_digest
  supersedes_policy_bundle_ref
  supersedes_policy_bundle_digest
  rollback_reason_digest
  rollback_incident_ref
  rollback_incident_digest
  effective_from
  issued_at
  policy_owner_signature_ref
  policy_owner_signature_digest
  publication_receipt_canonicalization_profile RFC8785-JCS-UTF8-NFC
  publication_receipt_digest_algorithm SHA-256
  publication_receipt_domain_separator flai.safety.policy-publication-receipt.v1\0
  publication_receipt_digest
}

SafetyIssuancePolicyHeadV1 {
  head_ref
  policy_role               ISSUANCE
  policy_owner_ref
  generation
  predecessor_head_ref
  predecessor_head_digest
  current_issuance_policy_bundle_ref
  current_issuance_policy_bundle_digest
  publication_receipt_ref
  publication_receipt_digest
  updated_at
  head_canonicalization_profile RFC8785-JCS-UTF8-NFC
  head_digest_algorithm      SHA-256
  head_digest_domain_separator flai.safety.issuance-policy-head.v1\0
  head_digest
}

SafetyVerificationPolicyHeadV1 {
  head_ref
  policy_role               VERIFICATION
  policy_owner_ref
  generation
  predecessor_head_ref
  predecessor_head_digest
  current_verification_policy_bundle_ref
  current_verification_policy_bundle_digest
  publication_receipt_ref
  publication_receipt_digest
  updated_at
  head_canonicalization_profile RFC8785-JCS-UTF8-NFC
  head_digest_algorithm      SHA-256
  head_digest_domain_separator flai.safety.verification-policy-head.v1\0
  head_digest
}

SafetyPolicyHeadPointerRevisionV1 {
  pointer_revision_ref
  pointer_revision_generation
  policy_role               ISSUANCE | VERIFICATION
  policy_owner_ref
  predecessor_pointer_revision_ref
  predecessor_pointer_revision_digest
  current_head_ref
  current_head_generation
  current_head_digest
  current_policy_bundle_ref
  current_policy_bundle_digest
  publication_receipt_ref
  publication_receipt_digest
  updated_at
  pointer_revision_canonicalization_profile RFC8785-JCS-UTF8-NFC
  pointer_revision_digest_algorithm SHA-256
  pointer_revision_digest_domain_separator flai.safety.policy-head-pointer-revision.v1\0
  pointer_revision_digest
}

SafetyPolicyAliasTransitionSubjectV1 {
  alias_transition_subject_ref
  alias_transition_subject_digest
  policy_role               ISSUANCE | VERIFICATION
  policy_owner_ref
  publication_receipt_ref
  publication_receipt_digest
  expected_alias_state_generation
  expected_alias_state_digest
  expected_pointer_revision_ref
  expected_pointer_revision_generation
  expected_pointer_revision_digest
  expected_policy_fence_epoch
  expected_alias_commit_fence_witness_ref
  expected_alias_commit_fence_witness_digest
  successor_pointer_revision_ref
  successor_pointer_revision_generation
  successor_pointer_revision_digest
  successor_policy_head_ref
  successor_policy_head_generation
  successor_policy_head_digest
  successor_policy_bundle_ref
  successor_policy_bundle_digest
  transition_idempotency_key_digest
  requested_at
  request_expires_at
}

SafetyPolicyAliasTransitionRequestV1 {
  alias_transition_request_ref
  alias_transition_request_digest
  policy_role               ISSUANCE | VERIFICATION
  policy_owner_ref
  alias_transition_subject_ref
  alias_transition_subject_digest
  policy_owner_attestation_ref
  policy_owner_attestation_digest
  policy_owner_attestation_verification_ref
  policy_owner_attestation_verification_digest
  publication_receipt_ref
  publication_receipt_digest
  expected_alias_state_generation
  expected_alias_state_digest
  expected_pointer_revision_ref
  expected_pointer_revision_generation
  expected_pointer_revision_digest
  expected_policy_fence_epoch
  expected_alias_commit_fence_witness_ref
  expected_alias_commit_fence_witness_digest
  successor_pointer_revision_ref
  successor_pointer_revision_generation
  successor_pointer_revision_digest
  successor_policy_head_ref
  successor_policy_head_generation
  successor_policy_head_digest
  successor_policy_bundle_ref
  successor_policy_bundle_digest
  transition_idempotency_key_digest
  requested_at
  request_expires_at
}

SafetyPolicyFenceWitnessV1 {
  fence_witness_ref
  fence_witness_digest
  fence_witness_schema_version
  fence_authority_ref
  fence_authority_epoch
  policy_role               ISSUANCE | VERIFICATION
  policy_fence_epoch
  witness_kind              ALIAS_COMMIT | SIGN_PRE | SIGN_POST
  alias_ref
  alias_transition_request_ref_if_commit
  alias_transition_request_digest_if_commit
  predecessor_alias_state_generation_if_commit
  predecessor_alias_state_digest_if_commit
  pointer_revision_ref
  pointer_revision_generation
  pointer_revision_digest
  policy_head_ref
  policy_head_generation
  policy_head_digest
  policy_bundle_ref
  policy_bundle_digest
  publication_receipt_ref
  publication_receipt_digest
  signing_request_ref_if_sign
  signing_request_digest_if_sign
  envelope_core_ref_if_sign
  envelope_core_digest_if_sign
  signer_operation_ref_if_sign
  signer_operation_digest_if_sign
  predecessor_sign_witness_ref_if_post
  predecessor_sign_witness_digest_if_post
  signature_bytes_digest_if_post
  trusted_time_attestation_ref
  trusted_time_attestation_digest
  trusted_time_commit_lease_ref
  trusted_time_commit_lease_digest
  trusted_time_commit_freshness_proof_ref
  trusted_time_commit_freshness_proof_digest
  trusted_time_checkpoint_ref
  trusted_time_checkpoint_digest
  trusted_time_upper_bound_utc
  fence_signing_key_ref
  fence_signing_key_epoch
  fence_trust_anchor_ref
  fence_trust_anchor_digest
  signature_algorithm
  signature
}

SafetyPolicyHeadCurrentAliasV1 {
  alias_ref                 flai://safety-policy-head-current/{policy_role}
  policy_role               ISSUANCE | VERIFICATION
  alias_state_generation
  current_pointer_revision_ref
  current_pointer_revision_generation
  current_pointer_revision_digest
  current_policy_fence_epoch
  current_alias_commit_fence_witness_ref
  current_alias_commit_fence_witness_digest
  alias_state_digest
}

SafetyPolicyAliasCommitResultV1 {
  alias_commit_result_ref
  alias_commit_result_digest
  alias_transition_request_ref
  alias_transition_request_digest
  committed_alias_ref
  committed_alias_state_generation
  committed_alias_state_digest
  alias_commit_fence_witness_ref
  alias_commit_fence_witness_digest
  fence_authority_sequence
  committed_at
}

SafetyReceiptVerificationV1 {
  verification_schema_version
  verification_key_digest
  verification_ref
  owner_receipt_ref
  owner_receipt_digest
  payload_ref
  canonical_receipt_payload_digest
  signature_envelope_ref
  signature_envelope_digest
  signature_envelope_core_ref
  signature_envelope_core_digest
  signing_request_ref
  signing_request_digest
  target_owner_attestation_ref
  target_owner_attestation_digest
  target_owner_attestation_verification_ref
  target_owner_attestation_verification_digest
  verifier_ref
  issuance_policy_head_ref
  issuance_policy_head_generation
  issuance_policy_head_digest
  issuance_policy_head_pointer_revision_ref
  issuance_policy_head_pointer_revision_generation
  issuance_policy_head_pointer_revision_digest
  issuance_policy_fence_epoch
  issuance_alias_commit_fence_witness_ref
  issuance_alias_commit_fence_witness_digest
  pre_hsm_fence_witness_ref
  pre_hsm_fence_witness_digest
  post_hsm_fence_witness_ref
  post_hsm_fence_witness_digest
  issuance_policy_publication_receipt_ref
  issuance_policy_publication_receipt_digest
  issuance_policy_bundle_ref
  issuance_policy_bundle_digest
  required_verification_policy_bundle_ref
  required_verification_policy_bundle_digest
  observed_verification_policy_head_ref
  observed_verification_policy_head_generation
  observed_verification_policy_head_digest
  observed_verification_policy_head_pointer_revision_ref
  observed_verification_policy_head_pointer_revision_generation
  observed_verification_policy_head_pointer_revision_digest
  verifier_policy_digest
  factory_policy_digest
  trust_snapshot_ref
  trust_snapshot_digest
  signing_material_ref_match True | False | Unknown
  signer_key_epoch
  signer_key_epoch_match     True | False | Unknown
  signature_algorithm_allowed True | False | Unknown
  signature_policy_match     True | False | Unknown
  signer_failure_domain_valid True | False | Unknown
  key_revocation_state       NOT_REVOKED | REVOKED | UNKNOWN
  trust_anchor_ref
  trust_anchor_epoch
  trust_anchor_match         True | False | Unknown
  trust_snapshot_fresh       True | False | Unknown
  trusted_time_attestation_ref
  trusted_time_attestation_digest
  trusted_time_checkpoint_ref
  trusted_time_checkpoint_digest
  trusted_time_upper_bound_utc
  canonical_encoding_valid   True | False | Unknown
  canonical_digest_match     True | False | Unknown
  receipt_envelope_binding_match True | False | Unknown
  signature_valid            True | False | Unknown
  trusted_time_valid         True | False | Unknown
  owner_effect_evidence_valid True | False | Unknown
  local_fence_verified       True | False | Unknown
  external_effect_applicability_valid True | False | Unknown
  external_postcondition_verified True | False | Unknown | NOT_APPLICABLE
  reconciliation_case_binding_valid True | False | Unknown
  reconciliation_observation_binding_valid True | False | Unknown | NOT_APPLICABLE
  authenticated_query_receipt_valid True | False | Unknown | NOT_APPLICABLE
  effect_observation_fresh True | False | Unknown | NOT_APPLICABLE
  provider_receipt_binding_valid True | False | Unknown | NOT_APPLICABLE
  dispatch_claim_binding_valid True | False | Unknown | NOT_APPLICABLE
  provider_call_attempt_binding_valid True | False | Unknown | NOT_APPLICABLE
  provider_send_receipt_binding_valid True | False | Unknown | NOT_APPLICABLE
  signing_request_binding_valid True | False | Unknown
  policy_fence_binding_valid   True | False | Unknown
  policy_fence_monotonic_valid True | False | Unknown
  pre_post_fence_chain_valid   True | False | Unknown
  target_owner_attestation_valid True | False | Unknown
  issuance_policy_head_publication_valid True | False | Unknown
  issuance_policy_head_binding_valid True | False | Unknown
  issuance_policy_bundle_binding_valid True | False | Unknown
  issuance_policy_bundle_accepted True | False | Unknown
  verification_policy_bundle_binding_valid True | False | Unknown
  verification_policy_head_binding_valid True | False | Unknown
  factory_policy_match        True | False | Unknown
  issuer_owner_match         True | False | Unknown
  actor_set_binding_valid    True | False | Unknown
  commit_admissions_fresh    True | False | Unknown
  nonce_consumption_valid    True | False | Unknown
  target_cas_valid           True | False | Unknown
  effect_key_binding_valid   True | False | Unknown
  supersedes_binding_valid   True | False | Unknown | NOT_APPLICABLE
  reconciliation_head_cas_valid True | False | Unknown | NOT_APPLICABLE
  target_owner_sequence_valid True | False | Unknown
  verification_outcome       VALID | INVALID | UNKNOWN
  verified_at
  freshness_deadline
  failure_codes[]
  verification_canonicalization_profile RFC8785-JCS-UTF8-NFC
  verification_digest_algorithm SHA-256
  verification_digest_domain_separator flai.safety.receipt-verification.v1\0
  verification_digest
}

FullSafetyEffectVerifiedV1 {
  result_ref
  result_key_digest
  result_chain_key_digest
  result_generation
  predecessor_result_ref
  predecessor_result_digest
  owner_receipt_ref
  owner_receipt_digest
  verification_ref
  verification_digest
  verification_policy_bundle_ref
  verification_policy_bundle_digest
  verification_policy_head_ref
  verification_policy_head_generation
  verification_policy_head_digest
  verification_policy_head_pointer_revision_ref
  verification_policy_head_pointer_revision_generation
  verification_policy_head_pointer_revision_digest
  factory_policy_digest
  external_provider_effect   CONFIRMED | NOT_APPLICABLE
  outcome                    FULL_EFFECT_VERIFIED
  constructed_at
  result_digest
}

LocalFenceVerifiedExternalPendingV1 {
  result_ref
  result_key_digest
  result_chain_key_digest
  result_generation
  predecessor_result_ref
  predecessor_result_digest
  owner_receipt_ref
  owner_receipt_digest
  verification_ref
  verification_digest
  verification_policy_bundle_ref
  verification_policy_bundle_digest
  verification_policy_head_ref
  verification_policy_head_generation
  verification_policy_head_digest
  verification_policy_head_pointer_revision_ref
  verification_policy_head_pointer_revision_generation
  verification_policy_head_pointer_revision_digest
  factory_policy_digest
  local_fence_outcome        CONFIRMED
  external_provider_effect   EFFECT_UNKNOWN
  reconciliation_case_ref
  display_state              AMBER
  outcome                    LOCAL_FENCE_VERIFIED_EXTERNAL_PENDING
  constructed_at
  result_digest
}

SafetyResultInvalidatedV1 {
  result_ref
  result_key_digest
  result_chain_key_digest
  result_generation
  predecessor_result_ref
  predecessor_result_digest
  owner_receipt_ref
  owner_receipt_digest
  verification_ref
  verification_digest
  verification_policy_bundle_ref
  verification_policy_bundle_digest
  verification_policy_head_ref
  verification_policy_head_generation
  verification_policy_head_digest
  verification_policy_head_pointer_revision_ref
  verification_policy_head_pointer_revision_generation
  verification_policy_head_pointer_revision_digest
  factory_policy_digest
  display_state              RED
  outcome                    SAFETY_RESULT_INVALIDATED
  reason_codes[]
  constructed_at
  result_digest
}

SafetyResultInconclusiveV1 {
  result_ref
  result_key_digest
  result_chain_key_digest
  result_generation
  predecessor_result_ref
  predecessor_result_digest
  owner_receipt_ref
  owner_receipt_digest
  verification_ref
  verification_digest
  verification_policy_bundle_ref
  verification_policy_bundle_digest
  verification_policy_head_ref
  verification_policy_head_generation
  verification_policy_head_digest
  verification_policy_head_pointer_revision_ref
  verification_policy_head_pointer_revision_generation
  verification_policy_head_pointer_revision_digest
  factory_policy_digest
  display_state              AMBER
  outcome                    SAFETY_RESULT_INCONCLUSIVE
  reason_codes[]
  retry_disposition          REVERIFY_SAME_RECEIPT_WITH_HEAD_CAS
  constructed_at
  result_digest
}

SafetyResultHeadV1 {
  result_chain_key_digest
  generation
  head_result_ref
  head_result_digest
  head_owner_receipt_ref
  head_owner_receipt_digest
  head_verification_ref
  head_verification_digest
  head_verification_policy_bundle_ref
  head_verification_policy_bundle_digest
  head_verification_policy_head_ref
  head_verification_policy_head_generation
  head_verification_policy_head_digest
  head_verification_policy_head_pointer_revision_ref
  head_verification_policy_head_pointer_revision_generation
  head_verification_policy_head_pointer_revision_digest
  head_verification_freshness_deadline
  head_outcome
  updated_at
  head_canonicalization_profile RFC8785-JCS-UTF8-NFC
  head_digest_algorithm      SHA-256
  head_digest_domain_separator flai.safety.result-head.v1\0
  head_digest
}

SafetyEffectUnknownV1 {
  effect_unknown_ref
  effect_unknown_digest
  commit_attempt_ref
  commit_attempt_digest
  dispatch_claim_ref_if_claimed
  dispatch_claim_digest_if_claimed
  provider_call_attempt_ref_if_entered
  provider_call_attempt_digest_if_entered
  provider_send_receipt_ref_if_any
  provider_send_receipt_digest_if_any
  command_digest
  prepared_command_digest
  challenge_digest
  commit_admission_digests[2]
  distinct_actor_refs[2]
  idempotency_key_digest
  effect_key_digest
  target_ref
  last_known_local_fence_state
  last_known_provider_state
  reconciliation_case_ref
  retry_disposition          DO_NOT_REPLAY
  observed_at
}
```

所有 `*_if_*` 字段都是**显式可空字段**，不是可省略字段：canonical object 中必须出现，
值只能是完整 ref/digest 或 JSON `null`；ref/digest 成对同空同非空，未知字段、单边为空和
字段缺失均拒绝。`dispatch_claim_*_if_applicable` 只描述 owner 是否采用异步领取拓扑：
若使用则 verifier 必须把 `dispatch_claim_binding_valid` 判为 `True`，同步 owner 执行则该对
为 `null` 且 gate 为 `NOT_APPLICABLE`。它不决定 external provider applicability。

Provider 相关字段按以下互斥分支解释，调用者不得自选 gate：

- `external_provider_effect=NOT_APPLICABLE`：ProviderCallAttempt、ProviderSendReceipt 与
  external-provider receipt 三组字段必须为 `null`，对应 gate 必须为
  `NOT_APPLICABLE`；
- 初始 `external_provider_effect=CONFIRMED`：ProviderCallAttempt 与
  `handoff_state=CONFIRMED` 的 verified ProviderSendReceipt 必须存在，对应 binding gate
  必须均为 `True`；
- 对账后的 `CONFIRMED`：若原 send receipt 缺失，ProviderSendReceipt 对可保持 `null` 且
  gate 为 `NOT_APPLICABLE`，但原 CallAttempt（若已进入 send boundary）、authenticated
  query receipt、EffectObservation、external-provider effect receipt 与 supersedes/head
  CAS gates 必须全部 `True`；
- `EFFECT_UNKNOWN`：只允许保留已实际形成的 Claim/CallAttempt/SendReceipt ref+digest，
  其余显式为 `null`，必须绑定 ReconciliationCase，并保持
  `DO_NOT_REPLAY`。任何 `Unknown`、字段/分支不一致或无法证明未进入 send boundary 都不得
  降格为 `NOT_APPLICABLE`。

`SafetyOwnerReceiptV1` 由被处置的 target owner Module 在本地 CAS 与 effect witness 形成后
**签发**：owner 先形成不可变 payload 与绑定自身 attestation 的 `SafetySigningRequestV1`。
独立 `SafetyReceiptSignerPort` 只接受该 request ref+digest，并在自己的 authority boundary
重验 request owner、payload、用途、TTL、当前 Issuance Policy Head 与 key policy 后，才用
HSM 内不可导出的 key 签名；它不接受裸 digest/任意 key handle，不能成为 signing oracle，
也不拥有或改写 target effect。`SafetyReceiptVerifierPort` 只验证 owner、key epoch/吊销
状态、trust anchor、签名、规范化 digest 与 effect evidence，不生成或补写 owner receipt。
`target_owner_attestation_ref+digest` 必须解析为通用
`SafetyOwnerWorkloadAttestationV1`，operation 为 `TARGET_OWNER_SIGNING_REQUEST`，subject
是具名、可解析的 `SafetyTargetOwnerSigningSubjectV1 ref+digest`，其内容冻结
payload/command/challenge/effect/target/Issuance Head+Bundle/audience/purpose/TTL。独立
verifier 的 verification ref+digest
必须一并进入 SigningRequest；signer 不自行相信 target-owner detached digest，只有
attestation verification `VALID` 且所有 gate `is True` 才能继续。
这里有两个不得混淆的 immutable policy role：

1. PreparedCommand、Challenge、OwnerReceiptPayload、SigningRequest、SignatureEnvelope 与
   signer 逐字绑定同一个具名发布的 `SafetyIssuancePolicyHeadV1 generation+digest` 及其
   `required_issuance_policy_bundle_ref + digest`；它记录命令、admission、签名和
   failure-domain 政策，随 receipt 永久不变。每个 `policy_role` 只有一个线性化
   `SafetyPolicyFenceAuthorityPort`，它也是 `SafetyPolicyHeadCurrentAliasV1` 的唯一
   single-writer owner。Policy owner 先形成可按 digest 解析但尚未生效的 immutable
   PublicationReceipt/Head/PointerRevision，再提交
   `SafetyPolicyAliasTransitionRequestV1`；Fence Authority 在**自己的同一原子提交**中
   逐字验证这些对象，把 `policy_fence_epoch` 从 expected `E` 严格推进至 `E+1`，追加绑定
   successor PointerRevision/Head/Bundle/publication receipt 的 `ALIAS_COMMIT` witness，
   CAS 新 `alias_state_generation/digest` 并生成 `SafetyPolicyAliasCommitResultV1`。
   不存在“Policy owner 数据库与独立 Authority 跨库同事务”的假设；只有该 alias commit
   之后新政策才生效。signer 在 HSM 调用前后只能从该 authority 的
   `begin_signing_fence` / `complete_signing_fence` 取得
   `SIGN_PRE`/`SIGN_POST` witness，禁止 cache、read replica、自报 epoch 或普通数据库时间。
   `commit_alias_transition`、`begin_signing_fence` 与 `complete_signing_fence` 虽由调用方只传
   exact TimeAttestation ref+digest，但 Authority 内部必须为各次操作以
   `alias_transition_request_digest | signer_operation_digest | sign_pre_witness_digest`
   派生不同的一次性 transaction nonce/commit subject，并通过自己的
   `SafetyTrustedTimeCommitGuardPort` 形成 lease、线性化 freshness proof 与 owner-local
   checkpoint。三类 `SafetyPolicyFenceWitnessV1` 都必须冻结 exact
   TimeAttestation/CommitLease/FreshnessProof/Checkpoint ref+digest 和 upper bound；
   `resolve_and_verify_witness` 必须重算该链、证明 checkpoint 与 witness 在同一 Authority
   store commit，不能接受调用者自带 checkpoint 或仅有 `trusted_time_valid=True`。
   两份 witness 必须绑定同一 role、fence epoch、PointerRevision/Head/Bundle、
   SigningRequest、`envelope_core_digest` 与 signer operation；POST 还必须绑定 PRE witness
   digest 与 `signature_bytes_digest`。Envelope 必须冻结共同 fence epoch、alias-commit
   witness 以及 PRE/POST ref+digest。任一 epoch/tuple 不同、witness chain gap/fork、
   signature/time/key/revocation Unknown、POST 不引用 PRE、或其间 alias transition，均返回
   `SAFETY_POLICY_DRIFT`：签名字节只进入受限 tamper audit 后立即封存/销毁，不得形成可解析
   Envelope、不得重试为旧 policy。有效 Envelope 的签名授权线性化点是同一 authority
   的 POST witness。`signer_operation_digest` 只由 role/current
   fence/PointerRevision/Head/Bundle/SigningRequest 决定，不含 envelope core；Envelope core
   随后纳入该 operation ref+digest，因此构造顺序为 operation → envelope core → PRE。
   PRE 以 domain-separated `signer_operation_digest` 做 CAS-on-NULL，
   POST 以 PRE digest 做一次性 completion CAS；同输入重放只返回原 witness，任一输入漂移
   拒绝。Authority 必须从 role/current fence/PointerRevision/Head/Bundle/SigningRequest
   自行重算 signer-operation ref+digest，再独立重算包含该 operation 的 envelope core，
   不能信任端口入参自报 identity。
   Fence Authority 的本地事务还必须以 `time_consumption_key_digest` 唯一约束 CAS
   TimeCheckpoint；ALIAS_COMMIT 的 alias state/witness/commit result，SIGN_PRE 的 PRE
   witness，SIGN_POST 的 POST witness 必须分别与对应 checkpoint 在同一原子提交出现。
   缺 checkpoint、proof 在消费前过期、线性化 tick 超 lease deadline 或 Guard/store profile
   不可验证时不得推进 fence epoch、不得返回 PRE/POST，HSM 也不得被调用或发布其字节。
   其后发布的新 Policy 不改写历史 receipt；
2. verifier、factory 与每次 `reverify_active_result` 逐字绑定同一个
   `SafetyVerificationPolicyHeadV1 generation+digest` 及其
   `required_verification_policy_bundle_ref + digest`；bundle 记录 verifier/factory policy、
   允许算法、当前 trust snapshot 和明确排序的
   `accepted_issuance_policy_bundle_digests[]`，可以随吊销与信任快照演进。

初次 verification 也必须显式提供两个角色，不能假定二者是同一对象；后续 verification
bundle 可以改变，但旧 receipt 的 issuance bundle 绝不改写。verifier 只有在 payload 与
SigningRequest/Envelope 的 issuance Head/Bundle 完全一致、Policy Head publication receipt、
target-owner attestation 与 SigningRequest 全链可验证、bundle digest 可重算且被 required
verification bundle 明确接受时，才把 issuance Head/publication/request/attestation/bundle
各 gate 置为 `True`。signer、verifier 或 factory 均不得自行解析
“当前策略”：它们只能解析调用中携带并由对应具名 Policy Head 证明的精确对象。任一
ref/digest/head generation 不等、publication receipt 无效、bundle 不可解析或
acceptance/trust/policy 不匹配都拒绝或产生 fail-closed verification outcome。

规范化与摘要合同固定如下，实施不得自选：

1. 被签 payload 的字段集合**恰好**是 `SafetyOwnerReceiptPayloadV1` 中列出的字段；wrapper、
   payload/envelope/receipt digest 与任何签名字段都不进入 payload，未知字段拒绝。
2. `payload_canonicalization_profile = RFC8785-JCS-UTF8-NFC`，
   `payload_digest_algorithm = SHA-256`，
   `payload_digest_domain_separator = "flai.safety.owner-receipt-payload.v1\0"`。
   三个 domain separator 中的尾随 `\0` 都表示单个 NUL octet，不是两个可见字符。
   输入字符串必须已经是 Unicode NFC，时间统一为 UTC RFC3339，禁止浮点数；可选字段也必须
   显式编码为 `null`。三组 actor/admission 数组按 `actor_ref` 的 UTF-8 字节序成组排序，
   `preexisting_local_evidence_refs[]` 按规范化引用字节序排序；这些引用必须在 payload
   形成前已存在，不能引用本 receipt 或其后继 seal。SHA-256 digest 统一为 64 位小写十六进制，
   二进制 signature 统一为无 padding 的 base64url。
3. `canonical_receipt_payload_digest =
   SHA-256(domain_separator_bytes || RFC8785_JCS_UTF8(payload))`。verifier 必须自行从
   `payload_ref` 解析的不可变对象重算，禁止信任客户端传入 digest。
4. signer 对上述 32-byte digest 签名；`SafetySignatureEnvelopeCoreV1.signed_digest` 必须
   精确等于重算值。为避免 detached core 与 fence/Envelope 摘要回环，调用者先发布不可变
   `SafetySignatureEnvelopeCoreV1 ref+digest`；它包含 signer material、key epoch、算法、
   signed digest、trust/policy、精确 Issuance Head+Bundle 与前一步确定的 signer operation。
   `envelope_core_digest = SHA-256(UTF8("flai.safety.signature-envelope-core.v1\0") ||
   RFC8785_JCS_UTF8(SafetySignatureEnvelopeCoreV1 excluding exactly
   envelope_core_ref/envelope_core_digest))`，ref 为
   `flai://safety-signature-envelope-core/{digest}`。Fence Authority 必须从 ref 解析对象并
   自行重算，`begin_signing_fence` 不接受 detached digest；PRE/POST witness 都绑定该 core
   ref+digest。
   `signature_bytes_digest = SHA-256(UTF8("flai.safety.signature-bytes.v1\0") ||
   decoded_base64url_signature_bytes)`，POST 必须绑定它。最终 envelope 使用
   `RFC8785-JCS-UTF8-NFC + SHA-256` 与
   `"flai.safety.signature-envelope.v1\0"`，其 digest 覆盖除
   `signature_envelope_ref/signature_envelope_digest` 外的全部字段，包括两份 witness。
5. receipt wrapper 使用 `RFC8785-JCS-UTF8-NFC + SHA-256` 与
   `"flai.safety.owner-receipt.v1\0"`；`receipt_digest` 覆盖除自身外的全部
   `SafetyOwnerReceiptV1` 字段。wrapper 只绑定不可变 payload/envelope ref+digest，不复制
   签名字段。任一引用解析、规范化、重算或 digest 绑定不等即拒绝。
6. Issuance/Verification Bundle 都拒绝未知字段，字符串必须 NFC，时间必须 UTC RFC3339，
   禁止浮点数。`allowed_signature_algorithms[]` 与
   `accepted_issuance_policy_bundle_digests[]` 按每项规范化 UTF-8 bytes 严格升序；重复、
   空字符串、未注册算法、非 64 位小写十六进制 digest 一律拒绝，不做静默去重或大小写转换。
   精确公式为：

   ```text
   issuance_policy_bundle_digest = SHA-256(
     UTF8("flai.safety.issuance-policy-bundle.v1\0")
     || RFC8785_JCS_UTF8(
          SafetyIssuancePolicyBundleV1
          excluding exactly issuance_policy_bundle_ref
                            and issuance_policy_bundle_digest
        )
   )
   issuance_policy_bundle_ref =
     "flai://safety-issuance-policy-bundle/" + issuance_policy_bundle_digest

   verification_policy_bundle_digest = SHA-256(
     UTF8("flai.safety.verification-policy-bundle.v1\0")
     || RFC8785_JCS_UTF8(
          SafetyVerificationPolicyBundleV1
          excluding exactly verification_policy_bundle_ref
                            and verification_policy_bundle_digest
        )
   )
   verification_policy_bundle_ref =
     "flai://safety-verification-policy-bundle/" + verification_policy_bundle_digest
   ```

   domain/profile/algorithm 字段本身保留在 hash projection 中；只排除上列 ref/digest。
   signer/verifier/factory 必须从 ref 解析 immutable object 并重算，禁止信任 detached digest。
7. `SafetyPolicyPublicationReceiptV1` 的 digest 覆盖除
   `publication_receipt_ref/publication_receipt_digest/policy_owner_signature_ref/
   policy_owner_signature_digest` 外的精确字段，ref 由 digest 派生；独立 policy-owner
   signature 必须签该 digest。两组 admission 必须解析为两个不同真人，actor/admission pair
   按 `actor_ref` UTF-8 bytes 严格排序并拒绝重复；两者都必须 fresh、满足
   `required_publication_assurance_profile_ref`，且
   `admission_kind=POLICY_PUBLICATION`、subject 精确等于同一个
   `SafetyPolicyPublicationChallengeV1 ref+digest`。该 challenge 在取得双人 admission
   **之前**形成，冻结 role/mode、scope/audience/purpose、expected Head 与 PointerRevision、
   new/supersedes bundle、rollback tuple、effective time、TTL 和一次性 nonce。
   `publication_mode=ADVANCE` 时三项 rollback 字段必须显式为 `null`；`ROLLBACK` 时
   `rollback_reason_digest + rollback_incident_ref/digest` 全部必填。

   每次 Head 更新先追加一个不可变 Policy Head version，再追加一个 content-addressed
   `SafetyPolicyHeadPointerRevisionV1` 和一个 `ALIAS_COMMIT`
   `SafetyPolicyFenceWitnessV1`；固定
   `flai://safety-policy-head-current/{role}` 只是解析当前 PointerRevision 的 mutable alias，
   不能作为历史证据或被 receipt/result 直接绑定。历史 Head version、PointerRevision、
   publication challenge/receipt、Reservation、Admission/SubjectNonce consumption 与 bundle
   必须按 ref/digest 在线 append-only 可解析，WORM 只是下游镜像。
   未签、多头、未绑定 rollback reason/incident/supersedes 的回滚、区间重叠、历史对象缺失或
   signature unknown 均 fail-closed。每个 policy role 只能前进到**从未发布过**的新 bundle
   digest；提交当前或任何历史 digest 只能幂等返回其原 publication record，绝不能生成新
   Head version/PointerRevision digest。受控回滚不是重用旧 digest：必须以新的 epoch、
   validity/trust snapshot 与新 digest 签发 bundle C（政策正文可显式恢复为旧语义），再由
   publication receipt 记录 rollback reason、incident 与 supersedes，执行 Head B→C。

   Safety Admission Coordinator 已在自己的事务中消费双 admission + publication nonce 并
   签发 immutable Reservation；Policy owner 不得跨 owner 再写 Consumption Store。Policy owner
   验证 reservation kind/subject/projection/admission set/nonce/ref/digest，形成并发布
   immutable PublicationReceipt、Head version 与下一 PointerRevision，然后签发
   `SafetyPolicyAliasTransitionRequestV1`。其中 Policy-owner attestation 必须是通用
   `SafetyOwnerWorkloadAttestationV1`，operation 为 `POLICY_ALIAS_TRANSITION`、subject
   精确等于从 request 业务字段重算的具名
   `SafetyPolicyAliasTransitionSubjectV1 ref+digest`，并携带独立
   verifier 的 VALID verification ref+digest。Fence Authority 不接受 detached owner
   digest。这些对象在 alias commit 前只是
   `PENDING_ACTIVATION`，不得被 signer/verifier 当成 current policy。Fence Authority
   `commit_alias_transition` 重读 request 与全部 immutable 对象，在自己的 serializable
   single-writer transaction 中以 expected alias-state/pointer/fence witness 做 CAS，
   同时追加 `policy_fence_epoch=expected+1` 的 ALIAS_COMMIT witness、新 alias state 和 commit
   result。任何一步失败都不改变 current alias；可能留下的 immutable proposal 不是生效政策。
   Reservation 保持已消费并进入对账；精确 replay 只能按 reservation + transition/publication
   idempotency 查询或返回同一 commit result，不能换 bundle、role、mode、Head 或 rollback tuple。

   transition 硬门不可由实现者简化：

   - genesis 仅允许 expected Head/PointerRevision ref+digest 为 `null`、两种 generation 为
     `0`；首个 Head 与 PointerRevision generation 都为 `1`，predecessor ref+digest 为
     `null`；
   - 非 genesis 的新 Head `generation = expected_head_generation + 1`，其 predecessor
     ref+digest 精确等于 expected Head，role/owner 不变，selected bundle 精确等于 challenge
     的 new bundle，publication receipt 精确等于本次 receipt；
   - 新 PointerRevision
     `pointer_revision_generation = expected_pointer_revision_generation + 1`，predecessor
     精确等于 alias 当前 expected revision；其 role/owner、current Head、Head generation/
     digest、current bundle 和 publication receipt 必须逐字等于本次新 Head/receipt；
   - `(policy_role, head_generation)`、`(policy_role, pointer_revision_generation)`、
     `head_ref/digest` 与 `pointer_revision_ref/digest` 分别唯一；同 role 的 owner 不得漂移；
   - alias CAS 只能从 expected revision 三元组与 expected fence epoch/witness 切到上述唯一
     successor；fence epoch 必须严格 `E→E+1`，ALIAS_COMMIT witness 必须逐字绑定新
     PointerRevision/Head/Bundle/receipt；generation gap、fence reuse、fork、错
     role/owner/bundle/receipt、predecessor 漂移或 unknown 全部拒绝。

   ```text
   publication_projection_digest = SHA-256(
     UTF8("flai.safety.policy-publication-authorized-projection.v1\0")
     || RFC8785_JCS_UTF8({
          policy_role,
          publication_mode,
          policy_owner_ref,
          required_publication_assurance_profile_ref,
          required_publication_scope_digest,
          publication_audience,
          publication_purpose,
          expected_policy_head_ref,
          expected_policy_head_generation,
          expected_policy_head_digest,
          expected_policy_head_pointer_revision_ref,
          expected_policy_head_pointer_revision_generation,
          expected_policy_head_pointer_revision_digest,
          expected_policy_fence_epoch,
          expected_alias_commit_fence_witness_ref,
          expected_alias_commit_fence_witness_digest,
          new_policy_bundle_ref,
          new_policy_bundle_digest,
          supersedes_policy_bundle_ref,
          supersedes_policy_bundle_digest,
          rollback_reason_digest,
          rollback_incident_ref,
          rollback_incident_digest,
          effective_from,
          publication_idempotency_key_digest,
          publication_one_time_nonce_digest
        })
   )

   policy_publication_challenge_digest = SHA-256(
     UTF8("flai.safety.policy-publication-challenge.v1\0")
     || RFC8785_JCS_UTF8(SafetyPolicyPublicationChallengeV1
          excluding exactly publication_challenge_ref
                            and publication_challenge_digest)
   )
   policy_publication_challenge_ref =
     "flai://safety-policy-publication-challenge/"
     + policy_publication_challenge_digest

   publication_receipt_digest = SHA-256(
     UTF8("flai.safety.policy-publication-receipt.v1\0")
     || RFC8785_JCS_UTF8(publication receipt excluding exactly
          publication_receipt_ref, publication_receipt_digest,
          policy_owner_signature_ref, policy_owner_signature_digest)
   )
   publication_receipt_ref =
     "flai://safety-policy-publication/" + publication_receipt_digest

   issuance_policy_head_digest = SHA-256(
     UTF8("flai.safety.issuance-policy-head.v1\0")
     || RFC8785_JCS_UTF8(SafetyIssuancePolicyHeadV1
          excluding exactly head_ref and head_digest)
   )
   issuance_policy_head_ref =
     "flai://safety-policy-head/issuance/"
     + decimal(generation) + "/" + issuance_policy_head_digest

   verification_policy_head_digest = SHA-256(
     UTF8("flai.safety.verification-policy-head.v1\0")
     || RFC8785_JCS_UTF8(SafetyVerificationPolicyHeadV1
          excluding exactly head_ref and head_digest)
   )
   verification_policy_head_ref =
     "flai://safety-policy-head/verification/"
     + decimal(generation) + "/" + verification_policy_head_digest

   policy_head_pointer_revision_digest = SHA-256(
     UTF8("flai.safety.policy-head-pointer-revision.v1\0")
     || RFC8785_JCS_UTF8(SafetyPolicyHeadPointerRevisionV1
          excluding exactly pointer_revision_ref
                            and pointer_revision_digest)
   )
   policy_head_pointer_revision_ref =
     "flai://safety-policy-head-pointer-revision/"
     + lower(policy_role) + "/"
     + decimal(pointer_revision_generation) + "/"
     + policy_head_pointer_revision_digest

   alias_transition_subject_digest = SHA-256(
     UTF8("flai.safety.policy-alias-transition-subject.v1\0")
     || RFC8785_JCS_UTF8(SafetyPolicyAliasTransitionSubjectV1
          excluding exactly alias_transition_subject_ref
                            and alias_transition_subject_digest)
   )
   alias_transition_subject_ref =
     "flai://safety-policy-alias-transition-subject/"
     + lower(policy_role) + "/"
     + alias_transition_subject_digest

   alias_transition_request_digest = SHA-256(
     UTF8("flai.safety.policy-alias-transition-request.v1\0")
     || RFC8785_JCS_UTF8(SafetyPolicyAliasTransitionRequestV1
          excluding exactly alias_transition_request_ref
                            and alias_transition_request_digest)
   )
   alias_transition_request_ref =
     "flai://safety-policy-alias-transition-request/"
     + lower(policy_role) + "/"
     + alias_transition_request_digest

   signer_operation_digest = SHA-256(
     UTF8("flai.safety.policy-fence-signer-operation.v1\0")
     || RFC8785_JCS_UTF8({
          policy_role,
          policy_fence_epoch,
          pointer_revision_ref,
          pointer_revision_digest,
          policy_head_ref,
          policy_head_digest,
          policy_bundle_ref,
          policy_bundle_digest,
          signing_request_ref,
          signing_request_digest
        })
   )
   signer_operation_ref =
     "flai://safety-policy-fence-signer-operation/"
     + signer_operation_digest

   policy_fence_witness_digest = SHA-256(
     UTF8("flai.safety.policy-fence-witness.v1\0")
     || RFC8785_JCS_UTF8(SafetyPolicyFenceWitnessV1
          excluding exactly fence_witness_ref,
                            fence_witness_digest,
                            signature)
   )
   policy_fence_witness_ref =
     "flai://safety-policy-fence-witness/"
     + lower(policy_role) + "/"
     + decimal(policy_fence_epoch) + "/"
     + lower(witness_kind) + "/"
     + policy_fence_witness_digest
   policy_fence_witness_signature_input =
     UTF8("flai.safety.policy-fence-witness-signature.v1\0")
     || RFC8785_JCS_UTF8(SafetyPolicyFenceWitnessV1
          excluding exactly fence_witness_ref,
                            fence_witness_digest,
                            signature)

   alias_state_digest = SHA-256(
     UTF8("flai.safety.policy-current-alias-state.v1\0")
     || RFC8785_JCS_UTF8(SafetyPolicyHeadCurrentAliasV1
          excluding exactly alias_state_digest)
   )

   alias_commit_result_digest = SHA-256(
     UTF8("flai.safety.policy-alias-commit-result.v1\0")
     || RFC8785_JCS_UTF8(SafetyPolicyAliasCommitResultV1
          excluding exactly alias_commit_result_ref
                            and alias_commit_result_digest)
   )
   alias_commit_result_ref =
     "flai://safety-policy-alias-commit-result/"
     + lower(policy_role) + "/"
     + alias_commit_result_digest
   ```

   Challenge 计算 projection 时将其 `one_time_nonce_digest` 映射为
   `publication_one_time_nonce_digest`；Receipt 使用自己的同名字段。Policy owner 必须从
   challenge 与 receipt 各自重算 `publication_projection_digest`，要求逐字段、projection
   digest、challenge ref+digest 全部相等后，才可消费 admission/nonce。不能用一个已获双人
   确认的 challenge 生成另一 role/mode/Head/bundle/rollback/effective-time receipt。
8. `SafetySigningRequestV1` 的 digest 覆盖除 `signing_request_ref/signing_request_digest`
   外的全部字段，ref 由 digest 派生。SignatureEnvelope 必须绑定 request ref+digest；
   target-owner attestation、request purpose/audience、payload digest、issuance Head/Bundle、
   command/challenge/effect/target 任一不等都拒绝签名。

   ```text
   target_owner_signing_subject_digest = SHA-256(
     UTF8("flai.safety.target-owner-signing-subject.v1\0")
     || RFC8785_JCS_UTF8(SafetyTargetOwnerSigningSubjectV1
          excluding exactly target_owner_signing_subject_ref
                            and target_owner_signing_subject_digest)
   )
   target_owner_signing_subject_ref =
     "flai://safety-target-owner-signing-subject/"
     + target_owner_signing_subject_digest

   signing_request_digest = SHA-256(
     UTF8("flai.safety.signing-request.v1\0")
     || RFC8785_JCS_UTF8(SafetySigningRequestV1
          excluding exactly signing_request_ref and signing_request_digest)
   )
   signing_request_ref = "flai://safety-signing-request/" + signing_request_digest
   ```

`SafetyResultFactory` 属于独立 Safety Receipt Verifier Module，是 Full/Pending/
Invalidated/Inconclusive 四类终态的**唯一构造器**；
`SafetySurvivalPort` 只是 sealed facade，必须依次调用 target owner、signer、verifier 和该
factory，Adapter/Hub/投影不得直接实例化结果。factory 先执行与被验证对象结论无关的
**meta-integrity admission**；以下条件必须全部满足，否则返回 Rejection 且不得写 Result/Head：

```text
verification schema/canonical profile/domain separator is supported
and verification_key_digest recomputes exactly
and verification_digest recomputes exactly
and required_verification_policy_bundle_ref/digest
    == factory arguments
    == verification fields
    == bundle selected by expected Verification Policy Head
and expected_verification_policy_head_ref/generation/digest
    + pointer_revision_ref/generation/digest
    == factory arguments
    == verification observed Head fields
and verification_policy_bundle_binding_valid is True
and verification_policy_head_binding_valid is True
and factory_policy_match is True
and result schema/canonical profile/domain separator is supported
and verification_outcome is consistent with all subject gates and precedence
and, in one owner-local serializable boundary,
    expected Verification Policy Head generation/digest matches current Policy Head
    and expected Result Head generation/digest matches current Result Head
```

通过 meta-integrity admission 后，factory 按下表决定唯一结果；`INVALID > UNKNOWN > VALID`
是强制优先级，不能由调用者自报：

| verification outcome | 机械条件 | 唯一允许结果 |
|---|---|---|
| `VALID` | 所有适用 subject gate 均 `is True`，revocation 为 `NOT_REVOKED`，required verification bundle/trust/evidence fresh，且 `trusted_now <= freshness_deadline` | 按 external effect 分支构造 Full 或 Pending |
| `INVALID` | 至少一个确定性 subject gate 为 `False` 或 revocation 为 `REVOKED`，并有绑定 verification evidence/reason code；即使同时存在 unknown 也由 INVALID 优先 | `SafetyResultInvalidatedV1` |
| `UNKNOWN` | 没有已知 invalid，但至少一个必需 gate 为 `Unknown/null`、revocation 为 `UNKNOWN`、trust/evidence stale/unavailable，或新 verification 已超 freshness | `SafetyResultInconclusiveV1` |
| 不一致或 malformed | outcome 与 gate 不一致、verification 自身 key/digest/schema 损坏、required bundle/factory/head CAS 不匹配 | Rejection；不写 Result/Head |

subject gate 包括 SigningRequest/target-owner attestation、signing material/key
epoch/algorithm/signing policy/failure domain、issuance Policy Head publication/binding、
issuance chain binding/acceptance、key revocation、trust anchor/snapshot、receipt
canonical/envelope/signature、trusted time、owner effect/local fence/external applicability、
issuer/actor/admission/nonce/target CAS/effect key/owner sequence 及适用 reconciliation 绑定。只有 `VALID` 路径要求
这些门全部显式 `is True`；Invalidated/Inconclusive 正是对确定性失败或不可判定状态的
fail-closed 事实，不能被 `VALID` 共同门挡死。

已经形成 immutable receipt 且在**新的 immutable Verification Policy Bundle** 下形成新
verification 时，factory 依上述矩阵构造结果，并用同一 Head CAS 取代旧 active result。仅因既有
verification 的 `freshness_deadline` 随时间经过而到期时，不得在同一 Verification Policy
Bundle 下伪造
第二个 verification/result；读取端立即派生 amber/unknown，持久 reverify 必须先签发新的
verification Policy Bundle epoch/digest。
`SafetyEffectUnknownV1` 只用于连 owner receipt/verification 都无法形成的执行、签名或回执
不确定；malformed/tampered/unauthorized 输入返回 Rejection。不得因为 reverify 失败而继续把旧
Full head 当作当前成功。

verification 与 result/head 的身份和唯一性也固定。verifier 先生成：

```text
verification_key_digest = SHA-256(
  UTF8("flai.safety.receipt-verification-key.v1\0")
  || RFC8785_JCS_UTF8({
       owner_receipt_digest,
       signature_envelope_digest,
       required_verification_policy_bundle_digest,
       observed_verification_policy_head_digest,
       observed_verification_policy_head_pointer_revision_ref,
       observed_verification_policy_head_pointer_revision_generation,
       observed_verification_policy_head_pointer_revision_digest
     })
)
verification_ref = "flai://safety-verification/" + verification_key_digest

verification_digest = SHA-256(
  UTF8("flai.safety.receipt-verification.v1\0")
  || RFC8785_JCS_UTF8(
       SafetyReceiptVerificationV1 excluding verification_digest
     )
)

result_key_digest = SHA-256(
  UTF8("flai.safety.verified-result-key.v1\0")
  || RFC8785_JCS_UTF8({
       owner_receipt_digest,
       verification_digest
     })
)
result_ref = "flai://safety-result/" + result_key_digest

result_chain_key_digest = SHA-256(
  UTF8("flai.safety.verified-result-chain.v1\0")
  || RFC8785_JCS_UTF8({
       command_digest,
       effect_key_digest,
       target_ref
     })
)
```

Verification Store 对 `verification_key_digest` 唯一约束并 CAS-on-NULL；同 receipt/
envelope + Verification Policy Bundle + observed Policy Head 的 replay 永远只返回首次
verification；`verified_at` 与 `freshness_deadline` 也是该首次对象的一部分，不因读取或重试
改写。`verification_digest` 使用字段中冻结的
canonical profile/algorithm/domain separator，覆盖除自身外的全部 verification 字段，verifier
和 factory 都必须重算。Issuance Bundle 规范化绑定命令/admission/signing/failure-domain
policy；Verification Bundle 规范化绑定 verifier/factory/issuance-acceptance policy、明确
排序的 accepted issuance digest 集、allowed algorithms、trust snapshot 与有效期。任一
Verification Bundle 或其具名发布 Head witness 变化都形成新的 verification identity，不能
改旧记录。
即使策略正文未变，重新验证也必须取得新的 trust snapshot/freshness window，签发新的
Verification Policy Bundle epoch/digest；同 verification bundle 不能充当新的 revalidation
attempt。`freshness_deadline` 必须是 verification bundle `valid_until`、trust snapshot
freshness deadline 与适用 effect/evidence deadline 的最早值，且由可信时间源计算。

`factory_policy_digest` 通过 Verification Policy Bundle 进入 verification/result 内容与
`result_digest`，**不直接进入**
`result_key_digest`。因此同一 owner receipt + verification 在 factory policy 改版后仍命中
同一 result key；新 factory policy 必须先形成新 Verification Policy Bundle、新 verification，再通过
`reverify_active_result + expected head CAS` 追加 successor result，不能静默分叉。

Result Store 分别唯一约束 `result_key_digest` 与 `result_chain_key_digest` 的
`SafetyResultHeadV1`。`result_digest` 使用 `RFC8785-JCS-UTF8-NFC + SHA-256 +
"flai.safety.verified-result.v1\0"` 覆盖结果对象除自身外的全部字段。Head Store 每个
result chain 只有一行；`head_digest` 使用
`"flai.safety.result-head.v1\0"` 覆盖 `SafetyResultHeadV1` 除自身外的全部字段。

Safety Verification Policy Head、Verification Store、Result Store 与 Result Head Store 必须
处于同一 Safety Receipt Verifier owner 的一致性边界。factory 在一个 owner-local
serializable 事务中：

1. 以 `expected_verification_policy_head_generation + head digest +
   pointer revision ref/generation/digest` 重读 current alias 指向的不可变
   `SafetyPolicyHeadPointerRevisionV1` 与 `SafetyVerificationPolicyHeadV1` version，验证
   publication receipt、Head digest 及其选中的 bundle；
2. 以 `expected_result_head_generation + expected_result_head_digest` 读取并 CAS Result Head；
3. 对 `result_key_digest` CAS-on-NULL 插入 immutable result；
4. 写入 generation+1 的新 `SafetyResultHeadV1`。

初始结果要求 expected head 为 `generation=0 + digest=null`；reconcile/reverify 必须精确匹配
当前 Result Head，并绑定当前 Verification Policy Head。result 只记录 predecessor result
ref/digest 和 generation，不保存新 head digest；
Head 记录单向引用 result digest，所以没有摘要自循环。`expected_reconciliation_head_digest`
精确指向 reconcile 前 `SafetyResultHeadV1.head_digest`。任一步失败则整事务失败，不留下孤儿
result。同 key、同 digest replay 返回首次对象（包括原 `constructed_at`）；同 key 不同
digest/outcome/ref、head CAS 冲突或 generation 跳跃一律审计并拒绝。
`reverify_active_result` 必须绑定 required Verification Policy Bundle ref+digest、具名
Policy Head generation+digest 与当前 Result Head CAS；相同 bundle+Policy Head 在未过期时
直接返回原 verification/result，在已过期时返回
`REVERIFY_REQUIRES_NEW_POLICY_BUNDLE`，均不得追加 successor。取得新的 Verification Policy Bundle 后才
可追加新 verification 和引用前序 result 的 successor；新 verification 为 INVALID/UNKNOWN
时，也必须分别把 Invalidated/Inconclusive successor CAS 为新 Head。不得修改旧
verification/result，也不能因 reverify 尚未完成、策略漂移、key revocation 或 trust source
不可用而继续沿用旧 Full head。

每次读取或投影都在**同一个 owner-local consistent snapshot** 取得
`SafetyVerificationPolicyHeadV1 + SafetyResultHeadV1` 并重验：只有
`head_outcome=FULL_EFFECT_VERIFIED`、Policy Head publication receipt 与 Head/result/
verification digest 全部重算一致、Result Head 记录的
`head_verification_policy_head_generation/digest +
head_verification_policy_head_pointer_revision_ref/generation/digest` 等于该 snapshot 的
Policy Head/current PointerRevision、该 Head
选中的 bundle 等于 `head_verification_policy_bundle_ref/digest`，且
`trusted_now <= head_verification_freshness_deadline` 时，才可显示完整处置成功。bundle
或 Policy Head 漂移、超 freshness、任一 Head/source unavailable 或任一比较 unknown 时立即 fail-closed 为
amber/unknown；若已知验证无效则显示红色 invalidated。该读取门不等待后台 reverify 完成。
过期本身只产生这一读取派生状态，不在旧 bundle 下写入 Inconclusive；新 bundle 下完成重验后，
factory 才可用 expected generation+head digest CAS 持久追加 Full/Pending/Invalidated/
Inconclusive successor。

- 初始 `external_provider_effect=CONFIRMED` 还要求
  `external_postcondition_verified is True`、
  `provider_receipt_binding_valid is True`、
  `provider_call_attempt_binding_valid is True` 与
  `provider_send_receipt_binding_valid is True`；
- `external_provider_effect=NOT_APPLICABLE` 还要求
  `external_postcondition_verified == NOT_APPLICABLE` 且
  `provider_receipt_binding_valid == NOT_APPLICABLE`、
  `provider_call_attempt_binding_valid == NOT_APPLICABLE` 与
  `provider_send_receipt_binding_valid == NOT_APPLICABLE`；
- 上述两类才可构造 `FullSafetyEffectVerifiedV1`；
- `external_provider_effect=EFFECT_UNKNOWN` 只在
  `reconciliation_case_binding_valid is True` 且
  `provider_receipt_binding_valid == NOT_APPLICABLE` 时构造
  `LocalFenceVerifiedExternalPendingV1`，保持 amber、展示“本地围栏已核验，外部撤销待确认”，
  不得显示最终成功；否则返回 `SafetyEffectUnknownV1`。
- 当 `supersedes_owner_receipt_ref_if_reconciled` 非空时，
  `reconciliation_observation_binding_valid`、`authenticated_query_receipt_valid`、
  `effect_observation_fresh`、`supersedes_binding_valid`、
  `reconciliation_head_cas_valid` 必须全部 `is True`，且
  payload、reconcile input 与 observation 的 ref/digest/query-receipt tuple 精确一致；初始
  非对账 receipt 中五门必须全部为 `NOT_APPLICABLE`。`False/Unknown/null` 一律不得晋级。
- 对账后的 `external_provider_effect=CONFIRMED` 允许
  `provider_send_receipt_binding_valid == NOT_APPLICABLE`，但仅限原 ProviderSendReceipt
  确实不存在、`provider_call_attempt_binding_valid is True`（或已证明 send boundary 从未
  进入时为 `NOT_APPLICABLE`），且上一条所列五个对账 gate、external postcondition 与
  external-provider receipt binding 全部 `is True`。它不能反向把缺失的 send receipt
  伪装成已确认 handoff。

pending 到 confirmed 只允许追加式对账：`SafetyEffectQueryPort` 以原
`command_digest + challenge_digest + effect_key_digest + target_ref` 做认证只读查询；
`SafetyReconciliationPort` 对当前 pending head 做 CAS。provider 返回 `CONFIRMED` 时，
target owner 创建新的
`SafetyOwnerReceiptPayloadV1`，保持原 command/prepared/challenge/effect key/target 不变，
提升 `target_owner_sequence`，以
`supersedes_owner_receipt_ref_if_reconciled` 指向前序 receipt，以
`expected_reconciliation_head_generation + expected_reconciliation_head_digest` 绑定 CAS
head，并把 observation ref/digest、
authenticated query receipt ref/digest 与 provider effect receipt ref/digest 全部写入被签
payload；
随后重新签名、验签、走唯一 factory。不得修改旧 receipt、复用已消费 challenge
再次执行、换 effect key 或覆盖历史。`CONFIRMED_NO_EFFECT/UNKNOWN`、source stale 或 head CAS
冲突都保持 pending/unknown 并进入具名 ReconciliationCase，不能形成完整成功。

receipt/result 验证完成后的 Audit/WORM seal 是下游追加记录，只能引用既有
receipt/verification/result digest，不得反向进入上述 payload 或 wrapper digest；这样既保留
不可变封存，又不形成摘要循环。payload 中的 `preexisting_local_evidence_refs[]` 已先锚定本地
fence 与双人处置证据。

该通道的验证只依赖预置 public trust anchors 与独立的组织 PKI/HSM/hardware attestation，
必须与飞书、Hub、主协作 SSO、普通工作负载身份和被处置系统的在线 Secret 解析解耦。普通
App/Connector Secret 仍全部由 `secrets-stackdocker` 拥有；人的硬件私钥、Safety
receipt-signing、三类 Owner workload-attestation、两类 Egress workload-attestation、
Policy-fence 与 Trusted-Time Authority/Commit-Guard material 分别由独立 Safety Identity / PKI / HSM / Time
owner 拥有，不复制为应用栈 Connector Secret，也不由普通 workload identity/进程自签 key
代签。验证用 public trust anchor 可以受控预置或分发，但它不是 Secret。

上述独立 Safety 能力当前均为 `ACCEPTED-NOT-IMPLEMENTED`，必须由 F0 的身份认证域和
Secret/连续性域共同具名裁决。若组织政策坚持把任一所需 Safety private key 也只放在
`secrets-stackdocker`，则
“secrets-stackdocker 总体 outage 时安全生存”必须保持 `DECLARED-NOT-VERIFIED`，并阻断
对应 D6/D7/D8 + F4 runtime exit。F0 只在组织拒绝“独立故障域”设计合同，或 owner/key/
revocation/outage fixture 与 drill 规格未冻结时阻断；实现和真实 outage witness 尚未产生
本身不阻断合同级 F0。不能以 `.env`、硬编码或长期明文救援 Key 补洞。

若 receipt signer 暂不可用而本地围栏仍可执行，Kernel 允许先完成 kill/deny/epoch bump，并将
两个操作者硬件签名、command/challenge digest 与本地 witness 写入预分配、追加式
`LocalSafetyEvidenceV1`。对外结果仍是 `SafetyEffectUnknownV1 / SAFETY_RECEIPT_PENDING`，
不能显示最终成功；恢复后只能由 target owner 根据原稳定 command/challenge 与追加式 witness
签发 canonical receipt，独立 signer 签名、owner-specific verifier 验证后单向 seal 至
Audit/WORM。verifier 不得生成 receipt。这样不因签名服务故障丢失止损能力，也不把未签记录
冒充最终回执。

`secrets-stackdocker` outage 时，Kernel 先使用本地 owner CAS 提升 credential/authorization
epoch 并关闭 lease、egress 和 SecretRef 使用；这条围栏路径不得 resolve SecretRef。
provider-side revoke 可进入 `EFFECT_UNKNOWN + reconciliation`，但不得阻断本地 kill/revoke，
也不得触发旧 Secret fallback。

飞书不可用时：

- 新的正常管理与治理动作暂停；
- 已发 Grant 只能在原范围和 TTL 内继续，不能扩权；
- kill、revoke、isolate、credential invalidation 和证据封存仍可由密封通道执行；
- 密封通道只减权、隔离、开对账案和验证恢复候选，不允许签发、发布、恢复权限、合并代码或
  创建正常项目事实；
- 所有动作要求具名职责、独立强认证、双人控制、最短 TTL、owner receipt 和事后复盘。

### 11.4 唯一中枢的连续性与退出

飞书成为唯一组织入口后，tenant/app 生命周期属于产品门，而不是运维备注。F0 必须由具名
责任域裁决且不在本文猜测数值：

```text
approved RTO/RPO by surface and fact class
tenant/app owner and renewal responsibility
permission-scope drift detection interval
event backlog capacity and replay window
projection rebuild source and maximum stale window
records retention/export format and custody
tenant offboarding and vendor-exit trigger
user communication and degraded-mode owner
```

连续性状态至少区分：

```text
HEALTHY
DEGRADED_READ_ONLY
SOURCE_STALE
INGRESS_PAUSED
REBUILDING
SAFETY_ONLY
EXIT_IN_PROGRESS
```

规则：

- tenant/app 权限丢失、回调断流或 token scope 漂移时停止受影响 intent，不能靠缓存按钮继续写；
- event backlog 按 owner sequence 与 source digest 重放；超出 replay window 时从 owner
  snapshot 重建，不用 Bitable 当前值反向补事实；
- projection 可从 owner facts + manifests 重建；HubStateStore 丢失不能改变 owner 事实；
- 正常管理 outage 超过获批 RTO 时进入具名 incident 和业务连续性流程，但不启动第二日常 Hub；
- records export 只导出飞书自有协作事实、稳定引用、projection manifest 与 owner evidence
  link；受限正文、Secret 和不具导出授权的 owner 数据不得打包外流；
- tenant offboarding/vendor exit 先冻结新 ingress，导出获批 records，验证 owner link
  完整性与重建能力，撤销 app/SecretRef，再按具名迁移决定切换组织入口；
- 退出计划不能把 Bitable dump 升格为 FLAi/GitHub/Knowledge/Audit 的替代数据库。

## 12. 从现有飞书应用迁移

当前 `feishu-assistant` 可复用：

- 长连接与事件入口；
- 消息、卡片和网页应用能力；
- Bitable CRUD；
- project、decision、risk、action、agent 等协作对象；
- 统计、日报、周报和测试骨架。

不能原样晋升为治理内核：

- 当前 open-id 白名单不是统一 ActorBinding；
- 本地 SQLite → Bitable 的 best-effort 双写不是可靠 outbox；
- Bitable 没有统一对象 ACL/classification enforcement；
- 当前 TeamLedger 没有 commit recheck、CAS、owner receipt 和 reconciliation；
- 当前 Codex 接入是只读助手，没有 Kimi-K3 开发 Adapter；
- 历史协作数据没有自动获得正式治理效力。
- 用户已说明现有运行时 App/Connector Secret value 已迁移到 `secrets-stackdocker`，但现有应用中仍可能保留历史 `.env`/本机凭据加载代码路径；正式 Adapter 必须证明这些路径不能成为生产 fallback；尚未实现的 Safety signing key 不在该声明范围内。

迁移原则：

1. 现有数据冻结为来源快照；
2. 按对象逐条分类为 `historical_source`、`draft_candidate`、`verified_reference`；
3. 未经具名确认不生成正式签发事实；
4. Bitable 受控字段改由 Projection Module 写；
5. 低风险输入先迁移，高影响治理后迁移；
6. 新旧系统并行期间只允许一个 owner 写事实；
7. 每一域用对账报告和回滚点切换，不做一次性大爆炸迁移。

## 13. 分阶段落地

### 13.1 F0 七域具名评审合同

F0 只冻结设计合同、威胁模型、责任、invalid-first fixture/drill **规格**与后续 witness
分配；它不要求尚未实现的 Runtime 先产出真实运行证据，也不证明任何 tenant/app、Secret、
Safety、GitHub 或执行能力已经可用。F0 只有在以下七个责任域对同一**合同 digest**给出具名
结论后才可关闭。本文没有这些人员的组织身份，因此当前全部是 `REVIEW-REQUIRED`，不得补造
姓名或批准：

七域评审的唯一被评对象是版本化 `F0ReviewManifestV1`，不是单个 17 文档 hash、聊天摘要或
工作树：

```text
F0ReviewManifestV1 {
  review_manifest_schema_version
  review_manifest_ref
  manifest_generator_subject_ref
  manifest_generator_subject_kind
  manifest_generator_tool_sha256
  repository_identity {
    vcs
    provider
    host
    repository_owner
    repository_name
    canonical_remote
  }
  frozen_git_commit_sha
  frozen_git_tree_sha
  normative_files[] {
    repository_relative_path
    git_blob_oid
    git_file_mode
    sha256
    normative_role
  }
  review_record_schema_version
  review_seal_schema_version
  manifest_generation_receipt_schema_version
  supersedes_review_manifest_ref
  supersedes_review_manifest_digest
  created_at
  review_manifest_digest
}

F0NamedReviewV1 {
  review_record_schema_version
  reviewer_actor_id
  reviewer_display_name
  reviewer_subject_kind
  responsibility_scope
  decision
  review_manifest_ref
  review_manifest_digest
  manifest_generation_receipt_ref
  manifest_generation_receipt_digest
  role_assignment {
    assignment_ref
    assignment_digest
    assigned_by_actor_id
    assigned_at
  }
  segregation_of_duties {
    reviewer_is_assignment_issuer
    reviewer_is_manifest_generator
    reviewer_is_automated_agent
  }
  design_evidence_refs[]
  assigned_runtime_witness_gates[]
  conditions[]
  blocking_findings[]
  residual_risks[]
  reviewed_at
  review_record_digest
}

F0ManifestGenerationReceiptV1 {
  generation_receipt_schema_version
  generation_receipt_ref
  review_manifest_ref
  review_manifest_digest
  generator_subject_ref
  generator_subject_kind
  generator_tool_sha256
  generation_channel_ref
  generation_event_ref
  generated_at
  attestation_evidence_ref
  external_verification_receipt_ref
  generation_receipt_digest
}

F0NamedReviewSealV1 {
  review_seal_schema_version
  review_seal_ref
  review_manifest_ref
  review_manifest_digest
  manifest_generation_receipt_ref
  manifest_generation_receipt_digest
  review_record_digest
  responsibility_scope
  reviewer_actor_id
  reviewer_subject_kind
  credential_or_audit_actor_id
  actor_credential_binding_ref
  evidence_kind
  key_usage_or_audit_event_type
  signature_or_audit_evidence_ref
  trusted_timestamp
  trust_policy_ref
  trust_verification_receipt_ref
  review_seal_digest
}
```

四份仅用于评审包、**不属于生产 Schema** 的机械合同位于：

- `schemas/f0-review-manifest-v1.schema.json`；
- `schemas/f0-named-review-v1.schema.json`；
- `schemas/f0-manifest-generation-receipt-v1.schema.json`；
- `schemas/f0-named-review-seal-v1.schema.json`。

其版本字段分别固定为 `F0ReviewManifestV1`、`F0NamedReviewV1`、
`F0ManifestGenerationReceiptV1` 与 `F0NamedReviewSealV1`，未知字段一律拒绝。
`repository_identity` 固定绑定本次 F0 的 GitHub 仓库：

```text
vcs              = git
provider         = github
host             = github.com
repository_owner = kogamishinyajerry-ops
repository_name  = flai-os
canonical_remote = https://github.com/kogamishinyajerry-ops/flai-os.git
```

仓库转移、镜像或 remote 别名不能静默继承该身份；身份中任一值变化都需要新 Schema、新 frozen
commit/tree 与新 manifest。`frozen_git_commit_sha` 是该仓库中 40 位小写十六进制 commit
OID；`frozen_git_tree_sha` 必须逐字等于
`git rev-parse <frozen_git_commit_sha>^{tree}` 的根 tree OID。

`normative_files[]` 至少完整覆盖 `CONTEXT.md`、ADR-0047～0062、本设计包 README、00～17、
`CODEX_HANDOFF_PROMPT.md` 与上述四份 review-package Schema。`normative_role` 只能是：

```text
DOMAIN_CONTEXT
ARCHITECTURE_DECISION_RECORD
DESIGN_PACKAGE_INDEX
DESIGN_CONTRACT
IMPLEMENTATION_HANDOFF_CONTRACT
REVIEW_PACKAGE_SCHEMA
```

每项 `repository_relative_path` 必须是 NFC、以 `/` 分段的仓库相对 UTF-8 字符串；拒绝空路径、
绝对路径、空分段、尾随 `/`、反斜杠、NUL、`.`/`..` 分段与重复路径。数组按
`repository_relative_path` 的 **UTF-8 byte sequence** 严格升序，不能按 locale、大小写折叠
或文件系统枚举顺序排序。路径必须在 frozen tree 中解析为 mode `100644` 或 `100755` 的
Git blob；symlink、submodule、tree 与缺失对象拒绝。`git_blob_oid` 必须等于该 tree entry 的
40 位小写 Git blob OID，`git_file_mode` 必须等于 tree entry mode。

逐文件 `sha256` 的输入是
`git cat-file blob <frozen_git_commit_sha>:<repository_relative_path>` 返回的**原始 blob byte
stream**；不得做 UTF-8 解码/重编码、NFC、换行、BOM、文件权限或尾随空白归一化。摘要输出为
64 位小写十六进制。只有 path 字符串参加上述 NFC 与排序规则，blob 内容不归一化。manifest
自身不能进入自己的 `normative_files[]`，否则形成 commit/digest 自引用；它可以存放在后续
review-package commit 或受控评审记录库中。

manifest 的 canonical projection 是从完整对象中**仅删除**
`review_manifest_ref` 与 `review_manifest_digest` 后得到的对象。所有字符串先验证为 NFC，所有
时间验证为 UTC `YYYY-MM-DDTHH:MM:SSZ`（禁止小数秒和非 `Z` offset），禁止浮点数，再执行
RFC 8785 JCS。单个尾随 `\0` 表示一个 NUL octet，不是两个可见字符：

```text
review_manifest_digest =
  lowercase_hex(
    SHA-256(
      ASCII("flai.feishu-hub.f0-review-manifest.v1") || 0x00
      || RFC8785_JCS_UTF8(canonical projection)
    )
  )

review_manifest_ref =
  "flai://f0-review-manifest/sha256/" || review_manifest_digest
```

verifier 必须从 raw object 自行删除精确字段并重算，不信任 detached/client digest。
`supersedes_review_manifest_ref` 与 `supersedes_review_manifest_digest` 必须同时为 `null`，
或同时指向上一 manifest 且满足同样的 ref/digest 派生关系。`created_at` 是 manifest 生成器
观察 frozen commit/tree 后写入的 UTC 秒级时间；它不表示任何人已评审、签发或授权。

任何 normative file、review-package schema、commit/tree、repository identity 或文件集合变化
都生成新 manifest；旧 review 自动 stale，不允许“沿用同意”。review records 不进入 manifest
digest，避免自引用；七域 `review_manifest_ref` 与 `review_manifest_digest` 必须分别逐字相等。

manifest 还必须内容绑定 `manifest_generator_subject_ref`、`manifest_generator_subject_kind` 与
生成器可执行文件的 raw-byte `manifest_generator_tool_sha256`。这些字段让 reviewer 能识别并
排除 manifest 生成者，但**不能自证身份**。生成后必须由生成器所属的受控认证通道形成独立
`F0ManifestGenerationReceiptV1`；该 receipt 绑定精确 manifest、生成器主体、工具 digest、
channel/event 与 trusted evidence。receipt 的 canonical projection 仅删除
`generation_receipt_ref` 与 `generation_receipt_digest`：

```text
generation_receipt_digest =
  lowercase_hex(
    SHA-256(
      ASCII("flai.feishu-hub.f0-manifest-generation-receipt.v1") || 0x00
      || RFC8785_JCS_UTF8(canonical projection)
    )
  )

generation_receipt_ref =
  "flai://f0-manifest-generation-receipt/sha256/"
  || generation_receipt_digest
```

组织批准的外部 verifier 必须回读并验证生成 channel/event、workload/actor binding、工具
digest、撤销状态和 attestation evidence；本地生成器不能给自己出可信 receipt。receipt 缺失、
未验、主体/工具不一致或 reviewer 与生成主体相同，F0 保持阻断。receipt 不进入 manifest
digest，避免回环；每份 `F0NamedReviewV1` 必须绑定同一 receipt ref/digest。

`F0NamedReviewV1.responsibility_scope` 只能是下表七域之一：

```text
ORGANIZATIONAL_PRODUCT_AND_GOVERNANCE
IDENTITY_AND_AUTHENTICATION_CHANNEL
ACL_CLASSIFICATION_AND_PRIVACY
FLAI_RUNTIME_EVIDENCE_AND_AUDIT
GITHUB_ENGINEERING_DELIVERY
KNOWLEDGE_AND_RECORDS
SECRET_AND_OPERATIONAL_CONTINUITY
```

`decision` 只能是 `APPROVED | CONDITIONAL | REJECTED | UNKNOWN`；`REVIEW-REQUIRED`、`PENDING`
和空值不是结论。`CONDITIONAL` 必须至少列出一个 `conditions[]`，`REJECTED`/`UNKNOWN` 必须
至少列出一个 `blocking_findings[]`；为保持 review record 不可变，`CONDITIONAL` 永远阻断
F0 关闭，条件满足后必须对同一仍有效 manifest 生成一份新的 `APPROVED` review record。

每份 record 必须解析 `role_assignment.ref+digest`，并证明 assignment 至少绑定
`review_manifest_ref+digest`、`reviewer_actor_id`、唯一 `responsibility_scope`、具名
`assigned_by_actor_id` 与 `assigned_at`。reviewer 与 assignment issuer 必须是两个不同的真实
人类 Actor；reviewer 不能是该 manifest 的生成者或自动化 Agent。七域必须各恰有一份当前
`APPROVED` record；同一人可以在组织明确授权下承担多个非冲突域，但
`IDENTITY_AND_AUTHENTICATION_CHANNEL` 与 `SECRET_AND_OPERATIONAL_CONTINUITY` 必须由不同
reviewer，`FLAI_RUNTIME_EVIDENCE_AND_AUDIT` 与 `GITHUB_ENGINEERING_DELIVERY` 也必须由不同
reviewer。跨 record 的唯一性和上述职责分离由 review-package verifier 检查，不能只依赖单份
JSON Schema。

`assigned_runtime_witness_gates[]` 不得为空，并按责任域精确冻结：

| 责任域 | 必须分配的 witness gate |
|---|---|
| `ORGANIZATIONAL_PRODUCT_AND_GOVERNANCE` | `F1_EXIT, F2_EXIT, F3_EXIT, F5_EXIT, PHASE_ENTRY` |
| `IDENTITY_AND_AUTHENTICATION_CHANNEL` | `F1_EXIT, F2_EXIT, F3_EXIT, D6_F4_EXIT, D7_F4_EXIT, D8_F4_EXIT` |
| `ACL_CLASSIFICATION_AND_PRIVACY` | `F1_EXIT, F2_EXIT, F3_EXIT, D6_F4_EXIT, D7_F4_EXIT, D8_F4_EXIT` |
| `FLAI_RUNTIME_EVIDENCE_AND_AUDIT` | `F1_EXIT, F2_EXIT, F3_EXIT, D6_F4_EXIT, D7_F4_EXIT, D8_F4_EXIT` |
| `GITHUB_ENGINEERING_DELIVERY` | `F1_EXIT, F2_EXIT, F3_EXIT, D6_F4_EXIT, D7_F4_EXIT, D8_F4_EXIT` |
| `KNOWLEDGE_AND_RECORDS` | `F1_EXIT, F2_EXIT, F3_EXIT, D6_F4_EXIT, D7_F4_EXIT, D8_F4_EXIT, F5_EXIT` |
| `SECRET_AND_OPERATIONAL_CONTINUITY` | `F1_EXIT, F2_EXIT, F3_EXIT, D6_F4_EXIT, D7_F4_EXIT, D8_F4_EXIT, F5_EXIT` |

数组顺序按上表保留；不得用空数组、`NOT_APPLICABLE` 或其他域的分配替代。若后续能力门调整，
必须先生成新 manifest/schema 和七域新 review。

NamedReview 的 canonical projection 仅删除 `review_record_digest`；其余字段（包括 role
assignment、SoD 声明、manifest binding、结论、条件/阻断项、witness 分配、风险和
`reviewed_at`）全部进入摘要。字符串、时间、浮点与 JCS 规则同 manifest：

```text
review_record_digest =
  lowercase_hex(
    SHA-256(
      ASCII("flai.feishu-hub.f0-named-review.v1") || 0x00
      || RFC8785_JCS_UTF8(F0NamedReviewV1 excluding exactly review_record_digest)
    )
  )
```

`reviewed_at` 是 reviewer 完成该结论的 UTC `YYYY-MM-DDTHH:MM:SSZ` 时间，不得从文件 mtime、
commit time 或模板生成时间推断。具名人类必须在组织批准的认证通道中形成 record；AI 输出、
聊天确认、Git commit 和模板都不是 review。

每份 `F0NamedReviewV1` decision core 必须配一份独立 `F0NamedReviewSealV1`。seal 绑定精确
manifest、manifest-generation receipt、review core digest、责任域与 reviewer，并引用组织
批准的签名或不可变审计证据、ActorBinding、key usage/audit event、trust policy、trusted
timestamp 与 verification receipt。seal canonical projection 仅删除 `review_seal_ref` 与
`review_seal_digest`：

```text
review_seal_digest =
  lowercase_hex(
    SHA-256(
      ASCII("flai.feishu-hub.f0-named-review-seal.v1") || 0x00
      || RFC8785_JCS_UTF8(canonical projection)
    )
  )

review_seal_ref =
  "flai://f0-named-review-seal/sha256/" || review_seal_digest
```

本地 verifier 只能重算 core/seal 摘要与绑定；只有组织批准的外部 verifier 能认证签名/审计
证据、身份、任命、撤销、trusted timestamp 和追加式历史。自报 `HUMAN`、三个职责分离布尔、
display name、无钥摘要或伪造 URI 均不能关闭 F0。

模板可以帮助收集输入，但模板必须使用不同的
`review_record_schema_version = F0NamedReviewTemplateV1`（本轮不定义模板 Schema），不得
携带 `review_record_digest`，不得通过 `f0-named-review-v1.schema.json`，也不得计入七域
review 数量。把 placeholder、示例姓名或预填 `APPROVED` 填进模板，不能把模板提升为 record。

当前工作树尚未形成包含这些文件的冻结 commit/manifest，因此本文只能提供
`F0-REVIEW-PACKAGE-DRAFT`，不能声称 F0 已可关闭。

| 责任域 | 必须裁决 | F0 最小评审输入（合同级） |
|---|---|---|
| 组织产品与治理 | 飞书是否是唯一组织 landing/inbox/orchestration Surface、哪些仪式可内嵌、哪些专业 Surface 保留、目标 RTO/RPO 与 degraded UX | IA、职责矩阵、正式签发政策、连续性目标与验收规格 |
| 身份与认证通道 | tenant/app/subject→ActorBinding、SSO/step-up、workload/delegation、撤权 epoch；独立 Safety 双人硬件身份、subject-bound admission、唯一 Coordinator/Reservation/nonce consumption/ChallengeState 与职责分离 | channel/identity threat model、Safety Identity/PKI admission + Reservation provenance、Trusted-Time interval/rollback、唯一 provider send boundary 与 invalid-first fixture 规格 |
| ACL、classification 与隐私 | 飞书租户/空间承载上限、audience、标题/计数/存在性抑制 | classification lattice、项目 ACL、目标空间批准 |
| FLAi Runtime、证据与审计 | Snapshot、ExecutionRun、Artifact、receipt、kill/revoke 与 WORM owner；target owner/signer/verifier 分工 | Production Snapshot 合同、canonical Safety receipt/signature/verification、algorithm downgrade、stable effect key、result uniqueness、追加式 reconcile fixture 规格与 outage drill 计划 |
| GitHub 工程交付 | Issue/branch/PR/review/CI/merge owner、原生 diff/approval/merge Surface、effect key、回读与迁移 | GitHub App 最小权限模型、CODEOWNERS/branch protection/CI 目标合同、reconcile fixture 规格 |
| Knowledge 与 records | Wiki/Docs 来源、KnowledgeVersion、档案留存、正式记录和替代关系 | source revision/digest/ACL、发布/撤销合同与 records 演练规格 |
| Secret 与运行连续性 | `secrets-stackdocker` workload identity、最小引用、旧值撤销、轮换、backup/restore；独立 Safety Signer、三类 Owner Workload Attestation、两类 Egress Workload Attestation、Policy Fence、Trusted Time Authority/Commit Guard material 的生成、保管、epoch、轮换/吊销、trust anchor、owner 与互不代签；tenant/app 权限丢失、backlog/replay、projection rebuild、records retention/export、offboarding/vendor exit | 普通 SecretRef 与全部 Safety material 分域矩阵；rotation/revoke/no-fallback/restore、time/commit-guard/fence/sign/verify、Secret 栈 outage、rebuild/export/exit 的 test/drill plan、owner 与通过标准，不要求 F0 实跑 |

每域记录上述 `F0NamedReviewV1`。任一 `CONDITIONAL`、`REJECTED` 或 `UNKNOWN` 都阻断申请
F1；F0 通过也不自动授权 F1。AI 评审、聊天确认、Git commit 或模板不能替代具名结论。

真实运行 witness 按能力成熟度后置，不能反向堵死 F0：

| 真实 witness | 最早必须通过的门 |
|---|---|
| tenant/app 权限、只读 ACL/classification、event backlog/replay、projection rebuild、F1 目标 RTO/RPO | F1 exit |
| ActorBinding、低风险 typed intent、幂等与 effect-unknown 对账 | F2 exit |
| step-up、prepare/challenge/commit、owner receipt 与职责分离 | F3 exit |
| ExecutionRun/Artifact/Delivery、kill/revoke、Audit/WORM、SecretRef no-fallback/rotation/revoke/restore、独立 Safety PKI/HSM 与全故障域 outage drill | 对应 D6/D7/D8 实现证据且 F4 exit |
| 历史 Bitable/TeamLedger、records export/retention/offboarding/vendor-exit | F5 exit |
| 生产/试点资格、目标主机与真实 cohort | 对应 R/Phase Entry、QualificationDecision 与 DeploymentBinding |

| 阶段 | 范围 | 退出证据 | 当前授权 |
|---|---|---|---|
| F0 合同冻结 | ADR、术语、Interface、Source Ownership、ActorBinding、classification、receipt、SecretRef、invalid-first fixture/drill 规格 | frozen Git commit/tree + `F0ReviewManifestV1`；manifest-generation receipt 通过外部验证；七域 review core+seal 一致且通过；后续 runtime-witness 分配冻结 | 本文完成设计输入；未形成 frozen manifest、未正式签发 |
| F1 只读联邦视图 | FLAi/GitHub → 飞书工作收件箱、项目和共建地图 | freshness、event gap、ACL、脱敏、对账测试 | 未授权实现 |
| F2 低风险协作意图 | 需求、关注、补证据、接收确认 | typed intent、幂等、拒绝与回告 | 未授权实现 |
| F3 正式治理仪式 | 验收、路线图、知识、Qualification、DeploymentBinding | prepare/commit、step-up、role separation、owner receipt | 未授权实现 |
| F4 执行与交付 | ExecutionRun 卡片、Artifact/Knowledge、DeliveryBundle | REAL/MOCK/TEST witness、取消、effect_unknown | 未授权实现 |
| F5 历史迁移与旧 Surface 退役 | TeamLedger/Bitable 历史分类；关闭重复管理入口 | 对账、回滚、用户验收、无第二 owner | 未授权实现 |

F0 不修改生产 Schema。任何后续 Schema、公开 Interface、第三方权限、真实飞书写入或试点都需要
单独授权。

## 14. Invalid-first 验收

实施前先写能咬住以下失败的 fixtures：

1. 未绑定飞书身份尝试签发；
2. callback replay 或跨 tenant/app 事件；
3. Bitable 直接修改受控状态；
4. stale projection 上继续签发；
5. expected digest 漂移后消费旧 challenge；
6. GitHub Issue 关闭冒充需求解决；
7. FLAi 缺 witness 却显示 completed；
8. `REAL/MOCK/TEST/UNKNOWN` 被折叠；
9. receipt 验证失败仍显示成功；
10. 外部请求超时后换幂等键重放；
11. classification unknown 仍向群聊发送正文；
12. 知道深链 ID 即可越权读取；
13. AI 草稿签发路线图、知识、资格、部署或交付；
14. `secrets-stackdocker` 不可用时回退旧值；
15. Secret 进入日志、Bitable、卡片或子进程；
16. 飞书不可用导致 kill/revoke 被阻断；
17. 双向同步按“最后写入者获胜”覆盖 owner 事实；
18. 指标 source gap 仍显示绿色或参与领导简报；
19. challenge 未绑定 payload/intent digest、ActorBinding、credential/policy epoch 或认证
    assurance 仍可 commit；
20. challenge nonce 被重复消费、换 actor/scope/audience/purpose 或降低 assurance 后仍产生
    第二次 effect；
21. receipt 缺 intent、challenge、actor、target、effect/outcome 或 owner-specific verifier
    仍显示生效；
22. target space ceiling 被混入内容密级 join，或 `can_project` 为 unknown 仍投影正文；
23. 飞书群成员、项目改名或 Bitable 字段可以创建/改变 FLAi ProjectMembership；
24. `SubmitDemandSignal` 后修改飞书需求草稿会覆盖既有不可变 DemandSignal；
25. Codex/Kimi-K3 两个活动 run 获得重叠文件/Interface 写范围；
26. `assistant_model` 标签存在但缺 actual workload/runtime/model receipt，仍声称执行者真实；
27. Assistant dispatch/pause/resume/cancel/reconcile/handoff 任一 control effect 为
    `effect_unknown` 后换键重派、继续控制或显示已暂停/已恢复/已取消/已对账；
28. handoff/rework/accept 缺 work item digest、当前 generation、具名人类 owner 或 CAS 前置条件
    仍推进状态，或把 accept 冒充 GitHub approval/merge；
29. Feishu、Hub、主协作 SSO 或 `secrets-stackdocker` outage 时安全通道形成循环依赖；
30. Safety receipt 与 signature envelope 的 digest 不匹配、signer key epoch 已吊销、trust
    anchor/epoch 不匹配、algorithm/policy downgrade、signer failure domain 不独立或签名无效
    仍生成任何 verified safety result；
31. Safety verifier 自行生成/补写 target owner receipt，或 signer 改写 target effect；
32. `external_provider_effect=EFFECT_UNKNOWN` 被显示为
    `FULL_EFFECT_VERIFIED`、最终成功或绿色，而不是 amber 的本地围栏已核验/外部待确认；
33. payload 字段增删、数组换序、非 NFC/非 RFC8785 编码、domain separator/自引用排除错误，
    或 verifier 信任 detached/client digest 仍验签通过；
34. factory meta-integrity gate 非 `True` 仍写 Result/Head，或 `VALID` 在任一适用 subject
    gate 非 `True`、key revocation unknown、trust snapshot stale/unavailable 或 verification
    超 freshness 时仍构造 Full/Pending；或反过来用 VALID 门阻断 Invalidated/Inconclusive；
35. pending→confirmed 修改旧 receipt、换 effect key、复用已消费 challenge、缺 expected-head
    CAS/supersedes/owner-sequence 门，或 signed payload 未绑定 observation/query receipt
    ref+digest，或使用 stale/unauthenticated provider observation；
36. receipt 丢失或 signer 不可用后的 SafetyEffectUnknown 缺稳定 effect key，导致无法按原 key
    查询，或改用新 key 对账；
37. verification 缺固定 key/canonical/domain/self-exclusion，或同 receipt/envelope/
    Verification Policy Bundle/Policy Head 的 replay 生成第二 verification；
38. factory policy 改版为同一 receipt+verification 生成新 result key/ref，Result Head 缺
    generation+digest CAS、pending result 内嵌新 head digest 形成循环、同 chain 分叉多个 head，
    或 replay 改写首次 `constructed_at`；
39. 安全通道执行扩权、正常签发、任意证据导出，或无法取得 owner witness 却显示处置成功；
40. tenant/app 权限漂移、event backlog 超窗或 projection rebuild 失败后仍沿用旧绿。
41. PreparedCommand、Challenge、OwnerReceiptPayload、SigningRequest、SignatureEnvelope 与
    signer 未绑定同一 Issuance Policy Head+Bundle，或 verifier/factory/reverify/result/head
    未绑定同一 required Verification Policy Head+Bundle，或任一组件隐式解析“当前策略”；
42. 旧 verification 超 freshness 后仍显示绿色，或在同一 Verification Policy Bundle 下创建第二个
    verification/Inconclusive result；取得新 bundle 后 INVALID/UNKNOWN successor 未以当前
    Policy Head + Result Head generation/digest CAS 推进，或 stale CAS 仍成功；
43. key revocation、required Verification Policy Head/Bundle 漂移或 trust source UNKNOWN 时
    继续显示旧 Full；已签发新 bundle 后未分别形成 Invalidated/Inconclusive successor，或旧
    Policy/Result Head generation/digest 可以覆盖并发新 Head。
44. reverify 新 Verification Policy Bundle 时要求改写旧 receipt 的 issuance bundle，或未验证
    payload/envelope issuance digest 一致、accepted issuance digest membership、算法与吊销
    状态，就接受旧 receipt。
45. commit 只给 `prepared_command_ref`、隐式选择 challenge，或 attestation/
    ConfirmationProof 未绑定 challenge/prepared/nonce/confirmation mode/audience/purpose 仍
    可消费 nonce；
46. Source Ownership Registry 未具名签发、零/多匹配、Head/Registry/Entry 漂移仍路由，或按
    receipt 自报 owner/type/schema 选择 verifier；
47. Issuance/Verification Bundle、Policy publication receipt、Policy Head、Registry/Entry/
    Resolution 的 exact field projection/self-exclusion/ref/domain/数组排序/去重未通过，仍接受
    detached digest；
48. 调用者提交自选 trust bundle，Policy Head publication receipt 未验证，verifier→factory
    或 reader→projection 间 Policy Head 发生 TOCTOU 仍显示/写入成功；同一或历史 bundle
    digest 被重新发布为新 Head，借新 Head digest 绕过 freshness/uniqueness；
49. signer 接受裸 digest/key handle，SigningRequest/target-owner attestation/issuance Head
    任一 binding 为 False/Unknown 仍签名；
50. 七域 review 未绑定同一 `F0ReviewManifestV1`，manifest 未绑定 frozen commit/tree 与完整
    normative path/hash 集，缺外部验证的 manifest-generation receipt、任一 review core 缺
    对应 seal/ActorBinding/trust verification，witness gate 分配为空/漂移，或 normative 文件
    变化后仍沿用旧 review。
51. `EmergencyActorAdmissionV1` 缺 kind/subject/nonce/replay-domain canonical binding，
    同一 admission digest 被跨 prepare/commit/publication、跨 subject 或跨 Reservation
    复用，或 consumption key 未 CAS-on-NULL 仍产生 effect；
52. Policy publication 两份 admission 未绑定同一 `SafetyPolicyPublicationChallengeV1`，
    publication nonce 未由 Coordinator Reservation 单次消费，Policy owner 未在自己的本地
    transaction 绑定该 Reservation 更新 Head/PointerRevision/current alias，或 fixed current
    alias 覆盖后导致历史 PointerRevision 无法按 ref/digest 在线重算。
53. 同一 prepare subject/nonce 换两份新 admission 获得第二个 Reservation，或 Admission
    Coordinator 未在一个事务 CAS 双 admission + subject nonce；
54. 把 Admission Coordinator、Safety Survival、target owner 或 Policy owner 伪装成一个
    跨 owner transaction；下游失败后释放已消费 admission/nonce，而不是保持 reserved+reconcile；
55. `SafetyChallengeV1` digest 包含可变 state，或 ChallengeState 存在第二写者、generation
    跳跃、predecessor/head CAS 漂移仍推进；
56. 新 Policy Head/PointerRevision 跳号、fork、predecessor/role/owner/bundle/receipt 错绑，
    genesis 非 null/0→1，或 `(role,generation)` 重复仍 CAS current alias；
57. Policy alias CAS 未由唯一 Fence Authority 在自身 single-writer 原子提交严格推进
    fence `E→E+1` 并形成
    ALIAS_COMMIT witness；signer 的 PRE/POST witness 未绑定同一 fence/Pointer/Head/Bundle/
    SigningRequest/envelope core，POST 未引用 PRE/signature-bytes digest，仍发布 Envelope，
    或漂移签名字节被暴露为可调用签名。
58. 下游只验 Reservation digest，不从 Coordinator 权威 resolve 双 AdmissionConsumption +
    SubjectNonceConsumption，孤儿/伪造 Reservation、attestation/key revocation Unknown 或
    任一 verification gate 非 `True` 仍创建 anchor；
59. resolver 返回 ACTIVE 后，owner-local commit 不消费
    `SafetyTrustedTimeAttestationV1 ref+digest`/CAS checkpoint；epoch transition 无
    continuity-root 签名或 Genesis/counter 初值错误；CommitLease 未绑定 transaction
    nonce/subject，FreshnessProof 未绑定可信 elapsed source/owner-store 线性化点，Fence
    witness 缺 exact lease/proof/checkpoint；旧 counter/epoch、断 predecessor、UTC bound
    回拨、skew/uncertainty 超限、source outage、缓存续期、host-clock fallback、陈旧事务或
    区间跨 deadline 仍创建 Prepared/CommitAttempt/Policy effect。
60. worker 把 outbox enqueue 或 `SafetyCommitDispatchClaimV1` 当作实际 send；唯一 egress
    boundary 未在第一字节前重新验 time/deadline、未 CAS 消费精确一次性
    ProviderMutationCapability、未写 ProviderCallAttempt 就直连 provider。
61. deadline 前形成 Claim，但 egress boundary 到达时已过期仍调用；应生成
    `EXPIRED_NOT_SENT` 且 provider call=0。
62. ProviderCallAttempt 落账后断电/超时且没有 verified ProviderSendReceipt，重启后仍重发、
    换 effect key/Capability，或把 capability consumption、HTTP 2xx、worker exit 当作 receipt。
63. F0 合同允许任一 Safety material（Signer、3 类 owner-workload、2 类 egress
    operation、Fence、Trusted Time Authority/Commit Guard）来自 `secrets-stackdocker`/普通 workload identity/
    应用进程自签 key，允许跨 operation 代签，或未冻结独立 failure-domain、key epoch/
    revocation/trust anchor、stack-outage fixture/drill 规格；真实 key 与 outage witness 尚未
    产生只阻断对应 D6/D7/D8 + F4，不得反向伪称其阻断合同级 F0。

## 15. 机械验收条件

### 15.1 各阶段共同不变量

- 本阶段纳入的 FLAi-owned 日常 Surface 都从同一飞书 FLAi 工作空间发现和编排；GitHub
  原生代码操作、FLAi 专业执行与密封安全通道使用受控深链，不另建组织首页；
- 普通用户无需理解 Bitable schema 或 FLAi 内核对象；
- 每个投影项有 owner、version/digest、classification、freshness 和适用的 source evidence；
- 治理变迁缺必需 owner receipt 时不显示生效，非治理只读事实不伪造 receipt；
- GitHub、FLAi、Knowledge、Audit 和 Secret owner 无双写；
- 当能力进入 F4/真实执行范围时，FLAi kill/revoke 不依赖飞书、Hub、主协作 SSO 或普通在线
  Secret 解析，并通过对应 D6/D7/D8 + F4 outage drill；F0 只冻结该演练规格；
- 当 Safety result 能力进入实现范围时，它仅由 verifier-owned factory 构造；外部 effect
  unknown 保持 amber，pending→confirmed 只走认证查询、追加 receipt 与 expected-head CAS；
- 飞书空间不满足密级时正文不落入飞书；
- Secret value 不在代码、配置、日志、卡片、表格、文档或测试 fixture；
- Source gap、receipt invalid、effect unknown 和 reconciliation 有不同状态；
- 全过程由真实人类签发，Codex、Kimi-K3 和 LLM 无签发能力。

### 15.2 累积分段退出门

后一阶段继承前一阶段已通过的不变量，但前一阶段不需要提前满足后一阶段功能：

| 阶段 | 只验收本段新增能力 |
|---|---|
| F1 | 只读投影有 source evidence、ACL/classification、freshness/event gap；ProjectContextBinding 单向且 membership drift fail-closed；backlog replay、projection rebuild、tenant/app 权限丢失和批准的 RTO/RPO 演练通过；没有飞书写 owner 事实 |
| F2 | 仅低风险协作 intent；ActorBinding/channel attestation、typed schema、幂等、拒绝、回告和 effect-unknown 对账通过；高影响意图仍不可达 |
| F3 | 高影响动作绑定 PreparedCommandV1、精确 ReviewChallengeV1+ConfirmationProofV1、SourceOwnershipRegistry Head/Entry、payload/target/actor/epoch/assurance/policy/gate digest、fresh step-up、一次性 CAS nonce、职责分离和 OwnerCommitReceiptV1；verifier dispatch 不信 receipt 自报，EffectUnknownV1 负例通过 |
| F4 | ExecutionRun/Artifact/Knowledge/DeliveryBundle 严守 REAL/MOCK/TEST witness；DeveloperAssistant dispatch/pause/resume/cancel/reconcile/handoff/rework/accept 全生命周期有实际 runtime/control receipt、文件/Interface scope、预算、幂等和负例对账；D6/D7/D8 的 kill/revoke、Audit/WORM、Secret/Safety PKI/HSM outage/rotation/restore witness 通过；GitHub diff approval/merge 仍由原生 Surface 与真人决定 |
| F5 | TeamLedger/Bitable 历史逐条分类；重复组织 Surface 退役且 owner 双写为零；records export/retention、tenant/vendor exit、回滚、重建、证据深链和用户验收通过 |

## 16. 明确非目标

- 不把飞书升级为 Agent Runtime、Policy Engine、Audit Ledger 或 FLAi Control Kernel；
- 不把 Bitable 当作运行、发布、授权或签发数据库；
- 不在 F0 一次性迁移现有数据或改生产 Schema；
- 不允许任意自定义脚本、通用 approve 或任意 URL Connector；
- 不承诺所有密级正文都可物理存放于飞书；
- 不取消 GitHub 的代码 review、merge 和 CI；
- 不取消密封的 kill/revoke 安全生存通道；
- 不用 AI 自动采纳需求、签发路线图、批准能力、合并代码或发布；
- 不把 Secret 配置存在冒充轮换、撤销和最小权限已验证。

## 17. 官方能力依据与项目证据

飞书开放平台当前公开支持网页应用、机器人、小组件、消息卡片、服务端 API 和基于长连接的事件
回调；这些能力足以承载本文的 Surface 和 Adapter 形态，但不自动提供本项目所需的权威签发、
classification、owner receipt 或安全生存语义：

- [飞书开放平台](https://open.feishu.cn/?lang=zh-CN)
- [工作台小组件概述](https://open.feishu.cn/document/uAjLw4CM/uYjL24iN/block/guide/hosting-scenario-introduction/workplace?lang=en-US)
- [开发工具概述](https://open.feishu.cn/document/tools-and-sdks/developer-tools-portal)
- [长连接事件示例](https://open.feishu.cn/document/develop-an-echo-bot/explanation-of-example-code?lang=zh-CN)
- [通讯录 API 的 tenant/user token 权限差异示例](https://open.feishu.cn/document/server-docs/contact-v3/department/parent?lang=zh-CN)

本地现有飞书应用的真实可复用点与缺口必须在实施时重新绑定精确 commit SHA、配置引用和测试结果；
本文不把当前工作副本或用户关于 Secret 迁移的说明冒充生产验证。

---

*飞书唯一组织协作与治理中枢设计 · 2026-07-23 · 设计确认，不授权实现*

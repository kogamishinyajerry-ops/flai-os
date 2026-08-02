# ADR-0062：飞书外网研发协作中枢（原全局范围已被 ADR-0063 取代）

- 状态：`superseded_in_part_by_adr_0063`
- 实现状态：`EXTERNAL-DEVELOPMENT-ONLY / ACCEPTED-NOT-IMPLEMENTED`
- 日期：2026-07-23
- 正式签发主体：`UNRESOLVED`
- 实施授权：否
- 生产准入影响：无；当前仍为 `NO-GO`
- 当前适用信任域：`EXTERNAL_DEVELOPMENT`

> **范围纠偏（2026-07-24）**
>
> owner 已明确：飞书用于当前外网研发团队共同开发 FLAi-OS；正式植入企业内网后，FLAi-OS
> 与飞书生态完全断开，并依赖内网自托管通讯、项目、知识、身份、代码和运行设施。自
> [ADR-0063](ADR-0063-external-development-airgap-internal-workspace.md) 起，本文所有未显式
> 限定作用域的“唯一组织入口”“全体人员”“内网知识/运行/治理从飞书进入”等表述，只能按
> `FeishuDevelopmentHub` 的**外网研发协作**理解；与 ADR-0063 冲突的内网产品和部署语义全部
> 失效。
>
> 本 ADR 不再定义 `AIR_GAPPED_INTERNAL` 的产品入口、身份、Secret、知识、Runtime、审计、
> 连续性或生产准入。原飞书中心化 F0 SHA 只保留为澄清前历史快照，不能沿用为内网自托管
> 工作空间的 F0。

## 背景

FLAi-OS 已经分别设计了工程智能体工作台、治理与运行中心、FLAi 共建地图和后期智能化指挥中心。继续把这些 Surface 独立建设成多个管理入口，会迫使普通用户在飞书、FLAi-OS 和 GitHub 之间切换，也会让项目、需求、会议、知识和 Agent 治理形成多个彼此竞争的协作空间。

组织已经有一个持续演进的飞书自建应用，具备机器人、长连接事件、卡片、网页应用、多维表格、项目、决策、风险、行动项和 Agent 统计等基础能力。用户明确选择让飞书承担类似 Notion 的唯一日常中枢，同时保留 GitHub 管理代码。

“唯一中枢”若被误解为“所有事实都存入飞书”或“多维表格直接成为授权和审计数据库”，会违反以下既有红线：

- FLAi Control Kernel 是执行、授权、审计、证据和交付决定的唯一控制内核；
- 人是唯一签发者，卡片点击、表格字段和 AI 草稿都不能代签；
- GitHub commit、PR 和 CI 是代码与工程交付事实；
- 密级、ACL、知识权威、FLAi Bench 和运行 witness 不能由展示层重写；
- 飞书故障不能阻断强停、撤权和安全恢复。

因此需要同时实现“一个入口”和“多类权威事实”，而不是建立一个飞书第二控制面。

## 决定

### 1. 产品定位

在 `EXTERNAL_DEVELOPMENT` 域，飞书被定义为 FLAi-OS **外网研发的唯一日常协作中枢**，
即外网研发团队的标准 landing、工作收件箱与编排 `System of Engagement`：

- 外网研发人员从飞书进入研发工作收件箱、项目空间、需求共创、设计会议工作包、非敏感研发知识、开发协作和外网研发回告；
- 所有外网研发协作从飞书发起、组织、跟踪和回告；外网研发签发仪式可在飞书内嵌页完成；
- 外网工程原型或研发工作台可作为飞书网页应用中的专业 Surface，或从飞书重新鉴权后打开；
- GitHub 仍是代码、commit、branch、PR、review、CI 和 merge 的唯一工程事实源；代码 diff
  review、PR approval、branch protection 与 merge 仍在 GitHub 原生专业 Surface 完成；
- 内网 FLAi Control Kernel、Qualification、Deployment、Execution、Delivery、Knowledge、Audit 与 Safety 不在本文信任域；它们由 ADR-0063 定义的自托管内网 owner 管理；
- `secrets-stackdocker` 是运行时 App/Connector Secret value 的唯一 owner，普通工作负载只持有
  `SecretRef`；Safety Identity / PKI / HSM / Time 独立拥有人的硬件身份、Safety
  receipt-signing、Coordinator / target owner / Policy owner 三类 workload-attestation
  material、Egress Boundary/Wire 两类 operation-bound workload-attestation material、
  Policy-fence 与 Trusted-Time Authority/Commit-Guard material，不能与普通 Secret 栈、普通 workload identity
  或彼此形成同一故障域。

飞书不是唯一 `System of Record`，不是 FLAi Control Kernel，也不是内网安全生存通道。
GitHub 原生代码操作不是第二个外网研发组织中枢；内网 `FLAiWorkspace` 属于不同网络和信任域，
不是飞书的备用界面或同步副本。

### 2. 事实所有权

| 事实类型 | 唯一 owner | 飞书中的形态 |
|---|---|---|
| 群聊、评论、会议来源、协作文档和项目协作草稿 | 飞书协作域 | 原生内容与追加式协作事件 |
| 项目协作计划与路线图草案 | Feishu Organizational Hub 协作域 | 可编辑协作对象，不直接改变承诺事实 |
| DemandSignal、策展事件、RoadmapVersion 与签发 | FLAi Demand / Roadmap Governance owner Modules | 权限过滤投影与 typed intent；owner receipt 后才生效 |
| SourceOwnershipRegistry、Head 与 publication receipt | FLAi Architecture / Governance Policy owner | 只读版本/摘要和受控变更仪式；Hub 不可改路由 |
| DeliveryWorkItem、assistant dispatch/handoff/accept | FLAi Delivery Governance owner Module | 工作收件箱、协作输入和权威投影 |
| commit、branch、PR、review、CI 和代码差异 | GitHub | 只读投影与受控工程意图 |
| OfficialMeetingRecord、ResponsibilityItem、验收与更正/补遗 | FLAi Meeting & Responsibility Governance owner Module | 飞书保留来源与工作包草稿；正式记录与初始责任事项由一个 owner-local transaction 创建，只在 owner receipt 后投影 |
| ExecutionRun、Artifact、Knowledge evidence、CapabilityReleasePackage、Bench、DeploymentBinding、DeliveryBundle | FLAi Control Kernel 及其 owner Module | 权限过滤后的投影与 typed governance intent |
| 权威知识内容 | 可联邦的飞书 Wiki/Docs 等来源系统 | 创作、协作和阅读；权威性由 Knowledge Authority 的版本、适用范围和真人签发决定 |
| 运行时 App/Connector Secret value、轮换和撤销 | `secrets-stackdocker` | 只显示健康、版本别名和不可用状态，不显示值 |
| 人的安全硬件身份与 Safety receipt-signing key | 独立 Safety Identity / PKI / HSM owner | 只显示 admission、签名能力健康和 receipt 验证结果；public trust anchor 可受控分发但不是 Secret |
| Coordinator / target owner / Policy owner workload-attestation material、Egress Boundary/Wire operation-bound material、Policy-fence 与 Trusted-Time Authority/Commit-Guard material | 分离的 Safety Owner/Egress Workload Identity / Policy Fence / Trusted Time owner | 只显示具名 authority、operation、epoch、吊销/连续性、commit freshness 和验证结果；不显示 key material |
| Issuance / Verification Policy Bundle、Head 与 publication receipt | 分离的 Safety Identity Policy owner / Safety Receipt Verifier Policy owner | 只投影具名签发 Head、有效期和验证状态；调用者不能自选 current policy |
| 不可变安全审计副本 | FLAi Audit / WORM sink | 受限深链和处置工作包；不得编辑源事实 |

投影字段、Bitable 单元格、机器人文案和缓存均不得反向成为外部 owner 的事实。

### 3. 深 Module 与外部 Interface

新增 `FeishuOrganizationalHub` 深 Module。其外部 Interface 只保留三个入口：

```text
open(actor_attestation, view_request)
  -> AuthorizedWorkspaceProjection | Rejection

prepare(actor_attestation, typed_intent)
  -> ReviewChallengeV1 | Rejection

commit(commit_actor_attestation, review_challenge_ref, confirmation_proof_ref)
  -> OwnerCommitReceiptV1 | EffectUnknownV1 | Rejection
```

`open` 只形成带来源、版本、freshness、classification、ACL、digest 和 unknown 语义的投影。

`prepare` 只接受版本化 tagged-union intent，禁止通用 `approve(object)`、任意脚本、任意 API、任意状态覆盖和客户端自报 actor/role/classification。

`prepare` 形成的不可变命令必须同时冻结 intent/payload digest、目标 owner 与版本、
ActorBinding 版本、credential/policy epoch、认证 assurance、授权 scope、职责、评审门、
幂等键、有效期和一次性 nonce；并冻结由具名签发 `SourceOwnershipRegistryV1` 解出的 Registry
Head/Registry/Entry digest、owner Port、receipt type/schema 与 verifier ref/digest。该
Registry 由 FLAi Architecture / Governance Policy owner 拥有，未知、多匹配、未签发或漂移
均 fail-closed；receipt 自报字段不得驱动 verifier dispatch。

`commit` 必须显式提交精确 ReviewChallengeV1 与 admission layer 生成的 ConfirmationProofV1，
两者和新鲜 attestation 都绑定 challenge/prepared/nonce digest、confirmation mode、
audience/purpose 与同一 actor；不得凭 prepared ref 隐式选择 challenge。它重新检查对象版本、
Registry Head/Entry/verifier、digest、职责、作用域、
ACL、classification、epoch、职责分离、必要领域/安全门、nonce 和有效期；任何绑定漂移都使
challenge 失效。nonce 只能 CAS 消费一次，重复提交只能在所有关联维度相同且重新授权通过时
返回同一脱敏终态或对账案件。飞书点击成功不等于 owner commit 成功；只有 owner-specific
verifier 验证了 intent、challenge、actor、target、幂等键、effect、outcome 和 before/after
digest 的 receipt 才能投影为生效，无法确认时必须进入 `effect_unknown`。

Hub 只拥有飞书原生协作草稿、inbox/outbox、投影 manifest、intent 状态和对账案件；DemandSignal、RoadmapVersion、QualificationDecision、DeploymentBinding、DeliveryBundle 等正式领域事实仍由对应 FLAi owner Module 拥有。不得因 Hub 是唯一入口而把这些事实迁入 HubStateStore。

### 4. 日常 Surface

飞书应用只提供一个顶层入口“FLAi 工作空间”，默认首页为按当前用户生成的工作收件箱。二级空间包括：

1. 我的项目；
2. 开发协作；
3. 需求共创与 FLAi 共建地图；
4. 会议工作包与责任事项；
5. 真相知识；
6. 能力与 FLAi Bench；
7. 治理与运行中心；
8. 安全与审计；
9. 指标与领导简报。

复杂表格是高级视图，不是普通用户默认入口。普通用户不需要在多个独立管理应用之间切换。

### 5. 身份、签发与分类

- `open_id`、`union_id` 等飞书标识只能来自已验证事件或飞书免登交换，不能从卡片 payload 自报；
- `tenant + app + subject` 必须映射到版本化内部 actor binding；
- 可见按钮只是授权投影，提交时必须重新授权；
- 高影响签发必须绑定精确 digest，并满足组织要求的 step-up authentication、双人控制或职责分离；
- 内容密级由 `join(source classification, derived taint, policy floor)` 计算，目标空间密级是
  独立承载上限；只有 classification flow、目标 audience/ACL 和 projection policy 都显式为
  `True` 时才可投影正文；
- 飞书租户若未获准承载某一密级，只能显示脱敏摘要、稳定引用或存在性抑制，不能复制正文；
- 飞书页面可见不等于源证据可见，所有详情重新鉴权；
- AI 只能起草 intent，不得成为 actor、reviewer、approver 或 signer。

### 6. Secret

用户已说明现有 key 已迁入 `secrets-stackdocker`。本决策将其作为运行时 App/Connector
Secret value 的目标 owner，但不把“存在配置”外推为已经完成最小权限、轮换、撤销、审计和
故障演练；尚未实现的人的安全硬件身份、Safety receipt-signing、Coordinator / target owner /
Policy owner workload-attestation material、Egress Boundary/Wire operation-bound material、
Policy-fence 与 Trusted-Time Authority/Commit-Guard material
不在该迁移声明范围内。

- 飞书、GitHub、模型和其他普通 Connector 只保存 opaque `SecretRef`；
- Secret value 不进入仓库、Bitable、Docs、卡片、事件、intent、receipt、日志或前端；
- SecretRef 的真实名称由部署配置解析，设计文档不得猜测；
- `secrets-stackdocker` 不可用、版本 unknown 或 credential 已撤销时，调用 fail-closed；
- 禁止回退到历史 `.env`、硬编码字面量或宿主全局凭据；
- 轮换必须使 token cache、连接和相关 credential epoch 失效，并形成 witness。

### 7. 安全生存通道

FLAi Control Kernel 必须保留一个密封、强审计、非日常可见的安全生存通道。它使用独立的
`SafetySurvivalPort`、两个具名安全职责、独立强认证、一次性 challenge、精确 target
digest/generation、幂等键、target owner 签发的 `SafetyOwnerReceiptV1` 与独立
`SafetyReceiptVerificationV1`，只允许：

- 强停执行；
- 撤销会话、Grant、DeploymentBinding 或 Secret；
- 隔离制品和执行 lane；
- 只开 ReconciliationCase，不裁决；
- 向预批准本地 WORM 封存事故证据；
- 验证恢复候选，但不重新启用权限。

该通道的身份和凭据路径不得依赖飞书、Hub、主协作 SSO、HubStateStore 或普通 Connector
Secret 解析；当 `secrets-stackdocker` 本身不可用或是撤销目标时，Kernel 必须先完成不依赖
Secret 解析的本地 epoch/lease/egress 围栏。provider-side revoke 可进入
`effect_unknown + reconciliation`，但不得阻断本地围栏，也不得回退旧 Secret。
本地围栏已核验但 provider effect unknown 时，只能投影 amber 的
`LocalFenceVerifiedExternalPendingV1`；只有 provider effect 为
`CONFIRMED|NOT_APPLICABLE` 且 receipt/verification 完整时，才可形成
`FullSafetyEffectVerifiedV1` 并表示完整处置成功。

普通 App/Connector key 继续全部由 `secrets-stackdocker` 拥有；安全生存只验证预置 public
trust anchors 与具名操作者的独立硬件/PKI admission。Safety receipt signer、Coordinator
workload attestation、Policy Fence Authority 与 Trusted Time Authority/consumer-local
Commit Guard material 都必须
处于独立故障域，不得来自应用进程、普通 workload identity、`SecretProviderPort` 或
`secrets-stackdocker`。若任一所需 Safety key 只存在于普通 Secret 栈，则 stack 总体 outage 下的
安全生存能力保持 `DECLARED-NOT-VERIFIED`，并阻断对应 D6/D7/D8 + F4 runtime exit。
F0 只在组织拒绝“独立故障域”这一设计合同，或 owner/key/revocation/outage fixture 规格仍
未冻结时被阻断；仅因实现与真实 outage witness 尚未产生，不阻断合同级 F0。receipt signer
暂不可用时允许先执行
本地围栏并写双人签名的追加式 LocalSafetyEvidence，但只返回 `effect_unknown /
receipt_pending`；恢复后由 target owner 根据原 command/challenge 与追加式 witness 签发
canonical receipt，独立 HSM signer 只签 payload digest，独立 verifier 只验证且不得生成或
补写 owner receipt。

EmergencyActorAdmission 必须是 domain-separated typed immutable 凭证，而不是 TTL 内可复用
的强认证会话：它绑定 `SAFETY_PREPARE | SAFETY_COMMIT | POLICY_PUBLICATION` 的精确
subject ref+digest、一次性 nonce、actor/scope/epoch/assurance/channel/audience/purpose。
唯一 Safety Admission Coordinator 在自己的事务中将两份 admission + subject nonce
CAS-on-NULL，并签发 immutable `SafetyAuthorizationReservationV1`；Safety Survival、target
owner、Policy owner 随后只在各自本地事务消费 Reservation，不伪装跨 owner 原子提交。崩溃时
保持 consumed+reserved 并对账；ChallengeState 全链只由 Coordinator 写。commit 的 owner-local
anchor 是 immutable `SafetyCommitAttemptV1`，最终 receipt/unknown 后续追加引用它；不同 phase
或 subject 永不复用。
Reservation digest 不证明 CAS provenance；下游首次 anchor 前必须从 Coordinator 权威 Store
resolve 三条 consumption，验证 workload attestation、全部 gate `is True`、status ACTIVE，并
在 owner-local commit 内消费独立 `SafetyTrustedTimeAttestationV1 ref+digest`、按保守 UTC
upper bound 检查 TTL，并以 transaction nonce/commit subject-bound CommitLease 和受信
monotonic elapsed 的 owner-store 线性化 FreshnessProof CAS consumer checkpoint；epoch
transition 必须是具名、continuity-root 签名且 Genesis/counter 初值连续。回拨、gap、偏差、
陈旧 lease、超 elapsed budget、source/key/revocation outage 或 Unknown 均拒绝。Policy
Fence 的 ALIAS_COMMIT/SIGN_PRE/SIGN_POST witness 必须冻结 exact
TimeAttestation/CommitLease/FreshnessProof/Checkpoint。过期前未形成 anchor 不得启动 effect；outbox enqueue 与
`SafetyCommitDispatchClaimV1` 都不算 send。唯一 egress boundary 必须在第一 mutating send
primitive 前重验 attested time/deadline、CAS 消费一次性
`SafetyProviderMutationCapabilityV1` 并创建 `SafetyProviderCallAttemptV1`；缺 verified
`SafetyProviderSendReceiptV1` 一律 effect unknown + DO_NOT_REPLAY，只能原键查询。
仅携带 subject ref/digest 不足以授权生成对象：PrepareSubject↔PreparedCommand、
Challenge↔CommitAttempt、PublicationChallenge↔PublicationReceipt 必须从实际重复字段各自
重算同一个 domain-separated projection digest，并在消费前逐字相等。

该通道不得创建需求、对外导出证据、恢复业务权限、签发路线图、批准能力、合并代码或正常管理
项目，因此不构成第二个日常中枢。

### 8. 迁移与当前合同

现有 `feishu-assistant` 的项目、决策、风险、行动项、Bitable 和本地 SQLite 数据先视为历史协作来源或候选记录。未取得具名确认和 owner receipt 的行，不自动获得正式治理效力。

当前仓库的 GitHub Issue 工作流仍保持有效，直到 Feishu Hub 的 ActorBinding、typed intent、receipt、reconciliation、classification 和迁移验收全部通过，并另有明确实施及切换决定。本文不修改 `AGENTS.md`、生产 Schema、公开 Interface、任务状态机或现行 Issue 流程。

## 对既有 ADR 的影响（仅外网研发域）

- 保留 ADR-0049、0050、0051、0053～0058 的控制内核、交付、人签、试点、知识和 Bench 决定；
- 调整 ADR-0052：外网研发工作台继续是专业 Surface，但外网研发组织默认入口改为飞书研发空间；
- 调整 ADR-0059：外网研发共建地图投影进入飞书研发空间，仍是证据派生视图；
- 调整 ADR-0060/0061：外网研发需求提交、策展和评审的日常人机 Surface 可为飞书；事实、签发和 GitHub 交付边界不变；
- 内网入口与治理不受本节调整，全部以 ADR-0063 为准；任何冲突不得据此削弱安全或事实所有权。

## 后果

### 正面

- 用户只学习一个组织入口，管理、治理、会议、知识和 Agent 使用处于同一上下文；
- FLAi 与 GitHub 复杂度隐藏在窄 Interface 和 Adapter 后，获得更高 Leverage；
- 飞书 SDK、Bitable schema、GitHub 字段和 FLAi 内核变化集中在相应 Adapter，保持 Locality；
- 可以在飞书中完成适合内嵌的治理仪式，并从同一工作收件箱进入 GitHub/FLAi 专业 Surface，
  同时用 owner receipt 保留人签、版本和审计真实性；
- Secret 不再散落在项目配置中。

### 代价

- 需要建设真正的 Hub Gateway、ActorBinding、typed intent、receipt verifier、outbox、reconciliation 和 classification projection，不能只依靠 Bitable 自动化；
- 投影最终一致，必须显式显示 freshness、unknown 和 source gap；
- 飞书会成为日常协作单点，需验证可用性和安全生存通道；
- 飞书身份是否满足组织正式电子签发要求，需要组织政策和身份责任域具名评审；
- 高密级内容能否存入飞书取决于租户的正式数据承载批准。

## 明确拒绝

- 把所有权威事实复制到多维表格；
- 通过拖动卡片或改单元格改变运行、评测、签发、发布或审计状态；
- 让机器人、Codex、Kimi-K3 或其他 AI 自动批准、合并、签发或发布；
- 让 Feishu Adapter 直接写 FLAi 数据库；
- 双向同步时按时间戳“最后写入者获胜”；
- 飞书不可用时阻断强停或撤权；
- 在代码、文档、环境变量或卡片中恢复长期 Secret value；
- 用本 ADR 直接授权生产接入、Schema 迁移、飞书外部写入或试点开放。

## 验证与后续门

F0 只冻结以下设计合同、威胁模型、invalid-first fixture/drill 规格、责任人与后续 witness
分配；不要求尚未实现的 Runtime 先产出 outage/rotation/restore 等真实 witness：

1. ActorBinding 与 channel attestation；
2. Source Ownership Registry；
3. typed intent schema；
4. prepare/commit challenge；
5. classification projection；
6. owner receipt verification；
7. idempotency、`effect_unknown` 与 reconciliation；
8. projection freshness 和 source event gap；
9. `SecretProviderPort` 与 `secrets-stackdocker` Adapter 合同；
10. Feishu outage 下的 kill/revoke 安全生存演练规格；
11. 独立 Safety Identity / PKI / HSM 的 signing material 生命周期、signer/verifier
    职责分离、key epoch/轮换/吊销、trust anchor 分发/回滚、固定 canonical
    payload/domain separator、两个不同真人以精确 subject-bound admission 签发的 append-only
    Issuance/Verification Policy Head version + content-addressed PointerRevision + CAS current
    alias（genesis/null 与 generation/predecessor/role/owner/bundle/receipt 严格连续，历史
    revision 在线可解析）、
    Prepared/Challenge/Receipt/SigningRequest/Envelope/signer 的 exact Issuance Head+Bundle
    绑定、verifier/factory/result/head 的 exact Verification Head+Bundle 绑定、signer
    anti-oracle、Fence Authority 对 current alias 的单写 CAS 在自身事务严格推进单调
    fence epoch 并形成
    ALIAS_COMMIT witness、HSM 前后从同一 Fence Authority 取得且 Envelope 绑定的
    SIGN_PRE/SIGN_POST witness、具名签名的 Trusted-Time EpochTransition、transaction-bound
    CommitLease、受信 monotonic elapsed 的 store-linearization FreshnessProof/checkpoint，
    且 ALIAS_COMMIT/PRE/POST 冻结 exact time/lease/proof/checkpoint、唯一 egress
    DispatchClaim→一次性 MutationCapability→ProviderCallAttempt/SendReceipt 边界、旧 issuance bundle 的显式
    acceptance/吊销判定、verification/result stable key、
    verifier-owned SafetyResultFactory、同 verification bundle freshness 到期的 read-derived
    amber、新 verification bundle reverify、独立 result-chain Head generation+digest CAS、
    pending→confirmed 追加式对账与 Secret 栈 outage 验签演练规格；
12. 现有 Bitable/TeamLedger 历史数据分类迁移合同；
13. tenant/app 权限丢失、RTO/RPO、backlog/replay、projection rebuild、records
    retention/export、offboarding/vendor-exit 的连续性与退出演练规格；
14. collaboration project 到 FLAi authorized project scope 的单向版本化映射；
15. DeveloperAssistant dispatch/pause/resume/cancel/reconcile/handoff/rework/accept 的全生命
    周期 runtime/control receipt 合同、GitHub 原生 review/merge 与人类集成决定；
16. 组织身份、密级和正式签发的具名评审；
17. `F0ReviewManifestV1`：frozen Git commit/tree、`CONTEXT.md`、ADR-0047～0062、V0.2
    README/00～17/handoff 的逐文件 hash、生成主体/工具与 review/generation-receipt/seal
    schema；manifest-generation receipt 必须经外部信任验证，七域 review core+seal 必须绑定
    同一 manifest/generation receipt，任何 normative 变更使旧 review stale。

真实 witness 分段后置：F1 验只读权限、backlog/replay/rebuild；F2 验低风险 intent；
F3 验正式治理 challenge/receipt；D6/D7/D8 + F4 验执行、kill/revoke、Audit/WORM、
Secret/Safety PKI/HSM outage/rotation/restore；F5 验历史迁移与 records/vendor-exit。
F0 关闭既不证明这些 witness 存在，也不自动授权 F1。

详细设计见
[17_Feishu_Organizational_Hub.md](../product/FLAi-OS_V0.2_Design_Package/17_Feishu_Organizational_Hub.md)。

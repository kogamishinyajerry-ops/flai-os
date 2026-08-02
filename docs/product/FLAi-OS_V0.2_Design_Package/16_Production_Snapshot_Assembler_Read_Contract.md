# 16｜Production Snapshot Assembler 只读设计合同

> 合同标识：`flai.production-snapshot-assembler.read.v1`
>
> 合同评审状态：`FROZEN-FOR-REVIEW`
>
> 实现状态：`ACCEPTED-NOT-IMPLEMENTED`
>
> 实施门：`CLOSED`（须完成本文件第 13 节评审并取得具名批准后另开实施切片）
>
> 生产 Schema / API / 状态机变更：**无**
>
> 正式内网生产部署结论：**NO-GO**
>
> 部署域与 Workspace 集成约束：[ADR-0063](../../adr/ADR-0063-external-development-airgap-internal-workspace.md)。外网飞书研发协作受 [ADR-0062](../../adr/ADR-0062-feishu-single-organizational-hub.md) 约束，但不能成为内网 Assembler 的远程 ingress；这些约束不改变本合同的公开 Interface、失败语义或冻结状态。

## 1. 冻结范围与法律效力边界

本文件只冻结 Production Snapshot Assembler 的**只读设计合同**，供架构、身份授权、安全密码、数据存储与工作台评审。它不创建数据库表、不增加 API、不改变现有任务状态机、不导入密码库、不接通真实 ExecutionBroker，也不授权任何代码进入生产。

本次冻结回答七个问题：

1. 谁可以通过什么受信通道请求快照；
2. 对 task、event、ExecutionRun、Artifact 与 Knowledge evidence 如何执行 ACL 与 classification；
3. 哪些事实必须位于同一一致性读取边界；
4. WitnessResolver 如何把 backend receipt、Sandbox witness 与执行阶段证据解析为 `REAL / MOCK / TEST`；
5. receipt 验签到底证明什么、验证哪些绑定；
6. `factSetDigest` 覆盖哪些事实、如何得到稳定字节；
7. 任何缺失、冲突、漂移或不可验证如何用稳定失败码 fail-closed。

`FROZEN-FOR-REVIEW` 只表示评审候选内容在本轮不再随实现便利任意漂移，不代表已通过组织评审。设计会话、AI 评审或测试绿灯都不能代替具名责任人的正式签发。

## 2. Module、公开 Interface 与结果语义

### 2.1 Module 责任

`ProductionSnapshotAssembler` 是 Control Kernel 内部的深 Module。它负责：

- 接受由受信认证边界铸造的不可伪造读取上下文；
- 对精确 task revision 与 execution epoch 做对象授权；
- 在一致性读取边界内收集最小观察事实；
- 验证 persisted classification，不在 read 时重派生历史分级；
- 通过内部 WitnessResolver 验证执行现实和 receipt；
- 生成稳定的 canonical fact set 与 `factSetDigest`；
- 输出既有 Stage C Runtime Observer Adapter 可消费的只读 bundle。

它不负责：

- 规划、执行、取消、恢复或重试任务；
- 写 task、event、ExecutionRun、Artifact、Knowledge 或 audit 状态；
- 代替 Identity / Authorization / Supply-chain owner；
- 把 Agent 日志、模型自由文本或 Adapter 自报转换成权威事实；
- 生成人签、工程结论、业务通过或交付成功；
- 创建第二套任务状态机或第二控制面。

### 2.2 唯一公开调用面

```text
assembleSnapshot(
  authenticatedReadContext,
  selector
) -> READY | DIAGNOSTIC_ONLY | REJECTED
```

`authenticatedReadContext` 必须是由第 3 节受信通道铸造的 opaque capability，不是 JSON body、HTTP header、用户名字符串或调用方可自行构造的普通字典。

`selector` 的字段冻结为：

```text
selector {
  taskId,
  taskRevision,
  executionEpoch,
  purpose = "runtime-observer",
  observerContractVersion = "flai.stage-c.observer.v2",
  adapterContractVersion = "flai.stage-c.runtime-observer-adapter.v3"
}
```

调用者不得在 `selector` 中提交或覆盖：

- `actor_id`、role、ACL 结果或 clearance；
- `source="control-kernel"`；
- `reality=REAL|MOCK|TEST`；
- backend、Adapter、witness、receipt 或签名验证结果；
- `capturedAt`、event offset、fact digest 或 classification。

这些字段都只能由 Assembler 的受信内部依赖解析。

### 2.3 三种结果

```text
READY {
  releaseMode = "observer-ready",
  bundle,
  assemblyMetadata
}

DIAGNOSTIC_ONLY {
  releaseMode = "diagnostic-only",
  bundle,
  assemblyMetadata,
  internalFailure
}

REJECTED {
  releaseMode = "none",
  internalFailure
}
```

`assemblyMetadata` 是 Control Kernel 内部的释放证据，不传给 Observer Adapter 或普通 UI：

```text
assemblyMetadata {
  contractId = "flai.production-snapshot-assembler.read.v1",
  authorizationDecisionRef,
  authorizationEpoch,
  currentVerificationPolicyEpoch,
  currentVerificationPolicyDigest,
  effectiveClassification,
  readBoundaryKind = "sqlite-read-transaction",
  strictValidatorVersion,
  adapterConformanceReceiptDigest,
  factSetDigest,
  assembledAt
}
```

它不包含 display name、session token、凭据、对象标题、路径、原始 receipt 或签名字节。其 retention、audit sink 与对用户可见投影不在本合同内；默认不得向浏览器透传。

约束如下：

- `READY`：主体、对象授权、classification、一致性读取、ExecutionRun、witness、receipt 与 digest 全部明确通过；bundle 才可进入 Observer Adapter。
- `DIAGNOSTIC_ONLY`：只允许表达“当前生产事实不足以形成可信活动观察”。它必须已经通过认证、对象授权、classification 与一致性读取；`executionRun.availability` 固定为 `partial`，传入 Adapter 后必须得到零 observer event。不得把安全拒绝、receipt 失败或事实冲突降级成诊断态。
- `REJECTED`：不返回 bundle、事实列表、对象存在性、classification、witness 内容或受限引用。

现有生产形状只有 `Task + task_events + ToolRun + files metadata + knowledge_search provenance`，既没有统一 ExecutionRun、单调 observation revision、可信 backend/Sandbox receipt 或真实 heartbeat，也没有可供本合同解析的权威 `taskRevision / executionEpoch`。因此：

- **按当前原样生产事实**，Assembler 不能满足精确 selector，必须以 `TASK_BINDING_UNAVAILABLE` 返回 `REJECTED`；
- 只有未来由另一个已批准、受信且不可变的 binding source 提供精确 `taskRevision / executionEpoch` 后，遗留事实才可能以 `executionRun.availability=partial` 返回 `DIAGNOSTIC_ONLY`；
- 在统一 ExecutionRun、receipt 与 witness 缺口闭合前，任何路径都不得返回 `READY + REAL`。

### 2.4 与既有纯函数 Adapter 的边界

`READY.bundle` 和 `DIAGNOSTIC_ONLY.bundle` 的 **Assembler → Adapter 内部公开形状**保持如下；它不是浏览器或普通 API 的响应：

```text
{
  binding,
  readSnapshot,
  taskEvents,
  executionRun,
  artifacts,
  knowledgeEvidence
}
```

随后仍调用：

```text
adaptRuntimeFactsToObserver(bundle)
  -> { observerEvents, diagnostics }
```

Assembler 是 I/O、安全与完整性边界；Adapter 仍是无 I/O 的纯函数投影。Adapter 不验签、不连数据库、不访问网络，也不通过检查 `source="control-kernel"` 字符串认证调用者。

## 3. 认证通道合同

### 3.1 允许的通道与两条认证状态机

Assembler **只接受同进程、不可序列化的 `AuthenticatedReadContext`**。允许形成该 capability 的入口有两条，但远程 envelope 永远不是 Assembler 入参。

**Local state machine**

```text
server-side session / trusted scheduler identity
  -> Identity owner verifies actor, subject, workload and credential epoch
  -> Delegation owner resolves on-behalf-of scope
  -> registered local minting boundary creates opaque capability
  -> Assembler validates mint provenance and expiry
```

**Remote state machine**

```text
mTLS workload channel
  -> dedicated Kernel ingress verifies protected envelope signature
  -> verifies audience + purpose + expiry + channel binding
  -> atomically consumes nonce in ingress anti-replay store
  -> validates end-user subject + calling workload + on-behalf-of delegation
  -> records immutable remote-auth admission ref
  -> registered local minting boundary creates new opaque capability
  -> Assembler receives only that local capability
```

远程 envelope 验签、nonce 消费和 admission 写入属于 ingress 认证边界，不属于只读 Assembler。任何一步失败都不得铸造 capability；Assembler 绝不接受“已验签”布尔值、原始 envelope 或调用方构造的 context。

浏览器、Agent Runtime、OpenClaw/OpenHands、Tool Adapter、Sandbox Provider 和普通内部 HTTP client 都不得直接铸造上下文或调用 WitnessResolver。

### 3.2 AuthenticatedReadContext 的最小语义

opaque context 内部至少绑定：

```text
authenticatedReadContext {
  actorId,
  subjectId,
  identityProvider,
  callingWorkloadId,
  onBehalfOfDelegationRef,
  delegationScopeDigest,
  sessionRef,
  authenticatedAt,
  credentialEpoch,
  authAdmissionRef,
  channelKind,
  channelBindingDigest,
  audience = "production-snapshot-assembler",
  purpose = "runtime-observer",
  issuedAt,
  expiresAt,
  nonce
}
```

字段语义冻结为：

- `actorId`：对本次读取承担责任的稳定真人或受控服务主体 ID；
- `subjectId`：Identity Provider 中被认证的稳定 subject；
- `callingWorkloadId`：实际调用 Kernel 的 workload / process identity；
- `onBehalfOfDelegationRef + delegationScopeDigest`：workload 代表 end-user 调用时的不可变委托证据；不存在委托时必须采用该 channel kind 的严格显式 sentinel，不得省略后猜测；
- `authAdmissionRef`：local mint record，或 remote ingress 已验签并消费 nonce 后的 admission evidence ref。

最终授权是 `subject/actor 权限 ∩ calling workload 权限 ∩ delegation scope ∩ session policy` 的合取，任何一项未知或缺失都拒绝。workload 身份不能借用户权限扩权，用户身份也不能借高权限 workload 扩权。

这些字段是 Identity / Delegation owner 的解析结果，不接受前端同名字段覆盖。`display_name` 只用于展示，不能参与授权键、摘要或资源归属。

### 3.3 必须 fail-closed 的通道检查

Assembler 在读取任何 task、event、Artifact 或 Knowledge 引用前必须逐项确认：

- context 由注册的 minting boundary 产生；
- actor、subject、workload 与 on-behalf-of delegation 关系完整且一致；
- workload / process identity 与允许调用方匹配；
- audience 与 purpose 精确匹配；
- local opaque capability 的 mint provenance、channel binding 与 expiry 仍有效；
- remote channel 必须已有已验签、已消费 nonce 且绑定当前 channel 的 `authAdmissionRef`；
- session 未过期，actor 仍 active；
- `credentialEpoch` 与 Identity owner 当前值一致；
- context 没有被序列化后从普通业务入参重放。

`binding.source="control-kernel"`、内网 IP、localhost、管理员用户名、HTTP 200 或“已登录”布尔值均不构成通道认证。

### 3.4 当前实现缺口

现有 AuthGateMiddleware 已经在服务端校验会话，并把解析后的用户写入 `request.state.user`；这是正确方向。但当前投影不足以证明：

- 哪个精确 session / channel 铸造了读取上下文；
- actor credential epoch；
- audience / purpose / nonce；
- 对象级授权与撤权 epoch。

因此生产实现不能直接把 `request.state.user` 普通 dict 当成 V1 opaque context。评审必须先决定内部 context carrier 和 owner seam；本文件不预建生产 Schema。

### 3.5 审计边界

Assembler 本身不写业务 DB 或 audit outbox。它返回最小的 `auditClass + correlationId + failureCode`，由 Control Kernel composition root 按现行审计策略记录读取、拒绝和完整性失败。日志不得包含受限对象标题、路径、正文、receipt payload、签名或密级细节。

审计写入失败如何影响只读服务由 Audit Policy 决定，不能由 Assembler 临时放宽。无论审计策略如何，审计失败都不允许把 `REJECTED` 改成 `DIAGNOSTIC_ONLY` 或 `READY`。

### 3.6 分域 Workspace Hub ingress 约束

`ACCEPTED-NOT-IMPLEMENTED` 当前部署域的 FLAi Workspace 可以成为观察结果的唯一日常人机 Surface，但它只能复用第 3.1 节既有 remote state machine，不形成第三条认证状态机。内网生产域只能接受内部 IdP 与内部 Hub workload 铸造的通道：

```text
verified current-zone Workspace event / app login
  -> current-zone ingress verifies issuer + app + channel + time window + replay
  -> current-zone Identity owner maps issuer/app/subject to versioned ActorBinding
  -> Hub workload uses mTLS to dedicated Kernel ingress
  -> protected remote envelope binds actor + workload + delegation + audience + purpose + nonce
  -> Kernel ingress verifies, consumes nonce and mints local opaque AuthenticatedReadContext
  -> Assembler receives only the local capability
```

约束：

- 外部或内部平台 subject id、display name、群管理员身份、卡片参数和协作表字段都不能作为 `authenticatedReadContext`、`selector` 或授权结果；
- Workspace user/app token 只用于当前域 Adapter 的最小平台调用，不能直接调用 Assembler；Hub workload identity 与 end-user delegation 必须同时成立；
- Workspace 事件已验签不等于 ActorBinding、对象 ACL、classification 或观察授权已经通过；
- 外网 Feishu token、event、ActorBinding、workload identity、mTLS 证书或 envelope 在内网一律无效；不得建立跨 AirGap RPC、身份代理或 token bridge；
- Hub 不得把 `source="control-kernel"`、`REAL`、backend、receipt validity 或 fact digest 写入 envelope 让 Assembler 信任；
- Assembler 返回后，当前域 Projection Module 还必须按目标 chat/space audience 和 classification ceiling 做第二次最小披露；目标不允许或 unknown 时抑制正文；
- source freshness、event gap、`DIAGNOSTIC_ONLY`、`REJECTED` 和公共 failure mapping 必须原样保留，Workspace 卡片不得沿用旧绿或根据 Agent 文案补状态；
- 当前域 Workspace 不可用只影响投影与新的正常管理动作，不影响 Kernel 执行、kill/revoke 安全生存通道或来源事实。

本节只冻结 remote ingress 的调用约束，不添加平台专用 selector、Schema、数据库列或失败码。任何实现仍须通过本合同第 13 节七域具名评审；外网 Feishu Adapter 另获 ADR-0062 F1/F4 授权，内网 Workspace Adapter 与断网 witness 另获 ADR-0063 A1～A5 授权。

## 4. ACL、classification 与最小披露

### 4.1 唯一授权 seam

Assembler 只依赖统一 Authorization Module：

```text
authorize(
  authenticatedPrincipalSet {
    actor,
    subject,
    callingWorkload,
    delegationScope
  },
  action = "read_observation_snapshot",
  resourceEnvelope,
  requestContext,
  policyVersion
) -> AuthorizationDecision {
  effect = deny | auto_execute,
  decisionRef,
  authorizationEpoch,
  evaluatedPolicyVersion,
  resourceEnvelopeVersion,
  principalSetDigest
}
```

读取观察快照不存在 `defer_to_delivery`：这不是待交付副作用。任何 `deny`、`unknown`、超时、缺 predicate 或策略版本不可解析都必须拒绝。

`decisionRef` 必须是 Authorization Module 对 `principalSetDigest + action + resourceEnvelopeVersion + evaluatedPolicyVersion + authorizationEpoch + effect` 生成的确定性不可变内容摘要，不是随机 request id。第一次授权时冻结完整 decision；release fence 以同一精确输入重新评估并比较 `effect + decisionRef + authorizationEpoch + resourceEnvelopeVersion`。Authorization Module 不能生成或重放该 ref 时，使用相应 unavailable code，不得由 Assembler 自行哈希一个“通过”结果。

Assembler 不新增 `is_admin`、项目 owner、部门或“内网用户”快捷分支。当前只有认证、没有统一对象授权的路径不能宣称满足本合同。

### 4.2 授权顺序

读取顺序冻结为：

1. 验证受信认证通道；
2. 通过 `actor/subject ∩ calling workload ∩ delegation` scope 的查询解析 task ResourceEnvelope；先做 scope 限定，不能先按裸 ID 读出对象再判断；
3. 授权 task 的 `read_observation_snapshot`；
4. 读取 task 已持久化的 `data_classification`，绝不在 read 时根据当前 Tool/Knowledge registry 重派生；
5. 通过已经授权的 task membership 与 actor/workload/delegation scope **同时约束** event、ExecutionRun、Artifact、Knowledge evidence 和 receipt metadata 查询；scope predicate 必须在 SQL / repository 的过滤、计数与排序之前生效，不能先枚举全部子对象再在内存裁剪；
6. 在读取任何可保护内容或回源字节前，逐对象执行 ACL 与 classification gate；
7. 聚合 effective classification；
8. 在返回前执行第 5.5 节 authorization release fence。

### 4.3 classification 规则

V1 不创建新的组织密级枚举，也不要求为了读取合同给每张现有表补一列。它沿用当前可执法的：

```text
internal < sensitive
```

并遵守：

- task 分级读取 CAS-on-NULL 后的持久值；
- `task_events` 当前物理行没有独立 classification；只有在 `task_id`、event membership 与 payload 白名单都明确绑定到该 task，且 payload 不携带跨资源内容时，投影才可继承 task 的持久 classification；
- ExecutionRun 与 task-scoped receipt metadata 可以按同样的、由 ResourceEnvelope owner 批准的继承规则取得 task classification，但 receipt 所引用的 backend、Sandbox、Artifact 或 Knowledge 资源仍须独立解析；
- Artifact、Knowledge source / version、跨资源引用或任何已有自身 classification 的对象必须保留自身分级；其分级高于 task 时只能抬高 effective classification，不能被 task 标签覆盖；
- “子表没有 classification 列”不等于未知；只有命中上述明确继承规则才可继承。无法证明继承条件、对象分级缺失、未知、低于已知父级或无法映射时，整体 `CLASSIFICATION_UNRESOLVED`；
- `effectiveClassification` 取所有成员的最高值；
- actor clearance 或对象 predicate 不能明确覆盖 effective classification 时拒绝；
- digest、文件名、计数、event type 和“是否存在”本身也属于受控 metadata，不能假设天然无密级；
- redaction 不是 authorization。Assembler 不以“把正文设 null”替代对象授权。

### 4.4 不做按权限裁剪的“半快照”

同一个 selector 对应一个精确 fact membership。若任何必需成员不可读，Assembler 不静默删除该成员后重新计算看似完整的摘要，而是整体拒绝。

这条规则阻止：

- 通过列表长度、排序空洞或缺失 Artifact 推断受限对象；
- task event 引用一组 Knowledge citation，而返回 bundle 偷换成另一组；
- 对同一 task 给不同角色拼出语义不同却共用一个 execution observation 的快照；
- 用 redacted payload 继续点亮“正在工作”动画。

### 4.5 存在性保护

外部安全响应中，以下情形统一映射为 `SNAPSHOT_NOT_VISIBLE`：

- task 不存在；
- task 存在但 actor 无权读取；
- task 可见但 selector 指向不可见的 revision / execution epoch；
- 必需子对象不可见。

内部审计可以在授权范围内保留真实原因，但 UI、API 状态码和 timing budget 不得成为稳定存在性 oracle。不存在、无权与子对象不可见必须采用同一公共响应形状和受控 timing bucket；禁止在授权前执行对象特异的大文件读取、验签或回源，从而泄露稳定时间差。

### 4.6 内容最小化

Assembler 只装配 Observer Adapter 实际需要的结构化事实：

- task event 不输出 `message` 或原始自由文本；只输出 event id、ordinal、event type、level、created_at、必要 agent id，以及事件类型白名单允许的结构化 payload；
- Artifact 不输出 path、uploaded_by、宿主 workspace 或正文；
- Knowledge evidence 只输出 `scope_id + chunk_id + source + fingerprint`，不回源正文；
- receipt 只通过受验证的 digest ref 与归一化 witness 进入 bundle，不向前端输出签名、证书或 SecretRef；
- 不保存或展示内部思维链。

## 5. 一致性读取边界

### 5.1 V1 支持范围

V1 的业务事实边界只支持：

- 一个本地 SQLite Control Kernel fact store；
- 由该快照内精确 digest 引用的 content-addressed immutable receipt / witness / ReceiptAdmissionCore / ReceiptAdmissionSeal blob；
- 不访问 live Agent Runtime、live Broker、live Sandbox 或当前 Knowledge index 来补事实。

如果 task、ExecutionRun、ACL/classification、Artifact metadata 或 Knowledge evidence 需要从多个不能提供同源 snapshot token 的活态 store 拼接，返回 `MULTI_STORE_SNAPSHOT_UNSUPPORTED`。不得用“依次请求很快”冒充一致性。

### 5.2 SQLite ReadUnitOfWork

生产实现必须使用专用只读连接：

```text
PRAGMA query_only = ON
BEGIN
  -- 第一次受控 SELECT 建立 WAL read snapshot
  -- 以下业务事实全部从同一 connection / transaction 读取
COMMIT
```

不使用 `BEGIN IMMEDIATE` 长时间阻塞 writer，不在事务中调用模型、工具、网络、Broker 或大文件哈希。任何意外写语句必须由 `query_only` 直接失败。

### 5.3 同一事务内必须读取的事实

按顺序读取：

1. session / actor live state 与 credential epoch 的可用重检事实；
2. task ResourceEnvelope、task status、持久 classification、`taskRevision`、`executionEpoch`；
3. 统一 ExecutionRun 的当前 observation 与 backend / witness / receipt refs；
4. `task_events` 的稳定写入序窗口；
5. task output Artifact metadata；
6. 窗口内 `knowledge_search` 的四钥 evidence；
7. 适用 AuthorizationDecision 的 `decisionRef / authorizationEpoch / evaluatedPolicyVersion / principalSetDigest / resourceEnvelopeVersion`、execution-bound historical trust-policy ref 与 current verification-policy epoch/digest；
8. 参与 receipt、ReceiptAdmissionCore、ReceiptAdmissionSeal 验证和 fact digest 的所有 immutable ref。

任何 `taskRevision`、`executionEpoch` 或统一 ExecutionRun 的权威来源缺失，都不能根据 task id、status、时间戳、ToolRun 或前端轮询次数猜测。

### 5.4 有界窗口与稳定顺序

V1 边界与既有 Adapter 上限对齐：

| 集合 | 上限 | 顺序 |
|---|---:|---|
| task events | 2,000 | SQLite `task_events.id ASC`；内部 SQLite id 永不暴露，`event_id` 是 Adapter item 身份；`ordinal` 只进入 FactSet，由 Adapter 以 `offset + array index` 推导，不作为 item 字段 |
| Artifacts | 100 | task `output_file_ids` 的持久顺序 |
| knowledge evidence events | 20 | 对应 task event ordinal |
| citations / knowledge event | 20 | event payload 中的持久顺序 |
| 总 knowledge refs | 400 | event ordinal，再按 citation 持久顺序 |
| witness evidence refs | 20 | receipt assertion 的 canonical 顺序 |

event window 固定取事务快照内最后 2,000 条：

```text
offset = max(0, totalEventCount - 2000)
ordinal = offset + rowIndex
```

必须同时读取 `totalEventCount` 和该窗口。只有 `executionRun.availability=verified` 时才要求其 `current_event_id` 位于窗口内；`partial` 没有权威 current event，不得伪造该字段，也不执行此检查。重复 event id、同 id 不同内容、计数/窗口不一致，或 verified current event 落在窗口外都拒绝，不静默截断。

### 5.5 读取、外部验签与 release fence

完整顺序为：

1. 在一个 SQLite read transaction 冻结第 5.3 节事实；
2. 关闭 read transaction；
3. 按事务中冻结的 exact digest ref，读取并验证小型 content-addressed receipt / witness / admission core / admission seal envelope；
4. 用新的短只读事务，以第一次冻结的 exact principal set、action、resource identity 与 policy selector 重新评估 AuthorizationDecision，并重检 actor/session live state、credential epoch、**current verification-policy epoch/digest**；
5. 按固定短路优先级比较并丢弃全部事实：① actor/session active state 或 credential epoch 变化 → `AUTHENTICATION_FENCE_CHANGED`；② **先单独比较 ResourceEnvelope version**，变化 → `RESOURCE_FENCE_CHANGED`，不再把因此派生的 decisionRef 变化另报为授权码；③ resource version 相同，但 authorization effect / epoch / evaluated policy / principal set / decisionRef 变化 → `AUTHORIZATION_FENCE_CHANGED`；④前三项相同但 current verification-policy epoch/digest 变化 → `VERIFICATION_POLICY_CHANGED`；
6. 只有 fence 通过后，才 canonicalize、计算 digest 并释放 bundle。

第二次事务不是重新选择业务事实，也不能把“新 task status + 旧 events”混入快照；它只做 release-time 收紧。它比较的是第一次读取时有效的 current verification policy 与释放时的 current verification policy，**不要求当前策略 digest 等于 receipt 在执行时绑定的 historical trust-policy digest**。这样既保持业务 fact set 是一个 point-in-time snapshot，也阻止在 receipt 验证期间发生的撤权或验签安全基线变化被旧快照绕过。

### 5.6 时间边界

- `capturedAt` 由受信服务器时钟在第一次 read transaction 完成读取后、释放前生成；
- 任何 event、ExecutionRun observation、reality witness 或 Artifact `created_at` 晚于 `capturedAt`，返回 `FACT_TIME_INCONSISTENT`；
- 活动态 freshness 继续由带版本的 Observer freshness policy 判定，不写死在 Assembler；
- terminal receipt 是历史证据，不因“现在晚于任务结束时间”失效，但仍须满足第 7 节签名、密钥与签发时点规则。

### 5.7 当前事实到目标合同的诚实映射

| 当前事实 | 当前可证明 | V1 结论 |
|---|---|---|
| `task_events` | event id、类型、时间、按 SQLite id 的写入顺序 | 可进入一致性窗口；不能单独证明正在执行 |
| Task + ToolRun | 状态、局部工具轨迹 | 只能组成 `executionRun.availability=partial` |
| 内部 `files` 行 | task 关联、kind、SHA-256、classification | 授权后可投影 Artifact metadata；现有 output-files HTTP API 缺 SHA-256，不能作为 Assembler 来源 |
| `knowledge_search` event | scope 与 citation 四钥 | 只证明检索 provenance；不证明 KnowledgeVersion 权威、有效或适用 |
| 现有日志 / Adapter 自报 | 调试信息 | 不能成为 receipt 或 REAL witness |
| 统一 ExecutionRun / signed receipt | 当前未实现 | `READY + REAL` 保持关闭 |

## 6. WitnessResolver 内部合同

### 6.1 Internal seam

WitnessResolver 是 Assembler 的私有 seam，不暴露给 API 或前端：

```text
resolveWitness(
  executionBinding,
  backendBinding,
  captureBoundary,
  persistedReceiptBindings[] {
    receiptRef,
    admissionCoreRef,
    admissionSealRef
  },
  historicalTrustPolicySnapshot,
  currentVerificationPolicySnapshot
) -> RESOLVED | WITNESS_REJECTED
```

输入必须来自第 5 节冻结事实；resolver 不接受调用方附加的 free-text witness、环境变量、fixture label 或“已验证”布尔值。`historicalTrustPolicySnapshot` 必须与 receipt 内的 `trustPolicyEpoch / trustPolicyDigest` 精确匹配，用于解释签发时允许的 issuer、算法与绑定；`currentVerificationPolicySnapshot` 用于执行当前吊销、retrospective compromise、算法禁用和最低安全版本。任一策略缺失、不可验证或二者职责混用都拒绝。

### 6.2 输出

```text
RESOLVED {
  backend {
    backend_id,
    backend_kind = execution-broker | mock | test,
    adapter_id,
    adapter_version
  },
  reality_witness {
    witness_id,
    reality = REAL | MOCK | TEST,
    phase,
    verification = verified | declared,
    execution_id,
    execution_epoch,
    backend_id,
    observed_at,
    evidence_refs[]
  },
  verified_receipt_facts[] {
    receipt_type,
    receipt_id,
    envelope_digest,
    signed_content_digest,
    admission_core_digest,
    admission_seal_digest,
    issuer_id,
    key_id,
    key_fingerprint,
    historical_trust_policy_epoch,
    historical_trust_policy_digest
  }
}
```

Resolver 只归一化已验证事实，不创建新 receipt、不写状态、不补签、不决定 task 终态，也不把 `completed` 解释成真人签发或业务通过。

### 6.3 Reality 规则

| reality | backend_kind | verification | 必需基础证据 |
|---|---|---|---|
| `REAL` | `execution-broker` | `verified` | `backend-receipt` + 独立 `sandbox-witness` + 阶段 receipt |
| `MOCK` | `mock` | `declared` | 受信 Kernel mock issuer 的 `mock-seal` |
| `TEST` | `test` | `declared` | approved test harness 的 `test-fixture` |

`backend` 表示 ExecutionBroker 组合身份，不得把 AgentRuntimePort、SandboxProviderPort 或 ToolExecutionPort 中任一个 Adapter 冒充整个 backend。receipt 必须分别展开具体 Adapter 与 policy digest。

`REAL` 还必须满足跨 receipt 独立性不变量：

- `backend-receipt` 的 issuer kind / key usage 固定为 ExecutionBroker composite attestation，并绑定 composite backend identity；
- `sandbox-witness` 的 issuer kind / key usage 固定为 SandboxProvider attestation，并绑定精确 provider、Adapter、sandbox instance 与 `sandboxPolicyDigest`；
- 两者的 `issuer.workloadIdentity`、leaf `keyId`、由 Trust Policy 解析出的 leaf public-key / SPKI fingerprint 与 key usage 必须不同；同一密钥材料注册成两个 keyId 仍视为同一 leaf key，不得同时替 Broker 和 Sandbox 作证；
- 两者可以锚定同一个组织 trust root，但 Trust Policy 必须分别授权两个用途；
- Resolver 必须对两份 receipt 做 task/revision、execution/epoch、lease generation、backend binding 与时间的交叉一致性检查；
- phase receipt 不能替代上述任一独立证明。

任何 issuer 被过度授权为多种类型，都不能绕过该组合不变量。

### 6.4 状态与阶段

| ExecutionRun status | witness phase | REAL 阶段证据 |
|---|---|---|
| `created / queued` | `admission` | `admission-receipt` |
| `validating / running / parsing / analyzing` | `activity` | `running-witness` |
| `waiting_review` | `review-ready` | `collect-witness` |
| `completed` | `result` | `result-witness` |
| `failed` | `failure` | `failure-witness` |
| `cancelled` | `termination` | `termination-witness` |

不允许：

- 根据 status 自动生成 phase witness；
- 用 collect receipt 冒充 result receipt；
- cancelled 只有数据库状态、没有 termination witness 时显示“已停止”；
- MOCK / TEST 借用 `verified` 或 REAL receipt 前缀；
- 同一 execution epoch 在 reality 间切换；
- witness 的 execution id、epoch、backend、lease generation 或 observation time 不一致。

### 6.5 两个允许的实现 Adapter

- `ProductionWitnessResolver`：只从受信 ReceiptStore / TrustPolicyResolver 读取并验签；只有它可能返回 `REAL`。
- `DeterministicFixtureWitnessResolver`：只供单元与合成 E2E；输出固定为 `TEST`，或在明确 mock fixture 中输出 `MOCK`，永不返回 `REAL`。

这两个 Adapter 是真实的第二实现，不是为了抽象而抽象。Production composition root 禁止注入 fixture resolver。

## 7. Receipt envelope 与验签合同

### 7.1 Receipt 类型

V1 只接受：

```text
backend-receipt
sandbox-witness
admission-receipt
running-witness
collect-witness
result-witness
failure-witness
termination-witness
mock-seal
test-fixture
```

未知类型、拼写近似、大小写漂移或把日志 URL 当 receipt ref 均拒绝。

### 7.2 SignedReceiptV1

```text
SignedReceiptV1 {
  protectedHeader {
    envelopeVersion = "flai.execution-receipt-envelope.v1",
    algorithm,
    keyId,
    keyUsage
  },
  signedPayload {
    receiptVersion = "flai.execution-receipt.v1",
    receiptId,
    receiptType,
    issuer {
      issuerId,
      issuerKind,
      trustDomain,
      workloadIdentity
    },
    audience = "flai-control-kernel",
    subject {
      taskId,
      taskRevision,
      executionId,
      executionEpoch,
      backendId,
      backendKind,
      adapterId,
      adapterVersion,
      leaseId,
      leaseGeneration,
      attesterSubject {
        portKind,
        providerId,
        adapterId,
        adapterVersion,
        instanceId?
      }
    },
    bindings {
      canonicalTaskGraphDigest,
      grantDigest,
      policyDigest,
      epochSnapshotDigest,
      trustPolicyEpoch,
      trustPolicyDigest,
      sandboxPolicyDigest
    },
    assertion {
      reality,
      phase,
      observedAt,
      outcomeCode,
      resultDigest,
      targetDigest,
      evidenceRefs[]
    },
    validity {
      issuedAt,
      notBefore,
      validUntil,
      sequence,
      nonce
    }
  },
  signature {
    value
  }
}
```

`algorithm + keyId + keyUsage + envelopeVersion` 位于被签名的 protected header，验证器不接受 signature 对象或外层 transport 重新指定算法。Trust Policy 必须让 `keyId` 唯一解析到允许的算法族和用途；若调用方字段与 policy 解析不唯一，直接拒绝。

所有 digest 字段使用 `sha256:<64 lowercase hex>`。某 receipt 类型不适用的字段必须按该类型的严格 Schema **省略**，不能填空字符串、`unknown` 或 `null` 糊弄验证。实施时须为 protected header、各 receipt type payload 与 signature 建严格、`additionalProperties=false` 的独立 Schema；本轮不创建生产 Schema 文件。

### 7.3 签名字节

签名输入固定为：

```text
signedContent = {
  protectedHeader,
  signedPayload
}

canonicalSignedContent = RFC8785_JCS(signedContent)

UTF8("FLAI-EXECUTION-RECEIPT" + NUL + "v1" + NUL)
  || canonicalSignedContent

signedContentDigest =
  "sha256:" + lowercaseHex(
    SHA256(
      UTF8("FLAI-EXECUTION-RECEIPT-SIGNED-CONTENT" + NUL + "v1" + NUL)
      || canonicalSignedContent
    )
  )

envelopeDigest =
  "sha256:" + lowercaseHex(SHA256(exactPersistedEnvelopeBytes))
```

只有 `signature.value` 不进入被签字节。`envelopeDigest` 绑定 ReceiptStore 实际保存的 UTF-8 envelope bytes；`signedContentDigest` 绑定唯一 canonical protected header + payload，二者不得混用。解析器必须拒绝：

- duplicate JSON key；
- 非 UTF-8；
- `NaN / Infinity / -0` 等非合同数值；
- 未知字段、类型漂移或超限数组；
- 无法得到唯一 canonical bytes 的 payload。

实施 conformance suite 必须为 `canonicalSignedContent`、signature input、`signedContentDigest` 与 `envelopeDigest` 提供跨语言 golden vectors。

### 7.4 算法与密钥策略

本合同不替组织密码合规责任人选择 Ed25519、ECDSA、SM2 或 HSM 产品。它冻结的是：

- `algorithm` 必须明确出现在 receipt 精确绑定的 historical `trustPolicyDigest` allowlist，并且没有被 current verification policy 禁用；
- allowlist 缺失或为空就是拒绝，不回退“任意可验证算法”；
- `issuerId + issuerKind + workloadIdentity + receiptType + protectedHeader.keyId + keyUsage` 必须被 Trust Policy 授权；
- `keyFingerprint` 只能由 verifier 对 Trust Policy 解析出的 leaf public key / SPKI 计算为 `sha256:<64 lowercase hex>`，不接受 receipt 自报；
- historical policy 解释签发时的 key 用途、信任域与有效期；current verification policy 执行当前吊销、retrospective compromise 与最低安全版本；
- test key、developer key、fixture key 不得进入 REAL trust domain。

### 7.5 验签顺序

每个 receipt 严格按以下顺序：

1. 验证 content-addressed envelope bytes 与 persisted ref digest 一致；
2. 严格解析 receipt type Schema；
3. 生成唯一 canonical signed bytes；
4. 解析 receipt 绑定的 exact historical trust-policy epoch/digest；
5. 验证 issuer 对该 receipt type 的签发权限；
6. 验证算法 allowlist、key usage、key version 与 trust domain；
7. 验证数字签名；
8. 验证 issuer 自报 `issuedAt` 位于 key validity 与 receipt validity 范围，但不把该自报时间当成 receipt 已经存在的证明；
9. 验证第 7.6 节 ReceiptAdmissionCore + ReceiptAdmissionSeal、受信 `ingestedAt / ingestSequence` 与 anti-replay verdict；
10. 应用 current verification policy：受信 admission time 晚于 key 吊销/失效时点必拒；若当前策略标记 retrospective compromise、算法禁用或低于安全版本底线，历史 receipt 亦拒；
11. 验证 audience、task/revision、execution/epoch、backend/Adapter、lease generation 与所有 digest binding；
12. 验证 receipt phase 与 ExecutionRun status；
13. 验证同一 bundle 内 receipt id、nonce、sequence 没有冲突，并验证 ingest 已给出跨 execution anti-replay admission；
14. 验证 evidence ref 集合、result / target digest 与当前 fact set 引用一致。

任何一步不是明确 valid，整体拒绝。验签异常不能映射成 500 后继续组装。

### 7.6 Receipt admission core、store seal 与 replay 的只读边界

Assembler 不创建“已使用 nonce”写状态。每个生产 receipt 在被 ExecutionRun 引用前，必须由 ReceiptStore ingest 写路径原子生成两个不可变对象：

```text
ReceiptAdmissionCoreV1 {
  admissionVersion = "flai.receipt-admission-core.v1",
  receiptStoreId,
  receiptId,
  envelopeDigest,
  signedContentDigest,
  replayDomainDigest,
  sequence,
  nonceDigest,
  executionBindingDigest,
  verdict = "ADMITTED",
  ingestedAt,
  ingestSequence
}

ReceiptAdmissionSealV1 {
  protectedHeader {
    sealVersion = "flai.receipt-admission-seal.v1",
    algorithm,
    keyId,
    keyUsage = "receipt-store-admission"
  },
  signedPayload {
    receiptStoreId,
    admissionCoreDigest,
    ingestSequence,
    ingestedAt,
    previousAdmissionSealDigest = "GENESIS" | sha256-ref
  },
  signature {
    value
  }
}
```

core 先独立 canonicalize，再由 seal 覆盖；seal 字段绝不回进入 core digest：

```text
canonicalAdmissionCoreBytes = RFC8785_JCS(ReceiptAdmissionCoreV1)

admissionCoreDigest =
  SHA256_REF(
    UTF8("FLAI-RECEIPT-ADMISSION-CORE" + NUL + "v1" + NUL)
    || canonicalAdmissionCoreBytes
  )

canonicalAdmissionSealContent =
  RFC8785_JCS({
    protectedHeader,
    signedPayload
  })

admissionSealSignatureInput =
  UTF8("FLAI-RECEIPT-ADMISSION-SEAL" + NUL + "v1" + NUL)
  || canonicalAdmissionSealContent

admissionSealDigest =
  SHA256_REF(exactPersistedAdmissionSealEnvelopeBytes)
```

这样依赖方向固定为 `core -> admissionCoreDigest -> signed seal -> admissionSealDigest`，不存在 digest / seal 循环。golden vectors 必须覆盖四组 bytes / digest。

`ingestedAt` 来自 ReceiptStore 的受信时钟，`ingestSequence` 在 store 内单调；seal 中二者必须与 core 精确相等。issuer 自报 `issuedAt` 不能替代 signed store admission seal。

ReceiptAdmissionSeal 不能自证受信：ReceiptStore workload identity、protected algorithm/key、`receipt-store-admission` key usage 与 signature 必须由 current verification policy 验证。`previousAdmissionSealDigest` 提供 append-only 对账链；只存在一行可改数据库记录、普通应用日志、未签 core 或自报 `ingestedAt` 时，不构成历史存在性证明。

唯一域冻结为：

- `receiptId` 在整个 `trustDomain` 内唯一；
- `nonce` 在 `trustDomain + issuerId + receiptType` replay domain 内跨 execution 唯一；
- `sequence` 在同一 replay domain 内严格递增，允许有洞，不允许重复或回退；
- admission core 必须绑定精确 task revision、execution epoch、lease generation 与 canonical envelope digest。

三个 admission 子摘要使用固定字节：

```text
replayDomainDigest =
  SHA256_REF(
    "FLAI-RECEIPT-REPLAY-DOMAIN" + NUL + "v1" + NUL
    || JCS({trustDomain, issuerId, receiptType})
  )

nonceDigest =
  SHA256_REF(
    "FLAI-RECEIPT-NONCE" + NUL + "v1" + NUL
    || UTF8(nonce)
  )

executionBindingDigest =
  SHA256_REF(
    "FLAI-RECEIPT-EXECUTION-BINDING" + NUL + "v1" + NUL
    || JCS({
      taskId, taskRevision, executionId, executionEpoch,
      leaseId, leaseGeneration
    })
  )
```

其中 `SHA256_REF(bytes) = "sha256:" + lowercaseHex(SHA256(bytes))`；字符串前缀同样以 UTF-8 编码。golden vectors 必须覆盖三者。

ReceiptStore ingest 必须在一个权威写判定中完成唯一性检查、core 与 seal 落地及引用绑定；这不是 Assembler 的实现范围，也不授权本轮修改 Schema。只读 Resolver 只接受已绑定到精确 ExecutionRun 的 persisted receipt ref + admission core ref + admission seal ref，并验证：

- core、seal、receipt envelope 与 signed content digest 全部一致；
- seal 的 `admissionCoreDigest` 精确覆盖当前 core，core 不包含 seal 字段；
- seal signature、store workload、key usage 与 `previousAdmissionSealDigest` 形状有效；
- verdict 精确为 `ADMITTED`；
- `notBefore <= issuedAt <= ingestedAt <= validUntil`；
- key / issuer 在受信 `ingestedAt` 时仍有效；
- 活动态 receipt 还满足 `capturedAt <= validUntil`；terminal receipt 可在到期后读取，但必须在有效期内已被可信接收；
- 同 bundle 内 receipt id、nonce、sequence 无冲突；
- lease generation 与 execution binding 一致；
- 不通过重新拉 live backend receipt 覆盖持久事实。

admission core / seal 任一缺失、seal 不可验证、唯一域不可解析或 verdict 不是明确 `ADMITTED` 时，必须 `REJECTED`；不得降级为 bundle 内局部 replay 检查，也不得把写 side effect 偷进 Assembler。

### 7.7 Receipt 不能证明的事情

有效签名只证明：

- 被签字节未被修改；
- Trust Policy 认可的 issuer key 对该类型做过声明；
- payload 与当前 execution binding 一致。

它不自动证明：

- 领域结果正确；
- Sandbox 机制真的满足全部威胁模型（还需要独立 conformance evidence）；
- `completed` 已获业务通过；
- 人已签发；
- 外部交付成功；
- audit ledger 已达到不可抵赖或 WORM。

## 8. Canonical fact set 与 fact digest

### 8.1 FactSetV1

`factSetDigest` 的输入不是 `readSnapshot` 外壳，也不是 request id。它绑定 canonical fact membership **以及 Adapter 用来判定事实时间的受信 capture boundary**：

```text
FactSetV1 {
  factContractVersion = "flai.production-snapshot.fact-set.v1",
  observerContractVersion = "flai.stage-c.observer.v2",
  adapterContractVersion = "flai.stage-c.runtime-observer-adapter.v3",
  binding {
    taskId,
    taskRevision,
    executionEpoch
  },
  captureBoundary {
    capturedAt
  },
  taskEventWindow {
    offset,
    totalEventCount,
    events[] {
      ordinal,
      eventId,
      taskId,
      eventType,
      level,
      createdAt,
      agentId?,
      observerPayload
    }
  },
  executionRun =
    PartialExecutionRunFact {
      availability = "partial"
    }
    |
    VerifiedExecutionRunFact {
      availability = "verified",
      executionId,
      taskId,
      taskRevision,
      executionEpoch,
      observationRevision,
      observedAt,
      status,
      action?,
      step {
        current,
        total,
        label?
      },
      currentEventId,
      currentObjectRef,
      backend {
        backendId,
        backendKind,
        adapterId,
        adapterVersion
      },
      realityWitness {
        witnessId,
        reality,
        phase,
        verification,
        executionId,
        executionEpoch,
        backendId,
        observedAt,
        evidenceRefs[]
      }
    },
  artifacts[] {
    artifactId,
    taskId,
    filename,
    kind,
    sizeBytes,
    sha256,
    classification,
    createdAt
  },
  knowledgeEvidence[] {
    eventId,
    taskId,
    scopeId,
    citations[] {
      chunkId,
      source,
      fingerprint
    }
  },
  verifiedReceiptFacts[] {
    receiptType,
    receiptId,
    envelopeDigest,
    signedContentDigest,
    admissionCoreDigest,
    admissionSealDigest,
    issuerId,
    keyId,
    keyFingerprint,
    historicalTrustPolicyEpoch,
    historicalTrustPolicyDigest
  },
  effectiveClassification
}
```

`observerPayload` 的 V1 形状精确冻结为：

```text
knowledge_search -> {
  scope_id,
  hit_citations[] {
    chunk_id,
    source,
    fingerprint
  }
}

all other event types -> {}
```

`knowledge_search` 只允许 scope 与 citation 四钥；message、模型原文、路径、思维链和未声明 payload key 不进入 bundle 或 digest。未来若 Observer 需要新增结构化字段，必须提升 fact contract / Adapter contract version，不能在 V1 payload 中静默透传。

### 8.2 稳定字节规则

- 使用 RFC 8785 JSON Canonicalization Scheme；
- 所有字段名与 enum 大小写固定；
- ID 不 trim、不 Unicode 归一化；不合法即拒绝，不能把两个不同 ID 合并；
- timestamp 必须是带 offset 的严格 RFC 3339，最多六位小数；解析后精确转换为 UTC，并输出恰好六位小数的 `YYYY-MM-DDTHH:mm:ss.ffffffZ`。不截断、不舍入；超过微秒精度或不能无损转换即 `FACT_TIME_PRECISION_UNSUPPORTED`；
- SHA-256 十六进制统一 lowercase；
- 所有 JSON integer 必须位于 JavaScript safe-integer 区间 `[-(2^53-1), 2^53-1]`；offset、count、ordinal、revision、sequence、size 与 step 等合同计数还必须非负并满足各自上限；
- 禁止浮点、`NaN`、`Infinity` 和 `-0`；
- object key 由 JCS 排序；
- event、Artifact、citation 的 array 顺序保留第 5.4 节业务顺序；
- `verifiedReceiptFacts` 按 `receiptType + receiptId` 排序；
- duplicate id 不去重；相同 id 同值重复和同 id 异值冲突都拒绝。

V1 的 absent / null 规则也属于 canonical contract：

- `PartialExecutionRunFact` **只能**包含 `availability="partial"`，其余 execution 字段全部 absent；
- `VerifiedExecutionRunFact` 除 `action` 与 `step.label` 外全部字段必需且非 null；
- `action` 只在 `validating / running / parsing / analyzing` 出现；其余状态必须 absent；
- `step.label` 无值时 absent；空字符串与 null 均非法；
- Artifact `createdAt`、receipt admission facts 与 verified witness 字段全部必需；
- FactSetV1 任何其他 null 或未声明字段都非法。

### 8.3 Digest 算法

```text
canonicalFactBytes = RFC8785_JCS(FactSetV1)

digestBytes = SHA256(
  UTF8("FLAI-PRODUCTION-SNAPSHOT-FACT-SET" + NUL + "v1" + NUL)
  || canonicalFactBytes
)

factSetDigest = "sha256:" + lowercaseHex(digestBytes)
```

计算失败、canonical bytes 超限或结果格式不精确匹配 `sha256:<64 lowercase hex>` 都拒绝。

### 8.4 包含与排除

必须包含：

- Adapter 真正消费的全部结构化值；
- Adapter 用于未来事实检查的受信 `capturedAt`；
- task revision、execution epoch、event ordinal 与内容；
- backend / Adapter identity、reality witness、receipt、admission core 与 admission seal digest；
- Artifact digest 与 classification；
- Knowledge citation 四钥；
- 事实合同、Observer 与 Adapter 版本。

明确排除：

- `assembledAt`；
- request / correlation id；
- actor display name；
- UI 展开状态；
- 日志 message；
- 签名原始字节；
- 任何随机数。

因此相同事实集合与相同 capture boundary 必须得到相同 canonical bytes 和 digest；重新读取时即使 membership 未变，只要 `capturedAt` 改变，digest 也必须改变。不同 actor 在都被允许读取同一个完整 fact set 且绑定同一 capture boundary 时得到同一 digest。actor、策略判定与 release fence 证据记录在 `assemblyMetadata`，不冒充 fact membership。

### 8.5 readSnapshot 投影

Assembler 从 FactSetV1 派生既有 Adapter 所需的：

```text
readSnapshot {
  factSetDigest,
  capturedAt,
  taskId,
  taskRevision,
  executionEpoch,
  taskEventWindow {
    offset,
    eventIds[]
  },
  executionFact,
  artifactFacts[],
  knowledgeRefs[]
}
```

其中精确投影为：

```text
executionFact {
  availability,
  executionId,
  observationRevision,
  backendId,
  backendKind,
  backendAdapterId,
  backendAdapterVersion,
  reality,
  realityWitnessId,
  realityWitnessPhase,
  realityWitnessVerification,
  realityWitnessObservedAt,
  realityWitnessRefs
}

artifactFacts[] {
  artifactId,
  sha256
}

knowledgeRefs[] =
  "knowledge:"
  + encodeURIComponent(scopeId)
  + ":"
  + encodeURIComponent(source)
  + ":"
  + encodeURIComponent(chunkId)
  + "@"
  + lowercaseFingerprint
```

`availability=partial` 时 `executionFact` 除 `availability` 外的字段全部为 `null`；`verified` 时全部非空。`artifactFacts` 保持 Artifact 业务顺序，`knowledgeRefs` 保持 event ordinal 与 citation 持久顺序。该投影必须与 Adapter v3 的机械比较完全一致。

`readSnapshot` 是 FactSetV1 的有损 manifest，不是 digest 输入本体。Adapter 负责 manifest 与 bundle 的机械对账；Assembler 负责 digest 的密码学内容绑定。二者不可互相替代。

### 8.6 Adapter v3 的规范投影

本节与 Adapter v3 的版本化 conformance tests 共同构成规范；实现不能只依赖“顶层字段名相同”。所有下列 object 均为 `additionalProperties=false`，所有可选字段在无值时必须 absent，不能填 null。

```text
binding {
  source = "control-kernel",
  taskId,
  taskRevision,
  executionEpoch
}

taskEvents {
  offset,
  items[] {
    event_id,
    task_id,
    agent_id?,
    event_type,
    level,
    payload,
    created_at
  }
}

executionRun =
  {
    availability = "partial"
  }
  |
  {
    availability = "verified",
    execution_id,
    task_id,
    task_revision,
    execution_epoch,
    observation_revision,
    observed_at,
    status,
    action?,
    step {
      current,
      total,
      label?
    },
    current_event_id,
    current_object_ref = "file:" + artifact_id,
    backend {
      backend_id,
      backend_kind,
      adapter_id,
      adapter_version
    },
    reality_witness {
      witness_id,
      reality,
      phase,
      verification,
      execution_id,
      execution_epoch,
      backend_id,
      observed_at,
      evidence_refs[]
    }
  }

artifacts[] {
  id,
  task_id,
  filename,
  kind = "input" | "output",
  size_bytes,
  sha256,
  classification,
  created_at
}

knowledgeEvidence[] {
  event_id,
  task_id,
  event_type = "knowledge_search",
  payload {
    scope_id,
    hit_citations[] {
      chunk_id,
      source,
      fingerprint
    }
  }
}
```

字段映射仅做命名风格转换：FactSet camelCase 到 Adapter snake_case；不得重新查询、重排、补默认事实或透传 message / path / uploaded_by / query / hit_count。`taskEvents.items[].payload` 使用第 8.1 节白名单；`knowledgeEvidence` 必须与对应 `knowledge_search` event 的 payload 字节语义一致。

生产请求路径**不得**加载前端 JavaScript、启动 Node/JS engine，也不得在 Python 复制 Observer 的 UI 投影逻辑。释放前由 language-native `StrictBundleConformanceValidator` 只执行本合同的结构与引用检查：

1. manifest 与六组投影逐项一致；
2. verified current event、current object 与 knowledge refs 全部可解析；
3. partial 严格保持本节最小形状，且只能用于 `DIAGNOSTIC_ONLY`；
4. 未声明字段、null/absent 漂移或 casing 漂移均拒绝；
5. 组合引用满足下述 200 code-unit 上限。

真实 Adapter v3 的行为由 CI / 跨进程 conformance suite 验证，而不是每次生产请求运行：

- 同一组 versioned golden READY bundle 送入真实 Adapter v3，必须得到恰好一个 observer event 且没有 blocking diagnostic；
- golden partial bundle 必须得到零 observer event；
- conformance receipt 必须绑定 fact contract、Adapter source digest、validator source digest、测试向量 digest 与测试结果，并进入部署 manifest；
- 部署缺失匹配的 conformance receipt，或任一 digest 漂移时，production composition root 不得启用该合同版本。

`StrictBundleConformanceValidator` 不生成标题、动作、动画或 ObserverEvent，不成为第二个 Observer Adapter。

Assembler 还必须在释放前渲染并检查 Adapter 会组合的每个引用；为与 v3 精确兼容，最终 JavaScript UTF-16 code-unit length 均不得超过 200：

```text
task-event:<event_id>@ordinal:<ordinal>
execution:<execution_id>@observation:<observation_revision>
backend:<backend_id>@adapter:<adapter_id>:<adapter_version>
reality-witness:<reality>:<witness_id>
artifact:<artifact_id>@sha256:<sha256>
read-snapshot:<factSetDigest>
knowledge:<encoded-scope>:<encoded-source>:<encoded-chunk>@<fingerprint>
```

单字段长度通过但组合后超限仍返回 `OBSERVER_REFERENCE_LIMIT_EXCEEDED`；不得把 Adapter 的零事件当成成功。

## 9. 失败对象与稳定失败码

### 9.1 InternalFailure 与 PublicFailure

`assembleSnapshot(...)` 是 Kernel 内部接口，只向受信 composition root 返回：

```text
InternalFailure {
  contractVersion = "flai.production-snapshot.failure.v1",
  code,
  stage,
  disposition,
  retryClass,
  blocksObservation = true,
  correlationId,
  auditClass
}
```

`InternalFailure` 即使在 Kernel 内也禁止包含 SQL、路径、对象标题、密级值、receipt payload、key material、stack trace 或 free-text 内部异常。只有受信 Kernel 控制流与受限审计投影可按 `code / disposition / retryClass` 分支，不能解析 message。

任何 UI、浏览器或普通 API 只能得到 composition root 生成的：

```text
PublicFailure {
  contractVersion = "flai.production-snapshot.public-failure.v1",
  code = safePublicCode,
  correlationId,
  retryHint = NONE | REAUTHENTICATE | RETRY_LATER
}
```

公共投影不得包含 internal `code`、stage、disposition、细粒度 retryClass、auditClass 或内部 timing 差异。下表的 `safePublicCode` 是唯一允许的外部映射，不表示内部与外部 failure 共用同一对象。

`stage` 与 `auditClass` 也采用封闭枚举：

```text
stage =
  AUTHENTICATION | AUTHORIZATION | READ_SNAPSHOT |
  EXECUTION_WITNESS | RECEIPT_VERIFICATION |
  FACT_CANONICALIZATION | ADAPTER_CONFORMANCE | RELEASE_FENCE

auditClass =
  AUTHN_DENIAL | AUTHZ_DENIAL | CLASSIFICATION_DENIAL |
  CONSISTENCY_FAILURE | INTEGRITY_FAILURE | TRUST_FAILURE |
  CONTRACT_UNSUPPORTED | TRANSIENT_DEPENDENCY
```

stage 映射固定为：9.3 认证 code → `AUTHENTICATION`，9.3 授权/classification code → `AUTHORIZATION`，9.4 → `READ_SNAPSHOT`，9.5 → `EXECUTION_WITNESS`，9.6 → `RECEIPT_VERIFICATION`，9.7 canonical code → `FACT_CANONICALIZATION`，9.7 reference / Adapter code → `ADAPTER_CONFORMANCE`。四个 fence code 覆盖上述 stage，统一使用 `RELEASE_FENCE`。

auditClass 必须按以下不交叉集合机械映射：

- `AUTHN_DENIAL`：`CHANNEL_UNTRUSTED`、`AUTH_CONTEXT_INVALID`、`AUTH_CONTEXT_EXPIRED`、`REMOTE_AUTH_ADMISSION_MISSING`、`AUDIENCE_PURPOSE_MISMATCH`、`AUTHENTICATION_FENCE_CHANGED`；
- `AUTHZ_DENIAL`：`SNAPSHOT_NOT_VISIBLE`、`AUTHORIZATION_FENCE_CHANGED`；
- `CLASSIFICATION_DENIAL`：`CLASSIFICATION_UNRESOLVED`、`CLASSIFICATION_CLEARANCE_DENIED`；
- `CONSISTENCY_FAILURE`：`RESOURCE_FENCE_CHANGED`、`TASK_REVISION_MISMATCH`、`EXECUTION_EPOCH_MISMATCH`、`EVENT_WINDOW_INCOMPLETE`、`FACT_IDENTITY_CONFLICT`、`FACT_TIME_INCONSISTENT`、`EXECUTION_FACTS_INCOMPLETE`、`EXECUTION_OBSERVATION_CONFLICT`；
- `INTEGRITY_FAILURE`：`WITNESS_MISSING`、`WITNESS_IDENTITY_MISMATCH`、`WITNESS_PHASE_MISMATCH`、`WITNESS_TIME_INVALID`、`RECEIPT_MISSING`、`RECEIPT_DIGEST_MISMATCH`、`RECEIPT_SCHEMA_INVALID`、`RECEIPT_CANONICALIZATION_FAILED`、`RECEIPT_ADMISSION_EVIDENCE_MISSING`、`RECEIPT_ADMISSION_EVIDENCE_INVALID`、`RECEIPT_SIGNATURE_INVALID`、`RECEIPT_TIME_INVALID`、`RECEIPT_BINDING_MISMATCH`、`RECEIPT_REPLAY_OR_CONFLICT`、`ARTIFACT_REFERENCE_MISSING`、`ARTIFACT_IDENTITY_MISMATCH`、`ARTIFACT_DIGEST_INVALID`、`KNOWLEDGE_EVIDENCE_MISMATCH`、`FACT_CANONICALIZATION_FAILED`、`ADAPTER_CONFORMANCE_FAILED`；
- `TRUST_FAILURE`：`WITNESS_REALITY_POLICY_MISMATCH`、`RECEIPT_ISSUER_UNTRUSTED`、`RECEIPT_KEY_REVOKED`、`RECEIPT_ALGORITHM_DENIED`、`VERIFICATION_POLICY_CHANGED`；
- `CONTRACT_UNSUPPORTED`：`MULTI_STORE_SNAPSHOT_UNSUPPORTED`、`TASK_BINDING_UNAVAILABLE`、`FACT_TIME_PRECISION_UNSUPPORTED`、`FACT_SET_TOO_LARGE`、`RECEIPT_SCHEMA_UNSUPPORTED`、`RECEIPT_HISTORICAL_TRUST_POLICY_UNAVAILABLE`、`OBSERVER_REFERENCE_LIMIT_EXCEEDED`、`CONTRACT_VERSION_UNSUPPORTED`；
- `TRANSIENT_DEPENDENCY`：`ACL_POLICY_UNAVAILABLE`、`AUTHORIZATION_SERVICE_UNAVAILABLE`、`READ_SNAPSHOT_UNAVAILABLE`、`RECEIPT_KEY_UNKNOWN`、`RECEIPT_TRUST_POLICY_RESOLVER_UNAVAILABLE`、`RECEIPT_VERIFIER_UNAVAILABLE`、`FACT_DIGEST_FAILED`。

一个 code 必须且只能落入一个集合。新增、删除或重命名 code 必须同时更新本集合与 invalid-first 测试；实现不得用名称通配符推导 auditClass。

### 9.2 disposition 与 retryClass

```text
disposition =
  DENY | DIAGNOSTIC_ONLY | RETRY | RECONCILE | UNSUPPORTED

retryClass =
  NEVER | REAUTHENTICATE | AFTER_POLICY_REFRESH |
  RETRY_SAME_SELECTOR | RECONCILIATION_REQUIRED
```

只有 `EXECUTION_FACTS_INCOMPLETE` 可以产生 `DIAGNOSTIC_ONLY` bundle。其余失败都返回 `REJECTED`。

Public `retryHint` 机械映射为：

- `REAUTHENTICATE -> REAUTHENTICATE`；
- `AFTER_POLICY_REFRESH | RETRY_SAME_SELECTOR -> RETRY_LATER`；
- `NEVER | RECONCILIATION_REQUIRED -> NONE`。

### 9.3 认证与授权

| code | disposition / retryClass | safePublicCode |
|---|---|---|
| `CHANNEL_UNTRUSTED` | `DENY / NEVER` | `SNAPSHOT_ACCESS_DENIED` |
| `AUTH_CONTEXT_INVALID` | `DENY / REAUTHENTICATE` | `SNAPSHOT_REAUTH_REQUIRED` |
| `AUTH_CONTEXT_EXPIRED` | `DENY / REAUTHENTICATE` | `SNAPSHOT_REAUTH_REQUIRED` |
| `REMOTE_AUTH_ADMISSION_MISSING` | `DENY / REAUTHENTICATE` | `SNAPSHOT_REAUTH_REQUIRED` |
| `AUDIENCE_PURPOSE_MISMATCH` | `DENY / NEVER` | `SNAPSHOT_ACCESS_DENIED` |
| `SNAPSHOT_NOT_VISIBLE` | `DENY / NEVER` | `SNAPSHOT_NOT_VISIBLE` |
| `ACL_POLICY_UNAVAILABLE` | `RETRY / AFTER_POLICY_REFRESH` | `SNAPSHOT_TEMPORARILY_UNAVAILABLE` |
| `AUTHORIZATION_SERVICE_UNAVAILABLE` | `RETRY / RETRY_SAME_SELECTOR` | `SNAPSHOT_TEMPORARILY_UNAVAILABLE` |
| `CLASSIFICATION_UNRESOLVED` | `DENY / NEVER` | `SNAPSHOT_ACCESS_DENIED` |
| `CLASSIFICATION_CLEARANCE_DENIED` | `DENY / NEVER` | `SNAPSHOT_ACCESS_DENIED` |
| `AUTHENTICATION_FENCE_CHANGED` | `DENY / REAUTHENTICATE` | `SNAPSHOT_REAUTH_REQUIRED` |
| `AUTHORIZATION_FENCE_CHANGED` | `RETRY / AFTER_POLICY_REFRESH` | `SNAPSHOT_ACCESS_CHANGED` |
| `RESOURCE_FENCE_CHANGED` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_BINDING_CHANGED` |

### 9.4 一致性与事实

| code | disposition / retryClass | safePublicCode |
|---|---|---|
| `READ_SNAPSHOT_UNAVAILABLE` | `RETRY / RETRY_SAME_SELECTOR` | `SNAPSHOT_TEMPORARILY_UNAVAILABLE` |
| `MULTI_STORE_SNAPSHOT_UNSUPPORTED` | `UNSUPPORTED / NEVER` | `SNAPSHOT_CONTRACT_UNSUPPORTED` |
| `TASK_BINDING_UNAVAILABLE` | `UNSUPPORTED / NEVER` | `SNAPSHOT_CONTRACT_UNSUPPORTED` |
| `TASK_REVISION_MISMATCH` | `DENY / NEVER` | `SNAPSHOT_BINDING_CHANGED` |
| `EXECUTION_EPOCH_MISMATCH` | `DENY / NEVER` | `SNAPSHOT_BINDING_CHANGED` |
| `EVENT_WINDOW_INCOMPLETE` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `FACT_IDENTITY_CONFLICT` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `FACT_TIME_INCONSISTENT` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `FACT_TIME_PRECISION_UNSUPPORTED` | `UNSUPPORTED / NEVER` | `SNAPSHOT_CONTRACT_UNSUPPORTED` |
| `FACT_SET_TOO_LARGE` | `UNSUPPORTED / NEVER` | `SNAPSHOT_LIMIT_EXCEEDED` |

`READ_SNAPSHOT_UNAVAILABLE` 唯一覆盖“无法建立/保持 SQLite read snapshot”以及在该 snapshot 内发生的 repository/storage read failure；不再另设语义相同的 `READ_BACKEND_FAILURE`。已建立 snapshot 后发现成员冲突，使用对应 `EVENT_WINDOW_INCOMPLETE / FACT_IDENTITY_CONFLICT / *_MISMATCH`，不能退回通用读失败。

### 9.5 ExecutionRun 与 witness

| code | disposition / retryClass | safePublicCode |
|---|---|---|
| `EXECUTION_FACTS_INCOMPLETE` | `DIAGNOSTIC_ONLY / RETRY_SAME_SELECTOR` | `SNAPSHOT_DIAGNOSTIC_ONLY` |
| `EXECUTION_OBSERVATION_CONFLICT` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `WITNESS_MISSING` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `WITNESS_IDENTITY_MISMATCH` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `WITNESS_PHASE_MISMATCH` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `WITNESS_REALITY_POLICY_MISMATCH` | `DENY / NEVER` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `WITNESS_TIME_INVALID` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |

码域优先级固定为：

- ExecutionRun 缺少某类**必需 receipt ref** → `WITNESS_MISSING`；
- persisted ref 存在但 content-addressed envelope 不存在 → `RECEIPT_MISSING`；
- 单份已解析 receipt 的 signed subject / phase 与 selector 或 run 不符 → `RECEIPT_BINDING_MISMATCH`；
- 每份 receipt 单独有效，但跨 receipt 的 Broker/Sandbox identity、独立 issuer、phase set 或 reality 组合不成立 → 对应 `WITNESS_IDENTITY_MISMATCH / WITNESS_PHASE_MISMATCH / WITNESS_REALITY_POLICY_MISMATCH`。

同一失败不得同时发出 witness 与 receipt 两个 primary code；更细节只进入受限 findings ref。

### 9.6 Receipt 验证

| code | disposition / retryClass | safePublicCode |
|---|---|---|
| `RECEIPT_MISSING` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `RECEIPT_DIGEST_MISMATCH` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `RECEIPT_SCHEMA_UNSUPPORTED` | `UNSUPPORTED / NEVER` | `SNAPSHOT_CONTRACT_UNSUPPORTED` |
| `RECEIPT_SCHEMA_INVALID` | `DENY / NEVER` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `RECEIPT_CANONICALIZATION_FAILED` | `DENY / NEVER` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `RECEIPT_ADMISSION_EVIDENCE_MISSING` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `RECEIPT_ADMISSION_EVIDENCE_INVALID` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `RECEIPT_HISTORICAL_TRUST_POLICY_UNAVAILABLE` | `UNSUPPORTED / NEVER` | `SNAPSHOT_CONTRACT_UNSUPPORTED` |
| `RECEIPT_ISSUER_UNTRUSTED` | `DENY / NEVER` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `RECEIPT_KEY_UNKNOWN` | `RETRY / AFTER_POLICY_REFRESH` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `RECEIPT_KEY_REVOKED` | `DENY / NEVER` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `RECEIPT_ALGORITHM_DENIED` | `DENY / NEVER` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `RECEIPT_SIGNATURE_INVALID` | `DENY / NEVER` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `RECEIPT_TIME_INVALID` | `DENY / NEVER` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `RECEIPT_BINDING_MISMATCH` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `RECEIPT_REPLAY_OR_CONFLICT` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `RECEIPT_TRUST_POLICY_RESOLVER_UNAVAILABLE` | `RETRY / AFTER_POLICY_REFRESH` | `SNAPSHOT_TEMPORARILY_UNAVAILABLE` |
| `RECEIPT_VERIFIER_UNAVAILABLE` | `RETRY / RETRY_SAME_SELECTOR` | `SNAPSHOT_TEMPORARILY_UNAVAILABLE` |
| `VERIFICATION_POLICY_CHANGED` | `RETRY / AFTER_POLICY_REFRESH` | `SNAPSHOT_ACCESS_CHANGED` |

### 9.7 Artifact、Knowledge 与 digest

| code | disposition / retryClass | safePublicCode |
|---|---|---|
| `ARTIFACT_REFERENCE_MISSING` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `ARTIFACT_IDENTITY_MISMATCH` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `ARTIFACT_DIGEST_INVALID` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `KNOWLEDGE_EVIDENCE_MISMATCH` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `FACT_CANONICALIZATION_FAILED` | `DENY / NEVER` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `FACT_DIGEST_FAILED` | `RETRY / RETRY_SAME_SELECTOR` | `SNAPSHOT_TEMPORARILY_UNAVAILABLE` |
| `OBSERVER_REFERENCE_LIMIT_EXCEEDED` | `UNSUPPORTED / NEVER` | `SNAPSHOT_LIMIT_EXCEEDED` |
| `ADAPTER_CONFORMANCE_FAILED` | `RECONCILE / RECONCILIATION_REQUIRED` | `SNAPSHOT_INTEGRITY_BLOCKED` |
| `CONTRACT_VERSION_UNSUPPORTED` | `UNSUPPORTED / NEVER` | `SNAPSHOT_CONTRACT_UNSUPPORTED` |

`KNOWLEDGE_AUTHORITY_UNRESOLVED` 不是失败对象，而是 non-blocking warning：它允许观察“发生过一次带 provenance 的检索”，但不允许把 citation 升级为权威、有效或适用依据。

Receipt parse code 的唯一边界为：

- 未知 envelope / receipt version 或未知 receipt type → `RECEIPT_SCHEMA_UNSUPPORTED`；
- 已知版本/type 下缺字段、额外字段、类型/长度/enum 不合法 → `RECEIPT_SCHEMA_INVALID`；
- duplicate JSON key、非 UTF-8、非法 JSON 数值或不能得到唯一 canonical bytes → `RECEIPT_CANONICALIZATION_FAILED`。

## 10. 关键不变量

1. Assembler 是 read-only Module；任何业务写、receipt ingest 或 nonce 消费属于别处。
2. `source="control-kernel"`、`verified=true`、fixture 文件名和内网来源都不能自证可信。
3. 认证、对象 ACL 与 classification 在任何受保护事实读取之前。
4. 当前持久 classification 只读，不在 read 时按当前 registry 重派生。
5. 一个 bundle 的业务事实只能来自同一 SQLite read snapshot。
6. release fence 只收紧，不把第二次读取的新业务事实混入旧快照。
7. live Runtime / Broker / Knowledge index 不能在组装期补写事实。
8. `REAL` 同时需要 ExecutionBroker receipt、独立 Sandbox witness 和阶段 receipt。
9. cancelled 缺 termination witness 永远不显示“已停止”。
10. `completed` 不等于人签、业务通过、绿色、交付成功或 REAL。
11. MOCK / TEST reality 永不自动升级，fixture resolver 永不返回 REAL。
12. receipt 签名证明 issuer 对字节的声明，不证明领域结论。
13. FactSetV1 覆盖 Adapter 消费的全部结构化事实；随机 request metadata 不参与 digest。
14. 同事实与同 capture boundary 得到同字节和同 digest；任何成员、值、顺序、`capturedAt` 或合同版本变化都改变 digest。
15. 安全、完整性和授权失败无 bundle；只有遗留事实不完整可返回 diagnostic-only。
16. Adapter 仍是纯函数，不增加网络、存储、验签或授权依赖。
17. 人仍是唯一签发者；Assembler、Resolver、Adapter 与 UI 都无签发权。

## 11. Invalid-first 评审与未来测试夹具

实现获批后，先写失败测试，再写 Assembler。最低测试矩阵：

| ID | 负例 | 预期 |
|---|---|---|
| A1 | 调用方只填 `source="control-kernel"` | `CHANNEL_UNTRUSTED`，零读取 |
| A2 | 序列化重放普通 user dict | `AUTH_CONTEXT_INVALID` |
| A2b | remote envelope 未经 ingress 消费 nonce 就直接调用 | `REMOTE_AUTH_ADMISSION_MISSING`，零读取 |
| A3 | 用户 A 用已知 ID 读用户 B task | `SNAPSHOT_NOT_VISIBLE`，响应不可区分不存在 |
| A4 | actor 在第一次读取后被停用 | `AUTHENTICATION_FENCE_CHANGED` |
| A5 | authorization epoch 在验签期间变化 | `AUTHORIZATION_FENCE_CHANGED` |
| A6 | 只改变 ResourceEnvelope version，decisionRef 因此也变化 | 仅 `RESOURCE_FENCE_CHANGED` |
| C1 | task classification 缺失且已有派生内容 | `CLASSIFICATION_UNRESOLVED` |
| C2 | 子 Artifact 低于 task classification | `CLASSIFICATION_UNRESOLVED`，不自动升标签后放行 |
| C3 | task_event 无独立分级列，但 task ownership 与白名单 payload 均可证明 | 继承 task persisted classification，不要求改 Schema |
| C4 | event 引用跨资源 Knowledge / Artifact，但对象分级不可解析 | `CLASSIFICATION_UNRESOLVED` |
| S1 | 尝试用两次轮询拼 events 与 ExecutionRun | `READ_SNAPSHOT_UNAVAILABLE` |
| S2 | snapshot 后追加 event | 本次不混入；下一次形成新 digest |
| S3 | 重复 event id、内容不同 | `FACT_IDENTITY_CONFLICT` |
| S4 | verified current event 不在 tail window | `EVENT_WINDOW_INCOMPLETE` |
| S4b | partial 没有 current event | 允许继续形成 diagnostic-only，不执行 current-event window 检查 |
| S5 | 多活态 store 无共同 snapshot token | `MULTI_STORE_SNAPSHOT_UNSUPPORTED` |
| W1 | REAL 只有 backend receipt、无 Sandbox witness | `WITNESS_MISSING` |
| W2 | cancelled 无 termination witness | `WITNESS_MISSING`，零“已停止”事件 |
| W3 | completed MOCK 把 verification 改 verified | `WITNESS_REALITY_POLICY_MISMATCH` |
| W4 | receipt execution epoch 与 run 不同 | `RECEIPT_BINDING_MISMATCH` |
| W5 | 同一 workload / leaf key 同时签 backend receipt 与 sandbox witness | `WITNESS_IDENTITY_MISMATCH` |
| R1 | envelope byte 与 persisted digest 不同 | `RECEIPT_DIGEST_MISMATCH` |
| R2 | duplicate JSON key | `RECEIPT_CANONICALIZATION_FAILED` |
| R2b | 已知 receipt schema 出现未知字段 | `RECEIPT_SCHEMA_INVALID` |
| R3 | test key 签 REAL receipt | `RECEIPT_ISSUER_UNTRUSTED` |
| R4 | 吊销后新签 receipt 但回填旧 issuedAt，受信 ingestedAt 已晚于吊销 | `RECEIPT_KEY_REVOKED` |
| R5 | 改 payload 后复用签名 | `RECEIPT_SIGNATURE_INVALID` |
| R6 | 同 receipt id / nonce 对应两个 payload | `RECEIPT_REPLAY_OR_CONFLICT` |
| R7 | historical trust policy 可用，但当前策略标记 retrospective compromise | `RECEIPT_KEY_REVOKED` |
| R8 | current verification policy 在验签后、释放前变化 | `VERIFICATION_POLICY_CHANGED` |
| R9 | receipt 缺 immutable admission core 或 signed store seal | `RECEIPT_ADMISSION_EVIDENCE_MISSING` |
| R10 | 只修改 protected algorithm 或 keyId 并复用签名 | `RECEIPT_SIGNATURE_INVALID` |
| F1 | 同 FactSetV1、同 capturedAt 重放 | canonical bytes 与 digest 完全相同 |
| F2 | 只改 correlation id / actor display name | fact digest 不变 |
| F3 | 只改 capturedAt | fact digest 必变 |
| F4 | 改 event ordinal / Artifact digest / witness ref | fact digest 必变 |
| F5 | 同 id 同值重复 | `FACT_IDENTITY_CONFLICT`，不静默 dedupe |
| F6 | timestamp 超过微秒精度或不能无损转换 | `FACT_TIME_PRECISION_UNSUPPORTED` |
| K1 | event citation 与 Knowledge evidence 四钥不一致 | `KNOWLEDGE_EVIDENCE_MISMATCH` |
| L1 | 当前生产无法提供权威 taskRevision / executionEpoch | `TASK_BINDING_UNAVAILABLE`，整体拒绝 |
| L2 | 已有受信精确 binding，但只有 Task + ToolRun | `EXECUTION_FACTS_INCOMPLETE` + `DIAGNOSTIC_ONLY`，Adapter 零 event |
| P1 | Assembler 尝试 INSERT / UPDATE | `PRAGMA query_only` 使测试失败 |
| P2 | production composition root 注入 fixture resolver | 装配失败 |
| P3 | 实施 diff 改生产 Schema | 本切片验收直接失败 |
| P4 | 单字段合法但组合 artifact evidence ref 长度为 201 | `OBSERVER_REFERENCE_LIMIT_EXCEEDED`，零 observer event |
| P5 | StrictBundleConformanceValidator 发现 manifest / 引用 / Schema 漂移 | `ADAPTER_CONFORMANCE_FAILED`，不得 `READY` |
| P6 | 部署 manifest 缺匹配 Adapter v3 的 CI conformance receipt | composition root 禁用该合同版本 |

未来实现的最小 conformance suite 还必须证明：

- 失败发生在内容读取之前；
- public failure 不泄露 object existence；
- 每个 failure code 只有一个稳定语义；
- `READY` bundle 通过现有 Adapter v3 全部机械检查；
- `DIAGNOSTIC_ONLY` bundle 永远得到零 observer event；
- 后端、前端和跨进程 E2E 均不能因 Mock 夹具点亮 REAL。

## 12. 明确非目标与递延裁决

本轮不裁决：

- 生产表、列、索引、迁移或 API route；
- cryptographic library、HSM / 密码机厂商或具体算法 allowlist；
- 组织最终密级枚举、AD/LDAP/OIDC、MFA 和角色模型；
- 多数据库分布式 snapshot；
- WORM / SIEM 产品与留存年限；
- ExecutionRun、ReceiptStore、TrustPolicyStore 的物理持久模型；
- Artifact 大文件重哈希策略；
- 生产 freshness 数值；
- Windows Adapter；
- UI 新控件；
- 真实 OpenClaw/OpenHands 接入。

上述事项必须由对应 owner 在实施 ADR / threat model / migration plan 中裁决。未知不能以宽松默认补齐。

## 13. 评审门与实施停止条件

### 13.1 必须具名通过的评审

| 评审责任 | 必须明确回答 |
|---|---|
| Control Kernel / 架构 owner | Module ownership、公开 seam、无第二状态机 |
| Identity / Authorization owner | opaque context、ACL、存在性、release fence |
| 数据 / SQLite owner | 单 read transaction、tail window、query-only、性能上限 |
| 安全 / 密码 owner | receipt Schema、issuer 权限、算法策略、密钥轮换/吊销 |
| ExecutionBroker / Sandbox owner | backend、Sandbox 与阶段 witness 的独立性 |
| Knowledge owner | 四钥 provenance 与 authority unresolved 边界 |
| 工作台 / Observer owner | Adapter v3 兼容、diagnostic-only、失败体验 |

每项评审记录必须绑定：

```text
reviewer_actor_id
responsibility_scope
decision = approve | changes_required | reject
reviewed_contract_id
reviewed_contract_digest
reviewed_at
findings_refs[]
signature_or_audit_evidence_ref
```

缺任一责任域的明确 `approve`，实施门保持关闭。AI review、聊天中的“接受”、文件已提交或单测通过不能填充 `reviewer_actor_id` 或签名证据。

### 13.2 实施前机械前置

评审通过后，仍必须另开实施切片，并在计划中列出：

1. 不改 Schema 的 in-memory / repository conformance fixtures；
2. authenticated context carrier 的实现位置与威胁模型；
3. Authorization / ResourceEnvelope 的现有可复用 seam 或明确缺口；
4. SQLite ReadUnitOfWork 与 release fence 测试；
5. strict Receipt Schema、Trust Policy 与 test keys；
6. Production / Fixture WitnessResolver 装配隔离；
7. FactSetV1 canonicalization golden vectors；
8. language-native StrictBundleConformanceValidator、Adapter v3 CI golden suite、部署 manifest conformance receipt 与 invalid-first E2E；
9. 若必须变更生产 Schema，停止当前切片、另立 ADR / migration plan 并重新获批。

### 13.3 当前停止结论

当前结论固定为：

```text
contract_review = PENDING
implementation_authorized = false
production_schema_change = false
production_ready = false
```

下一步只能进行设计评审、威胁建模和测试计划细化；不能开始 Production Snapshot Assembler 实现。

## 14. 关联依据

- [CONTEXT.md](../../../CONTEXT.md)
- [02_System_Architecture.md](02_System_Architecture.md)
- [04_Data_Model.md](04_Data_Model.md)
- [08_Core_Workbench_UX.md](08_Core_Workbench_UX.md)
- [14_Security_Sandbox_Governance.md](14_Security_Sandbox_Governance.md)
- [ADR-0025：不可变任务级分级](../../adr/ADR-0025-immutable-task-classification.md)
- [ADR-0029：知识引用回源只读通道](../../adr/ADR-0029-knowledge-chunk-provenance-readback.md)
- [ADR-0030：专家身份与密级/依据契约](../../adr/ADR-0030-expert-identity-clearance-evidence-contract.md)
- [ADR-0049：控制内核与可替换执行后端](../../adr/ADR-0049-flai-control-kernel-and-replaceable-execution-backends.md)
- Stage C Runtime Observer Adapter：供体快照 `9220cc3` 中的实现证据；本轮文档移植明确
  不移植 `frontend/`，因此该 Adapter 仍是 `DONOR_ONLY / EVIDENCE_ONLY`，不能作为
  当前 main 已实现能力引用。

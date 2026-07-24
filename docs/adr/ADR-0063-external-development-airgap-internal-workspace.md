# ADR-0063：外网研发协作面、离线发布准入与内网自托管工作空间

- 状态：`confirmed_in_design_session`
- 实现状态：`ACCEPTED-NOT-IMPLEMENTED`
- 日期：2026-07-24
- 正式签发主体：`UNRESOLVED`
- 实施授权：否
- 生产 Schema 变更：否
- 生产准入影响：无；当前仍为 `NO-GO`
- 取代关系：部分取代
  [ADR-0062](ADR-0062-feishu-single-organizational-hub.md)

## 背景

ADR-0062 曾把飞书定义为 FLAi-OS 的唯一日常组织协作与治理中枢。该决定混合了两个不同问题：

1. 外网环境中，Codex、Kimi K3、研发人员如何共同开发 FLAi-OS；
2. FLAi-OS 进入与互联网、飞书和 GitHub.com 完全断开的企业内网后，业务用户如何协作、使用
   Agent、沉淀知识和完成治理。

owner 随后明确澄清：飞书只用于**当前外网研发团队的多人开发管理**。正式植入内网后，
FLAi-OS 与飞书生态完全断开，并依赖内网自托管的通讯、项目管理、知识、身份、代码与运行设施。

这不是把一个 Feishu Adapter 换成另一个聊天 Adapter。它改变了信任域、身份域、Secret 域、
代码事实、发布事实和故障模型。若仍保留实时 Feishu/GitHub 依赖，会使所谓“内网部署”在外网
DNS、外部身份、外部租户、外部 token 或云端可用性上形成隐藏单点，也会打开未经批准的跨域
数据与控制通道。

## 决定

### 1. 冻结三个部署信任域

```text
EXTERNAL_DEVELOPMENT
  FeishuDevelopmentHub + GitHub + Codex/Kimi
                  |
                  | 仅允许受控介质承载的内容寻址发布包
                  v
TRANSFER_QUARANTINE
  AirGapReleaseAdmission + 扫描 + 复验 + 具名准入
                  |
                  | 只交付内部已接纳的制品
                  v
AIR_GAPPED_INTERNAL
  FLAiWorkspace + 自托管协作/知识/身份/代码/制品设施
  + FLAi Control Kernel + 内网模型 + Sandbox + Audit/WORM
```

三个域不得共享数据库、事件总线、身份会话、Secret value、SecretRef 命名空间、webhook、回调、
运行控制通道或可隐式访问的网络路径。`TRANSFER_QUARANTINE` 是准入区，不是同步桥。

### 2. 外网研发协作面

`ExternalDevelopmentCollaborationPlane` 只服务于 FLAi-OS 产品研发：

- `FeishuDevelopmentHub` 组织需求、工作包、架构评审、Codex/Kimi 双线程、研发会议和交付回告；
- GitHub 拥有外网源码、commit、branch、PR、review、CI 和 merge 事实；
- Codex 是主要实现执行器；Kimi K3 只在独立 branch/worktree 中承担经批准的 UI/UX 专项；
- 两个机器执行器只能读取批准的源码、合成 fixture 和可外网处理的非敏感材料；
- 飞书身份、GitHub 身份、Kimi OAuth、Codex 会话和外网测试结果均不获得任何内网权限。

飞书在此域是 `System of Engagement`，不是内网产品依赖、Agent Runtime、发布签发者或
FLAi Control Kernel。

### 3. 内网唯一日常入口

内网普通用户的唯一产品入口定义为 `FLAiWorkspace`。它包含工作收件箱、项目空间、讨论、
会议、真相知识、工程智能体工作台、共建地图、治理与运行中心及后置领导视图。

`InternalWorkspaceHub` 是隐藏协作差异的深 Module。其外部 Interface 保持：

```text
open(actor_attestation, view_request)
  -> AuthorizedWorkspaceProjection | Rejection

prepare(actor_attestation, typed_intent)
  -> ReviewChallengeV1 | Rejection

commit(commit_actor_attestation, review_challenge_ref, confirmation_proof_ref)
  -> OwnerCommitReceiptV1 | EffectUnknownV1 | Rejection
```

自托管产品通过以下 Ports 接入，而不是把供应商数据模型泄漏给 FLAi 领域：

- `CollaborationSurfacePort`：频道、讨论、通知和协作事件；
- `ProjectCoordinationPort`：项目、责任事项、需求、风险和会议工作包；
- `KnowledgeAuthoringSurfacePort`：Wiki、DMS、受控目录和专业编辑器；
- `IdentityDirectoryPort`：内网身份、组织、项目成员关系和认证 assurance；
- `InternalCodeForgePort`：内网源码镜像、内网补丁、review 和 CI；
- `InternalArtifactRegistryPort`：已准入源码包、镜像、依赖、模型和部署制品；
- `NotificationPort`：角色过滤后的回告，不拥有任务或治理事实。

具体 Mattermost、Rocket.Chat、Wiki.js、Outline、Open WebUI、GitLab、Forgejo 或其他产品都只是
候选 Adapter。本 ADR 不完成采购选型，也不把任何候选升级为控制内核、Knowledge Authority、
Audit Ledger 或 Agent Runtime。

### 4. 离线发布准入是唯一外网入站

跨域入站只接受 `OfflineReleaseBundleV1`。这是设计合同名称，不是本轮生产 Schema。

```text
sealRelease(release_request, external_attestation)
  -> OfflineReleaseBundleV1 | Rejection

admitRelease(sealed_bundle_ref, transfer_evidence, internal_admission_context)
  -> InternalReleaseCandidateReceipt | QuarantineCase | Rejection

sealSanitizedFeedback(feedback_request, internal_export_context)
  -> SanitizedFeedbackBundle | Rejection
```

`AirGapExchange` 不提供 `promote`。候选进入内网后，资格、ReleaseSet CAS、DeploymentBinding 和
实际部署全部属于内部 Release Governance；`InternalReleaseCandidateReceipt` 不能替代这些门。

Bundle 至少绑定：

- 外网 Git commit、tree 和源码归档的完整 digest；
- 构建产物、容器镜像、模型/工具包和依赖镜像的逐项 digest；
- 锁文件、构建说明、目标架构、最低运行环境和可复现构建信息；
- SPDX 或 CycloneDX SBOM、许可证清单、漏洞扫描结果及未决例外；
- 单元、集成、UI、迁移、恢复和安全测试证据；
- 变更说明、风险、回滚说明及兼容性声明；
- 发布者来源证明、Bundle 签名、时间、签名策略和公钥信任链；
- classification、允许目标域和显式排除内容；
- Secret 扫描声明，且 Bundle 中不得出现 Secret value。

内网必须从只读介质或批准的受控传输设备重新计算 digest、验证签名、做恶意代码/漏洞/许可证
扫描，在隔离暂存环境构建或复验，并由内网具名真人作准入决定。外部签名只证明来源和完整性，
不能授权内网导入、部署、开权或签发。

### 5. 外网 GitHub SHA 不是内网部署事实

- GitHub 继续是 `EXTERNAL_DEVELOPMENT` 的代码事实源；
- Bundle 中的 GitHub SHA 在内网只是 provenance；
- 内网导入后，由内部 Code Forge/Artifact Registry 保存内容寻址副本；
- 内部 `InternalReleaseCandidateReceipt`、`ReleaseSet` Head、`QualificationDecision`、`DeploymentBinding` 和运行 witness
  才能证明某版本被接纳、部署和真实运行；
- GitHub merge、外网 CI 绿灯或飞书“已完成”均不能使内网状态变绿。

若内网需要紧急修复，补丁只进入内部 Code Forge，并形成独立内部 lineage。任何向外反馈都必须
重新构造脱敏问题包；不得自动推送完整内部分支、配置、日志、样本或制品。

### 6. 外发反馈是独立、更窄的人工出口

内网到外网没有自动遥测、日志同步、知识同步、截图同步或错误上报。允许的
`SanitizedFeedbackBundle` 至少满足：

- 只包含最小复现、合成或脱敏 fixture、公开源码补丁和必要的错误分类；
- 重新计算 classification，去除姓名、项目代号、主机、路径、Secret、真实数据与可反推元数据；
- 由数据 owner、安全责任人和出口操作员按适用制度具名批准；
- 绑定 export digest、审批证据、受控介质和外网接收回执；
- `cannot_sanitize` 时停止外发，在内网自行修复或重建通用复现。

入站发布准入和出站反馈准入使用不同职责、不同策略和不同 receipt，不允许以同一“同步任务”
双向复用。

### 7. 身份与 Secret 完全分域

- 外网 Feishu/GitHub/Kimi/Codex 身份不能映射为内网 actor，也不能继承 role、scope 或 signer；
- 内网只信任内部身份目录、项目成员关系、认证 assurance 和独立签发体系；
- `secrets-stackdocker` 当前只作为外网研发普通 App/Connector Secret 的声明 owner；
- 内网必须使用独立部署实例或另一个内部 Secret owner，使用独立 root、namespace、policy、
  backup、rotation、revocation 和 outage path；
- Secret value 和 SecretRef 名称均不得跨域同步；
- Safety Identity / PKI / HSM / Trusted Time 继续保持与普通 Secret 栈分离的故障域。

### 8. 内网知识与旧系统

内网自托管 Wiki/DMS/文件系统只是知识创作或来源 Surface。Knowledge Authority 继续拥有知识项
版本、有效性、适用范围、classification、ACL、精确锚点和真人签发。

旧 OA、eSpace、UME、邮件和文件服务器只能通过逐来源批准的只读 Adapter 进入“历史考古”路径。
每个 Adapter 必须保留 source identity、版本、digest、ACL、classification、freshness 和来源
引用；“内网可访问”不等于“当前用户有权用于模型上下文”。

外网飞书文档若需进入内网，必须成为独立 `OfflineKnowledgeImportBundle`，经过同样的分类、
内容寻址、恶意内容检查和内网真人重新发布；不能通过 Feishu Connector 直连或继承外部文档
权限。

### 9. 内网 Agent 与模型完全本地

内网 FLAi-OS 不依赖 OpenAI、Kimi、飞书 AI、公共模型仓库、公共插件市场、CDN、在线许可证
验证或外部遥测。内网模型、Embedding、Rerank、工具、MCP Server 和 Runtime 都必须从内部
Registry 解析，并满足既有 Qualification、Sandbox、ACL、classification、evidence 和审计门。

Kimi K3 可以在外网优化代码和 UI，但其贡献只以待准入源码制品进入内网。Kimi K3 本身不是
内网运行依赖，也不能读取内网数据。未来若独立部署某个内网模型，必须重新完成模型身份、
供应链、评测、部署绑定和运行 witness，不能继承外网模型名称或测试结论。

### 10. ADR-0062 的剩余有效范围

ADR-0062 不删除，以保留决策谱系，但其规范范围缩减为：

- `FeishuDevelopmentHub` 的外网研发协作；
- 外网研发身份绑定、typed intent、GitHub 工程投影、Codex/Kimi 工作包与研发回告；
- 外网研发普通 Connector Secret 引用和飞书租户连续性。

以下 ADR-0062 表述被本 ADR 取代：

- 飞书是内网 FLAi-OS 或全体业务用户的唯一入口；
- 内网工程工作台、知识、会议、Agent 治理、Bench 或审计从飞书实时编排；
- 飞书不可用属于内网产品连续性条件；
- 外网 Feishu/GitHub 身份、状态、receipt 或 Secret 可进入内网信任链；
- `DEV-HUB-F0` 可以替代 `AIRGAP-WORKSPACE-F0` 或生产准入。

## 关键不变量

1. FLAi Control Kernel 仍是运行、授权、任务、证据、审计和交付控制内核。
2. 人是唯一签发者；AI、外网 CI 和协作卡片都不进入内部判决链。
3. 所有跨域内容都必须内容寻址、可验签、可追溯、可拒绝、可隔离和可回滚。
4. 入站与出站都默认拒绝；unknown、签名无效、分类不明、扫描失败或证据不全一律阻断。
5. 内网在无飞书配置、无 GitHub.com、无外网 DNS、无公共模型、无公共 registry 时仍能启动、
   执行、审计、备份和恢复。
6. 自托管协作/Wiki 故障不能阻断 kill、revoke、isolate、credential invalidation 或
   Audit/WORM 封存。
7. 自托管 Surface 可替换；领域 Interface、内部 owner 和历史事实不随 Adapter 迁移而改变。
8. 本 ADR 不修改生产 Schema、API、数据库、状态机或依赖，不授权连接真实系统。

## 七责任域评审

原飞书中心化 F0 的冻结 SHA 仅保留为澄清前历史快照，不能作为本架构的最终 F0。新的冻结 SHA
必须由以下七个具名真人责任域对同一 digest 评审：

1. `PRODUCT_ARCHITECTURE_AND_DOMAIN_OWNERSHIP`
2. `AIRGAP_CYBERSECURITY_AND_TRANSFER_CONTROL`
3. `INTERNAL_IDENTITY_ACL_CLASSIFICATION_AND_PRIVACY`
4. `SELF_HOSTED_COLLABORATION_RECORDS_AND_CONTINUITY`
5. `AUTHORITATIVE_KNOWLEDGE_AND_LEGACY_SOURCE_INGEST`
6. `AGENT_RUNTIME_SANDBOX_EVIDENCE_AND_AUDIT`
7. `SOFTWARE_SUPPLY_CHAIN_INTERNAL_RELEASE_AND_OPERATIONS`

AI 评审只能作为 advisory finding；不能填充 reviewer、assignment issuer、approver 或 signer。
任一域为 `CONDITIONAL|REJECTED|UNKNOWN` 都阻断架构 F0。七域通过也只关闭设计评审，不自动授权
采购、生产 Schema、真实连接、数据导入、试点或部署。

## 后果

### 正面

- 外网多人开发体验与内网产品安全可以分别优化，不再让飞书成为隐藏生产依赖；
- 跨域攻击面收敛到一个可审计的离线准入 Module；
- 内网协作产品可替换，不改变 FLAi 领域、知识权威和控制内核；
- GitHub/Kimi/Codex 的价值保留，但其权限停在外网研发域；
- 内外版本分歧、内部热修和脱敏反馈获得明确 lineage。

### 代价

- 需要内部身份、代码/制品 registry、依赖镜像、许可证、备份、监控和升级能力；
- 每次发布比公网 CI/CD 更慢，需要 bundle 构建、传输、扫描、复验、准入和内部部署；
- 外网无法直接查看内网运行状态，问题复现需要脱敏或合成 fixture；
- 自托管产品的许可证、离线激活、审计、中文体验、升级和长期维护必须逐项尽调。

## 被拒绝的方案

### 飞书经代理或网闸实时连接内网

拒绝。它把外网 SaaS 身份、可用性和数据流引入内网运行路径。未来即使存在经批准的单向装置，
也必须作为独立 Adapter 和明确数据产品重新评审，不能改变本 ADR 的默认“无实时链路”。

### 在内网部署一个 Feishu 兼容层并沿用外网身份

拒绝。名称兼容不能提供内部身份、分类、审计和连续性保证，反而会模糊信任域。

### 把 Mattermost、Rocket.Chat 或 Open WebUI 直接定义为 FLAi-OS

拒绝。它们最多是协作或 AI 对话 Adapter；不能拥有 ExecutionRun、Knowledge、Authorization、
Delivery、Bench 或 Audit 事实。

### 直接把 GitHub 仓库压缩包拷进内网

拒绝。缺少依赖、SBOM、签名、测试证据、许可证、分类、扫描、内部准入和回滚绑定。

## 实施顺序

1. 冻结本 ADR 与两份详细设计读模型，生成新的 clean SHA；
2. 完成七责任域具名评审，保持生产 `NO-GO`；
3. 只读尽调内部基础设施、许可与身份/分类制度，选定一个协作 Adapter 与一个知识创作 Adapter；
4. 先实现 `OfflineReleaseBundleV1` 的隔离夹具、验证器和失败码，不连接真实传输设备；
5. 在无外网依赖的测试网完成安装、升级、备份、恢复、断网和 fail-closed 演练；
6. 另获授权后才实现内部 Workspace Adapter、真实知识接入和受控试点。

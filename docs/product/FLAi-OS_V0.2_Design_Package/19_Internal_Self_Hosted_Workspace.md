# 19｜内网自托管智能协作空间

> 文档性质：V0.2 产品、信息架构与 Adapter 选型读模型；不是采购结论、部署清单或生产授权。
>
> 首要依据：
> [ADR-0063](../../adr/ADR-0063-external-development-airgap-internal-workspace.md)。
>
> 当前状态：`ACCEPTED-NOT-IMPLEMENTED / CANDIDATE-SELECTION / NO-GO`。

## 1. 产品结论

FLAi-OS 进入企业内网后，不是“一个 AI 聊天页面加若干旧系统 Connector”，也不是“内网版飞书”。
它是一个 AI 原生研发协作空间：

```text
FLAiWorkspace（唯一内网产品入口）
├── 工作收件箱
├── 项目空间
│   ├── 讨论与通知
│   ├── 会议与责任事项
│   ├── 文档与真相知识
│   ├── 任务、决策、风险与需求
│   └── Agent 会话、产物、依据与交付
├── 工程智能体工作台
├── 共建地图与需求闭环
├── 治理与运行中心
└── 后置只读指挥视图

背后自托管设施
├── 内网 IdP / AD / LDAP / OIDC
├── 通讯协作 Adapter
├── 知识创作 Adapter
├── 内部 Git Forge / Artifact Registry
├── 内网 Model / Knowledge / Tool Gateway
├── FLAi Control Kernel / Sandbox
└── Audit / WORM / Backup / Observability
```

用户感知是一个 Workspace；实施上是多个事实 owner 与可替换 Adapter。聊天、Wiki、项目表和 AI
对话界面都不能成为第二控制内核。

## 2. 最小组合建议

当前建议的第一阶段组合是：

| 能力 | 建议 | 状态 | 严格定位 |
|---|---|---|---|
| 产品入口与项目语义 | FLAi 自有 Workspace | `ACCEPTED-NOT-IMPLEMENTED` | 工作收件箱、项目、需求、Agent、任务、审批、共建地图和运行投影 |
| 通讯协作 | Mattermost Enterprise 条件性候选 | `DECLARED-NOT-VERIFIED` | 频道、线程、通知、文件交流；不拥有 FLAi 项目/审批/运行事实 |
| 知识创作 | Wiki.js 2.5 稳定线条件性候选 | `DECLARED-NOT-VERIFIED` | 编辑、阅读、revision 和 ACL 来源；不自动成为权威知识 |
| 人员身份 | 内网 AD/LDAP/OIDC | `DECISION-REQUIRED` | 唯一人员身份、组、认证 assurance 和撤权来源 |
| 代码与制品 | 内部 Git Forge + OCI/包/模型 Registry | `DECISION-REQUIRED` | 已导入源码、内部补丁与内容寻址制品 |
| AI 对话 | FLAi 工程智能体工作台 | `IMPLEMENTED-PARTIAL` | 目标、连续执行、观察、产物、证据和末端交付 |
| 通用 AI Console | Open WebUI 可选 sidecar | `OUT-OF-MINIMUM-PRODUCTION-SCOPE` | 受限模型实验；不接生产 Tool/Secret/知识权威 |

这不是最终产品采购表。Mattermost、Wiki.js 和任何配套组件都必须经过许可、供应链、断网、
身份、ACL、审计、备份恢复、升级和中文 UX 的具名评审。

## 3. 为什么 FLAi 必须拥有项目语义

第三方聊天或 Wiki 的对象不等于 FLAi 事实：

| 协作 Surface 对象 | FLAi 中的语义 | 所有权 |
|---|---|---|
| 频道/群 | 协作容器或通知目标 | 协作 Adapter |
| 消息/线程 | 来源材料、讨论或 intent 候选 | 协作 Adapter |
| Wiki 页面 | 工作材料或知识来源 revision | 知识创作 Adapter |
| Board/Card | 可编辑协作草稿 | 协作 Adapter |
| DemandSignal | 不可变需求输入 | FLAi Demand owner |
| ResponsibilityItem | 正式责任、验收和补遗 | FLAi Meeting/Responsibility owner |
| RoadmapVersion | 具名签发的路线图承诺 | FLAi Roadmap Governance owner |
| ExecutionRun/Artifact | 运行和产物事实 | FLAi Control Kernel |
| KnowledgeVersion | 权威知识版本 | Knowledge Authority |
| Qualification/Deployment | 资格和部署事实 | FLAi Release owners |

Mattermost Boards、Wiki 标签或任意表格字段可以投影这些对象，但删除、编辑或移动投影不能改变
来源事实。第三方产品更换时，FLAi 项目、任务、知识、运行和审计历史不随之丢失或改写。

## 4. 深 Module 与替换 Seams

### 4.1 `InternalWorkspaceHub`

外部 Interface：

```text
open(actor_attestation, view_request)
  -> AuthorizedWorkspaceProjection | Rejection

prepare(actor_attestation, typed_intent)
  -> ReviewChallengeV1 | Rejection

commit(commit_actor_attestation, challenge_ref, confirmation_proof_ref)
  -> OwnerCommitReceiptV1 | EffectUnknownV1 | Rejection
```

Module 隐藏身份解析、项目 membership、ACL/classification、来源版本、投影、幂等/outbox、owner
receipt、freshness、gap 和 reconciliation。普通用户只看到“开始、继续、检查、交付”，不需要
理解 Mattermost/Wiki/FLAi 的内部对象映射。

### 4.2 Ports

```text
IdentityDirectoryPort
  authenticate / resolve_actor / resolve_membership / resolve_groups / revoke_epoch

CollaborationSurfacePort
  read_thread / append_collaboration_event / publish_projection / notify

ProjectCoordinationPort
  open_project / submit_typed_intent / read_project_projection

KnowledgeAuthoringSurfacePort
  read_revision / read_acl_snapshot / export_content_snapshot / create_draft

InternalCodeForgePort
  resolve_commit / read_diff / read_ci_evidence / publish_internal_patch

InternalArtifactRegistryPort
  resolve_by_digest / stage / promote_release_set / revoke

AIConversationPort
  open_conversation / append_user_goal / stream_observation / close
```

其中 `ProjectCoordinationPort` 的正式实现由 FLAi 自己拥有。第三方聊天/Boards 只能投影和提交
typed intent，不能直接实现领域写入。

### 4.3 共同 Envelope

所有 Adapter 输入必须转换为 `WorkspaceEventEnvelopeV1` 逻辑合同：

```text
source_instance_ref
source_object_ref
source_revision
authenticated_actor_ref
actor_binding_version
project_context_ref
classification
source_acl_snapshot_ref + digest
payload_ref + digest
attachment_refs + digests
observed_at
freshness
```

字段缺失、ACL unknown、来源 revision 漂移或 actor 未绑定时，正式动作 fail-closed。该逻辑对象
本轮不创建生产 Schema。

## 5. 身份、ACL 与 classification

### 5.1 身份

- 内网 IdP/AD/LDAP/OIDC 是唯一人员身份源；
- Mattermost、Wiki 和 FLAi 的本地用户 ID 都只能映射到版本化内部 actor；
- 禁止以昵称、邮箱字符串、频道成员或 Wiki group 自报角色；
- 撤权必须提升授权 epoch，使缓存、session、执行 lease 和投影权限失效；
- break-glass、Safety signer 和服务 workload identity 不与普通协作 SSO 共用故障域。

### 5.2 三重权限交集

Agent 获取任一内容时，必须显式满足：

```text
当前用户权限 ∩ 原始材料权限 ∩ Agent/Tool 身份权限
```

再与项目 scope、classification flow、purpose、任务授权和目标输出域共同求交。任一维度为
unknown 都不能把正文送入模型。

### 5.3 分类与存在性

- 标题、计数、文件名、缩略图、频道名和搜索命中本身都可能泄露存在性；
- 目标 Surface classification ceiling 必须独立验证；
- 不满足正文流转条件时，根据策略显示脱敏摘要、稳定引用或完全抑制存在性；
- “都在内网”不是放宽 ACL 或 classification 的理由。

## 6. 通讯协作候选

### 6.1 Mattermost：条件性优先候选

适合进入隔离 POC 的原因：

- 官方提供明确的 air-gapped 部署指南；
- 支持本地 PostgreSQL、私有 Registry/软件镜像和离线插件上传；
- 可对接 LDAP/OIDC/SAML，并有企业权限、审计与合规能力；
- 频道、线程、通知和文件交流适合 20–30 人起步，也能向更大规模演进。

必须先过的门：

1. 商业版本、价格、离线许可、升级权益和长期支持；
2. 采购、法务与适用出口管制/合规审查；
3. 企业审计、留存、合规导出覆盖范围；
4. Boards/Playbooks 等非消息对象是否进入组织 records，不能因导出不覆盖而成为权威事实；
5. 中文搜索、客户端分发、离线升级、移动端政策和无外网推送的实际体验；
6. 无公共 DNS、无默认路由、无远程 marketplace、无 telemetry 的冷启动和恢复 witness。

结论：只有条件全部满足，才实现 Mattermost Adapter；失败时替换 Adapter，不降低 FLAi 治理
合同。

### 6.2 Rocket.Chat：备选而非默认退路

当前不作为默认原因：

- 官方 air-gap 文档要求特定商业许可或自维护 FOSS build；
- Community/Starter/air-gap 的版本与套餐语义需要书面澄清；
- 自行维护 fossified build 会把长期补丁、升级、SBOM 和安全责任转移给组织。

只有拿到明确的商业 air-gap 条款，或组织正式接受维护自编译分支，才进入同等级 POC。

## 7. 知识创作候选

### 7.1 Wiki.js：第一隔离 POC 候选

进入 POC 的原因：

- 官方明确提供 offline mode 与 sideload；
- 支持本地账号、LDAP/AD、OIDC、SAML 和页面/组权限；
- 可用 PostgreSQL 和自托管附件/搜索能力；
- 适合用 Markdown/页面结构快速建立规章、条款、决策和项目知识树。

必须先过的门：

- 精确稳定版和全部依赖 digest 固定；不使用 alpha 线或 `latest`；
- AGPL 义务、内部修改、网络提供和源代码交付方式由法务确认；
- 页面 revision、ACL、附件、导出、恢复和全文检索在完全断网下复验；
- Wiki 自有日志不足以成为不可变审计，因此发布、签发和引用仍写 FLAi Evidence Ledger；
- 编辑器宏、外链、远程图片、认证/search/storage modules 默认关闭或逐项 allowlist。

### 7.2 Outline：UX 对照候选

Outline 的实时共编和阅读体验可作为 UX 对照，但正式候选需先确认：

- 自托管 Business/Enterprise 功能和离线许可；
- SAML、安全审计、源代码可得性与 licensed image 供应；
- PostgreSQL、Redis、对象存储和升级依赖的完整离线镜像；
- 当前许可证与组织修改/分发/长期维护要求。

在获得明确证据前，不因 UI 更漂亮就优先于具备明确离线合同的候选。

### 7.3 Wiki 页面永不自动成为真相

```text
Wiki/DMS SourceRevision
  + content digest
  + classification
  + ACL snapshot
  + source identity
  + owner/effective period
  + human release receipt
          ↓
KnowledgeVersion
```

页面编辑、移动、打标签和链接只产生新候选。Agent 只能解析任务时冻结且当前有效的
KnowledgeVersion；冲突、过期、撤销、ACL gap 或锚点缺失返回 `cannot_confirm`。

## 8. Open WebUI 的正确位置

Open WebUI 可以作为受限模型实验 sidecar，但不进入首版生产必需组合：

- 权限模型不能替代 FLAi 的 deny、classification 与强制访问控制；
- audit 不能替代不可变 Evidence Ledger；
- Functions、Tools、Pipelines 等可执行扩展不能直接接触 CFD/FEA 主机、生产文件或 Secret；
- `OFFLINE_MODE` 不等于网络隔离，模型、Embedding、Rerank、Whisper 和插件必须预置；
- 品牌、活跃用户和商业许可要求需要单独法务/采购确认。

若部署，只允许通过 FLAi Model Gateway、Knowledge Gateway 和 Tool Gateway，并放在独立
Sandbox/网络策略中。其会话不成为权威任务、知识或审计事实。

## 9. 旧系统考古与新信息入口

### 9.1 旧系统

旧 OA、eSpace、UME、邮件和文件服务器按来源逐一调查：

1. 确认业务 owner、系统 owner、合法接口和数据分类；
2. 先建只读 Adapter，不使用 UI 爬取绕过权限；
3. 保留原始 actor、recipient、ACL、revision、时间、digest 和来源深链；
4. 首次只导入公开/内部级的小样本，验证召回、引用、撤权和删除；
5. 未经具名发布的历史材料保持工作材料或受控参考；
6. 不以“大模型能读到”冒充“组织已经沉淀”。

### 9.2 新信息

新内网项目默认在 FLAiWorkspace 中创建项目空间。讨论、会议、文档、代码引用、Agent 任务、
决策和责任事项从产生时就带项目 context、分类和来源。AI 可以总结和提取候选，但正式决定、
知识发布、责任签发和工程结论仍由真人完成。

## 10. 连续性与安全生存

协作/Wiki Adapter 故障时：

- 新消息、页面编辑和普通通知可以暂停或降级；
- FLAi Control Kernel 继续执行已授权任务并记录本地 evidence；
- kill、revoke、isolate、credential invalidation 和 WORM 封存不能被阻断；
- 投影显示 stale/gap，不使用缓存冒充最新事实；
- Adapter 恢复后按 source revision 和原幂等键对账，不按最后写入者覆盖。

每个候选必须完成：

- 完全断网冷启动；
- 节点故障、数据库恢复、附件恢复和索引重建；
- IdP 暂时不可用与撤权传播；
- 备份加密、介质 custody、RPO/RTO；
- 升级失败和已验证版本回滚；
- 许可证过期/验证服务不可达；
- 插件、市场、遥测、外链和远程字体全部禁用。

## 11. 隔离 POC 验收

首轮只做候选 POC，不修改 FLAi 生产 Schema。环境必须无公网默认路由、无公共 DNS、无 Feishu
配置、无 GitHub token、无公共 Registry 和无云模型。

### 11.1 通讯 Adapter

1. 内网 IdP 登录、撤权、项目 membership 和私有频道；
2. 中文线程、搜索、附件、通知和桌面客户端；
3. classification ceiling、存在性抑制和跨项目 BOLA/IDOR；
4. 消息 revision/delete/retention 与 FLAi 投影对账；
5. Outbox 重放、幂等、event gap 和 effect unknown；
6. 数据库/附件备份恢复和许可证离线连续性；
7. 插件/marketplace/telemetry/外链均不能产生外连。

### 11.2 知识 Adapter

1. page/attachment revision、完整 digest 与精确锚点；
2. LDAP/OIDC group、页面规则、继承和撤权；
3. 离线 sideload、全文检索、备份恢复和版本升级；
4. 页面 drift 后旧 KnowledgeVersion 不被覆盖；
5. ACL unknown、来源缺失、冲突和过期返回 `cannot_confirm`；
6. AI 摘要不能自我发布，Wiki 管理员也不能绕过 Knowledge signer；
7. 外链、远程图片、脚本、宏和存储 module 默认拒绝。

### 11.3 Workspace

1. 用户只经一个 FLAiWorkspace 完成“开始、讨论、执行、检查、交付”；
2. Stage C 中央时间线与右侧对象由真实 observer state 驱动；
3. 协作/Wiki 品牌和对象名不泄漏为 FLAi 领域概念；
4. Adapter 可被内存 fake 替换，核心项目/运行/知识测试不依赖第三方；
5. Feishu/GitHub/Kimi 全部不可达时，内网完整主流程仍可运行；
6. REAL/MOCK/TEST/UNKNOWN、waiting_review、completed、failed、cancelled 语义不变。

## 12. 决策门

| 门 | 所需决定 | 当前 |
|---|---|---|
| I0 架构 | FLAiWorkspace、Ports、事实 owner、AirGapExchange | `CONFIRMED-IN-DESIGN-SESSION` |
| I1 采购/法务 | 通讯与知识候选的许可、出口、AGPL、支持 | `DECISION-REQUIRED` |
| I2 安全 | IdP、ACL/classification、审计、离线更新、Secret | `DECISION-REQUIRED` |
| I3 隔离 POC | 无外网冷启动、权限、恢复、升级、性能、中文 UX | `NOT-RUN` |
| I4 Adapter 实现 | 精确 Interface、fixture、版本和 owner | `NOT-AUTHORIZED` |
| I5 非敏感试点 | 数据、人员、范围、时间、退出与责任 | `NOT-AUTHORIZED` |
| I6 生产 | 七域证据、恢复演练、具名签发 | `NO-GO` |

## 13. 官方参考

- [Mattermost Air-Gapped Deployment](https://docs.mattermost.com/deployment-guide/reference-architecture/deployment-scenarios/air-gapped-deployment.html)
- [Mattermost Editions and Offerings](https://docs.mattermost.com/product-overview/editions-and-offerings.html)
- [Mattermost Certifications and Compliance](https://docs.mattermost.com/product-overview/certifications-and-compliance.html)
- [Mattermost Compliance Export](https://docs.mattermost.com/administration-guide/comply/compliance-export.html)
- [Rocket.Chat Air-Gapped Deployment](https://docs.rocket.chat/docs/rocketchat-air-gapped-deployment/)
- [Rocket.Chat Plans](https://docs.rocket.chat/docs/our-plans)
- [Wiki.js Internet and Offline Requirements](https://docs.requarks.io/install/requirements/internet)
- [Wiki.js Authentication](https://docs.requarks.io/auth)
- [Wiki.js Groups and Permissions](https://docs.requarks.io/groups)
- [Wiki.js Releases](https://docs.requarks.io/releases)
- [Outline Business and Enterprise](https://docs.getoutline.com/s/hosting/doc/business-enterprise-rv0715NxO3)
- [Open WebUI RBAC](https://docs.openwebui.com/features/authentication-access/rbac/)
- [Open WebUI Hardening](https://docs.openwebui.com/getting-started/advanced-topics/hardening/)
- [Open WebUI Plugin Security](https://docs.openwebui.com/features/extensibility/plugin/)

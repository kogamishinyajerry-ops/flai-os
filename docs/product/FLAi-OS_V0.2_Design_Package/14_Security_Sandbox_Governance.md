# FLAi-OS V0.2 安全、Sandbox 与治理

> 文档性质：面向中国国企内网、macOS 首发的安全设计与上线门禁。
> 本文件不构成安全认证、等保/密评结论或上线授权；没有机器证据的控制均不得写成“已具备”。
> 现状证据基线来自本设计周期的 OpenClaw / WorkBuddy / FLAi-OS 安全治理研究、
> [生产就绪纲领](../../PRODUCTION-READINESS-PROGRAM.md) 和已接受 ADR。研究稿尚未进入本隔离基线，因此只作外部设计证据，不作为本包 SSOT；正式验收 Stage C 或申请 Stage D 前必须按精确 digest 导入或登记。

## 1. 状态标签与总判定

| 标签 | 本文含义 |
|---|---|
| `IMPLEMENTED-VERIFIED` | 当前精确范围、版本与环境有可复跑机械证据，绑定命令、结果引用和日期；不等于生产就绪 |
| `IMPLEMENTED-PARTIAL` | 有真实控制，但覆盖面或生产证据不完整 |
| `ACCEPTED-NOT-IMPLEMENTED` | 方向已接受，尚未授权或完成实现 |
| `DECLARED-NOT-VERIFIED` | 仅有声明、配置或历史证据，尚未在当前目标环境验证 |
| `OUT-OF-SCOPE` | 不属于当前阶段 |

**当前总判定：正式试点 `NO-GO`。**

原因不是平台没有任何安全基础，而是对象级授权、敏感附件、真正执行隔离、运行中 kill、统一出站、队列租约、终态假绿、防篡改审计和离线供应链仍存在 P0 未闭合项。已有登录、文件夹隔离、线程超时、`task_events` 或备份脚本都不能单独抵消这些缺口。

## 2. 安全目标

FLAi-OS 的安全模型不是“每一步都弹窗”，而是把复杂治理放进后台可验证机制：

1. 用户提交目标后，系统在受控会话中连续完成可逆工作；普通用户不逐命令、逐工具批准。
2. 每个动作都由统一策略 seam 依据认证主体、对象、项目、分级、能力和策略版本判定。
3. 不可逆外部效果被推迟到精确 Delivery Bundle，由具名真人末端一次授权。
4. 不可信 workflow、Tool、Skill、附件和检索内容不能与控制内核同权。
5. 执行必须可隔离、可强杀、可追溯；控制失效时 fail-closed，不能自动降级 Full Access 或 host exec。
6. 人是唯一签发者；LLM 不进入授权、工程判决、知识发布、评测晋级或路线图签发链。

## 3. 威胁模型

### 3.1 保护对象

- 内网工程文件、规章、领导指令、会议决定和权威知识版本；
- 用户、项目、部门和职责委派关系；
- Agent/Tool/Prompt/Workflow/Schema、模型与 Sandbox 策略；
- 任务状态、输入输出、评测、晋级、交付和审计证据；
- 模型、工具、Connector 与 CAE 系统凭据；
- 离线安装包、SBOM、签名、构建 provenance 和恢复介质。

### 3.2 不可信输入与主体

- 普通认证用户可能越权访问其他用户或项目对象；
- 上传文档、会议记录、网页、知识片段可能含提示注入或恶意载荷；
- Agent workflow、Tool adapter、Skill、插件和第三方执行后端按不可信代码处理；
- 模型输出可能错误、伪造依据、建议危险动作或尝试扩大权限；
- 失联 worker、晚到 writer、重复提交和恢复重放可能破坏状态；
- 内部管理员、维护者或签发者也可能误操作，因此高风险动作需要职责分离、最小权限和不可抵赖证据。
- 外网 Feishu/GitHub 事件与身份可能被误用为内网授权，或成为隐蔽实时跨域通道；
- 内网通讯/Wiki/项目 Surface 的事件、字段、成员关系和深链参数可能被伪造、重放、越权或
  因旧权限变得 stale；目标 Surface 也可能不具备目标 classification 承载资格；
- 离线发布包可能被篡改、夹带未声明 payload、恶意依赖、压缩炸弹、路径穿越、过期签名、
  不完整 SBOM、许可证风险或自报信任根；
- 外网 App/Connector Secret 虽已声明迁入 `secrets-stackdocker`，运行路径、旧值撤销、
  最小引用、轮换和 provider 故障行为尚未验证；内网必须使用独立 Secret owner，Safety
  signing material 另属独立 PKI/HSM owner。

### 3.3 不成立的假设

- “在内网”不等于可以忽略对象授权、出站或供应链攻击。
- “已登录”不等于可以访问所有 task/conversation/file/eval。
- “禁用写工具”不等于只读，只要 `exec/process` 存在就可能写文件或发网。
- “有 Docker/临时目录”不等于真正 Sandbox。
- “用户点了同意”不等于动作、参数、策略和产物精确匹配。
- “测试全绿”不等于没有假绿，必须有 invalid-first 与 tamper witness。
- “协作 Surface 里能看见/能点击”不等于拥有对象权限、签发资格或 owner commit 成功。
- “GitHub merge/外部签名/介质已导入”不等于内网已准入、已资格、已部署或 REAL。
- “现有 App/Connector key 已迁移”不等于其 Secret 生命周期、最小权限、审计与恢复已经通过，也不证明尚未实现的 Safety signing key 已部署。

## 4. 当前 P0 阻断项

| Gate | 当前状态 | 未闭合事实 | 正式试点硬门 |
|---|---|---|---|
| P0-0 可复现发布候选 | `DECLARED-NOT-VERIFIED` | 当前工作树混合，历史与候选证据不能混用 | clean worktree、全量验证、release SHA、制品 hash 可复算 |
| P0-0B 决策与准入来源 | `DECLARED-NOT-VERIFIED` | ADR 的设计会话确认不等于组织签发，尚无绑定 actor/scope/time/digest 的正式决策记录 | 实施与 Phase 0A 所需决定分别有 `formally_signed` 记录；AI/文档/Git commit 不代签 |
| P0-1A 统一对象授权 | `ACCEPTED-NOT-IMPLEMENTED` | 治理写入口、tasks/conversations/files/feedback 等存在 BOLA/IDOR 风险 | 所有资源动作过同一 actor/action/resource seam，commit-time recheck |
| P0-1B 敏感附件封口 | `ACCEPTED-NOT-IMPLEMENTED` | sensitive 文件可能通过会话附件路径进入模型上下文 | owner/project/classification/capability 双检，拒绝后无 model call |
| P0-2A 真正 Sandbox | `ACCEPTED-NOT-IMPLEMENTED` | workflow/adapter 仍可能在 worker 进程执行；工作目录不是隔离 | OS/虚拟化强制文件、网络、资源、进程边界，能力不可证即拒绝 |
| P0-2B 运行中 kill 与撤权 | `ACCEPTED-NOT-IMPLEMENTED` | running cancel、授权撤销、子进程树、既有连接与已注入凭据失效不完整 | Broker 强杀进程树，Egress/Secret 同步吊销，termination/revocation witness 可复算 |
| P0-3A 并发/租约/背压 | `ACCEPTED-NOT-IMPLEMENTED` | job、eval、Tool/provider 配额不统一，degraded 时仍可能接纳 | durable lane/budget/admission/lease/cancel，真实 readiness |
| P0-3B 终态 CAS | `ACCEPTED-NOT-IMPLEMENTED` | 恢复或晚写可能出现 `error/failed → completed` | 所有终态写绑定 active lease + expected version，晚 writer 被拒 |
| P0-4A 出站与凭据 | `ACCEPTED-NOT-IMPLEMENTED` | 缺 task-aware allowlist、SecretRef、目标 witness | 默认无网、受控代理、短期凭据、每次出站有策略和结果证据 |
| P0-4B 审计防篡改 | `ACCEPTED-NOT-IMPLEMENTED` | 本地 JSONL/SQLite 可变，关键状态与审计非完全原子 | audit outbox 同事务、hash chain、独立 append-only/WORM、校验演练 |
| P0-4C 离线供应链 | `DECLARED-NOT-VERIFIED` | wheel/cache、依赖 hash、SBOM、组织签名、断网安装不足 | quarantine、固定摘要、签名/验签、完全断网安装、回滚证据 |
| P0-5 macOS 本机门 | `DECLARED-NOT-VERIFIED` | 睡眠唤醒、故障恢复、Sandbox/kill、代理证书与 novice 路径未证 | 固定 macOS/Apple Silicon 基线全链验收 |
| P0-6A 内网身份与治理入口 | `ACCEPTED-NOT-IMPLEMENTED` | 无可信 Internal IdP/Surface→ActorBinding、prepare/commit、提交时重验和 owner receipt | instance/subject 防伪、防重放、职责/ACL/classification、exact digest 与 receipt 全链 |
| P0-6B Workspace 故障与安全生存 | `ACCEPTED-NOT-IMPLEMENTED` | 唯一日常入口会形成协作单点；kill/revoke 不得依赖它 | Workspace/协作/Wiki 断开时新治理暂停；独立 SafetySurvivalPort 仍可止损与本地 WORM 封存 |
| P0-6C 双域与离线准入 | `ACCEPTED-NOT-IMPLEMENTED` | 外网研发与内网运行尚无机械隔离和 closed-world Bundle verifier | 无实时链路；quarantine、内部扫描/复测、双人准入、ReleaseSet CAS 与最小反馈出口 |

只有 P0 全部有当前候选版本的机器证据，并由具名 owner 末端签发，才允许 Phase 0A 正式试点。任何一项 `unknown/failed/invalid/skipped` 都是未通过。

## 5. 统一授权与 BOLA/IDOR 防护

### 5.1 唯一 Policy seam

- **状态**：现有认证和局部角色门 `IMPLEMENTED-PARTIAL`；统一对象授权 `ACCEPTED-NOT-IMPLEMENTED`。

```text
authorize(actor, action, resource, request_context, policy_version)
  -> deny | defer_to_delivery | auto_execute
```

最小对象：request/session/CanonicalTaskGraph、task、conversation、file/artifact、feedback、Grant/QueueLease/ExecutionRun、agent/tool/connector、eval/Bench、sample、typed promotion/qualification、CapabilityReleasePackage/DeploymentBinding、knowledge、delivery/attempt/receipt、demand/roadmap、audit view、project membership。最小动作：read、list、search、export、aggregate、write、execute、cancel、review、approve、publish、revoke、audit。

强制规则：

1. `actor_id/subject_id` 是权威键，display name 只展示。
2. resource 同时带 owner、project、classification、visibility 和版本。
3. API、后台任务、自动恢复、附件装配、会话模型上下文和治理写入共用同一 seam。
4. 策略层只能单调收紧；空 allowlist 表示无能力，不退回全开放。
5. 发起时允许不够；在事务提交和不可逆效果前必须重检 actor live、role/membership、Grant 与 policy version。
6. 前端隐藏按钮、路由前缀或会话 ID 不是授权。
7. deny 写入脱敏审计，不泄露受限对象内容。
8. 集合查询必须在 SQL count、过滤、排序、分页和聚合之前应用对象 scope；禁止通过总数、时间序列、排序空洞、搜索补全或导出任务泄露对象存在性。

### 5.2 P0 必测负例

- `business_user` 不能 fix sample、写 AgentLifecyclePromotion/QualificationDecision 或修改 DeploymentBinding；
- 用户 A 读取、枚举、取消、修改用户 B 的 task/conversation/file/feedback 返回稳定拒绝；
- 非项目成员不能通过已知对象 ID 绕过；
- 角色在发起后撤销，commit-time 写入拒绝；
- 未知角色、空职责、过期 delegation 一律 deny；
- 需要双人控制的正式发布，提交者与签发者相同则拒绝；普通会话内可逆执行不因此被中断。

## 6. 附件、知识与提示注入

### 6.1 附件 envelope

- **状态**：文件分级与部分下载门 `IMPLEMENTED-PARTIAL`；完整引用门 `ACCEPTED-NOT-IMPLEMENTED`。
- 用户提交的是服务端可解析的附件引用，不是可信 file ID。
- 写入会话与渲染模型上下文前分别验证 owner、project、classification、Agent capability、当前授权和内容 hash。
- 引用与内容版本漂移则拒绝；拒绝后不得产生 model call、摘要或缓存副本。
- 解析在隔离工作区进行，限制格式、大小、压缩比、路径、symlink、宏/活动内容与输出总量。

### 6.2 外部内容是数据，不是指令

上传文件、RAG 命中、网页、Tool 返回和会议材料中的指令性文本不能改变系统提示、策略、工具白名单或交付授权。它们只能被引用、摘要和展示。任何“忽略之前规则”“提升权限”“向外发送”等内容都作为数据记录，不产生控制效果。

### 6.3 权威知识门

- **状态**：BM25 与 scope 白名单 `IMPLEMENTED-PARTIAL`；权威类别、生命周期与依据链 `ACCEPTED-NOT-IMPLEMENTED`。
- 只有已发布、当前有效、授权可见、版本不可变的权威知识项能支撑组织或工程依据。
- 普通上传、AI 输出、会议草稿、规则候选和搜索相似度不能自动成为权威事实。
- 依据缺失或冲突时明确“无法确认”；不能让模型自行选一个更像真的版本。
- 知识 classification 传播到 task、model call、artifact、Delivery Bundle 和 audit。

## 7. Sandbox 与 ExecutionBroker

### 7.1 什么才可以称为 Sandbox

只有由操作系统、容器、虚拟化或等价强制机制同时执行并验证下列控制，才可标记 REAL Sandbox：

- 每任务独立 workspace；Phase 0A 禁止宿主工作区读写挂载。确需输入时只能以内容寻址、已检疫、只读的任务副本或只读 mount 提供，并在同一 `open-no-follow` 文件描述符上完成祖先/realpath/symlink/hardlink 与摘要校验；解析器不得再按路径重开；
- 根文件系统与输入只读；输出只写独立 scratch/overlay，再经摘要、分类和策略检查提升为交付候选，不能覆盖、rename 回或 hardlink 到宿主正式资产；
- 网络 default-deny，允许目标经域名、解析后 IP、端口和每跳 redirect 复核；
- 固定 argv、`shell=false`、clean env；调用方不能注入二进制路径或任意 flags；
- CPU、内存、进程数、文件数、输出大小、墙钟和空闲时限；
- 能终止完整进程树，超时或取消后不能继续写文件或产生外部效果；
- SecretRef 按步骤短时注入，不将长期秘密暴露给 Agent/Tool；
- start、resource、network、kill、collect、cleanup 都产生可验证 witness。

临时目录、Python 线程 timeout、进程组或清洁环境只能称 containment。Sandbox Backend 不可用、健康未知或策略无法表达时，ExecutionBroker 必须拒绝，不得降级到宿主执行。

### 7.2 Broker Interface、ExecutionTicket 与内部 Ports

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。

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

Control Kernel 只依赖 Broker Interface；Broker 内部组合三类不可互换的 Port：`AgentRuntimePort`（Built-in/OpenClaw/OpenHands）、`SandboxProviderPort`（MacSandbox/测试实现）和 `ToolExecutionPort`（Python/Office/CAE/HPC）。Agent Runtime 每次动态 replan、Tool、Model、Knowledge 或 Connector 动作只能提交 `StepProposal`；Kernel 针对 step digest、Grant、policy、`credential_epoch + authorization_epoch_snapshot[] + trust_policy_epoch/digest`、lease id/generation、能力/目标、预算、有效期与 nonce 签发短时 `ExecutionTicket`。所有下游边界无票拒绝并返回 receipt，Adapter 无权写权威终态、授权或签发。移除任一 Adapter 不得改变任务、审计、评测和交付语义。

### 7.3 macOS 首发门

- **状态**：`DECLARED-NOT-VERIFIED`。
- 首期只验收 `SandboxProviderPort` 的 `MacSandboxAdapter`；Windows Adapter 为 `OUT-OF-SCOPE`。
- 固定支持的 macOS 与 Apple Silicon 版本，验证启动、睡眠/唤醒、强制退出、升级/回滚和并发。
- 验证越界读写、symlink escape、fork child、超时后继续写、网络访问、伪造二进制、kill 后副作用全部失败。
- macOS 威胁模型必须显式覆盖并默认拒绝：宿主 Unix socket、Mach port/service、XPC、Apple Events/Automation、Accessibility 与其他 TCC 受保护能力、Keychain access group、launchd、Launch Services、剪贴板、摄像头/麦克风、调试器/core dump，以及父进程继承的文件描述符、环境与句柄；只有逐项声明、最小授权并有负例证据的通道才可开放。文件边界负例必须包含 symlink、hardlink、rename、`dirfd/openat`、TOCTOU 与输出回链宿主。
- API、Model Gateway、Tool/Connector Adapter 等控制面与数据面进程都不得绕过 Egress Gateway 直接建连；固定基线必须验证最小 entitlements、无 Full Disk Access/Accessibility、隔离 uid、关闭非必要继承 FD 和本地 IPC。
- 验证无管理员常驻权限、无 Docker socket 暴露给 Agent、无 production `elevated/host exec`。

## 8. 出站网络与 SecretRef

### 8.1 四层出站控制

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。

1. Sandbox/VM 网络默认无网；
2. egress gateway / 防火墙强制所有允许流量经过受控路径；
3. 企业正向代理按声明式域名、解析后 IP、端口和协议决定；
4. 应用层做 SSRF、DNS 重绑定、redirect 和 metadata/private range 校验。

批准对象是目标集合和动作类别，不是任意 URL。模型、Tool 和 Connector 都绑定 task classification、policy ID、最大 body、超时、并发、重试和字段允许清单。DNS/CONNECT/拒绝原因和流量量级进入审计；认证头、Cookie、Secret 值和无必要正文不得记录。

### 8.2 SecretRef 与分域

- **合同状态**：`ACCEPTED-NOT-IMPLEMENTED`；外网 `secrets-stackdocker` 与内网 Secret owner
  Adapter 状态均为 `DECLARED-NOT-VERIFIED`。
- 外网研发与内网运行使用独立 Secret owner/instance/root/namespace/policy/backup；配置只保存
  同域 opaque `SecretRef`，序列化示例 `secret://provider/scope/name@version` 不代表真实名称。
  `secrets-stackdocker` 当前只属于外网研发域，不能向内网复制 value 或真实 SecretRef identity。
  人的安全硬件身份、Safety receipt-signing、Coordinator / target owner / Policy owner 三类
  workload-attestation material、Egress Boundary/Wire 两类 operation-bound material、
  Policy-fence 和 Trusted-Time Authority/Commit-Guard material 分别由独立 Safety Identity /
  PKI / HSM / Time owner 持有，各 operation 不得互相代签，也不得由普通 Secret 栈解析。
- Secret 在 Broker/Egress Proxy 最终边界解析为短期凭据；启动或快照切换原子化，required ref 解析失败则拒绝。
- 未知哨兵、明文残留、过期版本或 provider 不可用在任何网络活动前 fail-closed。
- 日志同时做 exact-value 与结构化字段脱敏；记录 Secret identity/version，不记录值。SecretRef identity 本身可能暴露系统、项目或权限范围，普通工作台只显示脱敏别名，完整 identity 仅对具备 `secret.audit` 作用域的治理角色可见且导出受控。
- 禁止回退历史 `.env`、硬编码字面量、宿主全局 Keychain 或 Agent 可见环境；Secret value 不
  进入 Feishu、GitHub、内网协作/Wiki、OfflineReleaseBundle、intent、receipt、fact digest、
  日志、LLM prompt、Tool stdout 或测试 fixture。
- 轮换必须使 token cache、长连接、旧 lease 与相关 credential/authorization epoch 失效，并形成访问、拒绝、轮换、吊销与恢复 witness。
- bootstrap/unseal/recovery 凭据与 Connector Secret 分离；备份/恢复不得导出明文。

## 9. 并发、队列、租约与取消

- **状态**：现有 SQLite Job Runner `IMPLEMENTED-PARTIAL`；统一治理 `ACCEPTED-NOT-IMPLEMENTED`。

### 9.1 必需合同

- durable lane：至少表达 session、project/user、Agent、Tool、provider/egress；
- budget：max queued/running、CPU/内存、外部调用、输出与磁盘预算；
- admission：在接纳前返回 accepted/rejected/deferred 和稳定 reason code；
- lease：owner、generation、heartbeat、expires_at、version；
- cancellation：requested、observed、terminated 三个不同事实；
- idempotency 与 side-effect class；
- readiness：真实反映 DB、worker generation、queue/broker、audit sink 和关键依赖。

### 9.2 不变量

1. 每会话至多一个 active run；运行中新增输入形成新版本，不注入已授权快照。
2. Tool manifest 的并发声明必须实际执法，不能只展示。
3. 队列满、磁盘预算不足或 worker degraded 时不继续无限接纳。
4. 终态更新绑定 active lease、generation 和 expected version；旧 worker/晚 writer 写入失败。
5. 只读或可证明幂等步骤可在新 lease 下重试；未知/外部副作用进入 `needs_reconciliation`。
6. running cancel 必须到 Broker/进程树并产生 termination witness；只改数据库状态不等于取消成功。
7. 普通协作/工作负载 Identity、Authorization 与 Supply-chain 分别唯一拥有各自的 credential、authorization partition 与 trust-policy epoch；独立 Safety Identity / PKI / HSM 另行拥有 EmergencyActorAdmission credential/key epoch，Kernel 只消费其 attestation。Grant 只冻结 `ExecutionEpochSnapshot`。账号/会话、Grant/职责/策略或供应链信任状态撤销时，对应 owner 必须以 CAS 提升 epoch，并在同一事务写 `revocation_id`、受影响 lease selector、CancellationToken 与 invalidation outbox；停止新 claim，把绑定旧快照的 active lease 送入 Broker 强杀，并使已注入短期凭据和既有出站连接失效。发行策略必须冻结从 revoke commit 到 worker/Broker 观察、进程树终止、凭据/连接失效的最大 SLA；`RevocationAttempt` 分别收集 termination/credential/connection witness。超时、缺失、目标 epoch 不符或任一 witness unknown 即 `revocation_incomplete/needs_reconciliation`，禁止交付、恢复和重试。

### 9.3 假绿负例

- 同步 eval 不能绕过 quota；
- `error/failed/cancelled → completed` 的晚写必须被 CAS 拒绝；
- lease 过期后旧 worker 不能继续注册产物或完成任务；
- cancel 后子进程继续写输出必须使 Gate 失败；
- 角色/Grant 在进程运行、连接已建立或 Secret 已注入后撤销，旧进程、连接或凭据仍可产生效果必须使 Gate 失败；
- `unknown` readiness 不能被 UI 显示为健康。

## 10. 审计与不可抗抵赖

### 10.1 当前边界

`task_events`、`tool_runs`、`model_calls` 和部分日志是真实业务证据，状态为 `IMPLEMENTED-PARTIAL`。它们目前不能被称为合规防篡改账本：本地 SQLite/JSONL 可由高权限主体修改，覆盖面、原子性、外部留存和验证演练尚未闭合。

### 10.2 目标审计链

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- 严格 event Schema、分区内单调 sequence、`prev_hash/event_hash`；实施规格必须冻结分区键、并发序列化、可信时钟来源、跨段/跨分区 seal 和缺口语义；
- actor/request/task/session/plan/policy/approval/execution/receipt 关联；
- grant/revoke、登录、拒绝、对象读取、治理写入、策略/配置/包变更、执行、kill、网络、SecretRef、交付、导出全部覆盖；
- 强治理状态与 audit outbox 同一 SQLite 事务；
- outbox 送往独立 append-only/WORM sink；它是不可变 evidence mirror/archive，不是第二写模型或状态裁决源。数据只从权威事务 outbox 单向投递，恢复时用于验链与对账，禁止自动反写业务终态；metadata 与敏感正文分层授权和留存；
- 定期 seal、验链、导出、告警、备份和恢复演练；
- 每个发行物冻结 `max_unacked_events/max_unacked_age`、WORM ack、seal/checkpoint 和告警阈值。sink 不可用但本地 outbox 仍原子可写且未超预算时，只允许策略明确的短时收容；超阈值后停止新执行、交付和治理写，只保留授权只读与 kill/revoke 等安全处置。若本地 outbox 本身不可写，所有状态改变 fail-closed，紧急强杀仍尝试但健康必须为失败且事后 reconciliation。

`phase0a-macos-v1` 精确冻结 `sink_ack_deadline=5s`、`max_unacked_events=100`、`max_unacked_age=30s`，seal/checkpoint 每 100 个事件或 60 秒（先到者）执行。任一阈值未知、配置未进入 release/environment policy digest、缺 ack、迟到或断链都不能通过 Entry；不得以“稍后补传”无限延长收容。

哈希链不等于 WORM，WORM 也不自动证明主体真实、时钟可信或事件完整。时间同步、签名密钥、轮换、吊销、留存年限、SIEM/WORM 产品与审计读取职责仍需组织裁决。

### 10.3 不记录内部思维链

审计记录输入摘要、规则/策略 refs、动作、工具/模型调用、结果和证据，不记录或声称还原 LLM chain-of-thought。若需要决策证据，使用有限 `decision_code` 和可解析 evidence refs，禁止自由文本“推理轨迹”冒充真实思考。

## 11. 评测治理与防假绿

- **状态**：现有 Eval Runner `IMPLEMENTED-PARTIAL`；完整 FLAi Bench 安全门 `ACCEPTED-NOT-IMPLEMENTED`。

1. 评测对象是冻结能力发布包，不只是 Agent version；模型、Tool、Adapter、Sandbox、权限、出站、知识与 rubric 都进入 digest。
2. 四轨结果独立：确定性回归、工程质量、安全治理、运行效率；不折算可互相抵消的总分。
3. 安全、诚实性、依据链和关键回归是绝对门；`failed/invalid/skipped/unknown` 均不能通过。
4. `honesty/traceability` 使用严格布尔，绝不 truthiness。
5. LLM-as-Judge 只能诊断；AI 不能批准金标准、晋级或签发。
6. Eval case 资产 `draft → approved → retired`，真实/synthetic 和 classification 明确。
7. 运行与真实 Runtime、Tool、Broker、Audit 同源；旁路脚本不能作为发布证据。
8. terminal CAS 防止恢复/晚写把失败翻绿；promotion 引用精确 release/bench digest。

P0 安全评测至少覆盖：BOLA/IDOR、附件旁路、提示注入、越界文件、symlink、网络、Secret 泄漏、进程树强杀、终态竞态、审计缺口、未知门、Mock 冒充 REAL、AI 自签发和历史评测错误继承。

## 12. 供应链与离线交付

### 12.1 Package Quarantine

- **状态**：Agent/Tool Package Schema `IMPLEMENTED-PARTIAL`；完整供应链 Gate `ACCEPTED-NOT-IMPLEMENTED`。

Agent、Tool、Skill、Connector、AgentRuntime/SandboxProvider/ToolExecution Adapter 和离线制品统一经过：

1. 离线导入 quarantine；
2. 路径、realpath、symlink、压缩炸弹、文件类型和大小检查；
3. manifest/Schema 严格校验，未知键拒绝；
4. package digest 覆盖 workflow、prompt、schema、adapter、依赖和能力引用；
5. 依赖锁、wheel/npm cache、许可证、SBOM、漏洞与恶意模式扫描；
6. 具名组织签名和签发记录；
7. 隔离环境运行合同、负例和 tamper；
8. 按 digest 进入批准目录，升级产生新版本，不原位漂移。
9. 信任根、签名门限、最低允许版本、签名密钥轮换/吊销和反回滚策略版本化；正式发布采用适用的职责分离/双人签发；
10. Registry 装载时、任务快照冻结时和每次执行前重验 package digest、签名链、最低版本与吊销状态；Grant、Ticket、Lease 和 ExecutionRun 绑定 `trust_policy_epoch/digest`。签名失效、低于当前版本 floor、信任根/门限策略变化、签名密钥吊销或任何校验非明确 valid 时，停止新 claim，并以 invalidation outbox 在冻结 SLA 内终止所有绑定旧 trust snapshot 的 active lease，产生 termination/reconciliation witness；缓存命中不能跳过执行时验签。

“可发现、可安装、可执行、可自动运行”是四个不同状态。运行节点禁止访问公共包市场、ClawHub、npm 或 git，不使用 `latest`、branch 或运行时下载。

### 12.2 macOS 离线发布门

- 固定源码提交、构建环境、backend/frontend/contracts/agents/tools/镜像/应用制品摘要；
- SHA-256、数字签名、SBOM、许可证与批准记录齐全；
- 断开互联网 DNS 和默认路由后完成安装、启动、模型/工具调用、审计导出；
- 缺镜像、依赖、证书或制品时退出，不隐式 pull/build 或写错误配置；
- 升级/回滚、数据库迁移、备份/恢复、签名吊销均有演练；
- Windows `.ps1` 和 Windows Adapter 为 `OUT-OF-SCOPE`，不阻断本阶段 macOS 质量收口。

## 13. 数据分类、最小化与隐私

- **状态**：`internal|sensitive` 与部分不可变分级 `IMPLEMENTED-PARTIAL`；完整数据域策略 `ACCEPTED-NOT-IMPLEMENTED`。
- 任务在产出任何内容前确定 effective classification 并 CAS-on-NULL；所有派生事件、调用、产物、知识引用和审计继承。
- 未知 Tool、历史来源不可考、Adapter 无法证明或 classification 缺失时 fail-closed。
- 全员共建地图只显示团队聚合；小样本可识别时抑制/合并；个人任务、反馈、节时样本只对本人及授权治理角色可见。
- Token 是资源成本，不做个人生产力榜；无价格表不显示成本，无节时基线不显示节省时间。
- 在正式组织密级与改级流程明确前，不增加只有标签没有执法语义的新等级。

## 14. 人签、职责分离与不中断体验

### 14.1 会话内

策略在后台自动判定 `auto_execute | defer_to_delivery | deny`。可逆、已隔离、可强杀且有执行凭据的动作连续执行；普通用户不审批 Bash、文件或每个 Tool。策略禁止或无法安全暂存的动作记录为聚合 blocked，不通过放宽 Sandbox 继续。

### 14.2 末端交付

只有任务交付副作用且 Policy 结果为 `defer_to_delivery` 时，才以 PendingDeliveryAction 进入不可变 Delivery Bundle；`deny` 永不可覆盖。知识发布/撤销、能力资格/发布、路线图签发和 break-glass 使用各自 typed governance command，Agent 调用一律 deny，不能被通用 Bundle 吞并。具名真人对精确 bundle digest 一次授权；主体、职责、策略、参数、产物、期限或 digest 漂移均 fail-closed。消费 Authorization、建立唯一 DeliveryAttempt 和全部 ActionIntent 必须同一事务完成；动作以稳定 effect key 和 CAS 执行 `prepared → executing → succeeded|failed|effect_unknown`。外部调用后、receipt 落库前崩溃一律为 `effect_unknown`，未经外部查询/receipt 对账不得重放，重新授权也不得换 key 绕过。多动作部分成功保持 `partially_applied/needs_reconciliation`，只有全部动作及后置验证成功才能显示“已交付”；不能用“已批准”冒充“已成功”。

内网 FLAiWorkspace 只承载上述审阅与 typed intent Surface。高影响动作在
InternalWorkspaceHub `prepare` 后冻结
PreparedCommand 并返回绑定 payload/target/actor/epoch/assurance/policy/gate digest 的
ReviewChallengeV1；`commit` 使用新鲜 channel attestation/step-up、CAS 单次 nonce，并重新
检查 actor binding、职责、scope、ACL、classification、epoch、TTL 和职责分离；只有相应
owner 返回并由 owner-specific verifier 验证通过的 OwnerCommitReceiptV1 才显示生效。

### 14.3 职责分离

- Agent/LLM 永不签发；
- 高风险 promotion、正式发布、break-glass 与适用的知识发布至少满足具名职责分离；
- Demand Curator 无权采纳路线图；领域/安全评审缺失或 false 时 Roadmap Owner 不能签发；
- Delivery Owner 不能以代码合并或自测自行宣布需求解决；
- 现有 `admin|agent_developer|business_user` 可作试点近似，但不能冒充最终治理模型。

## 15. Break-glass 与事故处置

- **状态**：`ACCEPTED-NOT-IMPLEMENTED`。
- production `host exec/elevated/sandbox-off` 默认不存在普通入口。
- 只有隔离运维场景可以提 break-glass：双人批准、具体主机/动作、最短有效期、专用凭据、全量审计、自动到期与事后复盘。
- break-glass 不能用于让 Agent 完成长任务，也不能把产生的未隔离结果直接晋级为正常 REAL 证据。
- 正常安全治理可以请求撤销会话/Grant/Secret/包版本、停止 lane、隔离制品、验链、受控导出
  和恢复；对外导出与恢复启用仍走常规 typed governance/Delivery，不进入安全生存通道。
- FLAiWorkspace 是唯一内网日常入口，但安全生存通道必须独立于 Workspace、通讯/Wiki
  Adapter、主协作 SSO 和普通在线 Secret 解析。`SafetySurvivalPort` 只允许
  kill/revoke/suspend/deny/isolate、只开对账案、向预批准
  本地 WORM 封存证据和只验证不启用的恢复候选；不得创建项目/需求、对外导出、恢复权限、
  签发路线图/知识/能力/交付、合并代码或正常发布，因此不构成第二日常管理面。
- Workspace/协作/Wiki 不可用时，新的正常治理动作暂停；不得从缓存卡片、离线项目表或通知
  副本执行不可逆动作。

## 16. P0 / P1 / P2 路线图

### P0：任何正式试点前

1. 恢复 clean、可复现 release candidate；
2. 统一对象授权、BOLA/IDOR 和附件封口；
3. ExecutionBroker + 一个低副作用 Tool + 最小真实 Mac Sandbox/kill；
4. durable lane/budget/lease、terminal CAS、running cancel、side-effect-aware recovery；
5. 审计 outbox、防篡改/WORM、SecretRef、受控 egress；
6. quarantine、SBOM、签名、断网发布和全资产 restore drill；
7. macOS 本机、模型 p99/429、睡眠唤醒、恢复和 novice 全链验收；
8. 所有 Gate 机器证据 + 具名 owner 签发。
9. 内网 IdP/Surface attestation、ActorBinding、ACL/classification projection、typed
   intent/receipt/reconciliation 和 outage 下安全生存演练。
10. 外网 `secrets-stackdocker` 与内网 Secret owner 分别完成最小 SecretRef、旧值撤销、
    轮换/吊销、无 fallback、审计与恢复 witness，且无跨域共享。
11. 独立 Safety Identity / PKI / HSM 的双人硬件 admission、不可导出 signing key、key
    epoch/轮换/吊销、trust anchor 分发与回滚、signer/verifier 职责分离、backup/restore 及与
    Workspace、主 SSO、Hub、普通 Secret 栈同时不可用的止损演练；固定 canonical receipt
    profile/domain separator、algorithm/policy downgrade 门、stable effect key；admission
    必须按 `SAFETY_PREPARE | SAFETY_COMMIT | POLICY_PUBLICATION` 绑定精确 immutable
    subject/nonce/replay domain，并以 append-only `EmergencyAdmissionConsumptionV1`
    CAS-on-NULL 单次消费；Subject↔Prepared/CommitAttempt/PublicationReceipt 的重复字段
    必须各自重算 domain-separated projection digest 且逐字相等。唯一 Safety Admission
    Coordinator 先在自己事务中消费双 admission+subject nonce并签发 immutable Reservation；
    下游 owner 只在各自本地 CAS，崩溃保持 consumed+reserved 并对账，ChallengeState 全链
    只由 Coordinator 写。target owner 的本地 anchor 是 immutable `SafetyCommitAttemptV1`，
    最终 receipt/unknown 追加引用；首次 anchor 前必须权威 resolve 三条 consumption、验证
    Coordinator workload attestation，所有 gate `is True` 且 status ACTIVE。owner-local
    commit 必须消费独立 `SafetyTrustedTimeAttestationV1 ref+digest`、按保守 UTC upper bound
    比较 TTL；Time epoch transition 必须具名、continuity-root 签名且 Genesis/counter 初值
    连续，并以 transaction nonce/commit subject-bound CommitLease、受信 monotonic elapsed
    的 owner-store 线性化 FreshnessProof CAS consumer checkpoint，和 anchor 同事务。
    epoch/counter/predecessor 回拨或 gap、陈旧 lease、超 elapsed budget、
    skew/uncertainty 超限、source/head/key/revocation outage/Unknown 一律 fail-closed，禁止
    host-clock/cache/call-before-only fallback。过期未 anchor 不得开始 effect；outbox enqueue 与
    `SafetyCommitDispatchClaimV1` 都不算 send。唯一 egress boundary 在第一 mutating send
    primitive 前重新验 time/deadline、CAS 消费一次性
    `SafetyProviderMutationCapabilityV1` 并创建 `SafetyProviderCallAttemptV1`；缺 verified
    `SafetyProviderSendReceiptV1` 一律 effect unknown + DO_NOT_REPLAY，只可原键查询；
    两个不同真人签发的 append-only Issuance/Verification Policy Head version +
    content-addressed PointerRevision；唯一 Fence Authority 在自身 single-writer 原子提交
    严格推进 policy fence epoch、形成 ALIAS_COMMIT witness 并 CAS current alias
    （历史 revision/witness 在线可解析）；
    Prepared/Challenge/Receipt/SigningRequest/
    Envelope/signer 对 current Issuance Head+Bundle、verifier/factory/result/head 对 current
    Verification Head+Bundle 的显式 generation/ref/digest 绑定、signer anti-oracle 与 HSM
    调用前后从同一 Fence Authority 取得 SIGN_PRE/SIGN_POST witness；ALIAS_COMMIT/PRE/POST
    均冻结 exact TimeAttestation/CommitLease/FreshnessProof/Checkpoint 并与各自 Authority
    store commit 同事务；Envelope 绑定共同 fence epoch、alias-commit/pre/post witness，
    漂移不发布 Envelope；旧 issuance
    bundle 的明确 acceptance/吊销判定、verification canonical/key、
    receipt+verification-derived result key、verifier-owned SafetyResultFactory、独立 chain
    Head generation+digest CAS、同 verification bundle freshness 到期的 read-derived amber
    与新 verification bundle reverify，以及 pending→confirmed 追加式 observation-bound
    对账负例。

### P1：可信基础上的企业工作台

- 项目空间、职责委派、临时授权与撤销；
- Final Delivery Review、Audit Explorer、队列/预算/执行单元视图；
- 自动化模板的触发、并发、停止和交付合同；
- 版本化人工评审与证据化运营指标；
- 治理 UI 只投影真实状态，不先做不存在的控制按钮。

### P2：规模化与生态

- 多 execution cell、部门隔离、HA 和容量调度；
- Windows Adapter 与目标机验收；
- Connector/Skill/Agent 内网目录和批准流水线；
- 安全 P0 基线之外的规模化 HSM 集群、集中 SIEM、长期归档和合规报表；
- 更细的多 Agent 委派预算与跨项目协作。

## 17. 尚待具名责任人裁决

这些问题保持 `UNKNOWN/BLOCKED`，实现者不得代填默认值：

| 决策 | 影响 |
|---|---|
| 生产身份源、MFA、离线账户降级 | actor ID、角色同步、撤销和事故恢复 |
| promotion/发布/break-glass 的双人职责范围 | 授权合同与 UI |
| EvaluationAdmission 签发职责及其与 Qualification/Deployment signer 的职责分离 | 未资格候选能否进入实验室 Bench；未知时不创建 eval task |
| Knowledge Publisher/Signer 与 Eval maintainer 的职责分离 | synthetic KnowledgeItem 的权威签发与 benchmark pack 收录必须是两类 typed record；是否可同人兼任未知时拒绝 |
| 审计留存年限、WORM/SIEM、不可用策略 | 存储、成本、降级与上线门 |
| 正式数据域、允许模型/域名和脱敏责任人 | Egress、Knowledge、Connector 能否开启 |
| Safety Identity / PKI / HSM 的组织 owner、双人介质保管、key generation/rotation/revoke/recovery 仪式、trust anchor 分发/回滚及 signer/verifier 职责分离 | 决定 `SafetySigningMaterialRef` 生命周期、离线验证、receipt 可接受性与 F0 合同是否可接受；真实 Secret 栈总体 outage 能否通过由对应 D6/D7/D8 + F4 runtime exit 裁决 |
| 离线根、签名/验签/吊销责任 | 制品是否可验证 |
| Phase 0B 20–30 人与正式服务的峰值任务、Tool/模型并发 | Phase 0A 已由 `phase0a-macos-v1` 冻结为每会话 Model/Tool 合计 1、全平台 Model 2/Tool 2/quarantine 2；扩大规模必须另做容量基准与新预算版本 |
| 适用的等保、密码应用或其他组织控制 | 合规范围；本设计包不作认证结论 |
| 内网自托管 Surface 可承载的正式 classification 与 audience 规则 | 未批准时只允许脱敏摘要、稳定引用、重新鉴权深链或存在性抑制 |
| 内网 IdP/Workspace 身份能否满足各级正式电子签发及所需 step-up | A1 普通协作、A2 组织 SSO、A3 exact digest/短 TTL/强认证的边界 |
| 外网 `secrets-stackdocker` 与内网 Secret owner 的 workload identity、最小引用、轮换、吊销、bootstrap 与恢复责任 | 用户声明只证明外网迁移方向；两域分别验证且不得共享 |
| ADR-0047～0063 的正式决策签发载体与签发人 | 当前会话确认只证明设计方向接受；进入实施/试点前须绑定身份、职责、时间和精确 digest |

## 18. 上线签发清单

签发不是打勾表。每项必须包含：控制 ID、精确 release SHA/制品 digest、目标机、验证命令、exit code、原始证据、tamper witness、验证人、日期、残余风险和 owner 结论。

最低拒绝条件：

- 任一 P0 为 `failed/invalid/skipped/unknown`；
- Sandbox 不可用时存在 host fallback；
- 可复现 BOLA/IDOR 或附件旁路；
- running task 无法强杀或 kill 后仍有副作用；
- 审计不可用但高风险写继续；
- 终态晚写可翻绿；
- 离线包无摘要/签名/SBOM 或断网安装需公网；
- 备份未做真实 restore/tamper drill；
- 没有具名 owner 的最终签发。

Phase 0A 通过只证明限定机制，不证明生产就绪或真实业务价值；进入 Phase 0B 还需要至少一条真实工具、真实数据工作流的安全和准确性验收。见 [ADR-0051](../../adr/ADR-0051-two-stage-controlled-and-business-pilots.md)。

## 19. 明确禁止

- 禁止 OpenClaw/OpenHands 成为第二控制面或第二审计事实源。
- 禁止 production sandbox-off、Full Access 或 host exec 快捷模式。
- 禁止用逐工具弹窗和复杂授权表替代后台策略与末端交付。
- 禁止让 AI 自批权限、知识、金标准、晋级、路线图或交付。
- 禁止用单一总分抵消安全失败，或把 `unknown/null` 显示为绿色。
- 禁止信任 Surface payload 自报 `actor/role/classification`，禁止用项目/Wiki 字段、
  HTTP 2xx 或消息送达替代 OwnerCommitReceiptV1。
- 禁止协作/Wiki Adapter 直接写 FLAi 数据库，或在其故障时阻断 kill/revoke。
- 禁止建立 Feishu/GitHub ↔ 内网实时通道，或把外部签名/CI/merge 当成内部准入/部署。
- 禁止任一域 Secret owner 不可用时回退 `.env`、硬编码或宿主全局凭据。
- 禁止把登录、Dockerfile、目录隔离、线程 timeout、日志存在或历史截图称为安全闭环。
- 禁止运行时从公网安装插件、技能、依赖或拉取 `latest`。
- 禁止在未裁决正式密级与适用性前自行宣称等保、密评、适航或其他认证。

## 20. 关联依据

- [系统宪法](../../00_FLAi-OS_Constitution.md)
- [Tool Package 标准](../../03_Tool_Package_Standard.md)
- [Model Gateway 标准](../../04_Model_Gateway_Standard.md)
- [Task/Event 标准](../../05_Task_Event_Standard.md)
- [Knowledge/Memory 标准](../../06_Knowledge_Memory_Standard.md)
- [Eval 标准](../../07_Eval_Standard.md)
- [生产就绪纲领](../../PRODUCTION-READINESS-PROGRAM.md)
- OpenClaw / WorkBuddy / 安全治理研究（外部设计证据；尚未进入本隔离基线，待按精确 digest 登记）
- OpenClaw Runtime 安全参考（外部设计证据；尚未进入本隔离基线，待按精确 digest 登记）
- [ADR-0025：不可变任务级分级](../../adr/ADR-0025-immutable-task-classification.md)
- [ADR-0030：专家身份轴与密级/依据契约](../../adr/ADR-0030-expert-identity-clearance-evidence-contract.md)
- `codex/agent-fact-projection-ui@52c3856` 中的 ADR-0046 ax Web Extract 边界（commit-bound evidence，尚未进入当前 main）
- [ADR-0047：主线 ADR 谱系与历史 safe-auto 对账](../../adr/ADR-0047-mainline-decision-lineage-reconciliation.md)
- [ADR-0049：控制内核与执行后端](../../adr/ADR-0049-flai-control-kernel-and-replaceable-execution-backends.md)
- [ADR-0050：自治会话与末端授权](../../adr/ADR-0050-uninterrupted-session-and-final-delivery-authorization.md)
- [ADR-0057：权威知识底座](../../adr/ADR-0057-authoritative-knowledge-foundation.md)
- [ADR-0058：FLAi Bench](../../adr/ADR-0058-flai-bench-evaluation-foundation.md)
- [ADR-0061：需求治理职责分离](../../adr/ADR-0061-demand-decision-rights-and-roadmap-signoff.md)
- [ADR-0062：飞书外网研发协作中枢](../../adr/ADR-0062-feishu-single-organizational-hub.md)
- [ADR-0063：双信任域与离线准入](../../adr/ADR-0063-external-development-airgap-internal-workspace.md)
- [隔离交换与内网发布准入](18_AirGap_Exchange_and_Internal_Release.md)
- [内网自托管智能协作空间](19_Internal_Self_Hosted_Workspace.md)

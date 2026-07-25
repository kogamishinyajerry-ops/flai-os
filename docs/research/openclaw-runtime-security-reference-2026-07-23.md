# OpenClaw 运行时与安全治理参考研究（2026-07-23）

> 面向 FLAi-OS 中国国企内网正式部署。本文只做架构与源码证据研究，不构成引入 OpenClaw、修改 FLAi-OS 架构或上线放行的授权。
> 用户已于 2026-07-23 明确确认研究对象为 **OpenClaw**；此前口述的 “OpenCloud” 是口误。当前产品实施采用 macOS-first，本文涉及 Windows 的内容仅是上游能力盘点，不构成本阶段适配要求。

## 1. 结论先行

研究对象已经锁定为 **OpenClaw**。其官方项目包含 Gateway、多智能体路由、沙箱、工具策略、执行审批、插件/技能、审计和多平台 Hub 等模块；后续源码引用、机制比较和版本固定均只指向 `openclaw/openclaw`，不再保留 “OpenCloud” 候选分支。

OpenClaw 很值得深度参考，但**不适合原样作为国企共享智能体平台的安全内核**。最根本的原因不是实现质量，而是威胁模型不同：OpenClaw 官方明确把一个 Gateway 视为一个“受信任操作者边界”，不是互不信任用户共享的多租户安全边界。FLAi-OS 应吸收它的分层治理思想和若干实现模式，同时把默认策略、审计持久性、队列、租户隔离和供应链治理重做成企业级、fail-closed 的控制面。

最重要的判断如下：

1. **以一个 Gateway 对应一个信任域，而不是一个 Gateway 对应全公司。** 不同密级、部门、项目或互不信任用户至少拆成独立运行单元，优先再叠加独立 OS 用户、虚机或主机。
2. **沙箱必须从 `all + session/agent` 的强制策略起步。** OpenClaw 的默认是 `off`，`non-main` 还会让主会话跑在宿主机，`shared` 会让会话共享环境；这些都不应成为 FLAi-OS 生产默认。
3. **工具授权应采用单调收紧的分层策略。** 全局、租户、智能体、会话、沙箱、子智能体只能继续收紧，不能在下层重新授予上层已拒绝的能力；`exec/process` 需要单独治理，不能以“禁用 write/edit”冒充只读。
4. **执行审批可参考“精确命令上下文绑定”，但不能当作用户鉴权或强隔离。** OpenClaw 的宿主机执行默认是 `security=full, ask=off`，这是个人助手便利性取向，不符合企业生产基线。
5. **出站网络应由操作系统/容器网络和企业代理共同执法。** OpenClaw 的进程级 HTTP/WebSocket 代理覆盖面很好，但 raw socket、原生扩展、子进程等仍可能绕过，不能单独承担内网出站边界。
6. **SecretRef 的快照、原子切换和未知哨兵拒绝出网很值得借鉴；“明文仍可用、引用可选”不应照搬。** 生产环境应把明文残留扫描设为部署门禁。
7. **OpenClaw 的内存队列适合个人助手交互，不适合企业任务调度。** FLAi-OS 应保留 SQLite 任务表与 Job Runner，补租约、幂等、重试、优先级、配额和恢复，不应换成进程内 Promise 队列。
8. **OpenClaw v2026.7.1 的审计投影不是合规审计账本。** 它仅记录元数据，30 天/10 万行，并使用最大 4096 项的非阻塞队列；队列满、工作线程异常或关闭超时都会丢记录而不阻断执行。
9. **插件在 Gateway 进程内运行，应按受信任代码而不是普通配置管理。** 公共 ClawHub/npm/git 安装路径不适合生产内网；应使用内部制品库、固定版本和摘要、人工批准、SBOM、恶意代码扫描、许可证审查与离线复现。
10. **Windows 支持可以参考，但内网交付链要重做。** 官方同时提供原生 Windows Hub、原生 CLI/Gateway 和 WSL2；官方仍推荐 WSL2 作为最兼容的 Gateway 运行时。生产不能采用 `iwr | iex` 或 `latest`，应交付经过签名和哈希固定的离线包。
11. **许可证允许借鉴和移植，但不替代逐项合规。** 核心为 MIT；第三方依赖、插件、字体和适配代码仍需保留通知并独立核验许可证与安全状态。

## 2. 研究基线与证据边界

| 项目 | 固定基线 |
| --- | --- |
| 官方仓库 | [openclaw/openclaw](https://github.com/openclaw/openclaw) |
| 研究版本 | [v2026.7.1](https://github.com/openclaw/openclaw/releases/tag/v2026.7.1)，2026-07-13 发布；截至 2026-07-23 为稳定版 `latest` |
| 固定提交 | [`2d2ddc43d0dcf71f31283d780f9fe9ff4cc04fe4`](https://github.com/openclaw/openclaw/commit/2d2ddc43d0dcf71f31283d780f9fe9ff4cc04fe4) |
| 研究方式 | 官方发布页、固定标签文档和固定标签源码静态审阅；没有把滚动官网文档当作稳定版源码的替代 |
| 未纳入基线 | `v2026.7.2-beta.*` 预发布内容、第三方博客、营销材料 |

固定标签非常重要。OpenClaw 文档更新快，官网可能先于稳定版源码。例如，稳定版控制面写操作限流源码是每个 `deviceId + clientIp` 每 60 秒 3 次；滚动文档若出现不同数字，不应反向解释已发布版本。本文所有“默认值”和“限制”以 `v2026.7.1` 固定链接为准。

本次没有运行 OpenClaw 实例、没有执行渗透测试，也没有对其形成等保、密评、关基、数据合规或国密适配结论。本文是设计输入，不是安全认证报告。

## 3. 架构与信任边界

### 3.1 Gateway 控制面

OpenClaw 采用一个长驻 Gateway 统一持有消息通道、会话、节点和工具执行控制面。客户端和节点通过 WebSocket 连接，默认监听 `127.0.0.1:18789`；协议帧经 JSON Schema 校验，副作用请求使用幂等键与短期去重。事件不提供完整重放，客户端检测序列缺口后需要重新拉取状态。参考：[`docs/concepts/architecture.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/concepts/architecture.md)。

可吸收点：

- 单一控制面持有路由和策略，执行节点只声明能力并接受受控命令。
- 协议消息强类型、Schema 校验、版本协商和副作用幂等键。
- 节点配对、能力声明、命令白名单与状态刷新分离。
- 控制面变更与执行面调用使用不同权限和限流。

不可照搬点：

- 官方安全文档明确声明“一个 Gateway = 一个受信任操作者边界”，认证后的操作者是控制面可信角色，`sessionKey` 只是路由键，不是授权令牌。互不信任用户必须拆 Gateway，最好再拆 OS 用户或主机。参考：[`docs/gateway/security/index.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/gateway/security/index.md)。
- 因此，多智能体路由不能被解释为租户隔离；Gateway 本身拥有所有代理的控制权，仍是高价值单点。
- 事件不重放和单进程控制面不应承担企业级审计恢复、跨节点一致性或灾备职责。

### 3.2 多智能体、工作区与会话

每个 OpenClaw agent 拥有 workspace、`agentDir`、认证配置和会话目录，bindings 按通道、账号和 peer 做确定性路由。跨智能体消息默认关闭。参考：[`docs/concepts/multi-agent.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/concepts/multi-agent.md) 和 [`docs/concepts/session.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/concepts/session.md)。

必须看到的边界：

- workspace 只是默认工作目录，不是硬沙箱；未启用沙箱时，绝对路径仍可访问宿主机其他位置。
- 禁止多个 agent 复用同一个 `agentDir`，否则认证和会话状态会冲突。
- 直接消息默认可折叠到 agent 的 main session；多人入口必须采用每通道/每发送者隔离，真正互不信任时应一人一 agent 或一信任域一 Gateway。
- 次要 agent 的 OAuth 刷新失败时可能读取主 agent 同 profile 的较新凭据；这对个人助手有用，但不是严格租户凭据隔离。
- 部分插件存储和共享技能根不是天然 per-agent；要逐一核对插件所有权与存储位置。
- 通道 allowlist 可能绑定到 channel account，而不是 agent；不能只看 agent 路由就声称完成用户授权。

FLAi-OS 应把 `tenant/project/user/agent/session/run` 六层身份写入不可变执行快照，并让授权决策引用该快照摘要。路由键、展示名称和会话 ID 均不能替代认证主体。

## 4. 沙箱、工具策略与执行审批

### 4.1 沙箱默认值与逃逸面

OpenClaw 沙箱只移动工具执行，Gateway 仍留在宿主机。稳定版默认值如下：

| 控制 | OpenClaw v2026.7.1 默认 | FLAi-OS 建议生产基线 |
| --- | --- | --- |
| `sandbox.mode` | `off` | 强制 `all` |
| `sandbox.scope` | `agent` | 高风险任务 `session`；低风险且同信任域可评估 `agent`；禁止 `shared` |
| backend | `docker` | Windows 内网优先受控 Linux VM/WSL2 + rootless 容器，或独立执行节点 |
| Docker 网络 | `none` | 保持无网；按任务授予代理出口 |
| 根文件系统 | `readOnlyRoot: true` | 保持只读，写入仅限临时卷和声明式工作区 |
| capabilities | `capDrop: ["ALL"]` | 保持全部删除，再按极小集合例外审批 |
| workspace access | `none` | 默认 `none`；只读任务可 `ro`；`rw` 必须绑定快照与审批 |
| elevated | 可绕过沙箱 | 生产默认禁用；break-glass 必须双人审批、限时和全量审计 |

证据：[`docs/gateway/sandboxing.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/gateway/sandboxing.md)。

关键风险：

- `non-main` 会让 main session 不进沙箱；不能因为群组会话被隔离就宣称平台整体已隔离。
- `scope: shared` 让多个会话共享容器和工作区，并忽略部分 per-agent backend/browser 覆盖；不适合作为企业隔离模式。
- bind mount 会直接穿透沙箱文件系统。OpenClaw 对系统目录、Docker socket 和常见凭据目录做了阻断，并进行 realpath/符号链接祖先复检，这一做法值得移植；任何 `dangerouslyAllow*` 开关都应在生产 Schema 中消失，而不是只发告警。
- Gateway 自身容器若通过宿主 Docker socket 创建兄弟沙箱，Gateway 实际拥有宿主容器控制能力。绝不能把 Docker socket 挂进 agent 沙箱，Gateway 也应运行在独立节点或受强约束的容器管理代理之后。
- `tools.elevated` 是明确的宿主逃逸路径；沙箱开启并不意味着所有命令都在沙箱内。

### 4.2 工具策略

OpenClaw 的工具过滤顺序大体是：工具 profile → provider 策略 → 全局策略 → agent 策略 → agent/provider 策略 → sandbox 策略 → subagent 策略。每层只能继续缩小能力，不能把上层拒绝的工具重新放回。参考：[`docs/tools/multi-agent-sandbox-tools.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/tools/multi-agent-sandbox-tools.md)。

可直接采用为 FLAi-OS 契约的原则：

- deny 优先于 allow；子层只可收紧。
- 空的显式 allowlist 应产生“无可调用工具”的明确失败，而不是退回全开放。
- 工具目录、前端按钮、模型可见 Schema 和后端执法必须由同一 effective policy 生成，避免假绿。
- `write/edit/apply_patch` 被拒绝不等于只读：只要 `exec/process` 仍在，命令仍可能修改文件或发网。
- skills allowlist 只是提示与可见性边界，不是 shell 授权边界。

### 4.3 执行审批

OpenClaw 支持 per-agent 可执行文件白名单、参数模式、`ask` 策略、`askFallback=deny`、解释器 inline-eval 检测，以及把节点执行的精确 argv/cwd/env/可执行文件和准备后的计划绑定到审批请求。无法唯一识别直接脚本/文件时，审批模式可拒绝执行。参考：[`docs/tools/exec-approvals.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/tools/exec-approvals.md)；核心实现位于 [`src/infra/exec-approvals.ts`](https://github.com/openclaw/openclaw/blob/v2026.7.1/src/infra/exec-approvals.ts)、[`src/infra/exec-approvals-analysis.ts`](https://github.com/openclaw/openclaw/blob/v2026.7.1/src/infra/exec-approvals-analysis.ts) 和 [`src/gateway/server-methods/exec-approvals.ts`](https://github.com/openclaw/openclaw/blob/v2026.7.1/src/gateway/server-methods/exec-approvals.ts)。

值得移植的是“审批绑定精确执行事实”，不是聊天里简单点一下同意。FLAi-OS 审批对象至少应包含：主体、租户、agent、run、工具、规范化 argv、cwd、环境变量键集合、输入文件摘要、镜像摘要、网络策略摘要、超时、资源上限、输出目的地和执行快照摘要；任何一项变化都使审批失效。

不可照搬的是默认策略：OpenClaw 对 gateway/node 宿主机执行默认 `security=full, ask=off`，这符合其单用户个人助手定位，却不符合国企共享平台。审批本身也不是 per-user 鉴权、只读文件系统或恶意命令语义证明。

## 5. 网络与出站治理

OpenClaw 提供进程级 HTTP/WebSocket 正向代理：覆盖 `fetch`、Undici、`node:http`、`node:https`、常见 WebSocket 和 CONNECT，并清除 `NO_PROXY` 以减少目的地绕过；配置代理但 URL 无效时，受保护进程拒绝启动。它还提供代理校验命令和一套特殊地址/元数据地址阻断参考。证据：[`docs/security/network-proxy.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/security/network-proxy.md)、[`src/infra/net/ssrf.ts`](https://github.com/openclaw/openclaw/blob/v2026.7.1/src/infra/net/ssrf.ts)、[`packages/net-policy/src/ip.ts`](https://github.com/openclaw/openclaw/blob/v2026.7.1/packages/net-policy/src/ip.ts)。

这是很好的纵深防御，但官方也明确列出限制：

- OpenClaw 不提供、配置或认证外部代理，真正的目的地策略由运维方负责。
- 这是 JavaScript 进程级覆盖，不是 OS 网络沙箱。
- raw `net`/`tls`/`http2`、原生扩展和非 OpenClaw 子进程可能绕过。
- IRC 使用 raw TCP/TLS，不走该 HTTP 代理。
- Gateway loopback、浏览器 CDP 和部分本地模型能力存在精确例外，需要单独审计。

FLAi-OS 应采用四层控制：容器/虚机默认无网 → egress gateway/防火墙强制路径 → 企业正向代理按域名和解析后 IP 决策 → 应用层 SSRF/DNS 重绑定校验。批准的是声明式目的地集合，不是任意 URL。DNS、CONNECT、拒绝原因和流量量级进入审计，但不得记录认证头、Cookie 和正文秘密。

## 6. 密钥与配置安全

### 6.1 SecretRef

OpenClaw SecretRef 支持 env/file/exec provider，启动时预解析到内存快照，成功后原子切换；活跃表面引用解析失败会阻断启动，reload 失败保留最后已知良好快照。模型凭据可用进程内哨兵流转，到最终出站适配器才解封；未知哨兵在网络活动前 fail-closed。file/exec provider 有文件类型、符号链接、权限、超时、输出大小和环境变量 allowlist 限制；Windows 无法验证 ACL 时默认失败，只有显式 `allowInsecurePath` 才绕过。证据：[`docs/gateway/secrets.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/gateway/secrets.md)。

需要保留的设计：

- 启动时解析、内存快照、原子切换、最后已知良好状态。
- 未解析值不退回明文或其他 provider。
- exec provider 直接执行绝对二进制、不经 shell，并限制环境、时限和输出。
- 未知哨兵在出网前拒绝，真实值只在最终适配器边界出现。
- `secrets audit --check` 作为迁移门禁，扫描配置、auth profile、`.env` 和生成文件中的明文残留。

需要收紧的地方：OpenClaw 明文凭据仍可用，SecretRef 是逐字段 opt-in，哨兵也不是进程隔离。FLAi-OS 生产配置应禁止支持字段出现明文；密钥只在独立 broker/sidecar 或短时凭据代理中解封，agent/Gateway 进程尽量不持有长期密钥。

### 6.2 配置治理

OpenClaw 配置采用严格 Schema：未知键、类型错误或非法值会拒绝 Gateway 启动；Control UI 与后端校验使用同一规范 Schema。热加载的无效配置被拒绝，现有运行时继续使用最后接受版本；拒绝内容另存供检查。写入采用原子替换，并对丢失关键字段、丢失 meta、文件缩小超过一半和数组缩短做防误覆盖保护。控制面 `config.apply/patch/update` 在稳定版按设备与 IP 限流为每 60 秒 3 次。证据：[`docs/gateway/configuration.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/gateway/configuration.md) 和 [`src/gateway/control-plane-rate-limit.ts`](https://github.com/openclaw/openclaw/blob/v2026.7.1/src/gateway/control-plane-rate-limit.ts)。

FLAi-OS 可移植同一 Schema 生成表单、校验和文档的思路，并继续增加：配置版本号/CAS、发起人和审批人、变更单号、diff、风险分类、签名、灰度范围、回滚目标和生效证明。高风险配置不能靠热加载自动生效，必须走受认证的人类审批。

## 7. 并发、队列与限流

OpenClaw 使用 lane-aware 的进程内 FIFO：未配置 lane 默认并发 1，main 默认 4，subagent 默认 8；每个 session lane 串行，再进入全局 main lane受 `maxConcurrent` 限制。消息队列默认 `steer`、500 ms debounce、每会话 20 条、溢出时摘要旧消息。它没有外部依赖或后台 worker，是纯 TypeScript + Promise。证据：[`docs/concepts/queue.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/concepts/queue.md)。

可借鉴：

- 每会话至多一个 active run，避免上下文和文件状态竞争。
- 全局、租户、agent、模型/provider、工具分别设置并发配额。
- 排队、执行、工具阻塞和恢复状态分开；取消请求要绑定原始 requester/run。
- 限流按凭据类别分 scope，限制内存键数量并周期清理。稳定版认证失败默认 60 秒内 10 次、锁定 5 分钟、最多 1 万身份；但 loopback 默认豁免，需要企业部署重新评估。证据：[`src/gateway/auth-rate-limit.ts`](https://github.com/openclaw/openclaw/blob/v2026.7.1/src/gateway/auth-rate-limit.ts)。

不可照搬：

- 进程退出会丢等待工作，不提供分布式租约、持久重试、跨节点公平性和灾后恢复。
- `steer` 改变运行中上下文，生产任务若已获审批会造成“审批内容与实际执行输入”漂移。治理任务应冻结执行快照；新消息只能形成新版本/新审批，不能直接注入已批准 run。
- 内存 IP 限流不适合多副本一致配额，也不能替代网关/WAF/身份系统限流。

因此 FLAi-OS 应保留 SQLite Job Runner，并把 `session_serial_key`、`tenant_quota_key`、租约、心跳、幂等键、重试预算、优先级、取消令牌和恢复状态固化到任务表。

## 8. 审计、日志与安全检查

### 8.1 v2026.7.1 审计账本的真实能力

OpenClaw 默认启用 metadata-only 审计投影，记录 agent run/tool action 的 start/finish、状态、actor、agent、session、run、哈希后的 tool call ID 和工具名。SQLite 记录按 source ID 幂等，默认保留 30 天、最多 100,000 行。证据：

- [`src/audit/audit-event-types.ts`](https://github.com/openclaw/openclaw/blob/v2026.7.1/src/audit/audit-event-types.ts)
- [`src/audit/audit-config.ts`](https://github.com/openclaw/openclaw/blob/v2026.7.1/src/audit/audit-config.ts)
- [`src/audit/audit-event-store.ts`](https://github.com/openclaw/openclaw/blob/v2026.7.1/src/audit/audit-event-store.ts)
- [`src/audit/agent-event-audit.ts`](https://github.com/openclaw/openclaw/blob/v2026.7.1/src/audit/agent-event-audit.ts)

但写入器是非阻塞 worker，最大 pending 4096；worker 不可用、队列满、postMessage 失败或关闭超时会返回失败/告警并丢元数据，执行本身继续。证据：[`src/audit/audit-event-writer.ts`](https://github.com/openclaw/openclaw/blob/v2026.7.1/src/audit/audit-event-writer.ts)。它也没有提供不可篡改链、签名、WORM 留存或第三方时间戳证明。

结论：可以移植其“可信生命周期事件 → 脱敏审计投影”的事件模型、关联 ID 哈希和幂等 source ID；不能把其持久化语义称为国企合规审计。FLAi-OS 的强治理事件必须与状态变更同事务提交或进入可靠 outbox；审计不可用时，高风险执行应 fail-closed。日志、指标和 trace 可以丢，授权/审批/执行/结果封存证据不能丢。

### 8.2 安全审计与可观测性

`openclaw security audit [--deep|--fix|--json]` 会检查入口策略、工具爆炸半径、exec 漂移、网络暴露、文件权限、插件 allowlist、沙箱配置未生效和危险开关；`--fix` 只做有限修复，不是认证或渗透测试。参考：[`docs/gateway/security/index.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/gateway/security/index.md) 与 [`docs/gateway/security/audit-checks.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/gateway/security/audit-checks.md)。

这类“声明配置与实际 effective policy 的漂移检查”非常值得引入 CI、启动门禁和周期巡检。FLAi-OS 还应增加：

- 沙箱镜像摘要、网络策略、工具 Schema 与审批快照是否一致。
- 运行时证据是否来自 REAL backend，mock 是否明确标注。
- 审计序列缺口、outbox 积压、签名失败、时钟偏差和导出失败。
- 权限扩大、密级越界、跨租户路径、共享凭据和插件变更。
- 人类签发身份、证书状态、撤销状态和不可变执行摘要。

## 9. Skills、插件与供应链

Skills 是可进入提示上下文的 Markdown 指令，来源有 workspace、project agent、personal、managed、bundled、extra/plugin 等优先级。省略 agent skill allowlist 等价于不限制，空数组才表示无技能；技能列表也可能因文件 watcher 或远端节点动态变化。官方明确要求把第三方技能视作不受信任代码，skill allowlist 不等于 shell 授权。证据：[`docs/tools/skills.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/tools/skills.md)。

Plugins 在 Gateway 进程内运行，官方要求按受信任代码处理。安装/更新支持 ClawHub、npm、git、本地路径和压缩包；内置安装流程不做本地危险代码阻断，可接入 `security.installPolicy` 让外部受信任命令在 staged source 上做 allow/block；官方建议固定精确版本并审阅解包代码。证据：[`docs/plugins/manage-plugins.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/plugins/manage-plugins.md) 和 [`docs/gateway/security/index.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/gateway/security/index.md)。

发布 npm 包使用 `npm-shrinkwrap.json` 固定传递依赖图，源码使用 `pnpm-lock.yaml`。这提高了可审阅性和可复现性，但官方也明确说明 shrinkwrap 不是沙箱，不证明依赖安全。证据：[`docs/gateway/security/shrinkwrap.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/gateway/security/shrinkwrap.md)。

内网生产建议：

1. 禁止运行时访问公共 ClawHub/npm/git；只允许内部镜像和离线制品。
2. 插件/技能先进入 quarantine，计算摘要、解包、静态/恶意代码/秘密/许可证扫描、人工审阅，再由独立批准人签发。
3. 生产引用 `package@version + artifact digest + publisher + approval id`，禁止 dist-tag、branch 和 `latest`。
4. 构建阶段完成依赖收敛；运行节点禁止安装脚本和包管理器联网。
5. 插件进程优先 out-of-process，使用窄化 RPC、独立 OS 身份和资源/网络策略；不要让第三方插件与 Gateway 同权。
6. watcher 只用于开发；生产技能快照与 run 的执行摘要绑定，运行中不得静默变化。

## 10. Windows、离线交付与许可证

### 10.1 Windows

v2026.7.1 同时提供：

- 原生 Windows Hub（WinUI，Windows 10 20H2+ / Windows 11，x64/ARM64 安装包）。
- 原生 Windows CLI/Gateway，后台启动优先 Scheduled Task，失败时回退到用户 Startup folder。
- WSL2 Gateway；官方仍称其为 Windows 上最兼容 Linux 的运行时，Windows Hub 可创建 app-owned WSL distro。

证据：[`docs/platforms/windows.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/platforms/windows.md)。Node 要求为 `22.22.3+`、`24.15+` 或 `25.9+` 对应区间，Node 24 是默认目标，见 [`package.json`](https://github.com/openclaw/openclaw/blob/v2026.7.1/package.json)。

FLAi-OS 内网生产更适合把 Linux/WSL2/受控 VM 作为执行平面，把 Windows 原生应用作为工作台和受限节点。若必须原生 Gateway，需专项验证 Scheduled Task 身份、ACL、服务恢复、EDR/杀软、代理、证书、长路径、编码、更新回滚和断网运行。

### 10.2 离线交付

OpenClaw Docker 安装提供 `--offline`：先导入本地镜像，禁止隐式 pull/build，并在启用 sandbox 时检查所需默认/per-agent 镜像及浏览器契约标签，缺失或过期则退出而不写入错误配置。这种“缺制品就退出，不报假绿”值得照搬。证据：[`docs/install/docker.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/docs/install/docker.md)。

但这不是完整的企业 air-gap 交付规范。正式包还应包含：

- 固定提交、源码归档、可复现构建说明和构建环境摘要。
- Gateway、sandbox、browser、Windows 客户端等全部镜像/安装包的 SHA-256 和数字签名。
- SBOM、漏洞扫描结果、第三方许可证清单和批准记录。
- 内部模型/provider、时间、DNS、证书吊销、OTEL/SIEM 等依赖的离线拓扑。
- 升级/回滚矩阵、数据库迁移演练、备份恢复演练和灾备 RTO/RPO。
- “断开互联网 DNS 和默认路由后完成安装、启动、执行、审计导出”的验收证据。

### 10.3 许可证

OpenClaw 核心使用 MIT License，版权归 OpenClaw Foundation；移植或分发实质代码时必须保留版权和许可声明。项目另有第三方通知，记录从 Pi/pi-mono 适配的代码等。证据：[`LICENSE`](https://github.com/openclaw/openclaw/blob/v2026.7.1/LICENSE) 和 [`THIRD_PARTY_NOTICES.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1/THIRD_PARTY_NOTICES.md)。

MIT 允许使用和修改，但不保证无专利、无漏洞或全部依赖均为 MIT。每个引入的源码片段、npm 依赖、插件、字体、模型和二进制资产仍需独立完成许可证与出口/使用条款审查。

## 11. 对 FLAi-OS 的采用分级

| 分级 | 建议内容 | 原因 |
| --- | --- | --- |
| 直接吸收为设计原则 | 一个信任域一个控制单元；Schema 驱动协议/配置；策略逐层单调收紧；精确执行上下文绑定；SecretRef 原子快照；realpath 防逃逸；缺镜像 fail-closed | 与 FLAi-OS 人类唯一签发、fail-closed、运行时真相一致 |
| 可移植实现模式，需重写和测试 | SSRF/IP 分类；配置防误覆盖与 CAS；exec argv/文件绑定分析；认证/控制面限流；脱敏审计事件投影；外部 installPolicy 协议 | 模块边界清楚、MIT 允许，但需按 Python/FastAPI/SQLite 技术栈重做 |
| 仅作产品体验参考 | Gateway/节点状态解释、sandbox explain、安全审计检查目录、审批队列信息架构、Windows Hub 诊断中心 | 用户体验成熟，但 UI 不能代替后端真实状态 |
| 不可照搬 | 单操作者 Gateway 作为全公司平台；沙箱默认 off；`non-main`/`shared` 生产默认；宿主 exec `full + ask off`；DM main session；进程内任务队列；可丢失审计；明文密钥可选；公网运行时插件安装；进程级代理作为唯一出站边界 | 与多用户内网、强审计和国企上线责任不相容 |

## 12. 推荐落地顺序（尚未授权实施）

### P0：上线前必须闭环

1. 定义信任域、租户/密级/项目隔离矩阵和独立 Gateway/执行节点拓扑。
2. 建立不可变 execution snapshot，并让人类审批绑定 snapshot digest；任何输入或策略变化生成新审批。
3. 建立统一 effective policy engine：身份、资源、工具、路径、网络、模型、并发和数据密级一次决策、多处执行。
4. 把沙箱设为强制 `all`，禁止 shared/elevated，默认无网、只读根、无 Linux capabilities。
5. 把授权、审批、配置变更、执行开始/结束、结果封存纳入可靠 outbox + 追加审计；审计不可用时阻断高风险执行。
6. 密钥迁入企业密钥系统，清除磁盘明文，并以扫描结果作为启动/发布门禁。
7. 完成内部制品库、插件/技能批准、SBOM、签名和完整离线安装链。
8. 在 Windows 目标环境完成 ACL、WSL2/虚机、代理、证书、EDR、服务恢复与升级回滚验证。

### P1：规模化前完成

- SQLite Job Runner 增加租约、幂等、恢复、优先级、配额与 per-session 串行键。
- 建立 OS/容器 + 企业代理的强制 egress，接入目的地审计和 DNS 重绑定测试。
- 建立 `security audit --json` 类的持续漂移检查，并把结果映射到 FLAi-OS 五槽信任色；只有 REAL 证据满足门禁才允许绿色。
- 为运维、审批人、安全员、审计员提供职责分离，不允许自批、自签或 LLM 进入判决链。

### P2：体验与生态

- 在不伪造状态的前提下，参考 WorkBuddy 的中文工作台习惯和 OpenClaw 的诊断/解释界面。
- 建立受控插件 SDK 和 out-of-process 插件宿主，再逐步开放内部技能市场。
- 完成多节点容量、故障注入、审计导出、备份恢复和灾备演练。

## 13. 建议验收门禁

| 门禁 | 机械化验证示例 |
| --- | --- |
| 跨租户隔离 | 租户 A 的 agent 以绝对路径、sessionKey、工具参数和插件 RPC 访问租户 B，全部被拒且产生审计 |
| 沙箱强制 | main、group、cron、subagent、重试和恢复 run 均证明在预期镜像摘要内；宿主无对应子进程 |
| 执行审批绑定 | 修改 argv/cwd/env/input digest/image digest/network policy 任一字段，旧审批必须失效 |
| 审计 fail-closed | 杀死审计 writer、填满队列、锁住数据库，高风险执行不得开始；恢复后序列无缺口 |
| 出站控制 | 直接 IP、DNS 重绑定、IPv4-mapped IPv6、metadata、raw socket、子进程均不能绕过 egress policy |
| 密钥隔离 | agent 可读路径、日志、trace、错误、模型上下文和生成配置中不出现长期密钥；未知哨兵不出网 |
| 并发恢复 | 进程在 queued/running/tool-wait 各阶段崩溃，重启后无重复副作用、无跨 session 并发、无任务静默丢失 |
| 供应链 | 未签名、摘要不符、许可证未批、含高危漏洞、来源为 branch/latest 的插件和镜像全部拒绝 |
| 真绿 | mock/未核/已完成但未验证不能显示 REAL 绿色；证据链可追到命令、退出码、制品摘要和审计事件 |
| 离线 Windows | 切断互联网后从内部制品完成安装、启动、升级、回滚、执行和审计导出，命令全部退出 0 |

## 14. 最终判断

OpenClaw 对 FLAi-OS 最有价值的不是“拿来即用”，而是一套已经把个人智能体运行时常见风险显式化的参考实现：Gateway 控制面、策略分层、sandbox explain、exec 审批、SecretRef、SSRF、配置防误覆盖、安全审计和插件供应链都有可复用的思想与源码入口。

正式内网平台必须反过来以 OpenClaw 官方自己声明的限制为设计起点：**它不是敌对多租户边界，沙箱不是默认开启，审批不是鉴权，代理不是 OS 防火墙，shrinkwrap 不是供应链证明，metadata audit 不是不可丢失合规账本。** 在这些边界之上重建企业级强制控制，才是“深度吸收”，而不是把成熟个人助手直接包装成企业安全平台。

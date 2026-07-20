# ADR-0043：JerryAgent 作为 FLAi-OS 核心 Agent-layer 底座

- 状态：Accepted（默认关闭、L0、非生产声明）
- 日期：2026-07-20
- 关联：ADR-0025、ADR-0032、ADR-0035、ADR-0036、ADR-0039、ADR-0040、`docs/research/2026-07-20-intern-discovery-jerryagent-reference.md`

## 背景

FLAi-OS 已经具备任务、事件、密级、产物、判断账本和人工签发的可信主线，但 Agent 执行仍
固定为包内 `workflow.py`。JerryAgent 已有 Pi 运行时、任务生命周期、子智能体/专家编排、
事件存储和 Desktop/TUI 投影；复制这些能力会制造第二套执行内核，也会把治理条件分散到
多个实现。

书生官方公开材料当前能验证的是 Intern-Discovery、InternAgent 与 SCP 的设计谱系，而不是
一份名为“端砚”的公开可复刻规格。可迁移原则是 Generation / Verification / Evolution、
依赖化并行探索、成功与失败经验的跨轮回流、统一能力生命周期和人类反馈；具体 `topic_id`、
实名签收、event gap 或 UI 字段不是已确认的官方事实。本 ADR 只采用前述原则，不把推断冒充
外部产品能力。

## 决策

### 1. 两层真相

JerryAgent 是 FLAi-OS 的核心 **Agent Runtime substrate**，负责计划、推理、并行专家、
子智能体和候选综合。FLAi-OS 是 **Governance / Product Control Plane**，继续唯一持有：

- task / conversation 状态与 SQLite 事实；
- 文件、知识、工具和外置运行时污点分级；
- FLAi event envelope、产物登记与 outcome ledger；
- 具名人工裁决、签发、发布和受控知识回流。

JerryAgent 的 `completed` 只表示侧车运行终止，绝不等于 FLAi `completed`、批准、签发或发布。
JerryAgent 返回的任何 `approved` / `signed` 字段都不进入判决链。

### 2. 深 Module，窄 Adapter seam

`AgentRuntime` 只调用 `AgentExecutionRouter.execute(request)`。Router 按任务创建时冻结的
`execution_adapter + execution_contract_version` 选择内部 adapter：

- `native_python@native.workflow.v1`：保持原 `workflow.py` 行为和事件序列；
- `jerryagent_sidecar@flai.agent-layer.v1`：调用令牌保护的 loopback sidecar。

任务冻结绑定必须与当前已锁定版本 manifest 的 `execution` 精确相等。adapter 缺失、配置关闭、
身份漂移或协议异常都真实失败；禁止静默回退 native，也禁止盲重试具有副作用的 POST。唯一例外是
POST 回执发生传输不确定性，或已经收到 `200/202` 但 bounded envelope 在完整解码前失败（截断、
严格 JSON、媒体/编码、大小或 deadline）：客户端先以已知 `executionId` GET 精确投影并核对完整
身份与 request digest；只有精确 `404 {"error":"not found"}` 才以完全相同的 canonical body
重发一次。第二次回执仍不确定时只再 GET 对账一次，绝无第三次 POST。已完整读取后的 receipt
字段/语义矛盾以及 unexpected HTTP status 不得用 GET 掩盖。

### 3. Sidecar protocol v1

JerryAgent namespace 为 `/api/agent-layer/v1/*`：

- 未配置 `JERRYAGENT_FLAI_TOKEN` 时整个 namespace 返回 404；
- 配置后每个路径要求精确 Bearer token；
- health 返回 product/schema/event schema/instance/session/runtime kind/revision；
- POST executions 以 `executionId + externalTaskId + requestSha256` 幂等；
- POST 另携带 wire-only 六键 `expectedIdentity`，不进入 request digest、不持久化；新执行在落库/dispatch
  前必须与当前 runtime identity 精确相等，已有 exact replay 则保留并返回旧冻结 identity；
- GET execution 只返回 `runtimeTaskId/status/detail/revision/identity` 轻投影；仅在
  `completed` 后再从 `/result` 取 `assistantText`，轮询面不携带消息历史或全局状态；
- v1 不开放 SSE；FLAi worker 只使用有界 polling，避免把 JerryAgent 全局事件面误当成
  单执行可信流；
- v1 不声明运行中 cancel、resume 或文件传输。

配置 token 后 JerryAgent 进入专用 data-plane 模式：只开放上述 namespace，Desktop HTML、
snapshot、commands、capabilities 及全局事件面均为 404。它必须使用固定正端口并禁用 ephemeral
fallback；执行时 instance/session identity 写入 `task.created` 后冻结，重启只改变 health 的
观察者身份，不得重标旧执行。服务端会独立重算 canonical request digest，子 Agent/专家进程
环境显式剔除 bearer secret。

FLAi 客户端只接受精确 `http://127.0.0.1:<port>`（不接受 localhost/IPv6），不读代理环境、
不跟随 redirect。POST 是 canonical UTF-8 JSON 且不超过 64 KiB；每次 I/O 最多 1 秒，并在
逐块读取 bounded JSON 时持续检查同一个总 deadline，拒绝慢滴流拖穿上限。客户端还拒绝
content encoding、重复 JSON key、身份变化和 revision 回退；同 revision 的投影必须完全不变，
任何变化都要求 revision 严格增加。sidecar 的 instance/session 必须为非空，避免多个运行时被
当成同一条执行链。POST 只接受 `202 + replayed=false` 或 `200 + replayed=true` 两种事实组合。
`202` 新执行的首个投影必须绑定本次 health identity；`200 + replayed=true` 或丢回执后的 exact
identity+digest 对账，可以首个精确投影里持久化的历史 identity 建立冻结执行身份，从而兼容
sidecar 重启。`expectedIdentity` 的服务端原子前置条件保证 sidecar 不会在 health 后换代时用新
identity 偷跑 fresh dispatch；后续投影和 result 必须始终匹配已冻结身份。projection/result 的
revision 是全局状态版本；result 只可等于或大于终态投影 revision，最终 receipt 记录 result 的
较新 revision。

### 4. 分类、产物与证据

任何非 `native_python` 绑定都静态派生为 `sensitive`。原因是 sidecar 内部模型、工具和子智能体
调用尚未逐条进入 FLAi `model_calls` / `tool_runs` 账本；loopback 不等于已证明。

Jerry adapter 只获得 FLAi 构造的请求摘要与 event logger，不获得 DB connection、repos、签发
API、knowledge 或 tool registry。首版不读取输入文件内容，只携带 file id 作为“未提供内容”的
边界说明。最终 assistant 文本原子写入固定 `jerryagent_result.md`，带 candidate-only 水印和
request digest；之后仍由 FLAi 完整注册文件、停在 `waiting_review`，由人决定是否签发。

外置执行另写 `agent_layer_started / submitted / observed / receipt` 折叠事件，记录 adapter、
contract、execution id、request digest、runtime identity、final revision，以及
`model_calls_attested_by_flai=false`。不保存私有思维链。

### 5. 默认关闭与部署代际

`jerryagent_research_agent` 保持 `status=disabled`。FLAi API 与 worker 仅在
`FLAI_JERRYAGENT_ENABLED=1` 且 URL/token 精确有效时装配 Jerry adapter；否则只装配 native。
新 worker 认得冻结绑定并会发起外部执行，故 `WORKER_GENERATION` 增加
`+jerryagent-layer-v1`，拒绝新 API/DB 与旧 worker 混跑。

API health 只公开 configured bindings，并显式报告 `runtime_attested=false`；它不通过“配了变量”
冒充 sidecar 在线。真实 attestation 只在任务执行的 health preflight 和不可变 receipt 中产生。
worker 心跳另持久化其**实际 Router canonical binding 集**；`/api/readyz` 要求它与 API Router
逐项 exact 相同，配置分叉即 503。历史/未显式传参的 heartbeat 只见证 native，绝不猜测 Jerry。

## 被拒绝的方案

- **把 JerryAgent 导入为 Python SDK**：当前 JerryAgent 是 Node/Pi runtime，不存在稳定嵌入式 SDK；
  直接导入会耦合私有状态和升级节奏。
- **替换 JobRunner 或 AgentRuntime**：会把状态机、文件核验和人签闸带出 FLAi，破坏唯一真相。
- **Adapter 不可用时跑 workflow.py**：造成同一 task id 在不同执行内核上产出，provenance 失真。
- **首版承诺 cancel/resume**：FLAi 当前只允许 created/queued 取消，running 没有可达 interrupt seam。
- **现在开放通用 JerryAgent 包**：Windows sidecar、token 轮换、进程隔离、实际模型/工具归因尚无证据。

## 后果与后续

当前交付的是生产形态的可信接缝，不是生产准入：默认关闭，禁用 Agent 包，全部外置产物
sensitive。下一阶段必须先取得 Windows 内网双进程监督、精确版本、凭证轮换和故障恢复证据，
再申请 `trial`。

课题空间与经验回流不在本 ADR 内直接放宽 conversation 边界。后续应只把**已人签**产物与结构化
驳回理由写入 topic knowledge scope，并在独立 ADR 中把依赖作用域从 conversation 安全扩展到
topic；JerryAgent memory 只能消费该受控视图，不能把 ambient memory 自动晋升为平台知识。

## 验证

- Agent/task schema 的 native 与 Jerry exact-pair 正负例；
- DB 冻结列默认回填、不可变 trigger 与 API single/batch 绑定；
- native adapter 事件序列回归；
- Jerry default-off、仅 IPv4 loopback/token、canonical 64 KiB POST、慢滴流总 deadline、
  丢回执后的 exact GET/单次同字节重发上限、重启 replay 冻结身份、全局 revision 单调性、
  轻投影与 completed-result 分离负例；
- runtime/worker 关闭释放 adapter transport，worker/API binding 心跳分叉使 readyz/selfcheck 失败；
- Jerry server namespace 404/401、专用 data-plane、固定端口、并发幂等、冲突 409、
  冻结 identity、轻 projection/result 与 secret 子进程隔离；
- FLAi runtime 的 unavailable adapter 无 native fallback、external classification=sensitive；
- 双仓真实 HTTP 握手；
- `bash scripts/verify_all.sh` 与 JerryAgent `npm test`。

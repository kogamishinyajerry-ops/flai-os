# ADR-0044：会话级 Agent Fact 全量投影

- 状态：Accepted
- 日期：2026-07-20
- 关联：ADR-0029（提议约束，非实施授权）、ADR-0032、ADR-0033、ADR-0039、ADR-0043

## 背景

会话主轴与按需监控栏需要同一份任务依赖、等待、接力、人签和 JerryAgent 内部子智能体事实。
前端若分别拼接 FLAi task/event 与 Jerry runtime，会形成第二套状态机，并可能把 Jerry 的
`completed` 或 `awaiting_approval` 冒充为 FLAi 人签。原始 runtime payload、错误正文、prompt、
tool 参数或内部 id 也不应成为浏览器合同。

ADR-0029 的 R1 owner 决策稿仍是未批准提议。本 ADR 只吸收其中“复用既有证据面、不得记录
内部推理、机器事实不得代替人签、不得新造平行 trace/编排平台”的约束；不批准或实施其
G1–G5、S1–S6 项。这里的 Agent Fact 是有界运行事实投影，不是 `decision_evidence`、治理评分或
评测合同。

## 决策

### 1. 单一读取接口

新增 `GET /api/conversations/{conversation_id}/agent-facts`。它只接受认证 principal 的 exact
username；foreign、missing 与 legacy NULL owner 统一 404。响应强制 `Cache-Control: no-store`，
永远返回 `agent_fact_projection.v1` 全量快照，不提供 delta。

快照携带会话全部 task 数量，并只返回按 `created_at DESC, id DESC` 排序的最新 100 项；
`taskCount` 与 `tasksTruncated` 明示截断，禁止把 100 项冒充完整集合。所有时间归一为 UTC `Z`。

### 2. FLAi 权威事实

依赖只来自 task 的冻结 `depends_on`。依赖 gate 只允许：

- 通过下述全部结构化决定、原始事件、不可变 witness 与 task 终态咬合校验的人工批准：
  `human_signed`；单独存在 `review_approved` event 不能放行；
- 冻结 `agent_version` manifest 同时显式声明 `model.profile == "none"` 与
  `workflow.requires_human_review is False`：`deterministic_provenance`；
- 未终结、失败或无法建立冻结 provenance：`pending | failed | unknown`。

当前 Agent registry 不参与历史依赖放行判据，包升级、缺 profile、空 manifest 都不能把历史任务
改判为确定性。生成任何 dependency/handoff 字段前，投影必须一次性证明每个冻结 dependency
真实存在且 `conversation_id` 与已授权会话逐字相同；缺行、跨会话、非字符串或重复边都使整份
快照以无事实正文的 503 fail-closed，不能跳过坏边或泄漏另一会话的 task id/status。

人签不能只看 `task_human_decisions` 行。`approved/rejected` 必须同时证明唯一
`task_review_event_witnesses.witness_kind='structured_v1'` 与原始 review event 的内部 id、task、
agent、type、level、message、payload bytes、时间逐字一致，payload 六键与 decision 精确绑定；
decision action 还必须与 task terminal status、`updated_at/finished_at == decision.created_at` 及
reject error rendering 一致。任一见证缺失或终态漂移只投影 `unknown`，不返回 reviewer/decidedAt。
Jerry approval、自由文本或 task `completed` 本身都不是签发。

handoff 只从原子 `dependency_resolved` event 派生，并只输出已声明 upstream 与 downstream 的
task id 和时间。event message、其余 payload 与产物正文不进入投影。

尚未产生决定时，`pending_result / awaiting_human / not_required` 也只读取 task 冻结
`agent_version` 的 manifest；当前 registry 升级不得改写历史提示。冻结 manifest 缺失、损坏或
`requires_human_review` 非显式 bool 时投影 `unknown`。

### 3. Jerry 只补内部 runtime

native task 固定 `reported=false, reason=not_applicable`。Jerry reader 只访问精确 loopback
`GET /api/agent-layer/v1/executions/{executionId}/facts`，沿用 Bearer、禁代理、禁 redirect、
1 秒 I/O 和 1 MiB strict JSON 上界。

reader 要求 top/nested exact keys、闭合 status/wait/hold/subagent 枚举、安全整数 revision、
连续一基 ordinal、合法 retry 引用、timezone-aware timestamps，以及
`executionId == externalTaskId == FLAi task id`、小写 64 hex request digest。identity 被删除，只把
canonical identity SHA-256 暴露为 `sourceEpoch`；实际子智能体 id、自由文本、错误字符串均不返回。

语法正确仍不够：request digest 必须等于 FLAi 不可变 `agent_layer_started` witness。每次提交还必须
在 `agent_layer_submitted` 之后、首次 observed/receipt 之前落唯一 `agent_layer_identity_bound` 事件，
把 execution、runtime task、request digest 与六字段 runtime identity 精确冻结。fresh submission 的
bound identity 必须匹配 started 的 instance/session；exact replay 也只允许使用这份 durable historical
identity，不能从当前 sidecar 进程身份补猜。`agent_layer_submitted.runtime_task_id` 是不可省略的 durable binding；facts 的
`runtimeTaskId` 必须与其逐字相同。所有合法 `agent_layer_observed` 的最大 revision 是重启后仍有效的
revision floor；facts 不得倒退，terminal receipt 的 final revision 也不得低于该 floor。一旦 durable
`agent_layer_receipt` 存在，facts 还必须与 identity-bound 及 receipt 的冻结 instance/session/runtime kind
三方一致，且 revision
不得低于 receipt final revision。waiting_review/completed 的 Jerry task 缺 receipt 一律 malformed；
不依赖当前 registry 建立任何 identity。

Jerry wait 还要满足跨字段不变量：`awaiting_approval` 与 `runtime_approval` 一一对应；terminal status
不能携带 wait 或活跃子智能体；armed hold、subagent completion/retry 的 subject、count、hold phase
必须互相咬合。任何一处矛盾都折叠为 malformed，不能留给浏览器猜测。

handoff 与 Jerry binding 查询只读取所需 `agent_log.workflow_event_type`，各自最多接受 4096 条相关
event；第 4097 条使整份投影 503 fail-closed，海量无关事件不占用此额度。disabled、transport
failure、精确 404、任意合同异常分别折叠为
`disabled | unreachable | not_found | malformed`，FLAi snapshot 仍返回 200。一个 snapshot 首次发现
sidecar unreachable 后，对其余 Jerry task 启用 snapshot-local circuit breaker，避免 100 个任务把
1 秒 timeout 乘成 100 秒。所有 Jerry GET 还共享 DB 读取事务结束后才启动的 2 秒 snapshot deadline；
每次 GET 使用 `min(1s, remaining)`，耗尽后其余 Jerry task 统一报 `unreachable`，不会持锁访问网络。

### 4. 等待优先级

task-level `wait` 是前端唯一文案映射输入，优先级固定为：FLAi dependency → FLAi human signoff →
Jerry internal wait。它只携 closed kind、结构化 subject/ordinal/count 与 `continueWhen`，不携带自由文本。
全部 dependency gate 已满足时 `wait` 必须为 null，不能制造 `pendingCount=0` 的伪等待。

## 被拒绝的方案

- 前端并行读取并合并两个系统：会制造客户端判决链与竞态。
- 把 Jerry `completed`/approval 投影成人签：违反“人是唯一签发者”。
- 用当前 registry 判历史 deterministic：升级后会漂移，缺字段还可能 fail-open。
- runtime 失败令整个 endpoint 失败：会让 FLAi 权威任务事实随可选 sidecar 一起不可用。
- 返回全部 raw event/runtime payload：泄漏正文和内部实现，且不是稳定 UI 合同。

## 验证

- exact owner、legacy owner、no-store 与全量 envelope；
- dependency waiting、冻结 deterministic gate 与原子 handoff；
- 版本漂移、缺 profile fail-closed；
- 结构化人工批准/驳回，Jerry approval 不冒充人签；
- 仅有弱/stale `review_approved` event 不得释放依赖，也不得落入 deterministic provenance 分支；
- 缺 review witness、decision/status 漂移、task terminal 时间漂移均降为 unknown；
- 缺失/跨会话 dependency 整份快照 503 且不泄漏依赖 id；
- Jerry valid sanitization、started digest、submitted runtime task、最大 observed revision、terminal
  receipt 与 durable identity-bound 咬合、wait/status 不变量、identity/ordinal/revision/free-text
  malformed、404、disabled、unreachable；
- unreachable 单次 circuit breaker、2 秒 snapshot deadline；
- 无关 event 被 SQL 过滤，相关 event 第 4097 条 fail-closed；
- 101 tasks 返回 count=101、items=100、truncated=true。

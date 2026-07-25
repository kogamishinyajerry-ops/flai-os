# ADR-0029：V0.2 治理、评估与生产证据补强（R1 owner 决策稿）

- 状态：**提议·R1 owner 决策稿（未批准、未授权实施）**
- 起草：2026-07-20
- R1 修订：2026-07-20
- 决策人：owner（待具名）
- 本地事实基线：`main` / `origin/main` 均指向 `7523edf`；原工作区为
  `feat/eval-async-queue@e504595`，落后本地 `main` 80 个提交
- 依据：
  1. 阿里云 Agentic Cloud 深度研究报告
     （`/Users/Zhuanz/Downloads/deep-research-report (2).md`）；
  2. 《FLAi-OS vs 端砚 — COMAC 内网部署深度评估报告》
     （`/Users/Zhuanz/.codex/attachments/86455910-e66f-470e-8d52-c5cb3957d899/pasted-text.txt`）；
  3. FLAi-OS 宪法、ADR-0013/0015/0018/0019/0021/0023/0028、
     `docs/07_Eval_Standard.md` 与 `docs/PRODUCTION-READINESS-PROGRAM.md`。

> **授权边界**：本 ADR 是 owner 的决策输入，不是实现授权。owner 未具名批准前，
> 不得据此修改运行时代码、数据库 schema、事件枚举、公开接口、Agent Package 或部署形态。
> 每个被批准项仍需独立实施计划、invalid-first 测试、tamper witness 和完成证据。

## 0. R1 为什么重写 R0

R0 抓到了五个有价值的方向，但混合了历史快照、外部平台宣传、当前主线事实、
生产准入门和长期成熟度，不能直接作为实施清单。R1 做四项纠偏：

1. **以当前本地主线为准**：不把已完成的 P0 代码项重复立项；目标机步骤与代码步骤分开。
2. **不做未经证实的外部优越性比较**：删除“已超过 AgentLoop”“持平或更深”等无法从
   对方公开实现复算的结论。外部报告只提供审计维度，不提供 FLAi-OS 的认证或排名。
3. **复用既有深模块与 seam**：G3 复用现有 stats 模块；G1 复用
   `task_events/model_calls/tool_runs` 证据面，不另造平行 KPI/trace 平台。
4. **把管理叙事改成机械证据**：人工评测有版本化契约；治理成熟度改为控制证据表；
   故障恢复必须有演练，不以“写完蓝图”冒充能力完成。

本次只读复核未执行远端刷新。`7523edf` 是 2026-07-20 本机可见的
`main` / `origin/main`，**不声称是 GitHub 当前最新远端**。任何实现开始前必须刷新代码真相。

## 1. owner 决策摘要

| 决策项 | R0 方案 | R1 建议裁决 | owner 终裁 |
|---|---|---|---|
| D29-1 / G2 | 四维人工评分 | **接受方向，重写为版本化人工评测合同** | ⬜ |
| D29-2 / G3 | 新建 `/api/platform/kpi` | **条件接受；复用 `/api/stats/overview`，先定指标语义** | ⬜ |
| D29-3 / G1 | `workflow_trace` + rationale + `/trace` | **拒绝原形；改为结构化决策证据，不记录内部推理** | ⬜ |
| D29-4 / G4 | 五维 1–5 分治理自评 | **拒绝自评分；改为控制—证据—差距登记表** | ⬜ |
| D29-5 / G5 | 新建故障恢复蓝图文档 | **接受方向；并入生产就绪纲领，以恢复合同和演练收口** | ⬜ |
| D29-6 / 部署安全 | 角色、TLS、国密、容器、SBOM 一并列 P0 | **拆分裁决；授权/TLS/供应链接受，国密与容器条件化** | ⬜ |
| D29-7 / 外部平台 | 引入 SCP、独立评审智能体等 | **只吸收评审独立性；不引入平行协议或签发型 LLM** | ⬜ |

**推荐 owner 选择**：条件批准 D29-1 至 D29-7 的 R1 裁决，仍不批准任何运行时代码实施；
先完成 §10 的 P0 基线刷新与 Gate 1 目标机证据，再逐项授权。

## 2. 当前事实：已具备、已完成、仍缺什么

### 2.1 已具备的证据面

| 能力 | 当前事实 | 本 ADR 的态度 |
|---|---|---|
| 输入输出与任务留痕 | tasks、samples、task_events；eval origin 隔离 | 复用，不另建证据库 |
| 工具调用留痕 | tool_runs + tool_version + started/finished/failed | G3 以 tool_runs 为事实源 |
| 模型调用留痕 | model_calls 记录 profile/name/status/摘要/token usage | G1 只引用，不要求暴露内部思维 |
| 评测与晋升 | ADR-0018 eval runner、digest、snapshot、curation、promotion 人签 | G2 为人工质量评测补合同，不替换绝对晋升门 |
| 平台聚合 | 已有 `GET /api/stats/overview` | G3 在同一 stats 模块深化，不建平行接口 |
| worker 生命迹象 | main 已有独立 `/api/readyz` 心跳就绪探针 | 不再要求把 worker 强塞进 `/api/health` |
| 失败样本回流 | samples → draft eval case → 人工策展 | 不另建“数据飞轮平台” |

### 2.2 本地主线已完成但仍需目标机闭合的 Gate 1 项

以 `main@7523edf` 的生产就绪追踪表为准：

- DB 本地盘 fail-closed：代码项已完成；
- 交互结构声明收窄与 interactive Agent 声明护栏：已完成；
- worker readiness：已通过 `/api/readyz` 完成代码落点；
- 模型网关 timeout 可配置与测量脚本：代码已完成，仍缺目标模型 p99 实测；
- 备份工具已存在，仍缺目标机计划任务与一次真实 restore drill；
- Gate 1 最终仍缺具名 owner 终裁。

**因此，本 ADR 不重复登记上述代码项。** 目标机 p99、备份恢复和 owner 终裁继续由
`PRODUCTION-READINESS-PROGRAM` 单一 SSOT 管理。

### 2.3 仍然真实存在的缺口

1. 人工评审集只有原则，没有版本化、可校验的记录合同；
2. stats 聚合已有浅接口，但缺少口径稳定、可复算的运行与质量指标；
3. workflow 的关键机器决策缺少统一的证据引用格式，但不能用内部推理文本补；
4. 平台级治理缺少控制—证据—差距视图；
5. 备份、reaper、readyz 等分散存在，仍缺幂等/重试/fallback/RTO/RPO 的恢复合同与演练；
6. 身份认证已存在，但运行时用户授权轴仍缺；生产 HTTPS、供应链证据仍未闭合。

## 3. D29-1 / G2：版本化人工评测合同（建议接受）

### 3.1 决策

扩展 docs/07 的 Human Review Set：机器评测与人工质量评测继续分离，人工评测记录
必须通过版本化 JSON Schema。人工评分**不可自动变成晋升通过**；只有真人可以记录
`adopted|needs_revision|not_adopted`。

### 3.2 外部 interface

候选路径：`contracts/human-review.schema.json` 与
`evals/<agent_id>/human_review/*.json`。每条记录至少要求：

```text
schema_version
rubric_version
review_id
task_id
agent_id
agent_version
reviewer_username
reviewed_at
evidence_refs[]
dimensions.correctness
dimensions.completeness
gates.honesty
gates.traceability
decision
notes
```

口径：

- `correctness`、`completeness`：有锚点的 1–5 分；Agent 可在公共 envelope 内引用
  自己的 domain rubric，不强迫不同工程任务用同一条细则；
- `honesty`、`traceability`：严格 boolean gate。`false` 是一条有效的失败评审，
  不能被其他高分抵消；
- 缺字段、未知 schema/rubric 版本、证据引用不可解析：记录 **INVALID**，不计入已评审；
- `reviewer_username` 必须来自认证身份或具名 Git 评审证据，不接受 LLM 自报名字；
- V0.1 封板文件不回写。R1 rubric 基线应新建记录，引用不可变的历史 task/eval snapshot，
  或在 V0.2 新跑等价 case；绝不修改旧证据冒充当时已做四维评审。

### 3.3 Done when

1. docs/07 明确公共 envelope、domain rubric、两项 gate 与“不得自动晋升”；
2. JSON Schema 对 required/type/enum/additionalProperties 全部 fail-closed；
3. 至少一条完整通过、一条 gate=false、一条缺字段 INVALID 的 fixture；
4. validator 单测先证无 `honesty` 字段必拒，再实现到绿；
5. tamper：删除 required 或把 `"false"` 当 true 后，对应测试必红；
6. 至少一个 Agent 形成 R1 基线记录，证据能反查 task、Agent 版本与产物摘要。

### 3.4 不证什么

- 不证人工分数客观；
- 不证不同 Agent 的 4 分可横向直接比较；
- 不证一条人工评审可以替代固定用例、tamper 或 promotion 绝对门。

## 4. D29-2 / G3：深化现有 stats 模块（建议条件接受）

### 4.1 决策

不新增 `/api/platform/kpi`。已有 `GET /api/stats/overview` 是真实 seam；在该模块内部
集中聚合，必要时以 additive nested object 或同模块的窄只读 route 演进。任何公开形状
变更须先补 response contract 和兼容测试。

G3 与 worker readiness **没有代码依赖**。排在 Gate 1 之后是优先级裁决，不是技术依赖。

### 4.2 指标定义约束

所有指标必须返回 `definition_version / since / until / sample_count / numerator /
denominator`，并遵守：

| 指标 | 事实源 | R1 口径 |
|---|---|---|
| 用户任务终态分布 | tasks | 只计 `origin='user'`；completed/failed/cancelled 分列；非终态不塞进成功率分母 |
| 工具运行结果 | tool_runs | 按 tool_runs.status 计，不以 task_events 数量冒充调用次数 |
| 任务时延 | tasks timestamps | 明确起止点；p50/p99 同时报样本量；小样本不做 SLA 外推 |
| 人审流量 | task + review events | 报 required/approved/rejected/pending；不称“人工接管率” |
| token 用量 | model_calls | 先报 token；只有价格表有 version 且适用于 resolved model 时才报 estimated_cost |
| eval 结果 | eval_runs | 与线上违规率分开；eval failed 不是宪法违规 |
| 知识检索 | knowledge_search | 仅在 hit/miss/refused payload 口径被契约化后统计 |

明确拒绝 R0 三个公式：

- `review_approved / (review_approved + auto_completed)`：`auto_completed` 不是 Task 状态；
- `eval failed / total = 违规输出率`：错误合并质量失败与治理违规；
- `event 数 = tool 调用数`：重试/重复事件会使口径漂移，已有 tool_runs 应作事实源。

### 4.3 Done when

1. 指标定义表先经 owner 审议，字段名、分母、排除项和空窗口行为冻结；
2. response contract 明确 unknown/null/zero 的差异；无数据不得假造 0% 成功率；
3. SQLite fixture 覆盖成功、失败、取消、等待人审、eval-origin、重试工具调用；
4. e2e 证明 eval-origin 不污染用户指标；
5. tamper：把 failed 计入 completed、把事件重复计数、删 origin 过滤，至少各有一条测试必红；
6. 前端只展示定义已有证据的字段，不先画空洞 KPI 仪表盘。

## 5. D29-3 / G1：结构化决策证据（拒绝原 trace，建议替代）

### 5.1 明确拒绝

不采纳以下 R0 interface：

- `rationale`、`alternatives_considered` 等自由文本“推理轨迹”；
- 宣称能还原 LLM 内部思考；
- 为同一份 task_events/model_calls/tool_runs 另建 `/api/tasks/{id}/trace` 平行投影。

理由：这些字段不可证明是模型真实推理，可能泄露敏感上下文，并会激励 workflow 编造
形式化“思考过程”。FLAi-OS 需要的是可审计的输入、规则、动作和结果，不是 chain-of-thought。

### 5.2 条件接受的替代 interface

若后续确有两个以上不同 workflow 与一个真实 UI/审计消费者，允许提议
`decision_evidence.v0.1`：

```text
step_id
stage
decision_code
rule_or_policy_refs[]
input_evidence_refs[]
output_artifact_refs[]
model_call_ref
actor_kind
result
```

约束：

- 不存原始 prompt、内部推理、未脱敏替代方案；
- refs 必须能反查既有 event/tool_run/model_call/file；
- 先通过既有任务详情/时间轴投影消费；只有既有 interface 无法满足真实消费者时，
  才可另提 route ADR；
- 一个 workflow 的一次性字段不是 seam。至少两个不同 workflow 复用同一合同并通过
  同一 validator，才证明该 interface 值得进入公共契约。

### 5.3 Done when

1. 先提交消费者场景与字段删除测试；删除任一字段会让哪个审计问题不可回答必须明确；
2. 两个不同 workflow 产出同一合同；
3. 任务时间轴可由 refs 回到真实证据；
4. 敏感输入 fixture 证明 payload 不泄露原文；
5. tamper：伪造不存在的 model_call/file ref 必被拒；
6. 文案只称“决策证据”，不得称“完整推理轨迹”。

## 6. D29-4 / G4：平台治理控制证据表（拒绝自评分，建议替代）

### 6.1 决策

不建立“身份/权限/审计/数据分级/合规各 1–5 分”的自评表。无锚点总分容易形成管理假绿。
改为平台治理控制证据登记表，候选路径：
`docs/10_Platform_Governance_Controls.md`。

每条控制至少包含：

```text
control_id
domain
applicability
applicability_owner
required_evidence
implementation_state
verification_state
evidence_links
owner
residual_risk
next_action
```

状态只允许：`unknown | not_applicable | planned | implemented | verified`。
`implemented` 无独立证据不得写 `verified`；`not_applicable` 必须有具名裁决和理由。

管理面如需总览，只能展示 verified/implemented/planned/unknown 的计数与缺口，不汇总成
“3.2/5”式单分数。

### 6.2 外部标准与合规边界

R1 将“不引入外部标准”修订为：

> 不宣称获得 ISO、EASA、等保、密评或其他外部认证；但必须维护适用性判断，记录哪些
> 标准或组织控制适用、由谁裁定、证据是什么。外部标准可作为控制来源，不可作为宣传背书。

国密/密评不得由本 ADR 自行定性。国家密码管理局《商用密码应用安全性评估管理办法》
针对依法应使用商用密码保护的重要网络与信息系统，要求形成密码应用方案、选择适用指标并
说明不适用项；FLAi-OS 是否落入范围及采用何种方案，必须由商飞正式责任主体或合格机构裁定。
官方来源：`https://www.nca.gov.cn/sca/xxgk/2023-10/07/content_1061109.shtml`。

### 6.3 Done when

1. 至少覆盖身份、授权、审计、数据分级、发布供应链、恢复、合规适用性七域；
2. 每个 `verified` 控制有可打开证据与验证日期；
3. 至少一个 `not_applicable` 和一个 `unknown` fixture/示例，证明系统允许诚实报缺；
4. owner 审查所有 applicability_owner 与 residual_risk；
5. 全文无“通过认证”“达到适航级”等证据外推。

## 7. D29-5 / G5：恢复合同与演练（建议接受并合并 SSOT）

### 7.1 决策

不以新增 `docs/11_Failure_Recovery_Blueprint.md` 作为完成判据。恢复属于生产就绪模块，
判据并入 `PRODUCTION-READINESS-PROGRAM`；操作步骤进入既有部署监督/运维 runbook。
若未来拆文件，生产纲领仍是状态 SSOT，runbook 只承载操作实现。

### 7.2 必须补齐的恢复合同

| 故障域 | 必答问题 |
|---|---|
| task/workflow | 哪些状态可重入；崩溃后失败、重试、人工重排分别适用什么条件 |
| 工具副作用 | 幂等 key/receipt 在哪；求解启动、文件写入等动作是否允许自动重放 |
| 模型调用 | 哪些错误可重试；profile/model fallback 是否显式；provenance 改变后如何标记证据失效 |
| worker/队列 | 心跳失效如何发现；非终态任务谁回收；卡队列如何人工处置 |
| SQLite/文件 | backup、restore、文件实体与 DB 一致性如何检查；会话如何吊销 |
| 运维目标 | RTO/RPO 由谁批准；当前目标机能力能否满足；不满足时如何 fail-closed 声明 |

自动 fallback 必须显式：不得从 reasoning 静默切 standard 后继续冒充同一来源；模型、参数、
工具或外部状态变化导致 provenance 不一致时，结果必须标记失效、重评或转人工，而非假绿。

### 7.3 Done when

1. 形成幂等/重试矩阵，所有有副作用工具逐项列明 `automatic_retry_allowed is True|False`；
2. 单测覆盖可重试与不可重试错误，严格使用 `is True`；
3. 演练至少覆盖：worker 中断、模型不可用、工具超时、DB restore 四类；
4. 目标机 restore drill exit 0，截断备份的 tamper drill 必失败；
5. RTO/RPO 有具名 owner、日期和证据等级；
6. 文档完成只能标 `planned/implemented`，没有演练证据不得标 `verified`。

## 8. D29-6：部署安全与供应链建议的拆分裁决

这些建议来自端砚对标报告，但不应混进 G1–G5 的评估实现。R1 只给 owner 决策方向：

### S1 · 运行时授权轴——建议接受，真实 sensitive 数据进场硬前置

- 当前认证只证明“是谁”，没有用户 role/capability 的统一强制点；
- 不直接把 `admin/agent_developer/business_user` 三值焊死为最终模型；
- 先定义权限矩阵：平台管理、Agent 发布/晋升、评测触发、人工签发、敏感数据访问、审计读取；
- 在单一 policy seam default-deny，路由与内部调用共享同一判定；
- SSO/AD 组是生产 adapter，本地用户是当前 adapter；测试使用内存身份/权限 fixture；
- 必测越权、同任务自审、未知角色、停用用户、sensitive 访问五类负例。

### S2 · HTTPS 与会话信任——建议接受，按部署 profile 实施

- 生产 TLS 可终止在可信反代/网关，不要求 FastAPI 自己持证书；
- 生产 profile 的 session cookie 必须 `Secure`，HSTS 在 TLS 终止层；
- HTTP 只允许显式开发/隔离 profile，启动与健康信息必须如实暴露其降级信任等级；
- 不把“应用未监听 TLS”误判为必须在应用内实现 TLS。

### S3 · 国密/密评——条件接受，拒绝“裸 SM3 密码迁移”

- 先完成系统定级、密码应用需求与适用性裁决；
- 不以“央企内网”四字自动推出等保三级或某个密码改造清单；
- 不把现有带 salt/work factor 的 PBKDF2 直接替换成裸 SM3；
- 若正式方案要求商密算法/产品，必须按合规方案实现并由有权主体评估。

### S4 · CI、SBOM、签名发布——建议接受；容器化条件化

- 复用 `scripts/verify_all.sh/.ps1`，区分提交快速门与完整手工/夜间门；
- 生成离线 SBOM、依赖哈希、构建 provenance 和签名 release manifest；
- manifest 覆盖 backend、frontend、contracts、agents、tools 与 SBOM，不只签 `agents/`；
- 部署目录只读，启动/部署自检核验 manifest；
- Windows 原生离线包是当前主部署 adapter；只有目标基础设施、CAE 驱动和许可证允许时，
  才新增 OCI adapter。Dockerfile 不是所有 COMAC 内网场景的统一准入门。

### S5 · `sample_run_dir` 允许根——建议接受，但绑定模块激活

`monitor_adapter_gen_agent` 读取外部目录；激活前必须校验配置允许根、resolve 后 containment、
symlink 逃逸和非目录输入。该项是该模块激活硬前置，不冒充全平台当前 P0。

### S6 · 多级密级——暂缓

当前 `internal|sensitive` 只回答“能否离场”，虽粗但有执行语义。没有商飞正式密级模型、
角色权限矩阵、改级审批与审计前，不增加 `confidential|secret` 等只有标签没有行为的枚举。

## 9. D29-7：外部平台建议的吸收与拒绝

| 外部建议 | R1 裁决 | 理由 |
|---|---|---|
| 独立评审智能体 | 吸收“提议者与评估者分离”，但只能 `REJECTED|REVIEWABLE` | LLM 永不签发、晋升或改活包，人是唯一签发者 |
| SCP/统一科研协议 | 不引入 | 当前 Tool/Agent 合同已有真实 seam；无第二生产 adapter 时不造假抽象 |
| JSON 证据链 | 复用并深化现有链 | task_events/tool_runs/model_calls/eval snapshot 已是 SSOT，缺口是完整性而非协议名 |
| 端砚私有化替代 | 不进入架构结论 | 公开证据不足以证明内网私有化、航空数据治理、国产算力或采购适用性 |
| 端砚公开试用 | 可作隔离研究 | 只用公开、非敏感材料，不把体验结果当生产资格证据 |
| AgentBay/桌面/移动沙箱 | 不进 V0.2 | 非当前 CAE 主战场 |
| ANOLISA/Token-less/OS 优化 | 不进 V0.2 | 未证为当前承重瓶颈 |
| STAROps 运维自治 | 不进 V0.2 | 先把确定性恢复合同与人工运维做好 |
| 新多 Agent 编排平台 | 不进 V0.2 | 协作继续走既有 Task/depends_on/Team 路径，不造第二内核 |
| MCP Server 统一代理 | 不进 V0.2 | ADR-0004 仍有效；有真实 adapter 需求时另议 |
| 商业模式/定价/外采 POC | 不进本 ADR | FLAi-OS 是商飞自建底座，采购研究是另一决策域 |

## 10. 实施顺序与 Stop-if

```text
P0 事实刷新（任何实现前）
  刷新远端 main → 在干净隔离 worktree 重定位证据 → 重新索引 → verify_all
  若失败或无法确认 tracker/主线真相：STOP，不改运行时

Gate 1 目标机闭合（既有 SSOT）
  备份计划任务 + restore drill
  目标模型延迟样本 + p50/p99 + timeout 配置
  owner 具名导入终裁

真实 sensitive 数据进场前
  S1 运行时授权轴
  S2 HTTPS/会话生产 profile
  S3 正式合规适用性裁决

V0.2 第一批（可独立验收）
  G2 人工评测合同
  G5 恢复合同与演练
  S4 CI/SBOM/签名 release manifest

V0.2 第二批（需定义先行）
  G3 stats 语义与聚合深化
  G4 治理控制证据表

条件触发
  G1 decision evidence：仅在 2 个 workflow + 1 个真实消费者成立后
  S5 sample_run_dir 允许根：仅在 monitor_adapter_gen_agent 激活前
  OCI adapter：仅在目标环境/CAE/许可证已确认支持后
```

**Stop-if（任一命中即停止相关实现）**：

1. 无法刷新或确认实现基线，当前 checkout 仍落后主线；
2. 需要修改宪法、人签红线、信任色五槽或既有 promotion 绝对门；
3. 需要泄露 sealed/sensitive 原文或内部推理才能让方案成立；
4. 指标没有唯一事实源、分母或空窗口语义；
5. 合规要求只能靠开发者推测，未获有权主体适用性裁决；
6. 实现需要覆盖用户现有 `docs/reviews` 证据或在脏工作区重跑截图型 E2E；
7. G1 只有一个 emitter、没有真实消费者，却要求新增公共事件/route；
8. G5 只有文档、没有可执行演练，却准备标记 verified。

## 11. 与既有 ADR / SSOT 的关系

| 既有决策或文档 | R1 关系 |
|---|---|
| ADR-0013（审计硬化） | G1/G3 复用 model_calls/tool_runs，不复制存储 |
| ADR-0015（Knowledge 内核） | 知识指标只有在 hit/miss/refused 契约足够时才开放 |
| ADR-0018（M10 治理闭环） | G2 是人工质量合同；绝不替换 eval/promotion 绝对门 |
| ADR-0019（鉴权） | S1 在认证身份上新增授权，不重写认证 seam |
| ADR-0021/0025（数据分级） | S1 解开 sensitive 黑洞；S6 不擅自扩密级枚举 |
| ADR-0023（日志审计） | G4/S4 登记完整性证据；WORM/外发由部署设施与合规裁决 |
| ADR-0028（同源律评估） | 保持候选与签发分离；不以自我评测宣称成熟 |
| PRODUCTION-READINESS-PROGRAM | Gate 1 与 G5 的状态 SSOT；本 ADR 不维护重复勾选表 |
| docs/07 Eval 标准 | G2 的规范入口；公共 envelope 与 domain rubric 分层 |

## 12. 状态追踪（owner 批准后才可从“提议”迁移）

| ID | 项 | R1 建议状态 | 实施授权 | Verified 证据 |
|---|---|---|---|---|
| G2 | 版本化人工评测合同 | 建议接受 | — | — |
| G3 | 深化现有 stats 模块 | 建议条件接受 | — | — |
| G1 | 结构化决策证据 | 原形拒绝、替代方案条件接受 | — | — |
| G4 | 平台治理控制证据表 | 原形拒绝、替代方案接受 | — | — |
| G5 | 恢复合同与演练 | 建议接受并入既有 SSOT | — | — |
| S1 | 运行时授权轴 | 建议接受，真实 sensitive 数据前置 | — | — |
| S2 | HTTPS/会话生产 profile | 建议接受 | — | — |
| S3 | 国密/密评适用性 | 待正式裁决；裸 SM3 方案拒绝 | — | — |
| S4 | CI/SBOM/签名发布 | 建议接受；容器化条件化 | — | — |
| S5 | sample_run_dir 允许根 | 激活前条件项 | — | — |
| S6 | 多级密级 | 暂缓 | — | — |

## 13. owner 终裁区

owner 请选择一项并具名：

- [ ] **条件批准 R1（推荐）**：批准 §1 的 R1 裁决方向；不授权运行时实现。
  实施必须按 §10 分批另行授权。
- [ ] **选择性批准**：仅批准以下 ID：`____________________________`。
- [ ] **退回 R2**：需补充或修改：`________________________________`。
- [ ] **拒绝本 ADR**：理由：`______________________________________`。

```text
owner：
日期：
基线 commit：
批准条件 / 残余风险：
```

## 14. 诚实边界

- 本 ADR 不证明 FLAi-OS 达到任何外部 Agent 平台、等保、密评、适航或生产成熟等级；
- 不证明端砚/Agentic Cloud 公开宣传对应其内部真实实现；
- 不证明 `main@7523edf` 是远端当前最新，只记录本机 2026-07-20 可见事实；
- 不证明文档判据已经落地；没有测试、tamper、目标机或具名人签证据即不得写 verified；
- 不重开或篡改 V0.1 封板证据；R1 新评审只能新增并引用历史证据；
- 不授权机器签发、自动晋升、修改活包、绕过 promotion 门或静默 fallback；
- 不以 KPI、治理总分或外部对标替代工程事实与 owner 责任。

---

*R1 将 R0 的“补强清单”改为 owner 可选择的条件决策合同。owner 终裁前，全文均为提议。*

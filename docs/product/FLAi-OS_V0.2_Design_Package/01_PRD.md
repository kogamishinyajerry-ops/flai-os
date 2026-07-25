# FLAi-OS V0.2 产品需求文档（PRD）

> 文档性质：V0.2 产品与验收 Interface。它将已接受 ADR 转换为待设计、待实现、待验证的产品需求，不授权修改运行时代码，也不把未来目标写成当前能力。术语以 [`CONTEXT.md`](../../../CONTEXT.md) 为准，决策冲突时以 [`docs/adr/`](../../adr/) 为准。
>
> Phase 0A 的精确输入预算、36 个 mandatory cases、Bench 门和未来实施切片见 [15_Phase_0A_MVP_Spec.md](15_Phase_0A_MVP_Spec.md)。其产品与合同语义已在设计会话中冻结并打开隔离 Stage C 原型门；组织身份签发、正式 Stage C 验收和 Stage D 实施授权仍未成立。

## 1. 状态标签

| 标签 | 含义 |
|---|---|
| `IMPLEMENTED-VERIFIED` | 当前精确范围、版本与环境有可复跑机械证据，绑定命令、结果引用和日期；不等于生产就绪 |
| `IMPLEMENTED-PARTIAL` | 有可复用骨架或局部实现，但未满足目标需求。 |
| `ACCEPTED-NOT-IMPLEMENTED` | owner 已接受产品方向，尚未形成可验收实现。 |
| `DECLARED-NOT-VERIFIED` | 有历史或文档声明，但本设计包未复核到足以准入的当前证据。 |
| `OUT-OF-SCOPE` | 当前版本主动排除。 |

## 2. 背景与问题

现有 FLAi-OS 已证明轻内核、Agent/Tool Package、任务事件、模型网关、协作会话和评测治理等基础结构可以成立，但这些结构尚未自动形成一个中国工程用户愿意长期使用的企业 Agent 产品。当前需要同时解决五类问题：

1. **工作体验**：用户给出目标后，不能被规划表、逐动作授权和内部 schema 反复打断；同时必须清楚 Agent 正在做什么、依据什么、还缺什么。
2. **工程可信**：规章、命令、边界条件和工程建议必须来自可追溯依据；缺失和冲突不能由模型猜测填平。
3. **企业控制**：Sandbox、身份授权、数据分类、网络外联、并发预算、取消强杀、恢复和审计必须在上线前形成可证伪门。
4. **组织共建**：真实需求要进入版本化路线图，能力要经过 FLAi Bench，使用、成本和价值要由事实派生，而不是闭门规划或手填指标。
5. **入口与信任域割裂**：外网研发需要飞书/GitHub 协作，内网业务用户需要一个自托管
   FLAiWorkspace；两者不能靠实时同步、共享身份或共享 Secret 粘在一起。Internal
   Forge/Registry、FLAi、Knowledge、Audit 和内部 Secret owner 各守权威事实。

## 3. 产品目标与非目标

### 3.1 Phase 0A 产品目标

- 让 5–8 名具名技术验收人员在 macOS 上通过工程智能体工作台完成三条黄金工作流的最小闭环；
- 证明不中断自治会话、受控执行、真实状态、证据链和末端 Delivery Bundle 可以共同成立；
- 建立权威知识最小发布/检索/引用链与 FLAi Bench 首批三套基准包；
- 让需求信号、路线图承诺、工程 Issue、能力发布和用户反馈能够回链；
- 用 fail-closed 负例证明越权、无依据、篡改、未知门和假绿不能通过。

### 3.2 非目标

以下均为 `OUT-OF-SCOPE`：

- Phase 0A 直接服务 20–30 名业务用户或处理未批准的真实敏感数据；
- 用 OpenClaw/OpenHands 替换控制内核，或导入第二套任务、权限、审计和晋级事实；
- 全自主 CFD 求解、工程校核或自动签发；
- 实时会议伴随、语音转写、自动通知、自动催办和完整责任事项生命周期；
- 同时交付完整 Office 全家桶、邮件发送和 Office GUI 控制；
- 建设领导驾驶舱、个人产能排名、Token 排名或无分母“完成度”；
- Windows 适配；本阶段只验收 macOS 首发质量；
- 声称生产就绪、适航级、通过外部认证或证明全面业务价值。

### 3.3 V0.2 目标态补充：双环境、内网自托管入口

`ACCEPTED-NOT-IMPLEMENTED` 飞书只作为外网研发团队的协作 Hub；正式内网默认入口是自托管
FLAiWorkspace，工程智能体工作台是其中的专业执行 Surface。两个域只通过
AirGapExchange 的签名离线发布包和独立脱敏反馈包交换成果。该目标不改变 Phase 0A 当前
“synthetic fixture、无真实协作 Connector、无内网写入”的冻结边界。

## 4. 用户与职责

| 用户/职责 | 核心任务 | 可做 | 不可做 |
|---|---|---|---|
| 试点使用者 | 发起任务、核对结果、反馈需求 | 提交目标和材料；查看本人任务；末端签发有资格的 Bundle | 改写策略、评测结果或路线图状态 |
| 会议负责人/工程签发人 | 对精确产物和例外负责 | 批准或退回精确 Delivery Bundle | 以空白授权、永久 Full Access 或口头确认代替版本绑定 |
| 需求策展人 | 保持需求池可读、可追踪 | 去重、合并、拆分、脱敏、请求证据 | 正式采纳路线图 |
| 领域评审人 | 审查专业口径与验收标准 | 提供具名、版本化专业评审 | 代替路线图负责人排序，或豁免安全门 |
| 安全评审人 | 审查权限、Sandbox、外联、密级、审计与破坏性动作 | 对不安全路径阻断 | 代替业务负责人宣布需求已解决 |
| 路线图负责人 | 签发某一版本共建地图 | 采纳、暂缓、不采纳并给出理由 | 让 AI 代签；绕过适用的领域/安全门 |
| 交付负责人 | 将已承诺能力实现为发行 | 创建 Issue、实现、回链证据 | 以代码合并或自测通过自行关闭用户问题 |
| 平台管理员/Agent Owner | 维护运行与能力资产 | 在授权作用域内管理 Agent、策略、队列、评测和恢复 | 使用粗粒度 admin 身份绕过职责分离 |

这些是能力与作用域职责，不要求立即扩展为固定全局角色枚举。最终授权应集中在单一 Policy Seam；当前粗粒度角色只是试点授权实现，不是满足统一身份 Interface 的可替换 Adapter。

## 5. 当前可复用基线

| 基线 Module | 当前事实 | 状态 | V0.2 使用方式 |
|---|---|---|---|
| Agent Registry / Agent Package | 已有配置、schema、版本、限制、成熟度与注册校验 | `IMPLEMENTED-PARTIAL` | 作为能力发布包的一部分深化，不另建 Agent 商店内核 |
| Task Center / Event Log / File Service | 已有任务状态、追加事件、文件与产物记录 | `IMPLEMENTED-PARTIAL` | 继续作为任务与证据事实源 |
| Agent Runtime / SQLite Job Runner | 已有 job 执行、队列与恢复骨架 | `IMPLEMENTED-PARTIAL` | 演进到 SessionExecutionGrant、受控并发、强杀 Sandbox 和 Delivery Bundle，不冒充已完成 |
| Model Gateway / Tool Registry | 统一模型与工具调用并记录调用事实 | `IMPLEMENTED-PARTIAL` | 保持唯一调用 Seam；扩展策略、版本和 receipt 证据 |
| 导引/协作工作台 | 当前 main 已有会话、任务召集和工作台骨架；`safe_auto` 只存在于 ADR-0047 记录的历史 commit-bound 分支证据，不是本基线事实 | `IMPLEMENTED-PARTIAL` | 当前基线不得宣称已有自动执行；未来只能选择性吸收历史不变量，不能把旧分支称为 ADR-0050 目标会话 |
| Knowledge Module | BM25 file_dir × document、Scope、引用、default-deny 已有 | `IMPLEMENTED-PARTIAL` | 补权威类别、发布生命周期、时间有效性、精确锚点和任务快照 |
| Eval / Snapshot / Promotion | 已有用例、快照、人工评审与真人晋级骨架 | `IMPLEMENTED-PARTIAL` | 深化为冻结能力发布包与四轨 FLAi Bench |
| Stats / Today / Feedback | 已有少量聚合、活动视图和任务反馈入口 | `IMPLEMENTED-PARTIAL` | 复用事实 Seam；不能把客户端近况或四个计数冒充共建地图指标体系 |
| 生产与安全状态 | 当前设计包没有全部目标机、Sandbox、权限、审计和负载门的全绿证据 | `DECLARED-NOT-VERIFIED` | 默认 NO-GO；每项门必须独立复核后才能改变状态 |

## 6. 核心用户旅程

### 6.1 发起与连续执行

1. 用户从单一 Composer 描述目标并上传允许的材料。
2. 控制内核冻结输入快照、解析身份与任务授权、选择已批准能力发布包。
3. Agent 在授权预算和 Sandbox 中连续规划、执行、观察、验证、恢复。
4. 工作台显示可验证的当前阶段、完成步骤、受阻原因、产物和证据摘要；不展示伪造思维链。
5. 缺失事实、冲突和策略禁止项不触发连续表单，而是形成聚合例外；安全的只读工作可以继续。
6. Agent 冻结 Delivery Bundle；具名真人在末端对精确版本批准或退回。
7. 涉及真实外部效果时，提交前重新校验身份与策略，CAS 单次消费授权；真实执行另产 receipt 与后置验证。

### 6.2 需求共创到能力发布

```text
自然语言需求信号
  → AI 预处理草稿
  → 人工策展
  → 领域/安全适用门
  → 路线图负责人签发版本
  → 工程 Issue
  → 能力发布包
  → FLAi Bench
  → 限范围发布与原提出者验收
```

每层保留自己的事实，使用稳定引用连接。任何层都不能自动提升下一层的权威性。

## 7. 功能需求

### 7.1 工程智能体工作台

| ID | 需求 | 验收要点 | 状态 |
|---|---|---|---|
| WB-01 | 内网 FLAi 工作收件箱与工程执行入口都以目标导向 Composer 为首要动作，可附加工作流允许的文件 | 发起三条黄金工作流不要求先填写 Agent 设计卡、权限矩阵或内部 JSON | `ACCEPTED-NOT-IMPLEMENTED` |
| WB-02 | Agent 自动推导可由材料和上下文确定的字段 | 相同事实不重复询问；无法确认的事实保留为未知，不能编造 | `ACCEPTED-NOT-IMPLEMENTED` |
| WB-03 | 会话中不出现通用逐工具、逐命令、逐文件审批 | 自动化范围只包含已授权、可逆、可停止且有 receipt 的动作 | `ACCEPTED-NOT-IMPLEMENTED` |
| WB-04 | 提供真实进度与渐进披露 | 每个可见状态由 task/event/tool/model/file 等事实支撑；无证据不显示“完成” | `ACCEPTED-NOT-IMPLEMENTED` |
| WB-05 | 聚合展示依据缺口、冲突、推断和责任字段缺失 | 用户在末端一次处理；会阻止不可逆动作的例外必须明确 | `ACCEPTED-NOT-IMPLEMENTED` |
| WB-06 | 生成不可变 Delivery Bundle | Bundle 至少绑定输入、产物 hash、差异、验证、残余风险、策略版本和待交付动作 | `ACCEPTED-NOT-IMPLEMENTED` |
| WB-07 | 只有认证、具名且有作用域资格的人可签发 | Bundle 漂移、过期、权限变化、重复消费均 fail-closed | `ACCEPTED-NOT-IMPLEMENTED` |
| WB-08 | 支持取消、超时、阻断和受控恢复 | 取消/强杀结果与未完成副作用可见；不得以“completed”覆盖失败 | `ACCEPTED-NOT-IMPLEMENTED` |

### 7.2 智能办公助手：DOCX 技术报告润色

| ID | 需求 | 验收要点 | 状态 |
|---|---|---|---|
| OFF-01 | 只接收允许预算内的 DOCX 和用户目标 | 非 DOCX、恶意包、超预算或解析异常均明确拒绝 | `ACCEPTED-NOT-IMPLEMENTED` |
| OFF-02 | 只在隔离副本上编辑 | 原始文件字节和摘要保持不变 | `ACCEPTED-NOT-IMPLEMENTED` |
| OFF-03 | 保持技术内容诚实 | 数字、单位、公式、表格、图片无静默变化；无法保真则拒绝或列入例外 | `ACCEPTED-NOT-IMPLEMENTED` |
| OFF-04 | 交付可核对结果 | 修改后 DOCX、修改摘要、重要差异、待确认问题、输入/输出摘要和执行证据齐全 | `ACCEPTED-NOT-IMPLEMENTED` |

### 7.3 CFD 工程助手：OpenFOAM 算例体检

| ID | 需求 | 验收要点 | 状态 |
|---|---|---|---|
| CFD-01 | 在只读、隔离环境解包并检查受支持 OpenFOAM 算例 | Zip Slip、符号链接逃逸、超预算、未知文件类型等负例 fail-closed | `ACCEPTED-NOT-IMPLEMENTED` |
| CFD-02 | 对规定检查域产出结构化 findings | 每条含检查项、当前设置、判断状态、风险、文件/字段锚点、建议和未知前提 | `ACCEPTED-NOT-IMPLEMENTED` |
| CFD-03 | 区分权威依据、工程师确认假设、模型建议 | 三类不可互相提升；缺少工况、物性或网格日志时显示未知 | `ACCEPTED-NOT-IMPLEMENTED` |
| CFD-04 | 首版禁止写入和求解 | 文件树与摘要不变；不存在 solver launch；报告明确不构成工程校核 | `ACCEPTED-NOT-IMPLEMENTED` |

### 7.4 会议行动助手：会后纪要与行动项

| ID | 需求 | 验收要点 | 状态 |
|---|---|---|---|
| MEET-01 | 接收批准的文本型会后材料 | 不采集实时音频、不加入会议、不自动外发 | `ACCEPTED-NOT-IMPLEMENTED` |
| MEET-02 | 生成带来源锚点的议题、决策、共识、未决问题和责任事项 | 任一组织事实都可回到来源；模型推断单独标记 | `ACCEPTED-NOT-IMPLEMENTED` |
| MEET-03 | 强制责任事项字段完整性 | 产出、唯一负责人、期限、验收标准、验收人任一缺失即保持例外，不能补造 | `ACCEPTED-NOT-IMPLEMENTED` |
| MEET-04 | 会议负责人签发精确版本 | Phase 0A 仅产生隔离 `SYNTHETIC/TEST` receipt；真实组织签发须待 R6/获批 Phase 0B，并由同一 owner-local transaction 创建正式记录、全部五字段责任项与一个绑定全体引用的 OwnerCommitReceiptV1 | `ACCEPTED-NOT-IMPLEMENTED` |

### 7.5 权威知识底座

| ID | 需求 | 验收要点 | 状态 |
|---|---|---|---|
| KNOW-01 | 提供逻辑统一、物理可联邦的知识目录与检索 Interface | 文件目录、DMS、Obsidian 等通过 Adapter 接入；索引不拥有权威性 | `ACCEPTED-NOT-IMPLEMENTED` |
| KNOW-02 | 已发布项绑定权威与生命周期语义 | 稳定 ID、发布主体、责任人、批准证据、不可变版本/摘要、密级、范围、有效期、替代关系齐全 | `ACCEPTED-NOT-IMPLEMENTED` |
| KNOW-03 | 所有组织要求与工程依据有精确锚点 | 至少定位到版本摘要和条款/章节/页码/单元格或等价位置 | `ACCEPTED-NOT-IMPLEMENTED` |
| KNOW-04 | 缺失、冲突、过期、撤销和范围不明 fail-closed | 回答“无法确认”并列来源；LLM 不选择看似合理版本 | `ACCEPTED-NOT-IMPLEMENTED` |
| KNOW-05 | 普通上传、会议草稿和 AI 产物不能自动晋升 | 只有具名授权真人可签发发布/撤销；受信源系统只提供上游签发 attestation；密级沿任务和产物传播 | `ACCEPTED-NOT-IMPLEMENTED` |

### 7.6 FLAi Bench

| ID | 需求 | 验收要点 | 状态 |
|---|---|---|---|
| BENCH-01 | 评测对象是冻结能力发布包 | Agent、prompt/workflow/schema、实际模型 endpoint/参数/tokenizer、Tool/Adapter、Sandbox、预算/权限/出站策略、完整 ReleaseKnowledgeBinding binding digest、用例/rubric/Gate Policy/environment 均有版本或摘要 | `ACCEPTED-NOT-IMPLEMENTED` |
| BENCH-02 | 提供确定性回归、工程质量、安全治理、运行效率四轨结果 | 轨道保持独立，不折算成一个综合分 | `ACCEPTED-NOT-IMPLEMENTED` |
| BENCH-03 | 不可抵消门 fail-closed | 必测 failed/invalid/skipped/unknown/不可解析任一存在即不可晋级 | `ACCEPTED-NOT-IMPLEMENTED` |
| BENCH-04 | 评测资产 draft→approved→retired | AI/线上样本只能产生 draft；具名维护者批准金标准 | `ACCEPTED-NOT-IMPLEMENTED` |
| BENCH-05 | 三条黄金工作流各有首批基准包 | 每包绑定版本化领域 rubric、真实/synthetic 标签和密级 | `ACCEPTED-NOT-IMPLEMENTED` |
| BENCH-06 | 未资格候选只能凭 EvaluationAdmission 运行 Bench | 具名 Eval maintainer 绑定 actor/scope、精确 release/approved synthetic fixture/pack、预算、TTL、epoch 和零外部效果；伪造 `origin=eval`、普通用户、真实数据或外部效果在 task 前拒绝 | `ACCEPTED-NOT-IMPLEMENTED` |

### 7.7 共建地图与需求闭环

| ID | 需求 | 验收要点 | 状态 |
|---|---|---|---|
| CO-01 | 全员可只读查看“战略目标→地基→工作流→能力发布→证据” | 地图不成为默认工作台，不持有独立任务或评测状态 | `ACCEPTED-NOT-IMPLEMENTED` |
| CO-02 | 路线图人工版本化，节点状态证据派生 | 无证据显示未知/待补/受阻；不能手工点绿 | `ACCEPTED-NOT-IMPLEMENTED` |
| CO-03 | 用户用自然语言低门槛提交需求 | 自动绑定认证身份、时间、来源和可用上下文；无长 PRD 表单 | `ACCEPTED-NOT-IMPLEMENTED` |
| CO-04 | AI 只做预处理草稿 | AI 不采纳、不拒绝、不定优先级、不派人、不排期 | `ACCEPTED-NOT-IMPLEMENTED` |
| CO-05 | 合并/拆分不丢来源 | 原文、提出者、时间、证据与关系保持不可变/追加 | `ACCEPTED-NOT-IMPLEMENTED` |
| CO-06 | 生命周期变化有理由并回告 | 已收到、补证/合并、候选、采纳、规划、开发、验证、发布、暂缓/不采纳均可追踪 | `ACCEPTED-NOT-IMPLEMENTED` |
| CO-07 | 需求池、路线图、Issue 各守事实层 | 只有已签发承诺可创建交付 Issue；能力发布、Bench 和验收回链原需求 | `ACCEPTED-NOT-IMPLEMENTED` |

### 7.8 指标与价值证据

| ID | 需求 | 验收要点 | 状态 |
|---|---|---|---|
| METRIC-01 | 每个指标有版本化定义 | `definition_version/since/until/sample_count/fact sources/formula` 齐全；unknown/null/zero 可区分 | `ACCEPTED-NOT-IMPLEMENTED` |
| METRIC-02 | 活跃只计认证 user-origin 工作 | 不以账号数、页面访问或 eval 任务冒充活跃 | `ACCEPTED-NOT-IMPLEMENTED` |
| METRIC-03 | Token 只作为资源成本 | 无个人 Token/生产力排行；无适用价格表时成本显示未知 | `ACCEPTED-NOT-IMPLEMENTED` |
| METRIC-04 | 节省时间来自基线与抽样 | 报区间、样本量和覆盖率；无基线不估算，不用运行时长或 LLM 自评推导 | `ACCEPTED-NOT-IMPLEMENTED` |
| METRIC-05 | 全员视图保护隐私 | 小样本抑制/合并/脱敏；个人明细只对本人和授权治理角色可见 | `ACCEPTED-NOT-IMPLEMENTED` |

### 7.9 双环境协作、内网 Workspace 与离线准入

| ID | 需求 | 验收要点 | 状态 |
|---|---|---|---|
| HUB-01 | 外网研发与内网运行属于不同 DeploymentTrustZone | 无共享身份、Secret、数据库、webhook、Runtime 控制或自动数据回流 | `ACCEPTED-NOT-IMPLEMENTED` |
| HUB-02 | 内网日常管理与治理从一个 FLAiWorkspace 发现和编排 | 默认工作收件箱；自托管通讯/Wiki/项目只是 Adapter；工作台和内部 Code Forge 是受控专业 Surface | `ACCEPTED-NOT-IMPLEMENTED` |
| HUB-03 | Workspace 投影同域权威事实 | 每个投影绑定 owner、version/digest、classification、freshness 和 source evidence；人工改协作字段不反写 owner | `ACCEPTED-NOT-IMPLEMENTED` |
| HUB-04 | 正式写动作编译为版本化 typed intent，高影响动作采用 prepare/commit | commit 使用新鲜内网 attestation，重验 digest、职责、作用域、ACL、classification、epoch、职责分离和 TTL | `ACCEPTED-NOT-IMPLEMENTED` |
| HUB-05 | 只有有效 OwnerCommitReceiptV1 才显示治理变迁生效 | 运行使用 witness，Internal Forge/Registry 使用 verified provider state；卡片/页面/HTTP 2xx 不等于 owner commit | `ACCEPTED-NOT-IMPLEMENTED` |
| HUB-06 | effect unknown、source gap 与投影漂移可对账 | 同一 effect key 查证；不得换键重放、last-write-wins 或用旧绿掩盖 stale | `ACCEPTED-NOT-IMPLEMENTED` |
| HUB-07 | GitHub 只拥有外网代码事实，Internal Forge/Registry 拥有已导入源码和制品 | GitHub SHA 在内网只是 provenance；内部 receipt/Qualification/Deployment/witness 才证明接纳与运行 | `ACCEPTED-NOT-IMPLEMENTED` |
| HUB-08 | Secret 完全分域 | 外网 `secrets-stackdocker` 与内网 Secret owner 使用独立 root/namespace/value；禁止 `.env`/硬编码 fallback；Safety keys 继续独立 PKI/HSM/Time owner | `DECLARED-NOT-VERIFIED` |
| HUB-09 | Workspace/通讯/Wiki 故障不阻断安全止损 | 独立密封通道仍可 kill/revoke/isolate/invalidate、开对账案和向本地 WORM 封存证据 | `ACCEPTED-NOT-IMPLEMENTED` |
| HUB-10 | 目标自托管 Surface 未获目标密级批准时不复制受限正文 | 只显示脱敏摘要、稳定引用、重新鉴权深链或存在性抑制 | `ACCEPTED-NOT-IMPLEMENTED` |
| HUB-11 | Safety TTL、Policy fence 与 provider send 边界可机械证明 | TTL 只用签名时间区间+单调 checkpoint；alias CAS 同事务推进 fence，Envelope 绑定 PRE/POST witness；Claim 不等于 send，唯一 egress 一次性消费 capability，Attempt 无 receipt 禁止重放 | `ACCEPTED-NOT-IMPLEMENTED` |
| HUB-12 | AirGapExchange 是唯一跨域入口 | Bundle 内容寻址、签名、closed-world、quarantine、内部扫描/复测/双人准入和 ReleaseSet CAS；反馈仅 allowlist + synthetic reproducer | `ACCEPTED-NOT-IMPLEMENTED` |

## 8. 非功能与治理需求

| ID | 需求 | 必须可验证的行为 | 状态 |
|---|---|---|---|
| SEC-01 | 身份与对象级授权 | 任何任务、文件、知识、Bundle、评测和治理对象都在请求与提交时重验主体、作用域和策略；未知即拒绝 | `ACCEPTED-NOT-IMPLEMENTED` |
| SEC-02 | Sandbox 隔离 | 每会话/任务有受控文件、进程、环境、资源、网络和时间预算；不能越过允许根或访问未授权宿主资源 | `ACCEPTED-NOT-IMPLEMENTED` |
| SEC-03 | 取消与强杀 | 超时、用户取消、策略撤销可终止进程树；终止后保留真实状态、残余副作用和 receipt | `ACCEPTED-NOT-IMPLEMENTED` |
| SEC-04 | 网络外联 default-deny | egress 仅由版本化策略和目的地白名单开放；DNS/IP/重定向变化不能绕过 | `ACCEPTED-NOT-IMPLEMENTED` |
| SEC-05 | 数据分类传播 | 输入的最高分类沿摘要、引用、任务、事件、模型调用、产物和导出传播，不能因生成而降级 | `ACCEPTED-NOT-IMPLEMENTED` |
| SEC-06 | 追加且防篡改的审计证据 | 认证主体、策略版本、动作、结果、对象摘要、时间和 receipt 可重建；缺失记录不能以应用日志补绿 | `ACCEPTED-NOT-IMPLEMENTED` |
| SEC-07 | 自托管 Surface identity 与内部 ActorBinding 分离 | Surface user id 只能来自受信 channel/SSO；instance/subject 映射、credential epoch、职责和作用域均版本化，频道管理员不自动授权 | `ACCEPTED-NOT-IMPLEMENTED` |
| SEC-08 | Classification-aware projection | 目标 Surface ceiling、来源密级或 ACL unknown 时正文不投影；深链重新鉴权 | `ACCEPTED-NOT-IMPLEMENTED` |
| REL-01 | 并发与预算 | 用户、Agent、工具和后端并发有显式配额；队列拥塞、取消、超时和公平性可观测 | `ACCEPTED-NOT-IMPLEMENTED` |
| REL-02 | 恢复与幂等 | 每类副作用标明是否可自动重试；模型/工具/provenance 变化不得静默继承旧结果 | `ACCEPTED-NOT-IMPLEMENTED` |
| REL-03 | Hub 最终一致性与对账 | owner 调用后丢失响应进入 `effect_unknown`；投影 gap/stale/drift 不能点绿或参与签发 | `ACCEPTED-NOT-IMPLEMENTED` |
| HON-01 | 真实状态与失败语义 | `failed/invalid/skipped/unknown` 不得映射成 completed 或绿色；`completed` 不代表工程有效 | `ACCEPTED-NOT-IMPLEMENTED` |
| UX-01 | macOS 首发质量 | 三条工作流在目标分辨率和键盘路径可用；错误、空态、等待、受阻、签发均有设计和验收基线 | `ACCEPTED-NOT-IMPLEMENTED` |

## 9. Module、Interface 与 Seam 约束

产品需求应收敛到以下深 Module，而不是把内部实现扩散到每个页面和 Agent：

| Module | 外部 Interface 应回答什么 | Seam / Adapter 策略 | Depth 与 Locality |
|---|---|---|---|
| Control Kernel | 谁可运行什么能力、任务处于何态、哪些证据有效 | Authorization、Broker、Artifact、Audit 由窄 Interface 接入 | 调用方不学习 Adapter 私有状态机；恢复与审计规则集中 |
| Session Execution | 开始、观察、重连、协调恢复与取消 | Broker 组合 AgentRuntimePort、SandboxProviderPort、ToolExecutionPort；动态动作无 ExecutionTicket 即拒绝 | Agent Loop 复杂度隐藏在会话 Interface 后，且无第二事实源 |
| Authoritative Knowledge | 在指定身份、时间、范围下哪些依据当前有效 | file_dir、DMS、Obsidian 等是内容 Adapter；BM25/向量是检索 Adapter | 权威、冲突与时间语义集中，不散落 Prompt |
| Capability Release / FLAi Bench | 这个精确能力版本是否具备哪类证据 | Runtime 是唯一评测执行路径；评审记录是证据输入，deterministic runner 只有满足统一 EvalExecutor Interface 时才称 Adapter | 变更一次即重评，发布规则集中 |
| Delivery Bundle | 用户究竟对哪个输入、产物、风险和动作签发 | 提交 Adapter 按外部系统变化；Bundle Interface 不变 | 不可逆动作与 UI 分离，签发语义集中 |
| Co-building Projection | 现有事实如何投影成路线图和指标 | 复用 task/events/tool/model/eval/promotion/feedback/stats；只读投影 | 指标定义集中，页面不各算一套 |
| InternalWorkspaceHub | 内网用户可看什么，以及 typed intent 是否已被 owner 接受 | 外部只暴露 `open/prepare/commit`；通讯、Wiki、内部身份、FLAi 与 SecretProvider 是 Adapter | 一个内网入口隐藏多平台复杂度，但不产生第二事实 owner |
| AirGapExchange | 外网成果能否成为内网候选，哪些最小反馈可外发 | `sealRelease/admitRelease/sealSanitizedFeedback`；各 Registry 先写 quarantine | 跨域供应链、准入和最小化集中，不形成同步桥 |

一个只有单一实现且没有测试替身或替换需求的地方，不应为了“架构感”预造 Seam。Interface 是调用与测试的共同表面，验收应通过该表面观察结果，不穿透实现细节。

## 10. Phase 0A 入场准备与退出验收

两组门不得混用。`Entry readiness` 决定是否允许邀请 5–8 名验收人员；`Exit acceptance` 是 Phase 0A 运行中产生的整合与用户证据。任一 Entry 门未知即不开始，任一 Exit 门未知即不得宣称 Phase 0A 通过。

### Gate A：Entry readiness

- 试点名单恰为 5–8 名具名技术验收人员；未在名单中的账号访问被拒；
- 数据清单只包含 approved `source_kind=synthetic` 材料，正常样本仅以 `fixture_class=canonical` 标识；真实敏感数据测试必须失败；
- macOS 构建、版本摘要、依赖和配置清单冻结；当前混合工作树不能作为发行物。
- 三条 tracer release、Phase 0A eligible decision、精确 DeploymentBinding、停止/撤权/回退脚本均冻结；
- 统一授权、附件检疫、Sandbox/强杀、queue/lease、受控出口、审计 outbox 和 Delivery CAS 的实验室 P0/conformance 套件通过。

### Gate B：Exit — 整合执行与安全

下列负例在入场前先以实验室 fixture 通过，并在 Phase 0A 实际 macOS 基线上重复取得整合证据：

- 每个任务绑定不可变输入、能力发布包、策略、ReleaseKnowledgeBinding 与运行时 TaskKnowledgeSnapshot 摘要；
- Sandbox 越权读写、进程逃逸、网络外联、超时、取消和强杀负例全部按预期失败；
- 并发超过用户/工具/后端预算时排队或拒绝，不能绕过配额；
- 任务中途没有通用 Action 审批；策略结果为 `deny` 的动作只能进入聚合 blocked 且任何末端授权都不可覆盖，只有 `defer_to_delivery` 的精确动作可以进入 Delivery Bundle；
- Delivery Bundle 篡改、过期、重复消费、签发人越权和提交前权限漂移均被拒。

### Gate C：Exit — 三条工作流

- Office 包证明原 DOCX 不变，受保护内容无静默变化，差异与例外齐全；
- CFD 包证明只读、不启动 solver，所有 finding 有真实文件/字段锚点，缺依据显示未知；
- Meeting 包证明不虚构决策、负责人和期限，责任字段缺失阻止正式签发；
- 每条工作流至少有一名非开发者技术验收人员按固定脚本完成全旅程。

### Gate D：Exit — 知识与评测

- 权威知识的普通上传越权发布、过期引用、冲突、范围不明和密级降级负例全部失败；
- 三套 FLAi Bench 包均冻结完整 capability-release manifest；
- 安全、诚实、依据链和关键回归任一门为 false/invalid/skipped/unknown 时晋级被拒；
- LLM judge 或能力作者无法自行批准金标准、评审或发布。

### Gate E：Exit — 审计、恢复与产品诚实

- 任一任务可由证据引用重建主体、输入、策略、知识、模型、工具、产物、Bundle 和真实 receipt；
- worker 中断、模型不可用、工具超时、数据库恢复至少各完成一次规定演练；
- UI 任何绿色状态都能反查证据；删除/篡改证据后界面降级为未知或失败；
- owner 对精确 Phase 0A 发行物与剩余风险具名签发。

## 11. Phase 0B 放大门

Phase 0B 不能只因 Phase 0A“体验不错”启动，必须同时满足：

1. Phase 0A 全部门仍有效，且无未关闭的安全绝对门失败；
2. 至少一条工作流接入真实工具与真实数据，并完成领域准确性、安全、分类和恢复验收；
3. 20–30 名具名业务用户、Agent 清单、项目范围、数据域、并发预算和支持责任人已冻结；
4. FLAi Bench 对拟开放能力重新评测，旧 synthetic 结果不得自动继承到真实环境；
5. 需求反馈、事故回告、撤回能力、版本回滚和用户支持路径可实际执行；
6. 指标定义、隐私抑制和节时基线经具名人员批准；无基线指标保持未知；
7. 扩大试点由具名 owner 对精确发行物和范围签发。

## 12. 成功口径

Phase 0A 的成功是**机制与最小工作流被证伪式验证**，不是产能宣传。首批应报告：

- 每条工作流完成、失败、受阻、退回与签发的任务数和样本量；
- 必测安全门与 Bench 门的通过/失败/未知矩阵；
- 证据完整率、来源缺口和人审退修原因；
- 模型、工具、时间、并发与 Token 消耗；无价格表不报成本；
- 用户采用或退回结果及定性反馈；
- 只有建立人工基线后才报告节时区间和覆盖率。

禁止输出一个综合“平台成熟度分”或个人生产力排行。

## 13. 决策与后续工件跟踪

Stage B 的产品与字段合同已由本次设计会话明确冻结，并已打开隔离 Stage C 原型门；但
`accepted_by_actor_id` 与正式 `decision_digest` 仍未由组织身份系统签发。下表的
`ACCEPTED-NOT-IMPLEMENTED` 只表示设计语义可被 Stage C 消费，不表示 Stage C 已正式验收，
更不授权 Stage D、Runtime、Schema、真实数据或试点。只有对应 future artifact/gate 真实通过
才能改变实现或准入状态。

| 事项 | Stage B frozen design resolution | Required future artifact / gate | 状态 |
|---|---|---|---|
| Phase 0A 人群与职责 | `15` 已冻结 cohort=5–8 的设计语义及选择/角色/签发合同；未虚构具名人员 | Entry 前的精确 actor/device 清单、scope、期限、职责分离与正式签发证据 | `ACCEPTED-NOT-IMPLEMENTED` |
| DOCX tracer | OOXML Transitional、保真、归档/内容/Token 预算、活动内容拒绝和差异合同见 `15 §6` | D11/D12 approved fixtures、parser/writer/font digests、tamper 与真实 artifact evidence | `ACCEPTED-NOT-IMPLEMENTED` |
| CFD tracer | Foundation 11、pimpleFoam/foamRun(incompressibleFluid)、只读范围、预算与 finding schema 见 `15 §7` | D11/D13 pack、rule/parser digests、进程/文件/锚点 witnesses | `ACCEPTED-NOT-IMPLEMENTED` |
| Meeting tracer | `.txt/.md/.docx`、锚点、五字段行动项与零 connector 见 `15 §8` | D11/D14 approved fixtures、抽取/冲突/外部效果 witnesses | `ACCEPTED-NOT-IMPLEMENTED` |
| Sandbox/并发/网络 | threat model、4 GiB/2 cores、host reserve、session/lane ceiling、零 Adapter 直连、一个受控模型端点与 kill/revoke 合同见 `14`/`15` | D6/D8/Entry 的真实 macOS isolation、kill、network、capacity 与 no-host-fallback evidence | `ACCEPTED-NOT-IMPLEMENTED` |
| 权威知识 | KnowledgeItem 生命周期、真人签发、完整 ReleaseKnowledgeBinding、TaskKnowledgeSnapshot、锚点与冲突算法见 `11`/`15` | D10/D11 的 typed publish、catalog/binding/snapshot digests、ACL/conflict/tamper evidence | `ACCEPTED-NOT-IMPLEMENTED` |
| Capability release / Bench | identity/envelope、EvaluationAdmission、四轨结果、Gate Policy、36 cases 与三套 rubric 见 `12`/`15` | D11 validator、approved pack bytes/digests、真人 review 与 qualification evidence | `ACCEPTED-NOT-IMPLEMENTED` |
| 共建地图与需求闭环 | 节点、需求事件、签发权、通知 outbox 与指标定义合同见 `13` | Phase 0A 只读 projection 属后续获批切片；完整协作/通知/运营扩展不夹带进三条 tracer | `ACCEPTED-NOT-IMPLEMENTED` |
| 双环境与内网 Workspace | 外网研发 Hub 见 `17`，AirGapExchange 见 `18`，内网自托管 Workspace 见 `19` | 新 SHA 七域评审后再分别授权 POC/Adapter；现阶段无生产 Schema、真实连接、导入或部署授权 | `ACCEPTED-NOT-IMPLEMENTED` |

## 14. 追踪关系

| PRD 范围 | 决策来源 |
|---|---|
| 唯一控制内核、可替换执行后端 | ADR-0049 |
| 不打断会话、末端 Delivery Bundle | ADR-0050 |
| Phase 0A/0B | ADR-0051 |
| 工作台、治理中心、共建地图、指挥中心顺序 | ADR-0052、ADR-0059 |
| 三条黄金工作流及首个 tracer bullet | ADR-0053～0056 |
| 权威知识 | ADR-0057 |
| FLAi Bench | ADR-0058 |
| 需求共创、路线图签发与职责分离 | ADR-0060～0061 |
| 飞书外网研发协作中枢 | ADR-0062（范围已收窄） |
| 双信任域、AirGapExchange 与内网自托管 Workspace | ADR-0063 |

---

*V0.2 PRD · 2026-07-23 · 先经架构评审与 MVP 冻结，再授权实现*

# 09 能力发布包与 Agent/Workflow 生命周期

> 文档状态：`ACCEPTED-NOT-IMPLEMENTED`
>
> 本文定义 V0.2 目标生命周期。生命周期的一级对象是**能力发布包**，不是单个 Agent。现行 Agent 状态仍以 [Agent Package 标准](../../02_Agent_Package_Standard.md) 为准；评测与发布方向以 [ADR-0042](../../adr/ADR-0042-flai-bench-evaluation-foundation.md) 为准。

## 1. 为什么不能只管理 Agent

一个可用工作流的真实行为同时受 Prompt、Workflow、Schema、实际模型、Tool/Adapter、Sandbox、权限/网络策略、知识版本和评测包影响。只把 `agent.yaml.version` 或模型名作为生命周期对象，会产生三个错误：

1. 关键依赖漂移后仍沿用旧评测和旧签发；
2. 同一 Agent 在不同知识或权限范围内被错误视为同一能力；
3. `status=released` 被误读为安全、工程质量和业务价值全部通过。

因此，Agent、Workflow、Tool 和知识各自保持资产生命周期；拟试点或发布时，由它们组装成不可变的能力发布包，FLAi Bench 和人类签发只绑定该精确对象。

## 2. 现状与目标模型的差异

| 维度 | 当前现状 | V0.2 目标 | 实施状态 |
|---|---|---|---|
| Agent 可见性 | `draft → trial → released`，可随时 `disabled` | 保留，继续回答“谁能看见/能否调用这个 Agent Package” | `IMPLEMENTED-PARTIAL` |
| Agent 成熟度 | L0–L3，与 status 正交 | 保留为 Agent 子资产治理信息，不等同于能力准入 | `IMPLEMENTED-PARTIAL` |
| 评测对象 | 以 Agent 包和 eval cases 为主 | 冻结完整能力发布包，四轨 FLAi Bench | `ACCEPTED-NOT-IMPLEMENTED` |
| 试点暴露 | 主要随 Agent status/role 表达 | Phase 0A/0B 绑定精确发布包、名单、数据域和策略 | `ACCEPTED-NOT-IMPLEMENTED` |
| 发布签发 | Agent status/changelog 与现有人审记录 | 具名人类对精确包及其范围作发布签发 | `ACCEPTED-NOT-IMPLEMENTED` |
| 运行变更 | Agent 版本化，但外部依赖未完整冻结 | 任一关键成分变化均生成新包并重跑适用门 | `ACCEPTED-NOT-IMPLEMENTED` |
| 退役 | `disabled` 可阻止 Agent 使用 | 区分紧急暂停、停止新建、归档证据、替代与最终退役 | `ACCEPTED-NOT-IMPLEMENTED` |

迁移时不得删除或重解释当前字段。V0.2 应以新的 Release Module 关联现有 Agent status，而不是把两套状态压成一个枚举。

## 3. 四类正交事实与唯一有效可调用性

### 3.1 资产轴

Agent、Prompt、Workflow、Schema、Tool/Adapter、Sandbox 镜像、策略、知识项和评测资产各自版本化。变更只能产生新版本或追加事件，不覆盖已被发布包引用的字节。

### 3.2 能力包生命周期

| Package 状态 | 进入条件 | 允许动作 | 退出证据 |
|---|---|---|---|
| `assembling` | 已有路线图承诺、Outcome Contract、具名 Owner | 组装依赖、编写限制、准备用例和策略 | Manifest 关键字段齐全，依赖可解析 |
| `frozen` | 所有关键成分有版本或摘要；外部活态已声明 | 只读检查、启动同源 Bench | 不可变 digest、冻结时间、创建者与环境等级 |
| `superseded` | 新包明确替代且历史关系已记录 | 只供已有任务重建和受控回查 | 替代 digest、影响范围和迁移证据 |
| `retired` | 已有替代、长期不再维护、风险或价值结论支持退出 | 仅历史查询，禁止新任务与新授权 | 退役签发、替代关系、保留策略和用户回告 |

表中状态只回答不可变包本身能否继续被引用。`evaluating` 属于 BenchRun，`eligible_*` 属于资格决定，`phase_0a/phase_0b/released/suspended` 属于暴露绑定，不能再塞回 `capability_release.state`。

### 3.3 资格决定轴

QualificationDecision 追加记录 `target_class=phase_0a|phase_0b|released` 与 `outcome=eligible|ineligible|expired`，绑定精确 release/bench digest、限制、范围、证据和具名人类签发。决定分区键是 `release_digest + target_class + qualification_scope_digest`；分区内由单调 `decision_epoch`、`supersedes_decision_id` 与 head CAS 形成唯一 current head。多头、断链、旧 epoch、过期或无法唯一解析都按 `unknown → deny`；旧 `eligible` 不得越过后续 `ineligible/expired` 继续生效。BenchRun 的 running/failed/completed 只是评测事实；它不能自动产生资格决定。

### 3.4 运行暴露轴

同一个能力发布包可以只对不同的用户组、项目、数据域和动作清单暴露。DeploymentBinding 绑定 `deployment_class=phase_0a|phase_0b|released` 与 `status=draft|active|suspended|revoked|expired`。范围扩大或暂停恢复属于新签发事件；若关键策略本身变化并影响行为，则必须形成新能力发布包。

### 3.5 Kernel 的 effective_callability

Kernel 只在下列条件全部明确为 true 时允许接纳任务：包为 `frozen`；Agent 非 `disabled` 且对主体可见；目标 deployment class 有唯一 current eligible decision；精确 release digest 有匹配且 active 的 DeploymentBinding；主体/项目/数据/动作/时间范围匹配；任务级授权、依赖健康且 Session Grant 可被有效派生。接纳后必须依次完成 Queue admission、claim lease 与 Broker prepare；只有绑定当前 lease generation 的具体 StepProposal 再次通过授权，才签发短时 ExecutionTicket 并允许该步骤执行。创建会话或任务不要求预先存在 ExecutionTicket。`suspended/revoked/expired/unknown` 任一命中都硬否决。L0–L3 只描述成熟度，不授予调用权限。

## 4. 从需求到首个冻结包

### 4.1 需求发现

原始需求先进入需求池，不直接创建发布包。AI 可以提取场景、痛点和候选验收，但只有路线图负责人在适用领域与安全评审后签发路线图承诺，才能进入能力孵化。

### 4.2 Outcome Contract

每项承诺先形成简短、可验证的结果合同：

- 目标用户和真实痛点；
- 用户提交的最小输入与期望交付；
- 必须保持不变的事实或资产；
- 权威依据与待确认假设；
- 允许的可逆动作、禁止动作和末端待交付动作；
- 正常、失败、越权和证据缺失的验收例；
- 具名业务/领域验收人与停止条件。

需求仍不清、权威依据缺失且会改变工作流语义、或无法定义可观察结果时，停止在孵化阶段，不以“先做个万能 Agent”继续。

### 4.3 POC 与 tracer bullet

POC 只证明一个最小机制可行，不授予试点或发布状态。首个 tracer bullet 必须走真实控制内核、Task/Event、Model Gateway、Tool Registry、Sandbox、知识和 Delivery Bundle seam；旁路脚本或演示录像只能记为探索证据。

三条 Phase 0A tracer bullet 为：

- 技术报告润色与规范化：只处理 DOCX 隔离副本，不静默改数字、单位、公式、表格和图片；
- CFD 算例体检：只读检查已有 OpenFOAM 算例，不修改、不求解，每条发现带文件/字段证据；
- 会后纪要与行动项整理：来源锚定，缺失责任字段集中为末端例外，AI 不签发组织事实。

## 5. 冻结与同源评测

Package Assembly Interface 在冻结时生成 manifest 和 digest。至少下列要素缺失时不得进入 `frozen`：

- Agent/Prompt/Workflow/Schema 的精确版本或摘要；
- Gateway 实际解析模型与参数档；
- Tool/Adapter、Sandbox 镜像和策略版本；
- ReleaseKnowledgeBinding（允许 scope、选择策略、目录根摘要）；运行时 TaskKnowledgeSnapshot 由每次任务按 Binding 解析，不参与发布包 digest；
- 评测包、rubric、必测门和环境等级；
- limitations、回退方案、责任人和外部活态清单。

FLAi Bench 必须复用真实 Runtime、Tool 和审计路径。四轨结果不折算为总分；安全、诚实性、依据链和关键回归的 failed/invalid/skipped/unknown 均阻断晋级。LLM-as-Judge 只提供诊断，不可写入通过或签发。

## 6. 试点、发布与变更

### 6.1 Phase 0A

Phase 0A 验证平台机制和黄金工作流，不验证全业务价值。试点名单、数据类型、任务预算、并发、停止条件和签发范围在开始前冻结。所有反馈绑定真实 release id 与 task id，不能混入其他版本。

### 6.2 Phase 0B

进入 Phase 0B 前，至少一条工作流必须接入真实工具和真实数据，并有安全、准确性与分类传播证据。扩大人群不自动扩大数据域、工具或外部动作权限。

### 6.3 正式发布

发布签发绑定精确 package digest、允许人群、项目/知识 scope、工具/动作、有效期、回退目标和残余限制。签发 receipt 只证明授权成立；首次真实执行及后置验证仍需独立 receipt，不能用签发冒充成功。

### 6.4 变更

下列任一变化原则上必须创建新能力发布包并重新评估适用轨道：

- Prompt、Workflow、Schema 或 Agent 配置；
- 实际模型、参数档或 fallback 行为；
- Tool/Adapter、Sandbox 镜像、权限或外联策略；
- ReleaseKnowledgeBinding、适用范围或关键外部活态；
- 评测包、rubric、门矩阵或用户可见能力边界。

纯展示文案且不改变合同的变更可由确定性规则判为非行为变更，但判定依据必须记录，不能由开发者口头豁免。

## 7. 暂停、恢复与退役

### 7.1 紧急暂停

安全泄露、越权、无法强杀、审计链断裂、关键依据错误、假绿或大面积不可恢复失败，应通过 typed Deployment Interface 暂停/撤销暴露并停止新 admission。Control Kernel 的同一事务中，由 DeploymentBinding 的唯一 owner Module 写入绑定转换、Authorization Module 唯一 CAS 提升对应 authorization partition epoch，并共同写 `revocation_id`、受影响 lease selector、CancellationToken 与 invalidation outbox；Identity 或 Supply-chain 撤权则分别由其唯一 owner 提升 credential/trust-policy epoch。所有绑定旧 `ExecutionEpochSnapshot` 的 active lease 在冻结 SLA 内进入 Broker 强杀、步骤凭据吊销与既有连接失效；缺 termination/credential/connection witness 时状态只能是 `revocation_incomplete/needs_reconciliation`，不能记“已取消”。历史证据保持可读。

### 7.2 恢复

恢复不是把状态手工改回绿色。必须有根因、影响范围、修复包、回归证据、适用安全/领域复核和具名恢复签发。若修复改变关键成分，应生成新 release digest，旧包保持 `frozen` 以供历史重建并标为 `superseded` 或 `retired`；暂停/恢复发生在 DeploymentBinding，不改写旧包字节。

### 7.3 退役

退役前必须：

1. 识别仍在运行或依赖该包的任务、知识快照和自动入口；
2. 给出替代包或明确“无替代”；
3. 停止创建新任务和签发新 Delivery Bundle；
4. 向受影响用户回告日期、原因、导出/迁移路径和剩余边界；
5. 冻结最终 manifest、评测、签发、事故与使用证据；
6. 按密级和保留策略归档，不删除可审计历史。

## 8. Interface、Seam 与 Adapter 规则

- Release Module 通过 Interface 引用 Agent Registry、Knowledge、Model Gateway、Tool Registry、Sandbox Policy 和 Eval，不复制其配置；
- OpenClaw/OpenHands 只位于 AgentRuntimePort seam，macOS 隔离位于 SandboxProviderPort，CAE/HPC 位于 ToolExecutionPort；三者无权写发布或签发状态；
- GitHub/内网 Issue Adapter 只同步交付引用，不把 issue closed 冒充需求解决或能力发布；
- Knowledge Interface 分开 ReleaseKnowledgeBinding 与 TaskKnowledgeSnapshot；后者必须返回版本、digest、有效性、scope 与 Binding conformance，普通检索结果不能冒充快照；
- Typed Decision Interface 分开 `AgentLifecyclePromotion`、`CapabilityQualificationDecision` 与 `DeploymentSignoff`，在提交事务时重新核验身份、职责、适用门、target type/digest 和范围，并以 CAS 防重复消费；
- 所有生命周期事件追加写入审计链，Projection 可以重建视图，但不得反向覆盖源事件。

### 8.1 角色 × 可读投影 × 可执行动作

| 角色/职责 | 可读投影 | 可执行动作 | 明确禁止 |
|---|---|---|---|
| 普通工作台用户 | 本人可调用能力的中文状态、限制、当前 release 与本人任务证据摘要 | 在 active DeploymentBinding 范围发起/停止本人任务、反馈 | 进入生命周期控制面、读取全量 manifest/安全证据、签发 |
| 能力 Owner / 交付负责人 | 本能力 manifest、任务/失败/限制、准备中的证据 | 组包、提资格申请、提交修订 | 自评自签、扩大暴露、修改 Bench 结果 |
| Eval 维护者 | 获授权评测资产、run 与 evidence matrix | 策展/运行 Bench、提交人工 rubric | 写 DeploymentBinding、删除失败 case |
| Domain / Security Reviewer | 与职责/作用域匹配的专业或安全证据 | 写具名 review/门结果 | 替代路线图、发布或其他独立职责 |
| Qualification / Release Signer | 精确 release、适用 Bench、reviews、范围、风险与历史决定 | 签发 typed QualificationDecision/DeploymentBinding | 空白授权、签漂移 digest、AI 代签 |
| Platform Ops / Admin | 受 scope 限制的运行健康、队列、审计与事故证据 | 停止 lane、隔离、恢复等运维动作 | 因 admin 身份自动拥有发布/路线图签发权 |
| 领导/组织视图 | 经隐私聚合的只读能力、风险与价值摘要 | 无生命周期写动作 | 查看个人明细、绕过审查点绿 |

前端路由可见性不是授权。深链、API、搜索、计数、导出和证据下载逐次调用统一 Authorization Interface；越权响应不得泄露对象存在性。完整治理视图只出现在角色化治理与运行中心，普通工作台只投影本人相关摘要。

Depth 的目标是把冻结、核权、证据完整性、密级传播和失败关闭藏在内层 Module；Locality 要求每条治理规则和状态写入只有一个 owner Module，不在页面、脚本和 Adapter 复制判定。一个治理视图可定位 manifest、证据矩阵、签发、暴露和变更，属于证据可查找性，不获得独立写权。

## 9. 转换白名单与默认拒绝

每次转换都必须记录 `from → to / actor / predicate / evidence / expected_version / CAS result / failure_target`；未在实施规格白名单中的转换一律拒绝。至少冻结以下语义：

- Package：`assembling → frozen → superseded|retired`；冻结失败保持 `assembling`，禁止原地修补 `frozen`；
- BenchRun：`queued → running → passed|failed|invalid|cancelled`；同 digest 重跑形成新 run，不覆盖旧结果；
- QualificationDecision：对 target class 追加 `eligible|ineligible|expired` 决定，修复后必须引用新证据，关键字节变化则引用新 release digest；
- DeploymentBinding：`draft → active → suspended|revoked|expired`；恢复由新签发事件生成新的 active version，不能手工把旧行改绿；
- 任一失败写入具名 failure target 与证据；`unknown` 不得被省略后继续。

### 9.1 明确禁止

- 原始需求或 AI 建议直接进入 `assembling`；
- 未冻结对象启动可用于准入的 Bench；
- Agent `status=released` 直接产生资格决定或 active DeploymentBinding；
- skipped/unknown case 被过滤后晋级；
- Phase 0A 使用 canonical 数据通过后直接宣传真实业务有效；
- 路线图负责人、交付负责人或全局管理员绕过适用安全门；
- 暂停后修改原 manifest 并复用旧 release id 恢复；
- 退役时删除来源需求、运行证据或历史签发。

## 10. 机械验收与退出条件

生命周期实现至少应具备以下 invalid-first 验收：

1. 缺任一关键版本/digest 的 manifest 无法冻结；
2. 冻结后修改任一关键字节会导致 digest 不匹配并拒绝运行；
3. 评测 case 为 failed/invalid/skipped/unknown 时不能生成 eligible QualificationDecision；
4. AI、需求策展人、无 scope 管理员不能签发路线图、评测资产或发布；
5. 签发前权限被撤销、package 过期或 digest 漂移时提交 fail-closed；
6. 同一包重复签发或重复消费不会产生两次有效发布事件；
7. Phase 0A/0B 外用户、数据域、工具或动作创建任务时被拒绝并留事件；
8. suspended/revoked/expired DeploymentBinding 或 retired 包不能创建新任务，历史任务和证据仍可按权限重建；
9. 替代包不会自动继承旧包的 Bench 结论；
10. 每次资格决定、Agent 晋级、暴露启停、恢复和退役都能回查具名操作者、时间、理由、前后版本及证据。

## 11. 本阶段非目标

- `OUT-OF-SCOPE`：立即修改现有 Agent schema、数据库状态枚举或 L0–L3 规则；
- `OUT-OF-SCOPE`：将全部 Agent 自动迁移成已发布能力；
- `OUT-OF-SCOPE`：Agent 市场、自动商业计费、跨组织公开排行榜；
- `OUT-OF-SCOPE`：由 AI 自动选择并签发所谓最佳模型或最佳工作流。

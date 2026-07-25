# 05 AI 团队运营模型

> 文档状态：`ACCEPTED-NOT-IMPLEMENTED`
>
> 本文是 V0.2 设计包的运营读模型，不覆盖 [FLAi-OS 系统宪法](../../00_FLAi-OS_Constitution.md)、现行标准或已接受 ADR。术语以 [CONTEXT.md](../../../CONTEXT.md) 为准；需求与发布决策分别受 [ADR-0060](../../adr/ADR-0060-demand-co-creation-loop.md)、[ADR-0061](../../adr/ADR-0061-demand-decision-rights-and-roadmap-signoff.md) 和 [ADR-0058](../../adr/ADR-0058-flai-bench-evaluation-foundation.md) 约束；外网研发协作入口受 [ADR-0062](../../adr/ADR-0062-feishu-single-organizational-hub.md) 约束，内外网边界与内网自托管入口受 [ADR-0063](../../adr/ADR-0063-external-development-airgap-internal-workspace.md) 约束，当前 Codex/Kimi 双线程责任章程受 [ADR-0064](../../adr/ADR-0064-workspace-foreground-verifiable-delivery-and-dual-track-development.md) 约束。

## 1. 目标与边界

FLAi-OS 的运营对象不是“多少个 Agent”，而是能否被定义、冻结、评测、试点、发布、追溯和退役的**能力发布包**。团队围绕真实工作结果组织协作，使业务痛点、权威依据、实现版本、安全控制、评测证据和用户反馈保持一条可回查的证据链。

本模型解决四个问题：

1. 谁可以提出需求、整理需求、作专业或安全判断、签发路线图和签发发布；
2. 哪些事实分别属于需求池、共建地图、工程 Issue、能力发布包和 FLAi Bench；
3. 一项能力凭什么从概念进入受控验收、业务试点和正式发布；
4. 发布后如何观察、复盘、暂停、修订或退役，而不抹去历史证据。

本模型**不是人员绩效系统**。个人 Token、任务量、响应时长、采纳数和需求点赞数都不得用作人员排名或绩效推断；共建地图只展示适当粒度的团队事实与能力证据。

## 2. 实施状态分层

| 状态标签 | 本文中的严格含义 |
|---|---|
| `IMPLEMENTED-VERIFIED` | 当前精确范围、版本与环境有可复跑机械证据，绑定命令、结果引用和日期；不等于生产就绪 |
| `IMPLEMENTED-PARTIAL` | 已存在可复用的 Module 或 Interface，但目标合同尚未完整实现 |
| `ACCEPTED-NOT-IMPLEMENTED` | 已由 ADR 接受为目标方向，但当前代码不可据此宣称可用 |
| `DECLARED-NOT-VERIFIED` | 有声明或人工记录，但缺少足够运行证据，不得用于准入 |
| `OUT-OF-SCOPE` | 本阶段明确不建设或不开放 |

当前可复用基线为 `IMPLEMENTED-PARTIAL`：Agent Package 已有 `draft/trial/released/disabled` 可见性状态、L0–L3 成熟度轴、Task/Event、反馈入口与现行 Eval 机制。完整能力发布包、四轨 FLAi Bench、需求共创、Phase 0A/0B 准入和退役合同均为 `ACCEPTED-NOT-IMPLEMENTED`。因此，当前 `released` Agent 不能自动解释为“已通过 V0.2 发布门”。

## 3. 运营 Module 与唯一事实源

| Module | 负责的事实 | 主要 Interface | 不得承担 |
|---|---|---|---|
| 需求共创 | 原始需求信号、来源、关系、补证据与处理事件 | 需求提交、聚类建议、策展、状态回告 | 自动承诺路线图或自动建 Issue |
| 路线图治理 | 版本化路线图承诺、理由、适用评审与里程碑 | 共建地图签发 Interface | 替代工程执行或直接点绿能力状态 |
| 能力孵化 | Outcome Contract、工作流边界、Capability Release Manifest 草稿 | Package Assembly Interface | 用单个 Agent 版本代表完整能力 |
| FLAi Bench | 冻结包、四轨运行、人工 rubric 与不可抵消门 | Evaluation Interface | 创建第二 Runtime 或用总分抵消失败 |
| 试点运营 | Phase 0A/0B 名单、范围、任务证据、问题和退出结论 | Pilot Exposure Interface | 把试用人数冒充生产就绪 |
| 发布治理 | 具名发布签发、暴露范围、回滚与撤销记录 | Promotion/Release Interface | AI 自批、交付负责人自验关闭 |
| 运行观察 | Task/Event、Tool、Model、反馈、安全与资源事实 | Evidence Projection Interface | 建个人生产力排行榜或手填绿灯 |
| 退役治理 | 停用原因、替代关系、保留期和历史重建证据 | Suspend/Retire Interface | 删除历史证据或让旧评测继承给新包 |
| 外网研发协作中枢 | 飞书中的工作收件箱、协作草稿、外网研发 typed intent、研发投影与回告 | `open/prepare/commit` | 定向控制内网 owner、接管 GitHub/FLAi/Knowledge/Audit/Secret owner 或用协作表改状态 |
| 内网生产协作中枢 | 自托管 `FLAiWorkspace` 的工作收件箱、项目/Wiki、内网 typed intent、联邦投影、回告和对账案件 | `open/prepare/commit` | 依赖飞书、GitHub.com 或公网模型；接管内网 FLAi/Forge/Knowledge/Audit/Secret owner |
| AirGap Exchange | 离线发行包准入、内网候选回执与脱敏反馈导出 | `admit_release/import_candidate/export_feedback` | 在线同步、共享身份/密钥、把文件复制视为发布或信任 |

这些 Module 通过稳定引用协作，不复制对方的权威状态。外网研发域以飞书为日常入口、GitHub 为代码/PR/review/CI 事实源、`secrets-stackdocker` 为外网研发 Secret owner；内网生产域以自托管 `FLAiWorkspace` 为日常入口、Internal Forge/Registry 为代码与制品事实源、Internal Secret Owner 为内网 Secret owner。FLAi owner Modules 拥有执行、授权、能力、Bench、交付和审计事实，Knowledge Authority 拥有知识有效性，独立 Safety Identity / PKI / HSM owner 拥有人的安全硬件身份与 Safety receipt-signing key。两域之间只通过 `AirGapExchange` 的签名、内容寻址离线包传递已准入对象；展示层只做投影，只有适用的有效 owner receipt 与验证证据能证明动作已生效。

## 4. 能力发布包运营单元

每次拟试点或发布的能力都必须形成冻结清单，至少绑定：

- Agent 配置、Prompt、Workflow 与输入输出 Schema；
- Model Gateway 解析后的实际模型和参数档；
- Tool 与 Adapter 版本；
- Sandbox/执行镜像、资源预算、权限和网络策略；
- `ReleaseKnowledgeBinding`、适用范围与外部活态清单；每次运行另以 `TaskKnowledgeSnapshot` 固化实际版本、命中、缺失与冲突证据；
- FLAi Bench 用例包、rubric、必测门和运行环境等级；
- 用户可见适用范围、限制、已知问题和回退路径；
- 责任人、领域评审、安全评审、发布签发和证据引用。

任一关键成分漂移都形成新的能力发布包，旧评测、旧签发和旧试点结论不得自动继承。无法冻结但会影响结论的外部活态必须显式列出；无法重建时状态保持 `DECLARED-NOT-VERIFIED` 或阻断晋级。

## 5. 职责与决策权

职责按能力、部门、数据域和时间范围委派，不固化为一个全局管理员角色。小规模试点允许同一人兼任多个职责，但同一决策仍须满足下表的独立证据，不能因为“都是同一个人”而省略适用门。

| 人类职责 | 可以做 | 不可以做 |
|---|---|---|
| 需求提出者 | 自然语言提交、补证据、关联同类需求、关注状态、自愿参加试用 | 通过点赞或提交数量决定优先级 |
| 需求策展人 | 去重、合并、拆分、分类、脱敏、异步请求补证据、形成候选摘要 | 正式采纳路线图、改写原始来源 |
| 领域评审人 | 判断专业痛点、适用范围、rubric 和工程未知项 | 绕过安全门或代替路线图排序 |
| 安全评审人 | 审查身份、权限、Sandbox、外联、密级、审计和破坏性动作 | 把缺失证据解释为通过 |
| 路线图负责人 | 对共建地图版本采纳、暂缓或不采纳，并记录理由与目标验收 | 让 AI 代签、豁免必需领域/安全门 |
| 交付负责人 | 建立 Issue、组织实现、版本回链和验证准备 | 以合并代码或自测通过关闭用户问题 |
| 能力 Owner | 维护 Release Manifest、限制、支持和变更建议 | 静默替换已冻结包中的成分 |
| Eval 维护者 | 策展评测资产、组织 FLAi Bench、核对可比性 | 让 AI 自动批准金标准或删去失败 case |
| 试点协调人 | 管理具名名单、培训、反馈与停止条件 | 代替领域、安全或发布签发 |
| 发布签发人 | 对精确能力发布包和暴露范围作具名决定 | 给 Agent 永久授权或追认漂移后的包 |

AI 只可提取、聚类、比较、生成候选验收和起草说明；AI 不得采纳需求、改变路线图、批准评测资产、判定不可抵消门、签发能力或关闭正式问题。

外网多人开发由飞书研发工作收件箱组织、FLAi Delivery Governance owner Module 持有
`DeliveryWorkItem` 生命周期、GitHub 证明外网代码事实；内网维护由 `FLAiWorkspace` 与 Internal
Forge/Registry 组织和证明，二者不在线同步。每项工作必须有一个具名人类 owner、冻结
SHA、独立 branch/worktree、文件/Interface scope、执行身份、密级/egress/工具范围、并发与
时间/Token 预算、Issue/PR、验证证据、交接 digest、所需评审和集成状态。当前责任章程将
Codex 定义为 **Platform & Integration Lead**，负责控制内核、领域/API 合同、后端、安全、
Runtime/Sandbox/Tool、Knowledge、Bench、测试、部署和集成；将 Kimi-K3 定义为
**Workspace Experience Lead**，负责 Workspace IA/交互、三栏工作范式、视觉与动效、
Artifact 工作台、前端体验、响应式/无障碍和视觉回归。

这些责任名称用于划分当前研发写范围，不是模型名驱动的硬编码授权；实际 dispatch 仍依赖
版本化 executor qualification、项目 scope、密级、egress 和预算。Codex 先冻结事实合同和
合成 fixture，Kimi 依合同实现体验；Kimi 可提交 scope-change request，但不得直接修改生产
Schema、安全策略、状态机或审计语义。两者不得并行拥有重叠文件或公共 Interface 写范围；
dispatch/pause/resume/cancel/reconcile/handoff/rework/accept 均使用 typed intent、幂等键与
effect-unknown 对账。AI 互审可以形成建议，但不能成为 CODEOWNER、批准人、merge owner 或
发布 signer。Kimi-K3 只在外网使用合成/脱敏资产协作，不能成为内网运行依赖。完整合同见 [17_Feishu_Organizational_Hub.md §8.2](17_Feishu_Organizational_Hub.md#82-codexkimi-k3-与多人开发) 与 [18_AirGap_Exchange_and_Internal_Release.md](18_AirGap_Exchange_and_Internal_Release.md)。

## 6. 标准运营回路

```text
当前部署域工作收件箱中的需求信号
  -> AI 预处理草稿
  -> 人工策展与适用评审
  -> 路线图负责人签发承诺
  -> Outcome Contract 与最小 tracer bullet
  -> 能力发布包组装并冻结
  -> FLAi Bench 四轨评测
  -> Phase 0A 受控验收
  -> R6 真实工作流验证
  -> Phase 0B 限范围业务试点
  -> 具名发布签发
  -> 运行证据、反馈与失败沉淀
  -> 新版本、暂停或退役
```

每一步只消费上一步的稳定引用和证据，不通过聊天总结、协作表字段或会议口头结论隐式推进。人的动作先形成 typed intent，高影响动作经过 prepare/commit，只有 owner receipt 才推进权威事实。跨域输入还必须先通过 AirGap 准入。失败、未知、跳过、证据不可解析均保留原状态并生成具名处理事件；系统不得自动寻找“更容易通过”的模型、策略或数据集。

## 7. Phase 0A、R6 与 Phase 0B 的运营合同

### 7.1 Phase 0A：受控验收试点

- 人群：5–8 名具名技术验收人员；
- 环境：macOS 首发环境，仅 approved `source_kind=synthetic` 数据；正常样本 `fixture_class=canonical`；
- 范围：三条黄金工作流各自的最小 tracer bullet；
- 目的：验证不中断自治、沙箱与强杀、并发/取消/恢复、审计证据、真实状态、依据链和末端 Delivery Bundle；
- 退出门：所有适用不可抵消门为 true，必测 case 无 failed/invalid/skipped/unknown，具名验收记录完整，剩余限制可被明确收容；
- 停止条件：越权、数据泄露、无法强杀、审计链断裂、假绿、依据冒充、关键状态不可恢复，任一出现即暂停相关能力。

Phase 0A 通过只证明限定机制成立，不证明真实业务价值、工程有效性或生产就绪。

### 7.2 R6：真实工作流验证

- 负责人：能力 Owner 组织，真实数据 Owner、领域评审人和安全评审人分别对数据范围、专业质量与安全边界负责；
- 输入：Phase 0A 通过的精确 release、获批的最小真实样本/工具路径、单独的 classification 与停止条件；
- 动作：只让具名验证人员执行一条精确真实路径，验证授权、依据、准确性、分类传播、回退、支持和动作 receipt；不得顺势扩大到 20–30 人；
- 产物：真实路径证据包、领域/安全结论、残余风险、支持责任、是否具备 Phase 0B eligible decision 的建议；
- 退出：真实路径各门有证据并由具名人员记录通过/不通过。Phase 0A synthetic 证据不能自动继承，R6 也不等于 Phase 0B 已获批。

### 7.3 Phase 0B：限范围业务试点

- 人群：20–30 名具名业务用户；
- 前置：Phase 0A 机械门通过，且至少一条工作流已经接入真实工具与真实数据并完成安全和准确性验收；
- 暴露：按能力发布包、用户群、项目、数据域、工具与动作白名单逐项开放；
- 目标：验证可采用性、真实质量、支持负担、业务基线和持续运行证据；
- 退出门：版本化业务 rubric、代表性样本、用户验收、故障处理、回退演练和适用生产准备门均有证据；
- 停止条件：风险超出已签范围、真实数据边界不清、失败不能收容、用户需要绕过限制才能工作，立即缩小范围或退回 Phase 0A。

## 8. 运营节奏与最小会议面

| 节奏 | 输入 | 输出 | 禁止 |
|---|---|---|---|
| 持续 | 当前部署域 Workspace 中的需求、任务失败、用户反馈、安全事件 | 不可变信号、typed intent、owner receipt 和追加式事件 | 在用户任务中强插长表单或改单元格推进状态 |
| 每周策展 | 新信号、重复项、缺证据项 | 候选、合并/拆分、异步补证据清单 | AI 自动排序、点赞晋级 |
| 每两周能力评审 | Release Manifest 草稿、实现与风险 | 继续组装、退回或准备冻结 | 用 Demo 代替合同证据 |
| 每个候选版本 | 冻结包与 Bench 计划 | 四轨证据矩阵和不可抵消门 | 只看平均分或 LLM 评审 |
| 每个试点周期 | 任务、反馈、支持、安全与价值证据 | 扩大、保持、缩小、暂停或退役建议 | 把 Token 或任务量变成人员绩效 |
| 每月共建回顾 | 路线图版本、需求回链、发布与风险 | 版本变化、已解决/未解决边界、下一周期目标 | 手填完成度、删除失败叙事 |

## 9. 架构原则在运营中的落点

- **Module**：需求、路线图、能力、评测、试点、发布和退役各有单一职责；
- **Interface**：状态变化只经版本化命令与事件合同发生，不能直接改展示字段；
- **Seam**：复用现有 Agent Registry、Task/Event、Model Gateway、Tool Registry、Knowledge、Eval 与反馈事实，沿 seam 加深能力，不建平行平台；
- **Adapter**：OpenClaw/OpenHands 只实现 AgentRuntimePort，macOS 隔离实现 SandboxProviderPort，Office/OpenFOAM 实现 ToolExecutionPort，GitHub/Internal Forge 实现各自网络域的受控 Connector；均不能夺取控制权；
- **Hub Adapter**：外网 Feishu Card/Bitable/Docs/Web App 与内网自托管 Chat/Wiki/Workspace 分别只实现所在域的 Surface 与 ingress Adapter；外网 `secrets-stackdocker` 和内网 Secret Owner 分别只通过当前域的 `SecretProviderPort` 向最终 Connector 提供 opaque lease；任何 Adapter 都不进入领域判决；
- **AirGap Adapter**：只交换签名、内容寻址、带 manifest 的离线包；不提供 RPC、身份代理、密钥桥接或双向数据库同步；
- **Depth**：权限重验、分类传播、冻结摘要、CAS、不可抵消门和审计完整性由内层 Module 吸收，普通用户只提交目标、查看证据和处理末端交付；
- **Locality**：同一治理规则、状态转换与失败归属只在一个 owner Module 实现，消费者通过 Interface 复用，不跨模块复制判定；单一发布视图属于“证据可查找性”，它汇总引用但不成为新的事实 owner。

## 10. 机械验收条件

当 V0.2 运营机制进入实施时，至少必须用自动化检查或可验证记录证明：

1. 每个进入评测、试点或发布的对象都有唯一 `capability_release_id` 和不可变摘要；
2. Agent/Prompt/Workflow/Schema、实际模型、Tool/Adapter、Sandbox/Policy、ReleaseKnowledgeBinding 和评测包任一变化都会产生新对象；符合 Binding 的运行时 TaskKnowledgeSnapshot 变化不反向改变 release digest；
3. 原始需求、路线图承诺、工程 Issue、能力发布包、Bench 运行和发布结论能双向回查；
4. AI 不能写入路线图签发、金标准批准、不可抵消门通过或发布签发；
5. 缺少适用领域或安全评审时，采纳与发布事务 fail-closed；
6. Phase 0A/0B 的名单、数据等级、暴露范围、开始与退出条件均冻结并可审计；
7. `failed/invalid/skipped/unknown` 均不能投影为通过；
8. 暂停和退役保留历史任务、知识快照、评测和签发证据，旧入口不能继续创建新任务；
9. 公开运营视图不出现个人 Token、任务量或“生产力”排行；
10. 任一状态都能解释“由哪条事实、哪位人、何时、依据什么版本产生”。
11. 外网研发运营从飞书研发空间进入，内网生产运营从自托管 `FLAiWorkspace` 进入；同一域对象仍能回查其代码、FLAi、Knowledge、Audit 或 Secret owner。
12. 卡片点击、协作表变更、HTTP 2xx、离线复制成功和 AI 草稿都不能替代 OwnerCommitReceiptV1；
    EffectUnknownV1 进入对账且不换键重放。
13. Codex/Kimi-K3 工作项有不重叠文件所有权和独立 branch/worktree，合并仍由具名真人与 GitHub review/CI 控制。
14. 内网断开飞书、GitHub.com、外网模型和外网 Secret 后，仍可完成工作收件箱、知识检索、运行观察、治理、审计与止损。

## 11. 本阶段非目标

- `OUT-OF-SCOPE`：人员绩效、积分激励、个人排行榜、AI 自动晋级；
- `OUT-OF-SCOPE`：一次性建设全功能 Agent 市场或全自主 CAE；
- `OUT-OF-SCOPE`：用 Management Plane 建第二用户库、第二任务状态机或第二评测链；
- `OUT-OF-SCOPE`：把现有 `draft/trial/released` 直接改名并假装已完成 V0.2 迁移；
- `OUT-OF-SCOPE`：在本设计包阶段修改数据库、API、角色枚举或生产权限。

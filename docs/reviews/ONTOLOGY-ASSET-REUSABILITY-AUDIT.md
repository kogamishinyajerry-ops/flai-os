# FLAi-OS 本体论资产可复用边界审查

- 日期:2026-08-05
- 审查人:fork-2(落地审查 agent)
- 审查对象:FLAi-OS 本体论子系统(资产治理链 + Agent Shell + 三正交轴)
- 目标:判断现有资产能否承载"生活场景本体论建模 demo",标出可复用边界与缺口

## 0. 关键前置事实(必须先读)

**team-lead 指派的审查路径 `/Users/Zhuanz/projects/aircraft-comac/flai-os-ontology-agent-shell-v1/` 是过时快照**。真实最新本体论在 `main` 分支:

- ontology-agent-shell-v1 分支头 = `609b49b` = main 与该分支的 merge-base
- main 在此之上**领先 129 个 commit**,已吸收该分支全部 6 个 ontology commit 并往前推进
- 该分支**未 push 到 origin**,仅本地存在
- main 新增:`backend/app/ontology/feature_asset_map.py` · `backend/app/api/object_authorization.py` · `backend/app/storage/asset_candidates.py` · ADR-0036(feature/asset 地图按需披露)· ADR-0037(V1 owner 对象授权)· ADR-0039(NemoClaw 沙箱 spike,裁决不迁移 agent 运行时)

**本报告所有 line 引用以 main 分支为准**。审查路径里 worktree 的代码仍可读(内容是 main 的子集),但任何"当前状态"结论都以 main 为准。

`codex/v02-mainline-consolidation`(主仓当前 HEAD)落后 main 129 commit、超前 10 commit;它不是本体论的最新载体。

## 1. 审查范围与方法

**范围**:
- 契约层:`contracts/` 全部 17 个 schema(main 含 feature_asset_map,worktree 不含)
- 后端实现:`backend/app/ontology/` 7 个 .py + `backend/app/api/asset_drafts.py` + `object_authorization.py`
- Agent 样例:`agents/guide_agent/`(50KB workflow) · `agents/hello_agent/` · 14 个工程 agent
- 文档层:`CONTEXT.md`(20+ 概念) · ADR-0030~0039
- 前端:`AssetBuilderDrawer.vue` · `AssetCandidateCallout.vue` · `ShellContextPanel.vue` · `FeatureAssetMapDisclosure.vue` · `GuidePage.vue` · `WorkbenchSession.vue`

**方法**:
1. 打开三个必读文件(`asset_builder.py` / `agent_shell.py` / `guide_agent/workflow.py`)逐行看工程耦合
2. 对每个资产判定:工程耦合度(无/低/中/高) + 可复用度(直接/适配/重造)
3. 标"哪一行绑定了 CFD/发动机/适航",没绑定就诚实说可复用

**工程耦合度判定标准**:
- **无**:代码里没有任何 domain/engine/CFD 字样,纯逻辑
- **低**:只在枚举常量里出现 domain 名,业务逻辑无关
- **中**:prompt 文案或 UI 文案带工程语境,但机制通用
- **高**:控制流绑死工程领域,换领域就崩

## 2. 资产清单

### 2.1 契约层(`contracts/`)

| 文件 | 用途 | 工程耦合 | 可复用 |
|---|---|---|---|
| `agent.schema.json` | Agent Package 契约 | 低 | 直接 |
| `agent_shell.schema.json` | Agent Shell 只读投影 | 低 | 直接 |
| `asset_candidate.schema.json` | 资产候选治理包络(digest/lineage/signoff) | 无 | 直接 |
| `asset_draft_bundle.schema.json` | 草稿包 | 无 | 直接 |
| `asset_draft_preview_request.schema.json` | 预览请求体 | 无 | 直接 |
| `candidate_skill_package.schema.json` | Skill Package | 无 | 直接 |
| `skill_package_decision_request.schema.json` | 包审核决策 | 无 | 直接 |
| `skill_package_event.schema.json` | 包事件 | 无 | 直接 |
| `skill_package_review_content.schema.json` | 包审核内容 | 无 | 直接 |
| `asset_candidate_event.schema.json` | 候选事件 | 无 | 直接 |
| `asset_candidate_decision_request.schema.json` | 候选决策 | 无 | 直接 |
| `feature_asset_map.schema.json` | 功能/资产地图(main 独有) | 无 | 直接 |
| `task.schema.json` | 任务契约 | 无 | 直接 |
| `tool.schema.json` | 工具契约 | 无 | 直接 |
| `knowledge_scope.schema.json` | 知识范围 | 低 | 直接 |
| `model_profile.schema.json` | 模型画像 | 无 | 直接 |
| `event.schema.json` | 事件契约 | 无 | 直接 |

**契约层结论**:15/17 完全工程无关,2/17 低耦合。

低耦合的两处具体位置:
- `agent.schema.json:172-187` 的 `expertise.domain` 枚举硬编码了 `policy_qa / standards_qa / fault_history / sys_calc / cfd_sim / test_data / design_opt / generic`。生活场景 demo 可以选 `generic` 合法存在,**不需要改 schema**。
- `agent.schema.json:199-201` 的 `evidence_policy.kinds` 枚举硬编码了 `regulation_clause / standard_clause / type_case / fault_case / knowledge_doc / calculation`。demo agent 不带 `evidence_policy` 块也能合法存在(整块 optional,缺省 fail-closed 取最严解释,见 ADR-0030)。

**这意味着**:跑生活场景 demo,**契约层零改动**。

### 2.2 后端实现(`backend/app/ontology/`)

| 文件 | 行数 | 工程耦合 | 可复用 |
|---|---|---|---|
| `asset_builder.py` | 433 | 无 | 直接 |
| `agent_shell.py` | ~800 | 低 | 直接 |
| `asset_candidates.py` | ~2050 | 无 | 直接 |
| `candidate_materializer.py` | ~1840 | 无 | 直接 |
| `skill_reuse.py` | ~600 | 无 | 直接 |
| `skill_reuse_evidence.py` | ~800 | 无 | 直接 |
| `feature_asset_map.py` | (main 新增) | 无 | 直接 |

**三个必读文件详判**:

#### `asset_builder.py`(审查路径:`backend/app/ontology/asset_builder.py:1-433`)

**完全工程无关**。这是一个纯函数模块:
- 入参:`conversation`(对话结构) + `generalization`(工程师写的抽象对象)
- 出参:content-addressed draft bundle(Work Case → Task Pattern → Skill)
- 全文 433 行没有一个"CFD""发动机""适航"字样
- 唯一硬约束是 `_GENERALIZATION_FIELDS`(`asset_builder.py:22-32`):title/trigger/desired_outcome/inputs/outputs/steps/evidence_requirements/human_decision_points/limitations 九个字段——这套字段对"周末做红烧肉"和"振动超标分析"一视同仁
- `_REVIEW_REQUIREMENTS`(`asset_builder.py:38-42`)的文案是通用的"核对草稿是否忠实对应原始 Work Case"——生活场景也能用
- digest 算法(`_digest_hex`/`_canonical_json`,`asset_builder.py:417-432`)是 SHA256 over canonical JSON,工程无关

**结论**:跑生活场景 demo,这个文件**一行都不用改**。

#### `agent_shell.py`(审查路径:`backend/app/ontology/agent_shell.py:1-200+`)

**低耦合**。这是只读投影模块,从三个 registry(agent/tool/scope)生成语义目录。

工程耦合点只有两处枚举常量:
- `agent_shell.py:25-34` 的 `_DOMAIN_ORDER` 硬编码了 8 个 domain(cfd_sim 等)——但投影逻辑对枚举外的 domain 标 `undeclared` 诊断,不会崩
- `agent_shell.py:43-52` 的 `_EVIDENCE_KINDS` 硬编码了 6 种依据类型——同上,demo agent 不带 evidence_policy 就不触发

核心投影函数 `_project_agent`(`agent_shell.py:217-412`)是通用的:identity/classification/capability/trust/launch 五维度,任何领域 agent 都能投影。

**结论**:跑生活场景 demo,**一行都不用改**。demo agent 走 `generic` domain 即可。

#### `guide_agent/workflow.py`(审查路径:`agents/guide_agent/workflow.py:176-306`)

**中耦合**。这是 50KB 的核心引导 workflow,机制通用但 prompt 文案带工程语境。

- `run(context)`(`workflow.py:176-256`)核心机制通用:接 messages → 注入 system prompt + 候选清单 + 附件名册 → 调 model_gateway.chat → 解析 PLAN 块 → 校验 → 返回 delegate/orchestrate/refuse
- `_candidates(registry)`(`workflow.py:261-313`)的筛选逻辑通用:排掉 disabled/自己/non-job-non-interactive,剩下的就是可路由面
- 工程耦合在 `_INTERACTIVE_HANDOFF_IDS` 白名单(`workflow.py:280` 引用,定义在文件头部):只有 `policy_qa_agent` 和 `standards_qa_agent` 允许对话型转交——生活场景 demo 不需要对话转交,用 orchestrate/refuse 就够
- `prompt.md`(`agents/guide_agent/prompt.md:1-60+`)的文案大量出现"性能盘/控制逻辑/故障树",但**五步编排机制(听懂需求/分析/完整性闸门/分流裁决/守住人签边界)对生活场景完全适用**

**结论**:跑生活场景 demo,这个 workflow **能直接跑**,只是 prompt 文案需要替换。最干净的做法是新造一个 `agents/life_guide_agent/`,复制 workflow.py,prompt.md 改成生活场景语境。

### 2.3 后端 API(`backend/app/api/`)

| 文件 | 端点 | 工程耦合 | 可复用 |
|---|---|---|---|
| `asset_drafts.py` | `POST /conversations/{id}/asset-draft-preview` · `POST /tasks/{id}/asset-candidate` · `GET /tasks/{id}/asset-candidate` · `POST /asset-candidates/{id}/decision` · `GET /skill-packages/{id}` · `GET /skill-packages/{id}/review-content` · `POST /skill-packages/{id}/decision` | 无 | 直接 |
| `agent_shell.py` | `GET /api/agent-shell` | 无 | 直接 |
| `object_authorization.py`(main) | owner 授权中间件 | 无 | 直接 |
| `governance.py` | 治理/晋级 | 无 | 直接 |
| `feature_asset_map`(main) | `GET /api/feature-asset-map` | 无 | 直接 |

**API 层结论**:全部通用,零工程耦合。asset_drafts.py 把 7 个端点聚合在一个文件里,从"预览草稿"到"审核 Skill Package"全链路打通。

### 2.4 Agent 样例(`agents/`)

| Agent | 用途 | 工程耦合 | demo 价值 |
|---|---|---|---|
| `hello_agent/` | 最小样例 | 无 | **直接当模板** |
| `guide_agent/` | 编排官 | 中(文案) | 复制改 prompt |
| `performance_disk_agent/` | 性能盘 | 高 | 不复用 |
| `cfd_evaluate_agent/` · `cfd_solve_agent/` | CFD | 高 | 不复用 |
| `fea_evaluate_agent/` · `fea_solve_agent/` | FEA | 高 | 不复用 |
| `control_logic_agent/` | 控制逻辑 | 高 | 不复用 |
| `fta_agent/` | 故障树 | 高 | 不复用 |
| `fault_history_agent/` | 故障历史 | 高 | 不复用 |
| `policy_qa_agent/` · `standards_qa_agent/` | 规章/标准 QA | 高 | 不复用 |
| `knowledge_qa_agent/` | 知识 QA | 中 | 可参考 |
| `step_response_evaluate_agent/` · `step_response_solve_agent/` | 阶跃响应 | 高 | 不复用 |
| `monitor_adapter_gen_agent/` | 监视器适配 | 高 | 不复用 |

**14 个工程 agent 是"样例"不是"硬绑定"**:它们各自独立,只是在 agent.yaml 里声明了各自的 domain/tools/scopes。删掉它们平台照样跑;它们的存在不阻塞生活场景 demo。

### 2.5 文档层

| 资产 | 工程耦合 | 可复用 |
|---|---|---|
| `CONTEXT.md` 20+ 概念定义 | 无 | 直接(生活场景直接套用) |
| ADR-0030(三正交轴) | 低 | 直接 |
| ADR-0031(Agent Shell 只读投影) | 无 | 直接 |
| ADR-0032(资产草稿预览) | 无 | 直接 |
| ADR-0033(会话优先自动路由) | 无 | 直接 |
| ADR-0034(任务证据绑定) | 无 | 直接 |
| ADR-0035(隔离 Skill Package) | 无 | 直接 |
| ADR-0036(feature/asset 地图) | 无 | 直接 |
| ADR-0037(owner 对象授权) | 无 | 直接 |
| ADR-0039(NemoClaw spike) | 无(裁决不迁移) | 直接 |

**CONTEXT.md 20+ 概念全部领域无关**:Work Case / Generalization / Task Pattern / Skill / Asset Candidate / Skill Package / Review Decision——每个定义都是"一次真实工作实例""可复用抽象""操作化表达"这种通用语言,**没有一个概念绑死工程**。这是本体论最值钱的地方:它本来就是一套"工作如何被沉淀为可治理资产"的通用语言。

### 2.6 前端(`frontend/src/`)

| 组件 | 用途 | 工程耦合 | 可复用 |
|---|---|---|---|
| `AssetBuilderDrawer.vue` | 资产草稿抽屉 | 无 | 直接 |
| `AssetCandidateCallout.vue` | 候选标注 | 无 | 直接 |
| `ShellContextPanel.vue` | Shell 上下文面板 | 无 | 直接 |
| `FeatureAssetMapDisclosure.vue`(main) | 功能/资产披露 | 无 | 直接 |
| `AgentCapabilityMap.vue` | 能力地图 | 无 | 直接 |
| `EvidenceList.vue` / `EvidenceTrace.vue` | 依据链 | 无 | 直接 |
| `VerificationCard.vue` | 校验卡 | 无 | 直接 |
| `GuidePage.vue` | 导引页 | 低(文案) | 适配 |
| `WorkbenchSession.vue` | 工作台会话 | 低(文案) | 适配 |
| `TaskCreateJourney.vue` | 任务创建旅程 | 无 | 直接 |
| `GovernanceJourney.vue` | 治理旅程 | 无 | 直接 |

**前端结论**:全部组件机制通用,只有 `GuidePage.vue` 和 `WorkbenchSession.vue` 的文案需要适配生活场景。组件命名都是"Asset/Task/Evidence/Governance"这种通用词,没有 `<CfdPanel>` 这种领域专用组件。

## 3. 可以直接拿来跑 demo 的最小集

**后端零改动 + 契约零改动**,demo 跑通需要的就是这些文件(全部 main 已有):

```
contracts/asset_candidate.schema.json          # 资产候选契约
contracts/asset_draft_bundle.schema.json       # 草稿包契约
contracts/candidate_skill_package.schema.json  # Skill Package 契约
contracts/agent.schema.json                    # Agent 契约(demo agent 走 generic domain)
backend/app/ontology/asset_builder.py          # Work Case → Skill 纯函数投影
backend/app/ontology/asset_candidates.py       # 候选账本
backend/app/ontology/candidate_materializer.py # Skill Package 材化
backend/app/ontology/skill_reuse.py            # 复用匹配
backend/app/ontology/agent_shell.py            # 只读投影
backend/app/api/asset_drafts.py                # 7 个资产端点
backend/app/api/agent_shell.py                 # Shell 端点
backend/app/api/object_authorization.py        # owner 授权
agents/hello_agent/                            # 最小 agent 模板
agents/guide_agent/workflow.py                 # 编排 workflow(机制直接用)
```

**这一套已经覆盖本体论闭环全链路**:Work Case 识别 → Generalization → Task Pattern → Skill Draft → Asset Candidate(内容寻址) → 人审 → Skill Package(隔离材化) → 复用匹配。

## 4. 需要适配才能用的

按优先级:

1. **`agents/guide_agent/prompt.md` 文案**(中耦合):全文 60+ 行带"性能盘/控制逻辑/故障树"。demo 要么复制成 `agents/life_guide_agent/prompt.md` 改写,要么在现有 prompt 里加"通用任务模式"分支。**最干净:新造 `life_guide_agent`**,见缺口 G1。

2. **`agents/guide_agent/workflow.py:280` 的 `_INTERACTIVE_HANDOFF_IDS`**(中耦合):硬编码了 `policy_qa_agent`/`standards_qa_agent` 白名单。生活场景 demo 不需要对话型转交,不影响;但如果要加"厨房_qa_agent"之类,需要扩这个白名单。**建议保持现状,demo 走 orchestrate/refuse 两路即可**。

3. **`frontend/src/views/GuidePage.vue` 与 `WorkbenchSession.vue` 文案**(低耦合):页面标题/引导文可能带"工程"字样。需要打开看具体文案,大概率只改 `<template>` 里的字符串。

4. **`agent_shell.py:25-34` 的 `_DOMAIN_ORDER`**(低耦合):生活场景 demo 的 agent 走 `generic`,在投影里会标 `undeclared` 诊断。这不是 bug(ADR-0031 明确未声明 domain 标 undeclared),但 demo UI 上会显示"未声明领域"——如果嫌难看,可以在 `_DOMAIN_ORDER` 加 `life_skill` 等枚举。**建议不动,demo 反而能借机讲清"generic 是合法态"**。

## 5. 缺口清单(跑生活场景 demo 必须新造的)

按优先级:

**G1(阻塞):新造 `agents/life_guide_agent/`**
- 用途:生活场景的导引 agent,prompt 文案替换为生活语境("你是一位会做饭的朋友"而不是"你是二所工程师")
- 实现:复制 `agents/guide_agent/` 全套,改 `agent.yaml`(id/name/summary)、`prompt.md`(全改)、`workflow.py`(可直接 import 原 workflow 的 run 函数,或复制后微调)
- 工作量:1 天
- 理由:现有 guide_agent 的工程文案直接给 FDE 工程师看会让 demo 失去教学价值(他们正要学本体论,不是学工程 prompt)

**G2(阻塞):新造 `frontend/src/components/LifeScenarioPicker.vue`**
- 用途:场景选择器("今天想建模什么?周末做饭 / 健身计划 / 旅行规划")
- 实现:Element Plus 的 el-select 或卡片网格,选完预填 `life_guide_agent` 的对话开场
- 工作量:半天
- 理由:现有 `GuidePage.vue` 直接进对话,没有"挑场景"这一步;生活场景 demo 需要一个明确的入口让工程师选

**G3(建议):新造 `docs/design/ONTOLOGY-DEMO-LIFE-SCENARIOS.md`**
- 用途:三个生活场景的完整本体论建模 demo 脚本(Work Case → Skill Package 全流程)
- 工作量:1 天(由教学设计 agent 产出,见 fork-1 任务)
- 理由:demo 不能临场发挥,需要写死脚本

**G4(建议):新增 `seed_work_cases/` 目录**
- 用途:存放 3 个生活场景的种子 Work Case(真实经历的对话记录 + 附件),供 life_guide_agent 第一次启动时用
- 工作量:半天
- 理由:demo 需要预设"已经发生的真实工作实例"作为抽象来源;CONTEXT.md 明确 Work Case 必须是"已经真实发生"

**G5(可选):新增 `docs/adr/ADR-0040-life-scenario-demo-charter.md`**
- 用途:正式声明生活场景 demo 的边界(是教学工具,不是生产 Agent;不进 Registry 正式注册;Skill Package 不进 reuse_eligible 全局池)
- 工作量:2 小时
- 理由:避免 demo 产生的 Skill Package 污染生产 reuse 池;ADR-0035 的 reuse_eligible 是全局布尔,demo 包必须显式排除

## 6. 架构风险(硬塞生活场景会断裂的地方)

**R1:`_INTERACTIVE_HANDOFF_IDS` 白名单边界**
- 位置:`agents/guide_agent/workflow.py:280`
- 风险:如果 demo 误把 `life_guide_agent` 加进对话型转交白名单,会让它走 delegate 路径,但 delegate 安全闭包会校验目标 agent 的密级/快照——生活场景 agent 没有这些,会 fail-closed
- 缓解:**不要改白名单**,demo 的 life_guide_agent 走 orchestrate/refuse,不走 delegate

**R2:Asset Candidate 的 owner 授权(ADR-0037)**
- 位置:`backend/app/api/object_authorization.py`(main)
- 风险:demo 用同一套后端,demo 产生的 Candidate 会跟工程师真业务 Candidate 共享同一 owner 命名空间。如果 demo 用户用 `life_user_demo` 账号,Owner 授权会正常隔离;但如果用真账号,demo Candidate 会混进生产
- 缓解:demo 用独立账号(如 `workshop_demo`),ADR-0037 的 exact-owner 比较会自动隔离

**R3:Skill Package 的 reuse_eligible 污染**
- 位置:`backend/app/ontology/candidate_materializer.py` 的 `list_reuse_eligible`(`candidate_materializer.py:461`)
- 风险:demo 产生的已批准 Skill Package 默认 `reuse_eligible=true`,会进全局复用池,下次任何 agent 跑 reuse 匹配时可能命中"周末做饭"包
- 缓解:G5 的 ADR 显式声明 demo 包不进 reuse 池;或在 demo 路径里强制 `reuse_eligible=false`

**R4:guide_agent 的 model.profile=reasoning 依赖**
- 位置:`agents/guide_agent/agent.yaml` 的 `model.profile: reasoning`
- 风险:demo 环境如果没有 reasoning 模型(只配了 fast/embedding),guide_agent 会诚实失败(prompt.md 明说"真实多轮对话依赖内网模型服务,未配置时导引会诚实失败")
- 缓解:demo 前确认模型配置;或 life_guide_agent 用 `profile: fast`

**R5:NemoClaw/沙箱执行 spike 的外延误读**
- 位置:ADR-0039
- 风险:有人可能误读 ADR-0039 认为生活场景 demo 可以借 NemoClaw 沙箱跑——**不行**,ADR-0039 明确裁决"不迁移 agent 运行时,FLAi-OS Agent 是确定性工程包"
- 缓解:demo 保持"确定性 workflow.py"形态,不要变成 OpenClaw 自主聊天体

## 7. 合并风险

**ontology-agent-shell-v1 分支合并到 main:零风险**。
- 该分支头 `609b49b` 已经是 main 的祖先(merge-base),main 已吸收其全部 6 个 commit
- 该分支未 push 到 origin,纯本地
- **结论:不需要合并,直接用 main 即可**。worktree 可以删除或留作历史快照

**主仓当前 HEAD `codex/v02-mainline-consolidation` 与 main 的关系**:
- v02 落后 main 129 commit、超前 10 commit
- 这 10 个 v02 独有 commit 如果要合并到 main,需要 rebase 或 merge;但**这跟本体论 demo 无关**,demo 应该基于 main,不是 v02
- 建议:demo 开发新开 worktree from main:`git -C /Users/Zhuanz/projects/aircraft-comac/flai-os worktree add ../flai-os-life-demo-main -b codex/life-scenario-demo main`

## 8. 结论一句话

**FLAi-OS 的本体论子系统本来就是一套"工作如何被沉淀为可治理资产"的通用语言,不是工程专用框架**。跑生活场景 demo,后端/契约/文档零改动,前端零改动,只缺 4 样东西:(1)一个生活语境的导引 agent,(2)一个场景选择 UI,(3)三个 demo 脚本,(4)种子 Work Case。现有 14 个工程 agent 是"样例"不是"硬绑定",删掉平台照样跑。

最大风险不是技术断裂,是**叙事断裂**:如果 demo 直接用现有 guide_agent 的工程 prompt,FDE 工程师会以为"本体论只适用于工程",反而失去了"生活场景做教学"的初衷。所以 G1(life_guide_agent)是不可省的。

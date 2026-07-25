# 方向裁决：组合式开源底座 vs 自研控制内核

> 状态：**OWNER-ACCEPTED DIRECTION / RESTRICTED OPTION 2 / NOT_IMPLEMENTATION_AUTHORIZATION**
> 接受记录：`human_owner = JerryKogami` 已在当前 Codex 任务中具名接受
> `flai-os-takeover-docs-kimi-001@2`，绑定接受前候选补丁摘要
> `sha256:504208932db4dea2a2dd92f1f4e13e352690467633431927189e03f544a3c4b9`，
> 并接受「受限选项 2」作为项目方向裁决。
> 性质：本文是项目 owner 的方向裁决记录，**不是实现授权、PoC 立项、依赖引入或上线授权**；
> 也不是密码学签名或组织生产签发。
> 日期：2026-07-25（Asia/Shanghai）
> 冲突双方出处：
> - **方案 A**：`docs/research/20260725FLAi-OS DeepResearch.md`（2026-07-25，外部研究输入，下称「DeepResearch」）
> - **方案 B**：`docs/adr/ADR-0033-flai-control-kernel-and-replaceable-execution-backends.md`（2026-07-23 设计会话确认；该文件为本仓**预编号草案**，V0.2 候选编号映射见 §0）

---

## 0. 已接受方向的决策锚点与编号映射

本方向以 **V0.2 候选编号线** `codex/flai-v02-foundation@9023776c4ffbff6c7d3e0484fe956d1956e948d7`
（ADR-0047 裁决重编后的 0047–0062）作为后续项目规划的权威引用锚点；
这仍不是组织生产签发，也不授权实现。当前分支文档批（43847bc）中的
0033–0045 继续标为预编号草案。旧号映射及源 blob：

| 本仓预编号草案 | V0.2 候选编号 | 主题 | `9023776` 中的 source blob |
|---|---|---|---|
| 旧 ADR-0033 | **ADR-0049** | 唯一控制内核与可替换执行后端 | `495413a8f14990be4085d399123f57648536aa5e` |
| 旧 ADR-0034 | **ADR-0050** | 不中断自治会话与末端交付授权 | `810a287acc86878f2c7f2f74a39b7b8498606bf4` |
| 旧 ADR-0041 | **ADR-0057** | 权威知识底座 | `e5666904d4e04b4a5c1688476f4e782711d91cf7` |
| （Workspace-first / 分角色治理面） | **ADR-0052** | Workspace 统一入口与分角色治理面 | `bffad6783f007932764e9304e1ed26081c273c36` |
| （飞书唯一组织中枢） | **ADR-0062** | 飞书作为外网阶段唯一组织协作中枢 | `67d12c6cadbc92551c089395b1215581548514ad` |

下文为行文简洁，引用处写作「ADR-0049（旧 0033）」样式；引文原文出自本仓预编号草案文件，
V0.2 候选语义以表中 commit/blob 为准。本次 owner 具名接受已把该映射升级为本项目后续
规划工作的权威引用，但未把任何 ADR 升级为组织生产签发或实现授权。

## 0.1 不可谈判前提（任何选项均不得违反）

以下前提来自宪法、ADR-0049/0050/0052/0057/0062 候选体系与 owner 已确认的设计方向；
它们是**本次评审的冻结约束**，不是组织层正式签发。任何改变必须另开 owner 决策，
不能在本评审内静默放松：

1. **Workspace 是统一入口和协作外壳**（ADR-0052）：治理对象默认渐进披露，不在入口层铺开全部控制面复杂度。
2. **外网研发阶段以飞书为唯一协作中枢、GitHub 为代码真相**（ADR-0062）。
3. **内网部署后与飞书断开**，依赖自托管协作环境；任何引入的组件必须能在该形态下闭合。
4. **FLAi Control Kernel 独占任务、授权、证据、知识、审计与交付语义**（ADR-0049/0050/0057）：任何外部框架不得成为第二事实源。
5. **`human_owner = JerryKogami`，人是唯一签发者**；LLM 不进入判决链。
6. **Stage D 继续冻结**；本文任何内容不构成 Stage D 或其实施切片的授权。

## 1. 冲突的一句话表述

DeepResearch 建议 FLAi-OS 改用「组合式开源底座」（Open WebUI 入口 + Dify 工作流 + LangGraph 编排 + OpenHands 执行，自研只做集中治理/知识/行业模板）；ADR-0049（旧 0033）已确认保留自研轻内核为唯一控制面（身份/授权/任务图/队列/审计/交付决定），第三方框架只能作为 `AgentRuntimePort` 的候选 Adapter——**前者让开源项目分层承担平台运行时，后者让自研内核权威持有全部控制语义，两者对「谁是平台的权威控制面」给出了互斥的回答。**

## 2. 双方主张的准确复述

### 2.1 方案 A（DeepResearch）主张什么

出处：`docs/research/20260725FLAi-OS DeepResearch.md`

- 「**FLAi-OS 不应继续被定义为"再造一个通用 Agent 壳"**……更准确的战略是采用**组合式架构**：用成熟开源/商用底座承载通用能力，再把自研资源集中到真正构成护城河的部分，即**行业流程编排、知识飞轮、工具链封装、治理与审计、Agent 资产管理、评测体系**。」（执行摘要）
- 「若以 **Open WebUI 作为统一入口、Dify 作为工作流与知识流水线、LangGraph 作为生产级编排内核、OpenHands 作为代码/终端/沙箱型 Agent 能力、LiteLLM 作为模型网关、Langfuse 与 OpenTelemetry 作为观测与评测底座**，已经能拼出一套更可控、可迁移、可内网演进的 FLAi-OS 技术底座。」（执行摘要）
- 「入口层首选 Open WebUI；应用工厂首选 Dify；核心编排首选 LangGraph；高权限执行 Agent 首选 OpenHands……这四者各自承担不同层，不宜互相替代。」（竞争与替代方案分析）
- 护城河定义：「其一，把动力系统设计、分析、验证、审查、归档等流程转成可复用的 Agent 化工作模板；其二，把知识库、工具链、日志、反馈、评测数据闭环成持续优化的知识飞轮；其三，把身份、权限、审计、数据分级、模型路由、人工审批、回滚与评测做成可治理的企业控制平面。」（执行摘要）
- 节奏：「Phase 0–3 共约 9–15 个月」，Phase 0 预算「15–40 万元」（分阶段路线图；该文自注「均为研究性粗估，不是采购报价」）。

注意：DeepResearch 自己也声明了一组「未指定」前提——「**等保级别未指定、是否涉密与密级边界未指定……是否允许使用源可见但非 OSI 标准许可的组件未指定**」（研究边界与判断前提），并明确这些会直接影响 Open WebUI/Dify 的可用性。

### 2.2 方案 B（ADR-0049/0050 及其体系）主张什么

出处：ADR-0049（旧 0033，本仓预编号文件 `docs/adr/ADR-0033-flai-control-kernel-and-replaceable-execution-backends.md`）、ADR-0050（旧 0034）、`docs/product/FLAi-OS_V0.2_Design_Package/02_System_Architecture.md`、`CONTEXT.md`「平台运行边界」。

- 「FLAi-OS 保持唯一控制内核，权威持有身份与资源授权、Canonical TaskGraph、队列与并发、任务状态、审计证据、产物和最终交付决定。」（ADR-0049，旧 0033）
- 「OpenClaw、OpenHands 只能实现 Agent Runtime 侧能力……三者互不替代，也不得拥有第二套任务真相、绕过平台策略、直接写权威终态或产生真人签发。」（ADR-0049，旧 0033）
- 「替代方案是以 OpenClaw 或 OpenHands 替换本平台 Runtime……其个人或软件工程 Agent 的信任边界、状态模型和产品范围不能直接成为国企多主体工程平台的权威边界，因此**否决**。」（ADR-0049，旧 0033）
- 授权语义：「动态 Agent Loop 每提出一次 replan、Tool、Model、Knowledge 或 Connector 动作，都必须回到控制内核，由唯一 Authorization Module……签发一次短时 `ExecutionTicket`；所有下游 Port 无票拒绝并返回可核验 receipt。」（ADR-0049，旧 0033）
- 末端交付：「对正式工程资产、外部系统或组织事实产生不可逆影响的动作……冻结成 Delivery Bundle；具名真人只在末端对精确匹配的 Bundle 作一次性交付授权。」（ADR-0050，旧 0034）
- 权威知识底座：知识由内核统一签发与版本化，外部知识库只能作为受控内容来源（ADR-0057，旧 0041 方向）。
- 边界术语（CONTEXT.md）：控制内核 = 「唯一拥有身份、策略、任务图、队列、权威状态、审计证据与交付决定的控制边界；任何外部 Agent 框架都不能成为第二事实源」；执行后端 = 「只能回报动作与观察，不能自行授权、签发或决定权威完成状态」。

两方案并非完全对立：DeepResearch 的「自研集中治理平面」愿景与 ADR-0049 的「唯一控制内核」在**目标层**都想要统一治理；冲突发生在**实现层**——DeepResearch 让 Dify/LangGraph/OpenHands 各自成为所在层的运行时主体，治理平面叠加在它们之上；ADR-0049 要求控制语义只存在于自研内核，外部框架只能作为被逐步验票的执行后端。

## 3. 逐维度对比证据

### 3.1 安全治理：身份 / 授权 / 审计 / 撤权 / 交付授权

| 维度 | 方案 A（组合式底座） | 方案 B（自研控制内核） |
|---|---|---|
| 身份 | DeepResearch 建议「身份认证统一到 OIDC/SAML/LDAP 对接企业目录」（接口规范），依赖 Open WebUI 的 SSO/RBAC/SCIM（其宣称社区版即有，**DECLARED-NOT-VERIFIED**（本项目未验证））。但各底座（Dify/LangGraph/OpenHands）各自持有自己的用户/会话模型，DeepResearch 未说明如何跨组件形成单一主体事实源。 | 已有认证与粗粒度角色（`IMPLEMENTED-PARTIAL`）；目标为统一 `authorize(actor, action, resource, context, policy_version)` + commit-time recheck（`ACCEPTED-NOT-IMPLEMENTED`，02_System_Architecture §4.3）。当前代码存在 BOLA/IDOR 与治理写入口缺口（NO-GO 研究 §3.3 P0）。 |
| 授权 | DeepResearch 建议「把策略外置为 policy-as-code……OPA 与 Cedar 都适合承担这一层」（技术护城河第四），但 Dify/LangGraph/OpenHands 各自有独立工具/执行权限模型，策略引擎如何对 LangGraph 节点内部动作、OpenHands 沙箱内命令做到逐步强制，DeepResearch 未给出机制。 | ExecutionTicket 逐步授权：「每提出一次 replan、Tool、Model……动作，都必须回到控制内核……签发一次短时 ExecutionTicket；所有下游 Port 无票拒绝」（ADR-0049，旧 0033）。目标合同完整，但 ExecutionTicket/Execution Broker 目前**完全未实现**（02_System_Architecture §4.7 `ACCEPTED-NOT-IMPLEMENTED`）。 |
| 审计 | DeepResearch 建议 OpenTelemetry + Langfuse 观测、「100% 审计留痕」KPI；Langfuse/OTel 是可观测性底座，不是防篡改合规账本；各组件自身审计面（Dify 企业版审计日志等）是否可拼成单一不可抵赖链，未经评估。 | 现有 `task_events/tool_runs/model_calls`（`IMPLEMENTED-PARTIAL`）；目标为 hash chain + outbox + WORM（NO-GO 研究 §5.7），当前审计可变、覆盖不全（P0 缺口）。对 OpenClaw 的专项研究已证明「metadata-only 审计投影不是合规审计账本」（openclaw-runtime-security-reference §8.1）——同类风险未经评估地外推到 Dify/LangGraph 不成立也不可排除。 |
| 撤权 | DeepResearch 未涉及运行中撤权语义。 | 有明确目标合同：epoch snapshot、lease 绑定、RevocationAttempt 三类 witness（进程树终止/凭据吊销/连接失效）（02_System_Architecture §4.5/§4.7，CONTEXT.md「执行 Epoch 快照/撤权尝试」）。`ACCEPTED-NOT-IMPLEMENTED`。 |
| 交付授权 | DeepResearch 有「高风险动作强制人工审批」「关键节点强制人工审批」主张（技术护城河表），但绑定到 LangGraph human-in-the-loop 节点；谁签发、签发对象摘要、单次消费、漂移失效等语义未定义。 | Delivery Bundle + 具名真人末端一次性授权、单次 CAS 消费、漂移/过期/越权 fail-closed（ADR-0050，旧 0034；合同完整，`ACCEPTED-NOT-IMPLEMENTED`）。 |

小结：方案 B 在治理语义上定义得更深更完整（ExecutionTicket、Delivery Bundle、撤权 witness），但**全部是纸面合同（`ACCEPTED-NOT-IMPLEMENTED`），当前代码均有 P0 缺口**；方案 A 的治理能力在目标层接近，但其治理是「叠加在四套各自持有状态机的开源系统之上」，**单一权威事实源如何实现是方案 A 全文未回答的问题**——而这恰是 ADR-0049 否决替换路线的核心理由（「避免……双控制面、双恢复语义和双审计账本」）。

### 3.2 内网离线部署可行性

- 方案 A：DeepResearch 宣称 Open WebUI「支持离线、自托管」、Dify「社区版可自托管」、整体「可内网演进」。**这些断言全部 DECLARED-NOT-VERIFIED（本项目未验证）**。本项目对 OpenClaw 的专项研究（openclaw-runtime-security-reference §10.2）已证明：即使上游提供 `--offline`，完整 air-gap 交付还需要源码归档、全量镜像/安装包 SHA-256 与签名、SBOM、离线拓扑、升级回滚矩阵与断网验收证据——对四个组件的组合栈，这条链要逐组件闭合，DeepResearch 未做此评估。另有许可风险：DeepResearch 自己标注 Dify 为「Apache-2.0 衍生/附加条款，严格法务需审」、Open WebUI「许可包含品牌保留条款」，且其「是否允许使用源可见但非 OSI 标准许可的组件」前提**未指定**。各组件的许可条款、air-gap 能力、安全默认值在本项目均为 **DECLARED-NOT-VERIFIED**（本项目未验证）。
- 方案 B：自研栈（FastAPI + SQLite + Vue，无 Redis/Celery/ORM）依赖面小；但本项目自身离线发布链同样是 `DECLARED-NOT-VERIFIED`（发布脚本缺少实现与本轮验证证据，见 NO-GO 研究 §3.3、02_System_Architecture §3）。两方案在离线交付上**都没有已验证证据**，差别在于组件数量与外部依赖面大小。

### 3.3 与既有资产的复用度（可核实事实）

可核实事实（2026-07-25 本仓库工作树实测）：

- 后端：108 个 Python 文件，约 31,300 行；前端 `frontend/src`：51 个文件，约 12,200 行；`agents/` 下 13 个 Agent Package。
- 测试：`.venv/bin/pytest --collect-only -q` → **1019 tests collected**（本次写作实测复算）。
- V0.1 已封板：tag `v0.1.0-sealed`（commit `1e3cebc`，2026-07-14，双判据齐 + owner 终裁）。
- 已有深 seam（NO-GO 研究 §3.2）：Agent Package（manifest/schema/version/tools 白名单/limitations）、Runtime → Tool Registry 中央入口、Model Gateway profile 归因、SQLite queue `BEGIN IMMEDIATE` claim + 状态 CAS、Task events JSON Schema 校验、人签链 review event、文件 hash 证据、ax L0 合同先例。

- 方案 B：路线就是在这 8 个 seam 上增量演进（「保留方式」列逐条给出），V0.2 架构明确「复用现有 seam 增量演进……不创建第二数据库、第二任务中心、第二评测平台」（02_System_Architecture §7.4）。1019 项测试与封板资产**按设计直接延续**。
- 方案 A：替换为 Dify/LangGraph/OpenHands 后，上述 seam 中 Model Gateway、Tool Registry、SQLite Job Runner、Task/Event 链与 LangGraph/Dify 的对应物功能重叠，原则上被替换或沦为旁路；1019 项测试中覆盖这些 seam 的部分需要重写或废弃（具体比例本次未逐条统计，属未知项）。Agent Package 的 manifest/schema 思想可映射为「行业 Agent 模板」，但包标准本身不直接兼容 Dify/LangGraph 的资产格式（未经评估）。

### 3.4 迁移 / 重写成本（只允许定性）

- 方案 A 的成本：四套系统的选型、许可审查、离线供应链闭合、跨组件身份/策略/审计打通、既有 seam 的替换或旁路化、既有测试的重建。DeepResearch 给出「Phase 0–3 共约 9–15 个月」与 Phase 0「15–40 万元」，但该文自注「均为研究性粗估」，且估算对象是**从零起步的组合式 PoC**，未计入替换既有 31,300 行后端 + 1019 项测试 + 封板资产的迁移成本。
- 方案 B 的成本：已确认但未实现的合同清单很长——Canonical TaskGraph、SessionExecutionGrant、Execution Broker、可强杀 Sandbox、ExecutionTicket、Delivery Bundle、防篡改审计、撤权链（02_System_Architecture §3 现状表几乎全列 `ACCEPTED-NOT-IMPLEMENTED`）；叠加现行生产准入门 P0 六项（PRODUCTION-READINESS-PROGRAM §1，自估闭合成本 ~1.5–2.5 天，仅 Gate 1）与 NO-GO 研究 P0-0～P0-5。**这条路线的工程量同样没有经 owner 签发的总体估算**；R0–R8 是证据门而非日期承诺（06_Roadmap §4）。
- 诚实的定性判断：方案 A 把「尚未建设的通用能力」外包给开源社区，但新增「四系统集成 + 治理穿透 + 既有资产迁移」成本；方案 B 保留全部自研建设成本，但不产生迁移与集成税。两边都缺可核实的总量估算，本文不提供数字结论。

### 3.5 供应链与版本漂移风险

- 方案 A：引入至少 6 个新上游（Open WebUI、Dify、LangGraph、OpenHands、LiteLLM、Langfuse/OTel、OPA/Cedar），各有独立发布节奏、许可条款（Dify 附加条款、Open WebUI 品牌条款）与破坏性升级风险；内网离线意味着每个组件都要固定版本 + 制品摘要 + 升级评审，供应链治理面显著扩大。DeepResearch 未评估四栈组合的版本兼容矩阵。
- 方案 B：外部依赖面小且已在锁内；但「自研内核长期由 20–30 人团队运维」本身是 DeepResearch 指出的真实风险（「继续从零自研完整壳层，投入大、收益低、维护负担重」）——这是方案 B 未正面回应的弱点。
- 共同约束：本项目供应链门（quarantine、package digest、SBOM、组织签名，NO-GO 研究 §5.8）对任何引入物都适用，方案 A 下该门的工作量级随组件数线性放大。

### 3.6 对三条红线的兼容性

| 红线 | 方案 A | 方案 B |
|---|---|---|
| 人是唯一签发者（宪法 §5.6） | DeepResearch 支持「关键节点强制人工审批」，但其审批语义（LangGraph HITL 中断点）不等同于本项目「具名真人对精确 Delivery Bundle 单次 CAS 授权」；LLM 是否进入判决链取决于集成方式，组合栈本身不保证宪法 §5.6 与宪法四「LLM 禁止判断最终工程结论」。 | 红线即该体系的设计起点：ADR-0050（旧 0034）末端一次性授权、06_Roadmap §2.6「人签不自动化」、ADR-0049（旧 0033）「不得产生真人签发」。兼容性是结构性的，但**实现未闭合**。 |
| fail-closed（宪法 / 准入门哲学） | DeepResearch 有「关键任务失败恢复率」等 KPI 主张，但 Dify/LangGraph/OpenHands 的默认失败语义（重试、降级、host 执行路径）均为 **DECLARED-NOT-VERIFIED**（本项目未验证）；「沙箱不可用即拒绝、不自动降级 host exec」这类硬约束需要逐组件改造验证。 | fail-closed 是全部目标合同的显式语义（无票拒绝、Bundle 漂移拒绝、审计不可用阻断高风险写）。同样：合同在，实现未闭合（当前代码存在超时后不可强杀等反例，NO-GO 研究 §3.3）。 |
| 假绿死罪（宪法 §5.5） | Langfuse/OTel 观测与「证据链」主张方向兼容；但「完成/验证为 REAL/真人签发三态分离」需要跨四套系统统一状态语义，DeepResearch 未涉及。风险点：多组件状态聚合处最容易产生「漂亮的假绿」。 | 现有判据纪律（`is True`/`is False`、tamper 咬合、completed 不使用 REAL 绿）直接延续；当前已知假绿路径（终态晚写翻绿）已有修复合同（终态 CAS）。 |

## 4. DeepResearch 中可不冲突吸收进 ADR-0049 框架的成分

以下成分与「唯一控制内核」不矛盾，可在 ADR-0049（旧 0033）边界内评估吸收（均需另行走需求/评审流程，本文不构成授权）：

1. **OpenHands 作为 `AgentRuntimePort` 候选 Adapter**——这正是 ADR-0049 已预留的位置（「OpenClaw、OpenHands 只能实现 Agent Runtime 侧能力」）；06_Roadmap §13 也登记「经证据证明需要时接入 OpenClaw/OpenHands AgentRuntimePort Adapter」。DeepResearch 对 OpenHands「代码/终端/沙箱执行成熟」的盘点（本项目状态：`DECLARED-NOT-VERIFIED`）可作为该 Adapter 立项时的输入。
2. **Open WebUI 作为入口层参考**——其统一入口、SSO/RBAC/SCIM 的能力清单可作为工程智能体工作台的对标参考（类似本项目已做的 WorkBuddy 实机研究）；仅作 UI 参考或可替换的隔离实验，**不拥有 Workspace 产品架构、身份或状态**（Workspace 权威架构属 ADR-0052）。
3. **模型网关先于业务系统**——「所有入口和 Agent 只认一个内网模型网关」（DeepResearch 技术护城河第三）与宪法 §5.1「所有模型调用必须经过 Model Gateway」同向；LiteLLM 的预算/费控/fallback 能力清单可作为既有 Model Gateway 演进（egress policy、SecretRef）的**后端候选**对标输入，而非替换 Model Gateway 本体。
4. **行业 Agent 模板与知识飞轮方法论**——行业 Agent 库、Agent 资产管理（owner/版本/评测/适用范围）与既有 Agent Package + FLAi Bench + 能力发布包方向一致；其「Agent 资产页」信息架构（摘要/适用边界/输入输出契约/权限边界/评测成绩）可直接喂给 P1 工作台设计。权威知识底座归属不变（ADR-0057，旧 0041）。
5. **策略外置为 policy-as-code 的主张**——与统一 `authorize(...)` seam 同向；OPA/Cedar 是否作为策略引擎实现选型，是 ADR-0049 框架内的实现细节问题，不构成方向冲突。
6. **UX 与运营指标**——任务成功率、证据点击率、SUS、首次价值达成时间等指标定义，以及「可信、克制、专业、可操作」的美学原则，与现行「诚实地板 + 信任色」纪律兼容，可进入 R2 原型验收的指标候选池。

## 5. 不可调和点清单（非此即彼）

1. **权威控制面的归属**：LangGraph 作为「生产级编排内核」持有任务状态机（方案 A）vs Canonical TaskGraph 只存在于自研内核、外部框架只能提交 StepProposal（方案 B）。二者必居其一——LangGraph 一旦权威持有任务状态，即构成 ADR-0049 明令禁止的「第二套任务真相」。**因此 Dify/LangGraph 不进入权威控制面，也不作为首版依赖。**
2. **Dify 作为「工作流与知识流水线」主体 vs 统一知识权威底座**：方案 A 让 Dify 持有知识流水线与检索；方案 B（ADR-0057，旧 0041 方向）要求权威知识底座逻辑统一、由内核签发与版本化。Dify 的知识库不能成为权威事实源，只能降级为受控内容来源之一——降级后方案 A 中 Dify 的核心价值主张（知识流水线产品化）大幅缩水。
3. **授权粒度**：方案 A 依赖各组件自带的权限/审批模型（组件级）；方案 B 要求逐步 ExecutionTicket、无票拒绝（动作级）。在 LangGraph/Dify 内部实现逐步票据强制，等于在这些框架外围再包一层控制内核——那正是方案 B，而非方案 A。
4. **既有 SQLite 轻内核的存废**：方案 A 实质替换 Runtime/队列/网关层（PostgreSQL/Redis 是 Dify 等组件的常见依赖，06_Roadmap/02_System_Architecture 明确「不引入 PostgreSQL、Redis」为现行约束）；方案 B 明确复用。引入 Dify 与「不引入新数据库」的现行约束直接冲突。
5. **工程结论判定链**：宪法四禁止 LLM 判断最终工程结论；方案 B 已把「确定性代码 + 人」固化进交付链合同。方案 A 未声明与该红线的关系，其组合栈默认形态（低代码工作流直接产出交付物）需要在集成层额外证明不越界——未证明前按 fail-closed 处理。

## 6. 给 owner 的裁决选项

### 选项 1：维持 ADR-0049（自研唯一控制内核），DeepResearch 仅作参考输入存档

- 内容：方向不变；DeepResearch 的可吸收成分按 §4 逐项走正常需求/评审流程。
- 代价：继续承担全部自研建设成本与 20–30 人团队长期运维轻内核的负担（DeepResearch 指出的真实风险，本体系未给出对照估算）；V0.2 大量 `ACCEPTED-NOT-IMPLEMENTED` 合同仍需逐门闭合，时间风险不变。
- 不可逆性：低。ADR-0049 本身已为 OpenHands/OpenClaw 预留 Adapter 位，未来证据充分时仍可在不推翻控制面的前提下吸收执行层能力。

### 受限选项 2（已接受）：OWNER-ACCEPTED DIRECTION——维持 ADR-0049，仅允许对 §4 中受限成分另行申请带证据门的独立冻结评估

> 状态：**OWNER-ACCEPTED DIRECTION / NOT_IMPLEMENTATION_AUTHORIZATION**。
> 本选项是原「选项 2」的受限收敛版：控制面不谈判，吸收范围被硬约束收窄如下。

- 受限边界（每条都是硬约束，越界即越权）：
  - **OpenHands 仅作为 `AgentRuntimePort` 候选 Adapter**；评估目标是 conformance 可行性，不触碰任务真相与授权语义。
  - **Open WebUI 仅作 UI 参考或可替换的隔离实验**；不拥有 Workspace 产品架构、身份或状态（Workspace 权威属 ADR-0052）。
  - **LiteLLM 只能作为现有 Model Gateway 的后端候选**；Model Gateway 本体、profile 归因与 egress 策略归属不变。
  - **Dify / LangGraph 不进入权威控制面，也不作为首版依赖**（§5 不可调和点 1/2/4）。
  - **每个 PoC / 依赖评估必须另行冻结独立工作项**（含范围、证据门、Stop-if、退出条件），**不能由本文直接启动**；本文不是任何 PoC 或依赖引入的授权。
- 代价（成本对称化修正）：**本选项完整继承选项 1 的全部自研内核建设成本**（`ACCEPTED-NOT-IMPLEMENTED` 合同清单一项不少），**并额外增加 Adapter/组件评估税**（实测、法务、供应链评审人力）；存在「评估变渗透」的范围蠕变风险——需要把每个评估项的边界写成「不动控制语义」的硬约束，并遵守 Stop-if（06_Roadmap §15）。
- 不可逆性：低到中。Adapter 评估本身可回退（ADR-0049 要求「移除任一 Adapter 不得改变权威任务语义」）；但若评估结论是否定性的，已投入的评估人力不可回收。
- 前置条件：DeepResearch 中相关组件的内网离线能力、许可条款、安全默认值均为 **DECLARED-NOT-VERIFIED**（本项目未验证），任何吸收立项前需先补实测/法务证据，不能以 DeepResearch 断言为准。

### 选项 3：重开方向 ADR 评审——正式评估以组合式底座替换/包围自研内核

- 内容：承认 ADR-0049 可能需要修订或推翻，启动一次正式方向评审（新 ADR 流程），对 DeepResearch 组合栈做本项目级实测（离线部署、许可、治理穿透、迁移范围）后再裁决。
- 代价：① 方向悬置期间 R0–R8 节奏受影响，V0.2 已确认的 ADR 体系（0047–0062 线）需要重新对齐；② 既有 1019 项测试、8 个深 seam、V0.1 封板资产的迁移/废弃范围需要正式盘点；③ 评审本身需要实测投入（四栈内网 PoC）。
- 不可逆性（成本对称化修正）：**评审动作本身可回退**——评审不通过即回到现状，损失的只是评审投入；**高不可逆性只在评审通过后、owner 另行签发迁移/替换授权时才发生**（届时代码与测试资产的相当部分进入迁移或废弃路径，且若「治理穿透四栈」事后证明不可行，回退到方案 B 时已损失的周期不可回收）。不得把「开评审」本身描述为高不可逆动作。
- 注意：DeepResearch 自身的「未指定前提」（等保级别、密级边界、许可口径、基础设施现状）与本项目 NO-GO 研究的 P0 缺口清单，是任何方向评审都必须先补齐的输入，否则评审将建立在未实测断言上。

## 7. 证据边界与未知项

**本文的证据边界（诚实边界，予以强化）：**

1. DeepResearch 对 Open WebUI（离线部署、SSO/RBAC/SCIM）、Dify（企业版 SSO/RBAC/审计、K8s 部署）、LangGraph（durable execution/HITL）、OpenHands（沙箱执行成熟度）、LiteLLM/Langfuse 的全部能力断言，以及全部第三方组件的**许可条款、air-gap 能力、安全默认值**，均为 **DECLARED-NOT-VERIFIED**（本项目未验证）；其引用为搜索摘要级来源（cite 标记），非本项目固定的版本化源码审阅。对比之下，本项目对 OpenClaw 做过固定版本（v2026.7.1、固定 commit）的源码级审阅——两类证据强度不同，本文对比表中已逐处标注。
2. 方案 B 侧的目标合同（ExecutionTicket、Delivery Bundle、撤权链、权威知识底座等）全部为 **ACCEPTED-NOT-IMPLEMENTED**；本项目纸面治理合同仍有大量 `ACCEPTED-NOT-IMPLEMENTED`，本文对其「兼容性」的评价是**合同级**的，不是实现级证据。当前代码的 P0 缺口以 NO-GO 研究 §3.3 为准。
3. 可核实事实已实测：1019 项测试（`.venv/bin/pytest --collect-only -q`，2026-07-25 复算）、后端约 31,300 行 / 前端约 12,200 行 / 13 个 Agent Package、`v0.1.0-sealed`（`1e3cebc`）。除此之外本文不发明任何量化数据。
4. 成本对比只有定性：两边都缺经签发的总量估算；DeepResearch 的「9–15 个月 / 15–40 万元」为研究性粗估且不含迁移既有资产的成本。

**明确的未知项（裁决前建议补齐）：**

- 1019 项测试中按 seam 分布、方案 A 下需重写/废弃的精确比例（未统计）。
- Dify 附加许可条款与 Open WebUI 品牌保留条款对本部署形态的法务结论（DeepResearch 自己标注「严格法务需审」；本项目状态：`DECLARED-NOT-VERIFIED`）。
- 四栈组合在内网离线环境的安装/升级/版本兼容矩阵（无实测）。
- 在 LangGraph/Dify 外围实现逐步 ExecutionTicket 级强制的技术可行性（若走选项 3，这是决定性未知项）。
- DeepResearch「未指定前提」清单（等保、密级、身份源、K8s/GPU/存储现状、预算口径）与本项目 D4–D9 待裁决项（NO-GO 研究 §10）的对齐。

---

*OWNER-ACCEPTED DIRECTION · RESTRICTED OPTION 2 · 2026-07-25 ·
`JerryKogami` 接受 `flai-os-takeover-docs-kimi-001@2`，绑定接受前候选补丁摘要
`sha256:504208932db4dea2a2dd92f1f4e13e352690467633431927189e03f544a3c4b9`。
任何 Stage D、实施、PoC、依赖引入或生产上线均需另行冻结与明确授权。*

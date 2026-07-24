# FLAi-OS V0.2 证据门路线图

> 文档性质：从 V0.1 可复用骨架走向 Phase 0A/0B 的产品路线读模型。路线图采用证据门而非拍脑袋日期；本文件本身不授权运行时代码、外部系统写入或试点开放。术语以 [`CONTEXT.md`](../../../CONTEXT.md) 为准，决策以 [`docs/adr/`](../../adr/) 为准，生产门以 [`docs/PRODUCTION-READINESS-PROGRAM.md`](../../PRODUCTION-READINESS-PROGRAM.md) 及后续经批准的替代文档为准。

## 1. 状态标签

| 标签 | 含义 |
|---|---|
| `IMPLEMENTED-VERIFIED` | 当前精确范围、版本与环境有可复跑机械证据，绑定命令、结果引用和日期；不等于生产就绪 |
| `IMPLEMENTED-PARTIAL` | 有基础实现，但尚未完成本路线图目标。 |
| `ACCEPTED-NOT-IMPLEMENTED` | 已在设计会话中确认 ADR 方向，尚未正式组织签发、实现和验收。 |
| `DECLARED-NOT-VERIFIED` | 有规划、历史结论或配置声明，但缺少本轮可复核的当前证据。 |
| `OUT-OF-SCOPE` | 本轮路线图明确不安排。 |

“已开发”“已合并”“能演示”都不能自动转成 `IMPLEMENTED-VERIFIED`。状态变化必须绑定精确发行物、验证命令/记录、证据摘要和具名责任人。

## 2. 路线原则

1. **顺序不可跳过**：架构评审 → MVP 定义 → 原型设计 → 开发 → Phase 0A → Phase 0B。
2. **放大跟随证据**：先验证控制、安全与三条最小工作流，再扩大用户、数据和工具范围。
3. **一条事实链**：任务、事件、文件、工具、模型、知识、评测、晋级、反馈和统计复用现有 Seam，不平行造平台。
4. **深 Module 优先**：把策略、执行、知识权威、评测与交付复杂度收进少量稳定 Interface，保持调用方 Leverage 与实现 Locality。
5. **invalid-first**：每个阶段先写出会失败的越权、篡改、未知和错误输入，再实现正向路径。
6. **人签不自动化**：AI、评测分数、需求热度和代码合并均无签发权。
7. **状态诚实**：没有证据就显示未知、计划、受阻或待补，不使用手填绿色和伪精度进度。

## 3. 当前基线

### 3.1 可复用资产

| 资产 | 当前窄事实 | 状态 |
|---|---|---|
| 轻内核与 Package 机制 | FastAPI + SQLite、Agent/Tool Registry、Task Center、Runtime、Model Gateway、Tool Registry、File/Event 基础链已存在并有 V0.1 审查记录；当前不是 clean release baseline | `IMPLEMENTED-PARTIAL` |
| 任务、会话与工作台骨架 | 当前 main 有任务页、导引会话、协作工作台和任务分组；`safe_auto` 仅是 ADR-0047 记录的历史 commit-bound 分支证据，不属于当前基线 | `IMPLEMENTED-PARTIAL` |
| 鉴权与粗粒度角色 | 已有认证与 `admin`、`agent_developer`、`business_user` 等试点角色检查 | `IMPLEMENTED-PARTIAL`：不能代表最终 capability/作用域授权 |
| Knowledge | BM25 file_dir × document、Scope、引用、来源摘要与 default-deny 骨架 | `IMPLEMENTED-PARTIAL` |
| Eval 与晋级 | eval cases、Eval Runner、快照、人工评审/策展/晋级骨架 | `IMPLEMENTED-PARTIAL` |
| 运行统计与反馈 | stats 概览、任务/工具/模型事实和 feedback 入口 | `IMPLEMENTED-PARTIAL` |
| 性能盘与 CFD 技术样板 | Mock/固定样例与求解—评测链可用于内核运行验证 | `IMPLEMENTED-PARTIAL`：不是三条首发产品能力的完成证据 |

### 3.2 当前不能宣称的状态

- `DECLARED-NOT-VERIFIED` 当前工作树不是经本设计包重新冻结、完整验证并签发的 V0.2 发行物；
- `DECLARED-NOT-VERIFIED` 本路线图没有目标机 Sandbox、对象级授权、外联控制、审计防篡改、并发容量和恢复演练全部通过的证据；
- `ACCEPTED-NOT-IMPLEMENTED` ADR-0050 的不中断自治会话、SessionExecutionGrant、ExecutionBroker、可强杀 Sandbox 与 Delivery Bundle 尚未作为完整链验收；
- `ACCEPTED-NOT-IMPLEMENTED` 三条黄金工作流、权威知识底座、完整 FLAi Bench、共建地图和需求共创均为已接受方向，不是当前产品能力；
- 因此当前默认结论是：**不得以本 V0.2 设计包宣称生产就绪或启动 Phase 0A/0B。**

## 4. 总体阶段图

```text
R0 架构评审
  → R1 MVP 定义冻结
  → R2 工作台原型验收
  → R3 控制与信任地基开发
  → R4 三条 tracer bullet + 基准包
  → R5 Phase 0A 技术验收
  → R6 真实工作流验证
  → R7 Phase 0B 限范围业务试点
  → R8 证据驱动扩展与后期指挥视图
```

任一阶段未通过时，后续阶段保持关闭。紧急业务压力、领导关注或需求数量不能绕过阶段门。

### 4.1 五条正交阶段轴

以下名称回答不同问题，不能互相替代或自动授权：

| 轴 | 回答的问题 | 当前窄状态 | 权威门 |
|---|---|---|---|
| Stage A～D | 设计与开发进行到哪一步 | Stage B 产品语义已由设计会话冻结；Stage C 已选择收敛方向但未正式验收；Stage D 关闭 | 产品/UX owner 对精确原型与切片的具名决定 |
| R0～R8 | 产品能力和证据成熟到哪一门 | 本包提供 R0/R1 设计输入与 R2 隔离原型证据；不证明 R3 以后实现 | 本路线图各 R 门的机械证据与具名签发 |
| Phase 0A / 0B | 哪些人、数据和能力可以被暴露 | 两者都未开放；Phase 0A 仍只允许未来的 approved synthetic 受控验收 | QualificationDecision、DeploymentBinding、Entry/Exit evidence |
| F0～F5 | 外网飞书研发协作中枢接入到哪一步 | `F0-REVIEW-PACKAGE-DRAFT`；只适用于外网研发域，F1～F5 未授权 | [ADR-0062](../../adr/ADR-0062-feishu-single-organizational-hub.md) 与 [设计 17](17_Feishu_Organizational_Hub.md) 的逐段门 |
| A0～A5 | 外网发行物如何受控进入内网并在断网条件下运行 | A0 合同设计中；A1～A5 未授权，内网生产结论 `NO-GO` | [ADR-0063](../../adr/ADR-0063-external-development-airgap-internal-workspace.md)、[设计 18](18_AirGap_Exchange_and_Internal_Release.md) 与 [设计 19](19_Internal_Self_Hosted_Workspace.md) |

依赖规则：

1. Stage C、外网 F0 与 AirGap A0 可以并行；当前 Stage C 只模拟当前域 Workspace 入口上下文，不接真实 tenant/app 或内网系统。
2. Stage D Runtime 切片必须先通过 Stage C 正式验收、适用 R0/R1 exit receipts 的正式签发，
   并另获精确实施授权；F0 设计完成不打开 Stage D。
3. 当前 Phase 0A 不依赖真实飞书。真实飞书只能进入外网研发流程，并须通过对应 F 门；内网
   Phase 0A 必须通过对应 A 门和自托管 Workspace 门，不得把 F 门结果继承为内网准入。
4. F1～F5 每段单独授权、累积验收；任一 F 段完成都不证明 R3～R8、Phase 0A/0B 或生产准入。
5. R 门可以消费其他轴的已验证证据，但不得从“原型好看”“飞书已接通”“离线包已复制”“代码已合并”自动
   推导 Qualification、DeploymentBinding、试点或发布。
6. 组织身份签发未解析时，设计会话决定保持 `confirmed_in_design_session`，不能冒充
   `formally_signed`。

## 5. R0：架构评审

**目标**：把 V0.2 产品读模型转成一套没有双控制面、没有隐含授权、没有假绿路径的可实施架构。

**状态**：`ACCEPTED-NOT-IMPLEMENTED`

### 交付物

- 控制内核 Module 图与所有权表：Identity/Policy、CanonicalTaskGraph、Session Execution、Sandbox、Artifact、Audit、Delivery Bundle；
- Broker Interface 与三类执行 Port：开始/观察/重连/协调恢复/取消、逐步 ExecutionTicket、receipt 与 lease/generation 语义；OpenClaw/OpenHands 只能作为 AgentRuntimePort 候选 Adapter；
- 身份、对象、能力、数据域、动作和时效组成的 policy Seam；
- Sandbox 威胁模型、进程树强杀、文件/网络/资源/时间预算和残余副作用合同；
- 权威知识发布/撤销、时间有效性、精确锚点、冲突和任务快照设计；
- capability-release manifest、FLAi Bench 四轨 envelope 与晋级绝对门；
- Delivery Bundle 冻结、授权 CAS、提交 receipt 和后置验证状态机；
- 数据模型与迁移策略；所有不可变列明确 CAS-on-NULL 或等价约束；
- 工作台、治理中心、共建地图的共享事实源和只读投影关系；
- 分域日常中枢的 Source Ownership Registry、`open/prepare/commit`、ActorBinding、classification projection、owner receipt、reconciliation、SecretRef 与安全生存通道；
- AirGapExchange 的签名、内容寻址、quarantine、ReleaseSet CAS、内网重验、脱敏反馈与失败码；
- 三条工作流的 Adapter 清单、输入预算和失败模式。

### 退出门

1. 每个权威事实只有一个 owner Module；不存在 OpenClaw/工作台/统计页持有第二状态机；
2. 每个跨 Module Interface 写明不变量、错误模式、排序/幂等、性能与审计要求；
3. 每个真实变化点至少有生产与测试两个合理 Adapter；仅一个实现的地方不预造 Seam；
4. 权限缺失、主体漂移、Bundle 漂移、未知分类、未知知识状态、未知 Bench 门全部 fail-closed；
5. 架构评审自身发现的所有权、Interface 和安全设计 P0 均已有处理结论；运行时 P0 必须被逐项映射到 R3/R4/R5 的实现与验收门，不能在只读评审阶段被宣称清零；
6. 具名 owner 签发架构版本和残余风险。

## 6. R1：MVP 定义冻结

**目标**：把宏观平台收窄为 Phase 0A 的精确发行范围，避免一边开发一边扩大产品面。

**阶段门状态**：`FROZEN-FOR-STAGE-C`

**实现状态**：`ACCEPTED-NOT-IMPLEMENTED`

owner 于 2026-07-23 在设计会话中明确说“冻结 Stage B，进入 Stage C”。该决定只冻结本节所述产品与合同语义并打开隔离 Stage C UI 原型门；`decision_status=confirmed_in_design_session`、`accepted_by_actor_id=UNRESOLVED`、`decision_digest=UNRESOLVED`。它不是组织身份系统正式签发，也不授权 Runtime、API/Schema、数据库、依赖、真实数据、Phase 0A cohort、试点、发布或部署。

### 必须冻结

| 范围 | 必须明确的 Interface/合同 |
|---|---|
| 人群与设备 | cohort 固定为 5–8 名技术验收人员；冻结选人条件、角色资格、签发职责、macOS 参考版本和硬件最低配置；具名 actor/device 清单是 Entry 前的受控运营工件，不在 Stage B 文档中虚构 |
| 数据 | 冻结仅允许 `source_kind=synthetic`、`fixture_class=canonical|edge|adversarial|tamper`、分类/来源/摘要字段合同及允许的输入输出位置；真实 fixture bytes、digest 和签名是 D11/Entry 工件 |
| Office | DOCX 版本、大小与复杂度预算、保真项、恶意文档策略、差异合同 |
| CFD | OpenFOAM 版本/求解器、包预算、允许文件、检查规则、finding schema |
| Meeting | 输入格式、锚点粒度、责任事项 schema、会议负责人身份与正式化条件 |
| Knowledge | 权威类别/状态、最小发布流程、锚点策略、冲突/有效期算法 |
| Bench | 三套 pack 的 36 个固定 case ID、用途、expected boundary/assertion/witness 必填合同、rubric、必测门、`source_kind`/`fixture_class` 和可比性规则；approved manifest 与实际内容摘要在 D11/Entry 冻结 |
| 运行 | 并发、CPU/内存/磁盘/时限、模型/Token、队列、取消和恢复预算 |
| 产品 | 页面范围、状态词典、错误/空/等待/受阻/签发态、无障碍与截图基线 |

### 退出门

- `01_PRD.md` 的每个 Phase 0A requirement 有负责人、验收测试和证据落点；
- 三条工作流的删除清单明确，任何超出内容标 `OUT-OF-SCOPE`；
- 所有**设计语义**开放问题都有 owner 裁决或成为明确 Stop-if，不留“开发时再看”；具名 cohort、设备证明、fixture bytes/digests、签名和运行证据必须被明确列为 Entry 工件，不能用占位值冒充已存在；
- capability-release manifest 和 Phase 0A release manifest 的字段、摘要输入、invalid 条件与验证命令已规格化；实际 validator 属于后续 R3/R4 实施，未实现前保持 `ACCEPTED-NOT-IMPLEMENTED`，不能用人工表格冒充已校验；
- owner 只签发 MVP 的产品与合同语义；此时才能进入原型设计。该签发不等于 QualificationDecision、DeploymentBinding、试点邀请或上线授权。

Stage B 的退出只证明“未来需要生成和验证什么”，不证明运营工件已经存在。D11 必须生成并验证 approved pack manifest 与 fixture digest；Entry 必须再绑定具名 cohort、设备证明、签发人、浏览器构建、候选 release digest 和全部门证据。缺少其中任一项都阻断 Entry，但不以伪造数据阻断本阶段的设计冻结。

## 7. R2：工作台原型验收

**目标**：在写运行时代码前证明产品不会退化成传统后台、复杂表单或逐动作审批器。

**阶段门状态**：`DIRECTION-SELECTED-FOR-CONVERGENCE`

**实现状态**：`ACCEPTED-NOT-IMPLEMENTED`

owner 于 2026-07-23 在设计会话中明确说“以 C 为主，吸收 A 的首页”。因此 Stage C 只把空任务收敛为 A 式低门槛首页，把提交后的工作收敛为 C 式连续执行工作台，并删除 A/B/C 比选壳。`decision_status=confirmed_in_design_session`、`accepted_by_actor_id=UNRESOLVED`；这只是方向选择，不是完整原型正式验收，也不打开 Stage D。

当前 Stage C 只允许隔离 UI 资源和内存 fixtures；不得连接或修改 Runtime/API、Schema、数据库、生产配置，不得新增第三方依赖、使用真实数据、开放试点、发布或部署。

ADR-0062 只形成外网研发协作入口目标；ADR-0063 决定内网生产使用自托管 `FLAiWorkspace`，并通过 `AirGapExchange` 与外网隔离。当前 A 首页 → C 执行态原型继续作为工程工作台的专业体验基线；真实飞书接入属于 F0～F5，内网 Workspace 与离线准入属于 A0～A5，均是独立门。

### 原型范围

- 默认首页与单一 Composer；
- 三条工作流的发起态；
- 自治执行中的计划摘要、真实步骤、证据、产物与聚合例外；
- 取消、超时、受阻、失败、恢复与权限不足；
- Delivery Bundle 比对、残余风险、待交付动作和一次性签发；
- 只读共建地图摘要与低门槛需求提交；
- 角色受限治理入口，不在普通用户首页展开后台信息架构。

### 退出门

1. 5–8 名候选技术验收人员中至少 3 名按固定任务脚本完成无引导走查；
2. 用户无需理解 Agent id、内部 schema、CanonicalTaskGraph 或权限枚举即可发起任务；
3. 任务中间不存在通用审批弹窗，未知项在末端聚合但不被隐藏；
4. 失败、未知、未验证和 completed 的视觉/语义可区分；completed 不使用 REAL 绿色；
5. Light/Dark、目标桌面尺寸、键盘焦点、长文本、空态和错误态有基线；
6. 走查问题按阻断/非阻断记录，阻断为零后由产品 owner 签发原型。

## 8. R3：控制与信任地基开发

**目标**：先完成三条工作流共同依赖的深 Module，使安全和证据不散落在各 Agent 内。

**状态**：`ACCEPTED-NOT-IMPLEMENTED`

### 工作包与依赖

| 工作包 | 主要结果 | 依赖 | 完成门 |
|---|---|---|---|
| K1 Control Kernel ownership | CanonicalTaskGraph、SessionExecutionGrant、策略解析、任务/状态唯一写入 | R0/R1 | 试图建立双控制面或让后端 Adapter 写权威终态的负例被拒绝 |
| K2 Sandbox & ExecutionBroker | 进程/文件/资源/时间/网络隔离，取消与强杀，receipt | K1 | 逃逸、超预算、外联、残余进程负例咬合 |
| K3 Delivery Bundle | 不可变 Bundle、差异、风险、策略、动作、CAS 授权、提交后验证 | K1/K2 | 篡改、过期、重复消费、越权，以及外部调用前/后、receipt 落库前/后的逐崩溃点负例咬合；未知效果不重放 |
| K4 Policy & classification | 对象级 capability/作用域/数据分类，提交前重验 | K1 | BOLA、身份漂移、未知角色/分类、同人越权自签均失败 |
| K5 Audit & recovery | 追加审计、防篡改证据、幂等/重试矩阵、演练入口 | K1/K2 | 删改证据、模型/工具 provenance 漂移和错误重放不能假绿 |
| K6 Concurrency & observability | 用户/Agent/工具/后端预算、队列公平、超时、容量测试 | K1/K2 | 超配额行为确定，队列与最老任务可观测，压力曲线可重跑 |
| K7 Authoritative Knowledge | 发布/撤销、有效期、替代、锚点、冲突、快照、分类传播 | K4/K5 | 普通上传晋升、过期/冲突回答、密级降级负例失败 |
| K8 Capability Release & FLAi Bench | 完整 manifest、四轨运行、绝对门、资产生命周期 | K2/K4/K5/K7 | incomplete/skipped/unknown/AI 自批无法晋级 |

### 退出门

- 每个 Module 的 Interface 测试覆盖正向与 invalid-first 场景；测试不穿透实现；
- 现有任务、事件、tool_runs、model_calls、eval、promotion 等事实被复用，不复制到新账本；
- `bash scripts/verify_all.sh` 或经 MVP 批准的等价完整验证在冻结发行物上退出 0；
- 安全对抗套件、恢复演练和 tamper witness 全部附原始证据；
- 独立审查无 P0；具名 owner 签发地基发行物。

## 9. R4：三条 tracer bullet 与首批基准包

**目标**：在共同地基上完成三个不同类型的完整用户结果，证明平台不是单一 CAE 或文档工具。

**状态**：`ACCEPTED-NOT-IMPLEMENTED`

三条工作流可以在共同地基稳定后并行开发；ADR-0053 没有授权一个跨工作流的固定开发优先级。资源不足时，路线图负责人必须以独立版本记录选择和理由，不能让实现顺序反写成产品重要性。

三条 tracer 的冻结预算、invalid-first cases、FLAi Bench 门与分片依赖统一见 [15_Phase_0A_MVP_Spec.md](15_Phase_0A_MVP_Spec.md)。该规格的冻结只授权 Stage C UI 原型；“以 C 为主，吸收 A 的首页”只选择收敛方向。R4 与任何 Stage D 实施仍保持关闭，直到收敛原型被 owner 另行明确接受且 owner 点名并精确授权对应冻结切片。

| 发布候选 | 第一薄切片 | 不可抵消门 | 首批 FLAi Bench 重点 |
|---|---|---|---|
| CR-OFFICE-01 | DOCX 技术报告润色与规范化 | 不覆盖原文；数字/单位/公式/表格/图片无静默改变 | 保真、差异、可撤销、恶意文档和证据完整性 |
| CR-CFD-01 | OpenFOAM 算例只读体检 | 不写目录、不启动求解；finding 有文件/字段证据；未知不补造 | 解析、规则、依据/假设/建议分离、恶意压缩包 |
| CR-MEETING-01 | 会后纪要与行动项整理 | 不虚构组织事实；责任字段缺失阻止正式签发 | 来源锚点、冲突、角色身份、精确版本签发 |

### 退出门

1. 每个候选由同一 capability-release Interface 冻结 Agent、模型、工具、Sandbox、策略、知识、用例和 rubric；
2. 每个候选四轨评测完成，所有必测门为明确 `passed`，且有具名工程质量评审；
3. 每个候选完成至少一次完整工作台旅程和一次签发失败旅程；
4. 三个候选均只使用 approved `source_kind=synthetic` 数据，正常样本只以 `fixture_class=canonical` 标识；
5. 任何外部活态无法冻结时明确标记证据边界，不得显示可复现全绿；
6. 能力发布、限制、已知问题和回退方式齐全。

## 10. R5：Phase 0A 技术验收

**目标**：由 5–8 名具名技术人员验证产品机制、三条工作流和安全门在 macOS 限定环境成立。

**状态**：`ACCEPTED-NOT-IMPLEMENTED`

### 进入门

- D15 已形成完整、可复算且未过期的 qualification evidence，但未被机器自动写成资格；
- 具名真人已对精确 release/Bench/P0 digest 签发 current `QualificationDecision(target=phase_0a, outcome=eligible)`；
- 另一个具名签发动作已产生限定 5–8 个 actor、macOS environment、synthetic data、三条能力、允许动作、预算和时间窗的 active `DeploymentBinding`；
- `01_PRD.md` Gate A 全部通过且在整个 R5 期间持续有效；任一关键 digest、身份、策略、环境或证据漂移立即暂停绑定并回到 Entry，不继续采样。

### 运行方式

- 每名人员只看到被分配的能力、数据域和治理入口；
- 使用固定任务脚本与少量开放任务，不用开发人员代操作；
- 收集真实任务事实、失败、退回、反馈、资源和用户理解问题；
- 需求提交只需自然语言，后续策展、评审和路线图签发在工作之外异步完成；
- 共建地图可先展示只读版本、能力、限制、证据和下一目标，不建设领导指挥中心。

### 退出门

- `01_PRD.md` Phase 0A Gate B～E 全部通过，且 Gate A 在退出时仍 current/valid；
- 试点任务没有未解释的状态漂移、审计缺口、越权或假绿；
- 三条工作流的采用、退回、失败、受阻和问题样本均可回查；
- 线上失败形成 draft eval case 或具名不固化理由，不能修完即忘；
- 安全、产品、领域和运维各有独立验收记录；
- owner 记录“Phase 0A 机制通过/不通过”及剩余边界。通过不等于工程有效、业务价值成立或生产就绪。

## 11. R6：真实工作流验证

**目标**：为 Phase 0B 选择至少一条工作流，以真实工具和真实数据建立可扩大证据。

**状态**：`ACCEPTED-NOT-IMPLEMENTED`

### 选择原则

候选必须同时满足：真实需求来源明确、数据授权可闭合、工具或材料可冻结/追溯、领域 reviewer 可参与、错误后果可控制、回退可执行。性能盘是首个 Fast Follow 专业候选，但不阻塞首发共同地基与三条黄金薄切片；其既有 Mock/技术样板不能替代真实 Tool Adapter 与业务验收。

### 退出门

1. 真实数据与工具的授权、分类、保留、输出和外联策略具名批准；
2. 真实环境重新冻结 capability-release manifest，synthetic 评测不自动继承；
3. 领域 rubric、基线和 golden cases 由具名专家批准；
4. 安全、准确性、恢复、容量和用户验收在真实环境重跑；
5. 至少一个可比较人工基线用于价值验证；无基线保持未知；
6. 公开能力声明仅覆盖已验证版本、数据域、工具和限制。

## 12. R7：Phase 0B 限范围业务试点

**目标**：面向 20–30 名具名业务用户验证真实采纳、组织价值和支持机制。

**状态**：`ACCEPTED-NOT-IMPLEMENTED`

### 开放方式

- 按 Agent/工作流、项目、数据域、用户组、并发预算和有效期逐项开放；
- 未在清单中的能力不可见或明确标记未开放；
- 每次发布都绑定能力版本、Bench 证据、支持人和回退方式；
- 需求提出者或同类代表优先受邀试用和验收；
- 共建地图展示团队聚合与经隐私处理的需求/证据转化，不展示个人生产力排行。

### 退出门

- 20–30 人范围内的授权、容量、支持、事故响应和撤回演练通过；
- 使用采纳、质量安全、资源和价值指标均有版本化口径；
- 节时只报告人工基线支持的区间、样本量和覆盖率；
- 发布回告能够说明解决范围、版本、证据和剩余边界；
- 具名 owner 决定继续扩大、保持限范围、回退或停止。

## 13. R8：证据驱动扩展

**目标**：只在真实证据和路线图签发后扩展能力与管理视图。

**状态**：`OUT-OF-SCOPE`（不进入 Phase 0A/0B 交付承诺）

候选方向包括：

- Office 的 Excel/PPT、规章快查和邮件草拟；
- CFD 隔离副本受控修改、已有结果后处理与报告；
- 性能盘真实专业闭环；
- FEA、控制逻辑、FTA、P-ACE 等领域工作流；
- 完整行动项跟踪、通知 Adapter；
- 内网 `FLAiWorkspace` 中的领导只读智能化指挥中心；
- Windows 适配与后续内网发行 Adapter；
- 经证据证明需要时接入 OpenClaw/OpenHands AgentRuntimePort Adapter。

这些方向都必须从需求池进入、经过适用领域/安全门、由路线图负责人签发，不能因为“长期愿景”自动形成 Issue。

## 14. 横向工作流

### 14.1 需求共创

`ACCEPTED-NOT-IMPLEMENTED` R0 起即可用文档或最小原型验证自然语言需求入口，但正式平台实现须等合同冻结。每个需求保持原始文字与追加事件；AI 只预处理。只有路线图版本签发后，交付负责人才能创建或关联 GitHub Issue。

### 14.2 共建地图

`ACCEPTED-NOT-IMPLEMENTED` R5 前只需最小只读投影：当前发行版本、三条工作流、限制、Bench 结果、下一门和需求回告。完整指标与战略组合在 R7 后依据真实样本深化。指挥中心保持后置。

### 14.3 指标注册表

R3 定义 Interface，R5 才开始积累技术验收事实，R7 才允许报告业务价值。每个指标要求定义版本、时间窗、样本量、事实源和公式；Token 不是贡献度，无价格表不估成本，无人工基线不估节时。

### 14.4 治理与运行

治理中心随 K1～K8 逐步形成当前部署域 Workspace 内的角色化视图；外网是飞书研发空间，内网是自托管 `FLAiWorkspace`。普通用户不需要先进入后台才能工作。任何治理操作都通过同一 policy Seam 和追加审计，不在 UI 内复制权限判断。

### 14.5 分域日常中枢与离线交换

该横向工作流不重排 R0～R8，也不授权实现。F 轴只适用于外网研发飞书；A 轴适用于离线交换与内网自托管环境，两者不得互相替代：

| 阶段 | 最小范围 | 退出门 |
|---|---|---|
| F0 外网合同冻结 | 飞书研发域的 Source Ownership、ActorBinding、typed intent、classification、SecretRef 与对账 | 绑定精确 digest 的外网研发评审；不得声明内网准入 |
| F1 外网只读投影 | GitHub、外网研发工作项与合成/脱敏证据进入研发工作收件箱 | ACL、freshness、source gap、脱敏、对账与漂移恢复 |
| F2 低风险协作意图 | 提需求、补证据、评论、关注、接收确认 | channel attestation、ActorBinding、typed intent、幂等与真实回告 |
| F3 外网高影响研发治理 | 外网路线图、代码评审与 release request | prepare/commit、step-up、职责分离、exact digest 与 owner receipt；不能定向内网 owner |
| F4 外网发行准备 | 从 exact merged SHA 构造候选 Bundle | 外网测试、SBOM、签名与 release witness；不等于内网接受 |
| F5 外网旧协作退役 | 历史 TeamLedger/Bitable 分类迁移，关闭重复外网研发入口 | 双写为零、对账通过、回滚演练与用户验收 |
| A0 AirGap 合同冻结 | Exchange Interface、对象、失败码、七域职责与内网 Workspace 边界 | 新 frozen SHA + 七域具名评审入口，当前批准范围止于此 |
| A1～A5 | 纯夹具、供应链、断网安装、恢复回滚、受控内网试点 | 逐段另行授权；详见设计 18 |

当前只允许外网 F0 与 AirGap A0 设计评审。F1～F5、A1～A5 的 Schema、权限、真实外部写入、Secret Adapter、内部 Registry 与生产配置均须逐片授权。

## 15. 依赖与 Stop-if

出现以下任一可检测条件，当前阶段停止，不扩大范围：

1. 权威事实在两个 Module 中可被独立写入，或任一 Runtime/Sandbox/Tool Adapter 能绕过 ExecutionTicket 与控制内核；
2. 缺少对象级授权、Sandbox 强杀、外联 default-deny 或审计证据，却计划接触真实敏感数据；
3. 任一不可抵消 Bench 门为 failed、invalid、skipped、unknown 或证据不可解析；
4. Delivery Bundle 不能绑定精确输入/产物/策略，或真人授权不能单次 CAS 消费；
5. 任何工作流需要模型静默补造组织事实、工程边界条件、责任人或期限才能完成；
6. 当前发行物无法从干净基线重建，或验证记录与发行摘要不匹配；
7. Phase 0A 试点人群超过 8 人、数据超出批准清单，或 Phase 0B 未满足真实工作流门；
8. 路线图状态、指标或能力绿色只能靠人工编辑而无法反查事实；
9. 安全/领域评审缺失或为 false，仍试图以管理员身份、热度或领导关注绕过；
10. 用户体验再次退化为复杂表单、逐动作审批或默认管理后台，且原型阻断问题未关闭。
11. 任一协作 Surface 出现可独立改写代码、FLAi、Knowledge、Audit 或 Secret owner 的第二事实路径。
12. 当前域 Secret Owner 不可用时需要回退 `.env`、硬编码、宿主全局凭据或另一网络域凭据才能继续。
13. 当前域 Workspace 不可用会阻断 kill/revoke/isolate/credential invalidation，或密封通道可用于正常签发、发布、合并代码。
14. 内网运行需要飞书、GitHub.com、外网模型、公共软件源、外网 DNS 或外网 Secret 才能启动、观察、审计、恢复或治理。
15. 入网或出网离线包缺签名、摘要、classification、custody、双人复核或可验证 receipt，仍被导入或外发。

## 16. 路线图版本与签发

当前路线图的 Stage B 产品与合同语义已在设计会话中冻结，Stage C 已选择“A 首页 → C 执行态”的收敛方向；所有目标能力的实现状态仍为 `ACCEPTED-NOT-IMPLEMENTED`。这不是完整 Stage C 验收、正式排期承诺、组织签发、Stage D 开发授权、试点或部署授权。正式共建地图版本必须记录：

- `roadmap_version` 与内容摘要；
- 签发人、签发时间、职责作用域；
- 来源需求与权威指令引用；
- 适用领域/安全评审；
- 每个节点的目标发行物、验收与证据类型；
- 变更理由、延期/不采纳理由和上一版本关系。

路线图负责人有权签发优先顺序，但无权豁免安全门、伪造领域结论、让 AI 代签或用代码合并宣布需求解决。

## 17. ADR 追踪

| 路线范围 | ADR |
|---|---|
| 控制内核、ExecutionBroker 与三类执行 Port | ADR-0049 |
| 连续会话与末端交付 | ADR-0050 |
| Phase 0A/0B | ADR-0051 |
| 工作台先行、治理角色化、指挥中心后置 | ADR-0052 |
| 黄金工作流与薄切片 | ADR-0053～0056 |
| 权威知识 | ADR-0057 |
| FLAi Bench | ADR-0058 |
| 共建地图与指标 | ADR-0059 |
| 需求闭环与路线图签发 | ADR-0060～0061 |
| 外网飞书研发协作中枢 | ADR-0062 |
| 外网开发、AirGap Exchange 与内网自托管 Workspace | ADR-0063 |

---

*V0.2 路线图读模型 · 2026-07-23 · 所有推进由证据门和具名签发驱动*

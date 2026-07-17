# ADR-0030：专家身份轴与密级/依据契约（agent.yaml 三可选 block）

- 状态：Accepted（批七，2026-07-17）
- 关联：docs/design/AGENT-TEAM-B7-DESIGN.md（设计契约）· ADR-0025（运行中密级遮蔽）· ADR-0029（知识回源指纹）· docs/02_Agent_Package_Standard.md
- 源料：内网《AI平台运作策划》（XMind）与航空场景对谈（语音转写）——owner 提供的部门 AI 平台策划，专家团队垂类清单与诚实/密级/依据底线均从中直译。

## 决策

`contracts/agent.schema.json` 新增三个**可选**顶层 block（顶层 additionalProperties=false 纪律不变——扩展先改契约并记本 ADR）：

### 1. `expertise` 专长身份轴

- `domain`（枚举 policy_qa | standards_qa | fault_history | sys_calc | cfd_sim | test_data | design_opt | generic）：业务垂类域。**与 category 正交**——category 是 AI 适配类型轴（任务书 §12.1 四型），domain 是业务身份轴（策划一/二/三阶段工具清单）；一个 knowledge_qa 型包可以是 standards_qa 域专家。
- `specialty`：≤80 字一句话专长，门户与方案卡主展示位。
- `usefulness_level`（L1/L2/L3）：有用性承诺阶梯（源料原话）：L1 帮我省事（比我快）/ L2 比我聪明（告诉我别人怎么做）/ L3 带我做（替我执行且消化进流程）。**装载期不变量：L3 且 mode=job ⟹ requires_human_review 必须 true**，否则拒载——带我做级产物没有免签通道（人是唯一签发者）。
- `charter`：第一人称开场章程（「我会基于规范条款与已有机型实例回答；超出范围我会明说」）——与 limitations 成对，把「不会就说不会」从 prompt 祈祷升格为契约字段。运行时作为任务首条旁白事件写入。**防漂移纪律**：charter 必须随 workflow 能力变更同步修订并记 changelog；每个垂类包 eval_cases 必含 ≥1 超范围拒答 case（charter 不漂移的唯一机器可判防线）。

### 2. `evidence_policy` 依据纪律轴

- `required=true` ⟹ 包内 output_schema.json 顶层 properties 必含 `findings` 定义（装载期读盘 spot-check，缺失拒载）——「每个推荐必须附带依据和置信度」（策划方法论）的契约化；无处兑现的承诺=假绿温床。
- `kinds`：允许引用的依据类型白名单（default-deny）。
- findings 输出惯例（详 docs/02 增补节）：每条 finding = claim + evidence[]（kind/source_ref/quote/resolved）+ confidence（level: high|medium|low + basis 文字说明）。**`resolved=true` 只能由后端知识回源指纹校验置位（ADR-0029 血统），前端绝不从 LLM 自报推断**；未核依据全链 amber。LLM 自报置信度与任何绿色在契约层切断——假绿死罪的具体化。
- `refusals` 非空 = 正常 completed（走人签），不是 failed——诚实拒答是履约。

### 3. `clearance` 密级准入轴

- `max_data_classification`（public/internal/sensitive）：本 Agent 可处理材料的密级上限。
- **缺省语义 = internal（fail-closed 取最严的向后兼容解释）**：13 个存量包零改动即默认最严约束。
- **时点语义**：创建任务时点由密级 gate 判定（`max(输入文件密级) ≤ 上限` 判定式必须 `is True`，四路复用：create_task / tasks:batch / 手建路径 / 未来 teams summon）；运行中材料密级变化仍归既有 classification gate 遮蔽（ADR-0025 不动）。gate 拒绝用中性文案（策略拒绝非报警红）。
- 源料红线：「论坛泄薪一次越权全盘丧失信任」——任何创建路径绕过 gate = 红线事故。

## 解释条款

- **schema_version 不强制升**：包未消费新字段时不强制升 schema_version；三 block 均 optional，存量包合法。
- **运营口径红线**：「查询 10-15 分钟→30 秒」及一切效率倍数属运营宣传口径，**绝不写入 agent description/charter/UI 承诺**——采纳率与效率数据由运营侧实测自证，产品文案只承诺「条款溯源、双依据、超范围明说」。
- teams 团队模板实体（DDL 已 spec 于设计契约 §2.6）后移批八——封板期不扩第二个 fail-closed gate 与新 API 面。

## 后果

- 前端可从 /api/agents 投影（expertise + clearance.max_data_classification，additive）渲染专长牌/密级 pill/章程口播。
- 垂类专家从策划直译落包：一阶段 policy_qa / standards_qa / fault_history（批七），二阶段 sys_calc / cfd_assistant / test_data，三阶段 design_opt（maturity 阶梯承载能力路线，不另立新包）。
- 仓内垂类包语料全合成（EAR/内网红线），本批证明契约与协作结构，不证明检索质量——对外表述勿越界。

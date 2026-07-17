# FLAi-OS 批七设计契约 · 专家团队语义层先行，协作加载 UI 只做忠实投影

> 生成：批七 ultracode 设计工作流（10 agents：3 理解 / 3 设计角 / 3 评委 / 1 合成；真源料 v2 轮）。
> 状态：DESIGN-FINAL，待 owner 裁决两项（见 §五/§六 N4）后开工。


> **合成谱系**：骨架 = 评审团 2/3 最优「注册表语义优先角」方案；嫁接被评委点名的落选方案优点：
> ①（方案二·R7）改 sa-row 必同批重录批五 craft 视觉基线并重证 tamper 咬合，防守门自身假绿；
> ②（方案二·R5+e2e②）诚实灯 oracle 显式 tamper 化 + 接力翻转「首次观察事件」触发 + 重播抑制探针；
> ③（方案一）「查询 10-15 分钟→30 秒」钉死为运营宣传口径，绝不入 agent 文案 / UI 承诺；
> ④（方案一·risks-8）charter/limitations 随能力变更同步修订入 changelog 纪律，eval_cases 超范围拒答 case 为机器可判防线；
> ⑤（方案二）cross_model_matches 结构化字段并入 fault_history_agent 输出契约；
> ⑥（方案一）fault_history 三阶段能力路线显式映射 maturity L0→L1→L2 晋升阶梯；
> ⑦（方案二）S 式切口独立回退排布；.sa-squad-line 编队总览行 + 收束态假绿探针；
> ⑧（评审团三）teams 实体后移独立批；batch 前端全量切换列 owner 裁决项。

---

## 0. 硬约束（原样继承，全文不变量）

1. **信任色锁五槽**：clay=正在发生（唯一活性色）· amber=未核/待你签发 · teal=人已签发 · 玫红=真失败（只染动词）· **绿=仅 REAL 核验**。completed 一律中性墨。
2. **诚实地板**：零假进度条、零插值、零人工延迟；秒表=1s 离散文本替换零动画；数字骤变不做平滑假渐进；没干活的行不给活着信号。
3. **人是唯一签发者**：waiting_review 必经人签；AI 自报置信度绝不构成放行依据。
4. **密级 fail-closed**：任一创建路径越过密级 gate = 红线事故（源料「论坛泄薪一次越权全盘丧失信任」）；gate 判定一律 `is True` / `is False`。
5. **内网/EAR**：垂类包 demo 语料全合成，挂既有 mock「真实性未核」徽；真实规章/规范/排故库内容绝不入仓。
6. **假绿是唯一死罪**：声明 ≤ 证据等级；不可验证残差显式标注。

---

## 一、多 agent 协作加载编排（组件 · 动效 · 时序 · 文案）

### 1.1 总纲

UI 上一切「专家团队协作感」必须是注册表字段与任务状态机的**忠实投影**，前端不虚构身份、不虚构进度。不新造动效语言：全部复用既有 token（`flai-work-pulse` / `sa-shimmer` / `fx-ink-in` / `fx-rise` / `fx-stagger`（App.vue:642-651）/ `dock-pulse-echo`（StatusDock.vue:5,181,240，**复制不提升作用域**））。信息结构 = 实机拉片 D2-5 三级下钻：**L1 编队总览行 → L2 成员生命周期行/分组 → L3 既有 TaskDetail 独立转录**。不画 DAG 图、泳道、甘特。

数据基础：既有轮询（running 族 2s / waiting_review 8s / 终态停）+ 后端 depends_on/resolver 全链（repos.py:57-141 已落列、jobs runner 已 fail-closed）——**前端首次接通，后端零新状态**。成员级「waiting_upstream」是**纯前端派生态**（status=created 且 depends_on 非空），任务 status 是唯一真值，事件只做旁白。

### 1.2 组件清单

| 组件 | 性质 | 位置 |
|---|---|---|
| `.sa-squad-line` 编队总览行 | 一个 div，非组件（嫁接方案二） | GuidePage 方案卡 sa-row 列表顶部（模板 line 137 前） |
| sa-row 状态语法补全 | 改既有行，四态→六态 | GuidePage.vue 模板 137 区 + 样式 1684-1754 区 |
| WorkbenchSession 三组 roster | 改既有 roster（82-100 区） | 进行中展开 / 等待接力单行 / 已完成收纳 |
| `EvidenceList.vue` | **唯一新组件** | 签发卡上方（TaskDetail）+ DeliveryCard 依据区共用 |
| 接力血缘行 | 一行深链 | TaskDetail 任务上下文区（retry_of 同区） |
| StatusCenter 灰注 | 一条映射 | 运行中组行尾「(等待接力)」 |

### 1.3 时序编排（T0-T6，逐拍）

**T0 召集拍**：用户点「按方案召集」→ `POST /api/tasks/batch`（见 §3-B6；前端切换时点见 §5）。按钮 0.7s send-spin，文案「正在召集专家团队…」。全有全无：失败整组不入场，逐项失败清单玫红（真失败才红）。
**T1 入场拍**（batch 返回同帧）：sa-row 组 `fx-stagger` 0.03s 错峰入场（排版错峰≠时间造假，语义时间戳显真值）。

- 无依赖成员：clay 灯 `is-pulsing`（GuidePage.vue:143,1801）+ 现在时「正在准备…」+ 秒表锚 started_at。
- **有依赖成员（waiting_upstream 态，新）**：**空心灯（1px ink 描边圆，绝无 `is-pulsing`）**+ 灰字「等待〈{上游人话名}〉的产物 · 就绪后自动接力」（上游名经 agentNames 解析）+ **无秒表**（未开工不计时）。
- 每行 name 旁：domain 徽（domain 色轴，categoryColor 退居治理弹窗）+ 密级 pill（「内部」灰描边 /「敏感」amber 描边）。

**T2 首行口播拍**：任务首个 agent_log 若含 charter（运行时把 `expertise.charter` 作为开场事件写入），stageline 首条渲第一人称章程：「我会基于规范条款与已有机型实例回答；超出范围我会明说。」随后被常规 stage 旁白替换。
**T3 运行拍**：既有语法不变——stageline `sa-shimmer` 2.4s 灰阶扫光（每行**唯一**动效）+ 右槽等待三件套灰括号「(1m 12s · 8 条事件 · 中止)」；≥30s 无新事件追加「仍在处理，已 {elapsed}。可在详情页中止。」
**T4 接力拍**：**触发判据（嫁接方案二 R5，实现级钉死）**——以「**本 channel 首次观察到 `dependency_resolved` 事件**」触发一次性翻转，带重播抑制（组件内 Set 记已播 task_id）；**灯的翻转只认 status**（status 离开 created 才由空心→clay），事件先到 status 未翻的 2-5s 错拍窗内只更新旁白不翻灯。翻转表现：该行 `fx-ink-in` 重播一次（fresh 门控复用）+ 文案「前序产物已就绪，接力开始」+ 秒表从 0 起跳 + 灯播 2 轮 `.sa-relay-echo`（GuidePage css 内**复制** dock-pulse-echo keyframes，不动 StatusDock）后自停。**没有连线飞线**。上游 failed → 下游行兜底文案「前序失败，接力已暂停 · 详情→」（中性灰，任务实际被 resolver 置 cancelled 时同帧翻「已取消（上游未交付）」）。
**T5 落定拍**（同帧多处解锁）：行翻过去式「已完成 · 用时 2m 08s」中性墨 ✓（**绝不绿**），产物锚点行同帧长出；**依据摘要 chip 行**（新）：「依据 3 条（2 已核验 · 1 未核）· 置信度 中（模型自评）」——含未核则整 chip amber 底纹；点击展开 EvidenceList。waiting_review 成员 amber「待你签发」pill 常驻。
**T6 拒答拍**：输出含 refusals 的 completed 成员，行尾 amber 行「已如实说明：N 项超出能力范围 →」（点开见 reason +「一般使用 X，当前平台未接入」）。**拒答用 amber 不用红**——诚实拒答是产品在履约，不是失败。

### 1.4 `.sa-squad-line` 编队总览行（L1，嫁接方案二）

- 文案：「{N} 位专家协作 · {a} 运行中 · {b} 等待接力 · {c} 待你签发 · {d} 已完成」——零计数段省略；数字 tabular-nums 纯文本替换零动画；a>0 行首一枚 work-pulse-dot（clay），a=0 无点；c>0 段染 amber。
- **收束态假绿禁令**：只要 c>0（待签发）或存在非终态成员，该行**禁止出现「全部完成/完成」类措辞**；全终态且 c=0 才渲「协作已收束 · 用时 {max duration}」。此禁令有 tamper 探针（§4-O7）。
- 数据源：纯 computed 聚合既有 per-member 任务快照，抽 `frontend/src/utils/squad.js` 纯函数（~40 行），GuidePage 与 WorkbenchSession hero 共用。

### 1.5 WorkbenchSession 镜像

roster（82-100 区）改三组渲染：①「正在进行 · N」展开卡占面积，组头右侧 work-pulse-dot；②「等待接力 · N」单行收纳（空心灯+灰字）；③「已完成 · N」折叠单行（名字+过去式+用时+依据 chip 缩略），完成瞬间打未读空心环（复用 TaskConsole 未读语法）。hero 进度句（summonedCount 区，line 57）换 squad.js 分组计数句。蓝图块补一行纯文字依赖摘要：「接力顺序：规范问答 → 热载荷计算 → 试验数据分析」（depends_on 拓扑序生成，不画图）。task-chips 状态词映射加「等待接力」条目，该态 chip-lamp 不脉动。

### 1.6 EvidenceList.vue（唯一新组件）

每条依据一行：kind 徽（条款/机型实例/知识文档/计算，单字符 glyph）+ source_ref 粗体墨色 + quote 灰引文（数字证据如「不超过 5 毫米」用行内 code 胶囊）+ 核验态：`resolved=true` → 中性 ✓「已回源核验」；false → **amber「未核」**。密级遮蔽联动 classification_gate：无权限依据行渲「〔敏感内容，按密级隐藏〕」灰块不渲 quote。confidence 固定格式「置信度：中（单源 · 模型自评）」——basis 必显，绝不裸报等级，**任何情况不染绿**。TaskDetail 签发卡上方强制挂载；evidence_policy.required 但零依据 → amber 警示行「本次输出未提供依据，请谨慎签发」（**不阻塞人签**——人是唯一签发者）。

### 1.7 文案总表（时态即状态）

- 现在时+clay：正在准备… / 正在检索历史故障… / 正在核对规范条款…
- 等待态灰：等待〈X〉的产物 · 就绪后自动接力 / 前序失败，接力已暂停
- 过去式+中性：已完成 · 用时 Xm Xs / 检索了 412 份排故记录
- amber：待你签发 / 依据未核 / 已如实说明超出范围 / 未提供依据请谨慎签发
- 玫红（仅真失败）：失败 · 查看失败详情 →

全部动效 prefers-reduced-motion 静态降级（沿既有覆盖，含 `.sa-relay-echo` 与空心灯）；每运行行唯一活性信号（shimmer 与灯脉动互斥挂载）。

---

## 二、agent 专家团队注册表

### 2.1 agent.yaml 契约扩展（contracts/agent.schema.json，须 ADR）

顶层 `additionalProperties:false`（schema.json:7，description 明定「扩展必须先改契约并记 ADR」）。新增三个**可选** block，13 个存量包零改动通过校验：

```yaml
expertise:                    # 专长身份轴（与 category 类型轴、maturity 治理轴正交）
  domain: cfd_sim             # 枚举: policy_qa|standards_qa|fault_history|sys_calc|cfd_sim|test_data|design_opt|generic
  specialty: "Fluent/CCM/CFX 三软件的网格、参数与边界条件问答"   # ≤80 字
  usefulness_level: L1        # L1 帮我省事 | L2 比我聪明 | L3 带我做（承诺声明，见 2.3 校验）
  charter: "我会基于规范条款与已有机型实例回答；超出三种软件范围我会明说并告知一般用什么软件。"
                              # 第一人称开场章程，与 limitations 成对=「不会就说不会」契约化
evidence_policy:
  required: true              # true ⟹ output_schema 必含 findings 定义（装载期校验）
  kinds: [regulation_clause, type_case, knowledge_doc, calculation]
clearance:
  max_data_classification: internal   # public|internal|sensitive；缺省=internal（fail-closed 取最严）
```

语义钉死（写入 ADR，编号取 docs/adr/ 现最高序号+1，现为 ADR-0029 → **ADR-0030「专家身份轴与密级/依据契约」**）：domain≠category（业务垂类轴 vs AI 适配轴）；charter/limitations 成对；clearance 缺省最严；「包未消费新字段不强制升 schema_version」的解释条款；**运营口径红线**（见 2.7）。

### 2.2 输出契约惯例（docs/02_Agent_Package_Standard.md 增补节，不动 task.schema.json）

evidence_policy.required=true 的 agent，其 output_schema.json 必含：

```json
{ "findings": [{ "claim": "…",
    "evidence": [{ "kind": "regulation_clause|type_case|knowledge_doc|calculation",
                   "source_ref": "CCAR-25.853(a) / ARJ21 排故记录#F-2019-0312",
                   "quote": "…不超过5毫米…",
                   "resolved": false }],
    "confidence": { "level": "high|medium|low", "basis": "双源(条款+机型实例)|单源|推断" } }],
  "refusals": [{ "question": "…", "reason": "仅支持 Fluent/CCM/CFX，STAR-CCM+ 未集成",
                 "suggestion": "一般使用 STAR-CCM+，当前平台未接入" }] }
```

三条不变量：
1. **`resolved=true` 只能由后端知识回源指纹校验置位**（复用既有回源机制，ADR-0029 血统），前端绝不从 LLM 自报推断；未核依据全链 amber。自报 high 置信度与任何绿意在契约层切断——假绿死罪的具体化。
2. **refusals 非空 = 正常完成**（completed 走人签），不是 failed。
3. **fault_history_agent 专属**（嫁接方案二）：findings 外加顶层 `cross_model_matches: [{model, fault_ref, similarity_basis, disposition_summary}]`——「型号间经验打通」这条最真痛点的结构化落点；similarity_basis 必非空（引用检索命中特征），「相似≠适用」提示由 UI 固定渲染。

### 2.3 装载期校验（registry 扫描侧，fail-closed 拒载）

`backend/app/runtime/registry.py` `_load_one` 尾部补两条（与既有跨字段校验同址同风格）：
- ① `usefulness_level == "L3"` 且 mode=job ⟹ `workflow.requires_human_review is True`，否则拒载——「带我做」级承诺在装载期就被人在回路不变量咬住。
- ② `evidence_policy.required is True` ⟹ 包内 output_schema.json 顶层含 findings 定义（读盘 spot-check），否则拒载。

### 2.4 密级 gate（单一后端函数，四路复用）

新 `backend/app/api/classification_gate.py::check_agent_clearance(agent, input_file_rows) -> bool`（并入既有 cgate 模块，tasks.py:15 已 import）：判定 `max(file.data_classification) ≤ agent.clearance.max_data_classification` 写 `is True`，不满足 → 400 + 中性文案「该专家的密级上限为{X}，无法处理{Y}级材料」（策略拒绝非报警红）。**四路复用**：`create_task`（tasks.py:177 起）、`POST /api/tasks/batch`（新）、TaskCreate 手建路径（同走 create_task 即覆盖，e2e 验证防旁路）、未来 teams summon（批八）。时点语义写入 ADR-0030：gate 只管创建时点准入；运行中文件密级变化仍归既有 classification_gate 遮蔽（ADR-0025 不动）。

### 2.5 垂类专家清单（通用层 = 现有 13 包零改动；新增按阶段）

| 批次 | id | domain | usefulness | mode | 一句话 | 人在回路点 / 关键 limitations |
|---|---|---|---|---|---|---|
| 一阶段(本批) | policy_qa_agent | policy_qa | L1 | interactive | 职能规章制度问答（质量/保密/人事/流程/负责人），举例+溯源+方案三段 | 不答未收录制度；不替代正式审批 |
| 一阶段(本批) | standards_qa_agent | standards_qa | L1 | interactive | 专业规范/标准条款问答，条款号溯源，双依据(条款+机型实例) | 只覆盖已入库规范；条款冲突不裁决只并列 |
| 一阶段(本批) | fault_history_agent | fault_history | L2 | job(review-gated) | 故障/排故/技术通报结构化检索，新问题推荐历史相似故障原因+处置，**跨型号打通**(cross_model_matches) | 相似≠适用；处置建议必经人签 |
| 二阶段 | sys_calc_agent | sys_calc | L1 | job(review-gated) | 管路压降/热载荷/燃油测量/灭火剂计算辅助（profile 尽量确定性工具，可入依赖链） | 输入超工况范围拒算 |
| 二阶段 | cfd_assistant_agent | cfd_sim | L1→L2 | interactive | CFD 问答（网格/参数/边界条件），只支持 Fluent/CCM/CFX，超范围明说+告知一般用什么 | charter 即诚实边界样板；不执行求解（求解走既有 cfd_solve 链） |
| 二阶段 | test_data_agent | test_data | L2 | job(review-gated) | 试验/仿真数据异常识别+初步结论草稿 | 结论是草稿；异常判据必附计算依据 |
| 三阶段 | design_opt_agent | design_opt | L3 | job(强制 review-gated) | AI 设计参数搜索推荐 | L3⟹装载期强制人签（2.3-①） |

**能力路线 ↔ maturity 映射**（嫁接方案一）：fault_history 三阶段（只能搜→相关性处理→出有价值结论）显式映射 maturity **L0→L1→L2** 晋升阶梯，用既有治理弹窗评测门推进；cfd_assistant 三阶段（问答→流程辅助→全自动）同法承载，不另立新包。写入两包 README。

### 2.6 teams 实体（DDL 级 spec，**整体后移批八**，本批不实施）

```sql
CREATE TABLE teams (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, goal_template TEXT,
  owner_user TEXT NOT NULL, created_from_conversation_id TEXT, created_at TEXT NOT NULL);
CREATE TABLE team_members (
  team_id TEXT NOT NULL REFERENCES teams(id), agent_id TEXT NOT NULL,
  agent_version_at_save TEXT NOT NULL, role TEXT, seq INTEGER NOT NULL,
  after_json TEXT,          -- 同团队内前序 agent_id 列表
  PRIMARY KEY (team_id, seq));
```

summon 时对账 fail-closed（成员 disabled/下线/大版本 → 拒发整单提示，绝不静默跳过）；团队密级 = min(成员 clearance)。**后移理由**：第二个 fail-closed 新 gate + 三端点扩 API 面，封板期 Gate2 尚待 owner 终裁，时机不利（评审团三意见采纳）。

### 2.7 运营口径红线（嫁接方案一，写入 ADR-0030 + standards_qa README）

「查询 10-15 分钟→30 秒」及一切效率倍数属**运营宣传口径**，绝不写入 agent description/charter/UI 承诺——采纳率与效率提升数据由运营侧实测后自证，产品文案只承诺「条款溯源、双依据、超范围明说」。

### 2.8 charter 防漂移纪律（嫁接方案一 risks-8）

写入 docs/02 包规范：**「charter 与 limitations/refusal 边界必须随 workflow 能力变更同步修订，changelog 逐条留痕」**；每个垂类包 eval_cases **必含 ≥1 超范围拒答 case + ≥1 双依据 case**——拒答 case 是 charter 不漂移的唯一机器可判防线。

---

## 三、外科改动清单（file → 改动，含批六合并代码衔接点；S 式独立回退切口）

绝对路径根 = `/Users/Zhuanz/projects/aircraft-comac/flai-os-inline-wt`。

**S1 契约与注册表（先行，其余皆其投影）**
1. `contracts/agent.schema.json` — properties 新增可选 expertise/evidence_policy/clearance 三 block（required 不动；顶层 additionalProperties:false 保持）。
2. `docs/adr/ADR-0030-…md` — 三 block 语义/缺省最严/正交性/resolved 置位权/gate 时点/运营口径红线/schema_version 解释条款。
3. `docs/02_Agent_Package_Standard.md` — §依据输出契约（2.2 全文）+ charter 防漂移纪律（2.8）。
4. `backend/app/runtime/registry.py` — `_load_one` 尾部两条 fail-closed 校验（2.3）。
5. `backend/app/api/agents.py` — `_project`（line 28 起）增投 expertise、clearance.max_data_classification（列表+详情，additive）。

**S2 调度语义（后端）**
6. `backend/app/api/tasks.py` — 新 `POST /api/tasks/batch`：入参 `[{agent_id, params, input_file_ids, after(同批下标)}]`，同事务建 N 行 + after→depends_on 映射（复用既有 ≤32/同 conversation/origin=user 校验；repos.create_task 已带 depends_on 形参，repos.py:81；「depends_on 非空不自动入队」短路既有，repos.py:89），全有全无回滚 + 逐项错误清单。密级 gate 在 batch 与 create_task（line 177 起）同函数落地（2.4）。
7. `agents/guide_agent/prompt.md` + `workflow.py` — 方案 agents[] 增可选 `after`；`_validate_orchestrate`（workflow.py:221-279）补校验：after 仅可引用本 plan 更早条目（按构造无环，零环检测代码），非法引用**剥离该字段降级为无依赖**并入 dropped 审计（复用 _MAX_DROPPED=20 界，workflow.py:45）；prompt 明示「仅当下游确需上游产物才声明 after」。无 after = 现状扁平，向后兼容。
8. 新 `agents/policy_qa_agent/`、`agents/standards_qa_agent/`、`agents/fault_history_agent/` 三包 — 完整包件（agent.yaml/prompt.md/workflow.py/schemas/README/changelog/eval_cases 合成数据遵 EAR），charter/limitations/evidence_policy 全填；fault_history 带 cross_model_matches；eval_cases 按 2.8 双必含。

**S3 前端投影（依赖 S1/S2 API，本身按视图独立可回退）**
9. `frontend/src/utils/squad.js`（新，~40 行纯函数）+ `frontend/src/stores/agentNames.js` — 投影扩为 id→{name, domain, clearance, charter?}（保持懒加载与回退）。
10. `frontend/src/views/GuidePage.vue` — ①模板 line 137 前插 `.sa-squad-line`；②sa-row（模板 137 区+样式 1684-1754 区）补 waiting_upstream 态/T4 翻转/T5 依据 chip/T6 拒答行/domain+密级 pill；③`.sa-relay-echo` keyframes 复制；④`openPlan`（line 1021 起）改调 batch 携 after（切换时点见 §5）。
11. `frontend/src/views/WorkbenchSession.vue` — roster（82-100 区）三组分组；hero（line 57 区）分组计数句；蓝图依赖拓扑一句话；task-chips「等待接力」。
12. 新 `frontend/src/components/EvidenceList.vue` + `frontend/src/views/TaskDetail.vue` — 签发卡上方挂载 + 零依据 amber 警示行 + 接力血缘行「接力自：〈…〉→」（depends_on 已在 GET 投影，repos.py:59，后端零改）。
13. `frontend/src/components/DeliveryCard.vue` — citations/confidence/refusals 条件块（字段缺省渲染无，全存量 agent 向后兼容）。
14. `frontend/src/views/AgentPortal.vue` — meta 行 specialty 副文 + domain/密级/L1-L3 pill（治理弹窗不动）。
15. `frontend/src/components/StatusCenter.vue` — 运行中行「(等待接力)」灰注。

**S4 e2e oracle** — 新 `frontend/e2e/batch_g_squad_acceptance.py`（命名循 batch_a…d 惯例）+ **重录 `frontend/e2e/craft_desktop_acceptance.py` 基线**（见 §4），登记入 `scripts/verify_all.sh` e2e 列表（line 70-86 区）。

---

## 四、e2e oracle 设计（craft 式探针 + tamper 候选）

> 施工顺序警告（方案三 risk 自觉，全批遵守）：**探针先于对应 UI/后端落地会假红**——每条探针与其被测切口同 commit 或紧随其后合入，绝不提前挂账。

| # | 探针 | tamper 候选（必咬证明） |
|---|---|---|
| O1 | batch 含 after → DB depends_on 正确落列 + 下游滞留 created → 上游 completed 后 resolver 接力 → UI 行「等待接力」翻 clay（**真跑全链非 mock**，resolver 前端流量首验） | 断开 after→depends_on 映射 → 探针必红 |
| O2 | **诚实灯**：waiting_upstream 行断言**无** `is-pulsing` 类 + 无秒表 DOM | **强制加 is-pulsing 类必咬**（嫁接方案二 e2e②） |
| O3 | **重播抑制**：同 channel 重复投递 dependency_resolved → `.sa-relay-echo` 只播一次；事件缺席（状态窗跳过）→ 翻转仍由 status 兜底发生 | 移除已播 Set → 重播必咬；反向：改为状态沿触发 → 「永不播」case 必咬 |
| O4 | 密级 gate：sensitive 文件 + internal-clearance agent → 400 + 中性文案；TaskCreate 手建同路 400（防旁路） | **注释掉 gate 判定必咬** |
| O5 | evidence 投影：resolved=false 依据 → 全链 amber「未核」、计算色断言无任何绿 | **confidence 自报 high 强渲绿必咬** |
| O6 | 拒答态：refusals 非空 → status=completed + amber 行，非红非 failed | 强改为 failed 渲染必咬 |
| O7 | **收束假绿**：待签发 c>0 时 `.sa-squad-line` 及 hero 句**不含「完成」类措辞** + amber 段在场 | **强改文案「全部完成」必咬**（嫁接方案一/评审团三） |
| O8 | guide after 幻觉引用 → dropped 审计可见 + plan 仍可开（降级无依赖） | 移除剥离逻辑 → 后端 422 必咬 |
| O9 | 装载期：L3 且无 requires_human_review 的构造包 → registry 拒载；evidence_policy.required 但 output_schema 无 findings → 拒载 | 注释校验必咬 |
| O10 | completed ✓ 计算色断言 = 中性墨非绿 | 强染绿必咬 |
| O11 | reduced-motion：全新增态静态降级快照（空心灯/relay-echo/shimmer） | — |
| O12 | **craft 基线重录**（嫁接方案二 R7）：S3 改 sa-row 渲染必动批五视觉基线——同批重录 craft_desktop_acceptance.py 基线，并让既有 tamper12 探针在**新基线上重新证咬合**（`scripts/tamper_replay.sh`），否则守门自身假绿 | 重录后跑一轮 tamper 全集，未咬项即守门失效上报 |

---

## 五、分期

**本批（批七）实施**：S1（契约+ADR+registry 校验+投影）→ S2（batch 端点+密级 gate+guide after+三垂类包）→ S3（前端投影六视图+EvidenceList）→ S4（O1-O12 + craft 基线重录）。S1+S2 语义完备可先合（纯 API 可验证）；S3/S4 紧随同批。openPlan 切换 batch 随 S3 落地；**若 owner 裁决 batch 端点暂缓**，S3 降级预案 = 保留串行循环 + 上游创建失败时跳过下游 dep 声明并行内如实透出「前序召集失败，已改为独立执行」（方案二 S4 语义，记留痕 §6-N4）。

**留 retro / 批八**：
- teams 实体三件（表+API+summon 对账 fail-closed）+「存为团队模板」入口（2.6）。
- 二阶段垂类包（sys_calc/cfd_assistant/test_data）与三阶段 design_opt——契约与首批三包已证结构，按运营节奏铺。
- `.sa-relay-echo` 与 dock-pulse-echo 双份 keyframes 归并（两处稳定后再议）。
- **运营面四条**（三案共同缺口，评审团二点名，属运营机制非本仓代码，移交 owner）：操作日志审计面（M12/ADR-0023 已有底座，缺运营视图）、分批授权/种子名额、反馈激励换额度、采纳率/止损标准看板。
- SSE/流式通道：明确**非目标**（2s 轮询对 job 型协作足够）。

---

## 六、风险与反采纳留痕

**风险**（带缓解）：
- R1 契约演进触封板边界：additionalProperties:false 下三 block 必须 optional + ADR-0030 同 commit 落地，否则 13 存量包全拒载；不可当普通前端批静默合入，与 R4 P1-2「密级绑定采纳 V0.2」主线对齐后走治理审。
- R2 依据/置信度假绿最高危点：LLM 可整段幻觉条款号。双防线缺一不可——resolved 后端置位权（2.2-①）+ 未核全链 amber；O5 tamper 是本批 oracle 核心咬合点。
- R3 depends_on 前端首用 = resolver 链首吃真实流量：input_binding 产物注入在真 UI 会话下未经实测——O1 真跑全链是 S3 合并前置门；prompt 先只对双 agent 简单链鼓励 after。
- R4 waiting_upstream 派生态错拍闪烁：已钉「灯以 status 为唯一真值、事件只做旁白」（1.3-T4）；实现若图省事用事件翻灯即违约，O3 反向 case 咬。
- R5 batch 全有全无与旧串行逐个透错的体感差异：逐项错误清单必须清晰可读，否则用户体感「点了没反应」——S3 验收含失败清单可读性走查。
- R6 垂类包知识底座仓内只能合成：本批证明**契约与协作结构**，不证明检索质量，对外表述勿越界；mock「真实性未核」徽全程在场。
- R7 charter 静态字段漂移成假承诺：2.8 changelog 纪律 + eval_cases 拒答 case 双防线；治理审查时抽查 charter 与 workflow 一致性。
- R8 guide after 质量不可控（提不出/错序/过度串行化）：降级语义内置（无 after=扁平、非法=剥离降级），e2e 观察 dropped 率入 retro。

**反采纳留痕**（评审可追溯）：
- N1 不采纳方案一「四幕戏」新组件族（TeamStage/AgentEntranceRow/TeamSynthesisCard/TeamPulseBadge + stages[] 结构化编排）：与外科纪律张力最大、押注 LLM 输出 stages 最不可控、正撞源料「业务导向避免炫技」警告、且其行号锚点未经实读（评审团三实证）。协作感由既有 sa-row 语法补全 + 忠实投影达成。
- N2 不采纳 capability_tier/usefulness 只降 README 文案（方案二）：采信更硬一档——usefulness_level 进 schema 且 L3 装载期强制人签（2.3），正交性由 ADR 钉死而非注释声明。
- N3 不采纳「10-15 分钟→30 秒」入任何 agent 文案/UI（方案二、方案三清单表均越界）：钉为运营口径（2.7）。
- N4 batch 端点保留本批后端（2/3 评审团选中方案三含此项；评审团三「后移」意见部分采纳为：**前端切换时点与降级预案挂账 owner 裁决**，见 §5）。
- N5 teams 实体后移批八（方案三自建议+评审团三）：封板期不扩第二 fail-closed gate 与三端点 API 面。
- N6 不画 DAG 图/泳道/甘特/连线飞线：两家实机拉片一致结论，依赖关系用计数徽标+血缘文本行+拓扑一句话表达。
- N7 `.sa-relay-echo` 复制而非提升 dock-pulse-echo 作用域：用 DRY 换 StatusDock 零回归（方案二 R8 取舍原样采纳），归并入 retro 队列。
- N8 SSE 流式通道不做：轮询粒度诚实呈现（等待三件套+慢速行）优于引入新通道的回归面。

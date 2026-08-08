# map #46：非航空通用任务能力边界——17 包现状、覆盖缺口与接法候选（票 #58）

> 基线：`origin/main` @ `a32b36e48c83`（含 PR #68）。
> 性质：research 盘点（plan, don't do）——本报告不修改 Agent、Tool、路由、契约或 Destination；所有施工方向均是候选，不替 owner 定稿。
> 证据口径：**事实**均来自当前仓库、已接受 ADR 或 GitHub owner 留痕；**估算**统一标为「估算」，用于比较量级，不是排期承诺。
> 关联：[wayfinder map「通用好用面 × 隐藏工程可信内核」（#46）](https://github.com/kogamishinyajerry-ops/flai-os/issues/46) · [task「通用执行样板包（脚本/表格/翻译）」（#53）](https://github.com/kogamishinyajerry-ops/flai-os/issues/53) · [research「非航空通用任务能力边界」（#58）](https://github.com/kogamishinyajerry-ops/flai-os/issues/58) · [research「行话摩擦 × 通用性缺口」批 0 审计（#47）](./MAP46-BATCH0-JARGON-AUDIT.md)。

---

## 零、先给结论

1. **“通用任务接不接”已经不是未决问题。** owner 在 2026-08-05 已裁“接——走既有
   Agent Package 契约与签发闸”（[裁决留痕](https://github.com/kogamishinyajerry-ops/flai-os/issues/46#issuecomment-5190686379)），并已建立 OPEN 施工票
   [#53《通用执行样板包（脚本/表格/翻译）》](https://github.com/kogamishinyajerry-ops/flai-os/issues/53)。
   本票应盘清的是**接受范围、首个黄金任务、是否拆票、脚本只产草稿还是执行、表格是否后置、复核策略**，不能把“接不接”重新伪装成待裁问题。
2. **当前物理上已有 17 个 Agent Package，但仍没有生产可用的非航空通用执行包。**
   票面“16 包”来自 2026-08-05 的旧清单；旧 16 **已经包含** `hello_agent`，当时尚无
   `life_guide_agent`。当前 17 = 旧 16 + 后增的 `life_guide_agent`。若按用途另分，可说
   “16 个非 Golden Sample 包 + 1 个 `hello_agent` Golden Sample”，但其中
   `life_guide_agent` 是教学 demo，不能据此称为生产业务能力。
3. **现有路由内核已经能组合多个 job Agent，不需要先造一套新编排框架。** 新增一个
   非 disabled 的 job 包后，它会进入 Guide 候选面；多个 job 可用现有 `orchestrate`、
   `after` 和原子 batch 承载“通用执行 + 工程执行”。但“通识直答 + 工程任务”或
   “interactive 专家 + job”的混合没有正式合同，不能笼统宣称“混合路由已经完成”。
4. **推荐候选（不是 owner 定稿）是 A1 → A2 的小步序列：**
   - A1：先做一个边界清楚的通用文本/Markdown 草稿 job 包，以“粘贴一段内部非敏感文本
     → 生成带 AI 草稿标识的 Markdown 摘要 → `waiting_review` 人工放行”为黄金任务；
   - A2：再做确定性表格读写/变换工具与对应 job 包；复用既有 `openpyxl`，但不复用
     性能盘专用 Excel 契约冒充通用能力；
   - 脚本仅可作为**未运行、未测试、待人审的源码草稿**另切；任意用户生成代码的执行
     明确排除，直到真实沙箱、安全威胁模型与负向金丝雀另线通过。
5. **#53 现有“脚本/表格/翻译各一起步且同票落地”范围过宽。** 三者分别对应文本生成、
   确定性文件变换、代码执行安全三个风险等级。候选处置是收窄/拆分/替换票体，而不是本
   research 擅自改写或关闭 #53。

---

## 一、包数校正与现有能力盘点

### 1.1 为什么票面是 16，而当前是 17

- 旧静态清单明确写了 16 个包并逐项列出 `hello_agent`（
  `docs/reviews/map46-batch0-jargon-shots/traces/static_copy_inventory.md:140-161`）；
  [批 0 审计](./MAP46-BATCH0-JARGON-AUDIT.md)据此给出“11 航空/工程执行向 +
  2 平台件 + 3 问答向”的 P0-1 结论（`:35-48`）。
- 当前 `agents/*/agent.yaml` 实数为 **17**：**13 job + 4 interactive**；17 个包均声明
  `status: draft`、`maturity: L0`。
- 新增量是 `life_guide_agent`（git 记录 `3a7bb26`、`33bd720`）。它的 manifest 明写
  “主持人不执行工作、不签发、不注册、不晋级”（
  `agents/life_guide_agent/agent.yaml:7-16`）；[ADR-0040](../adr/ADR-0040-life-scenario-demo-charter.md)
  进一步钉死“教学工具，不是生产 Agent；输出是教学投影，不是工程资产”（`:23-36`）。

因此，本报告后续统一使用“**当前物理 17 包**”。“16 包”只保留为票面历史口径，不继续
把旧数字当现状；也不拿教学 demo 充抵通用生产执行缺口。

### 1.2 17 包逐项覆盖矩阵

| Agent Package | mode | 当前真实职责 | 对非航空通用任务的贡献 | 能否完成通用执行任务 |
|---|---|---|---|---|
| `cfd_solve_agent` | job | 发起固定 OpenFOAM CFD 算例 | 无，航空 CFD 专用 | 否 |
| `cfd_evaluate_agent` | job | St/Cd 确定性判据 + 叙事草案 | 无，CFD 结果专用 | 否 |
| `fea_solve_agent` | job | 梁一阶固有频率求解 | 无，结构分析专用 | 否 |
| `fea_evaluate_agent` | job | 梁频率解析解对照 | 无，结构分析专用 | 否 |
| `step_response_solve_agent` | job | 二阶系统阶跃响应求解 | 无，控制工程专用 | 否 |
| `step_response_evaluate_agent` | job | 超调量解析解对照 | 无，控制工程专用 | 否 |
| `control_logic_agent` | job | 控制逻辑结构草案 | 只覆盖控制工程结构，不是通用代码/文档 | 否 |
| `fta_agent` | job | FTA 草案，强制人审 | 可复用“LLM 草案 + 水印 + 人审”的**实现范式**，不能复用其业务能力 | 否 |
| `fault_history_agent` | job | 合成故障史检索 | 有限工程知识域 | 否 |
| `monitor_adapter_gen_agent` | job | 监控 adapter 草案 | 固定仿真监控接入语境 | 否 |
| `performance_disk_agent` | job | 性能盘 mock 批量计算 | 表格链路是专用样板，结果还来自 mock | 否 |
| `knowledge_qa_agent` | job | 锁定 scope 的语料检索归纳 | 只在 `ecm_frr_demo` 白名单内，零命中拒答（`agent.yaml:24-42/61-66`） | 否 |
| `hello_agent` | job | Agent/Tool/Task/Event 闭环 Golden Sample | 平台自验；manifest 明写“无业务含义”，工具为 `mock_echo`（`agent.yaml:7-11/50-53`） | 否 |
| `guide_agent` | interactive | 统一入口、通识直答、自动分流/编排/拒绝 | 已能回答概念、澄清需求和给出 refusal 出口 | **只解释/路由，不执行** |
| `policy_qa_agent` | interactive | 所内制度问答 | 有限制度域，且知识源尚未接入 | 否 |
| `standards_qa_agent` | interactive | 专业标准问答 | 有限标准域，且知识源尚未接入 | 否 |
| `life_guide_agent` | interactive | 生活场景本体论教学 demo | 教学用途；不产生产任务/资产 | 否 |

结论仍与旧审计一致：**包数从 16 增至 17，没有改变“通用执行面为零”这一能力结论。**

### 1.3 7 个注册工具也没有通用执行面

当前 Tool Registry 物理上有 **7 个工具：5 real + 2 mock**。

| Tool | mock | 真实边界 | 能否直接复用为通用能力 |
|---|---:|---|---|
| `cfd_result_read` | false | 固定 CFD 结果读取 | 否 |
| `cfd_solve_launch` | false | 固定 OpenFOAM 求解发起 | 否 |
| `monitor_adapter_recon` | false | 仿真监控目录只读侦察 | 否 |
| `excel_case_parser` | false | 必须有 `case_id/altitude_m/mach/power_kw`，并做固定量纲范围校验（`adapter.py:22-31/78-157`） | 否，契约是性能盘专用 |
| `excel_summary_writer` | false | 固定参数列/输出列顺序，写 `result_summary`（`adapter.py:27-30/41-96`） | 否，契约是性能盘专用 |
| `mock_echo` | true | 平台回显示例 | 否 |
| `performance_disk_mock` | true | 虚构性能盘计算 | 否 |

正面先例是：`excel_summary_writer` 已用“所有字符串强制惰性文本”防 Excel 公式注入（
`tools_impl/excel_summary_writer/adapter.py:10-19/33-38`）；这一安全范式可以复用。负面边界是：
**不能把专用列名去掉就宣布它是通用表格工具**，那会改坏既有稳定契约，也没有覆盖通用变换语义。

---

## 二、非航空通用任务覆盖缺口

### 2.1 能力矩阵

| 用户意图 | 当前能到哪一步 | 当前缺口 | 安全可接方向（候选） |
|---|---|---|---|
| 解释术语、方法、流程概念 | Guide 通识直答；不输出计划块（`agents/guide_agent/prompt.md:22-32/70-77`） | 不是 Task Center job，无任务产物、人工放行或可下载制品 | 维持现状；不要把直答虚报为“走通任务” |
| 摘要、改写、生成 Markdown 初稿 | Guide 可讨论做法，但没有可召集包 | 无注册 job、无版本化 prompt/eval、无任务事件/产物 | A1：有界文本草稿 job，经 Model Gateway，输出 `.md`，强制人审 |
| 翻译一段文本 | 同上 | 无翻译包；质量不能由确定性代码判真 | 可作为 A1 的受控 `task_kind`，或在首个摘要黄金任务后另开 eval；始终标 AI 草稿 |
| 读取 `.txt/.md/.csv/.json/.../.py` 附件 | Guide 只做每文件 16K、总计 24K 的**预览**；计划可把附件绑定给 `params` job，Runtime 核验后通过 `context["files"]` 交给 workflow（`backend/app/runtime/attachments.py:27-41/77-84`；`agents/guide_agent/workflow.py:787-904`；`backend/app/runtime/runtime.py:1430-1489`） | 没有通用 job 定义全量读取语义；`params` 本身没有附件数量/后缀白名单，Guide 预览也不是执行期全量内容 | A1 首片仍用零附件的粘贴文本；后续可在同一 `params` 包内显式限数量、类型、总字节与截断策略，或在确需“恰好一件+后缀白名单”时选 `file_upload` |
| 读取/清洗/重排 `.xlsx` | Guide 只预览活动 sheet 前 30×16；现有工具固定性能盘列 | 没有通用操作合同、资源/路径/公式安全的通用工具 | A2：新建确定性表格工具 + 白名单操作 DSL；复用既有 `openpyxl`，不新增依赖 |
| 读取/生成 `.docx`、`.pdf` | 只列文件名，不解析；源码明标 V0.3 债（`backend/app/runtime/attachments.py:13-15/179-183`） | 无解析器、生成器和安全预算；引入库会撞“零新依赖” | 不进 A1；如 owner 需要，单独裁依赖、解析预算与恶意文件测试 |
| 生成 Python 源码草稿 | `.py` 可被 Guide 当文本预览，但无 job 包 | 无源码产物合同、无“未运行/未测试”水印、无代码特有 eval | 可另切 draft-only job；不调用工具、不声称运行/测试/正确 |
| 执行 Python/shell/任意生成代码 | 无 | 当前无真沙箱、无强制 egress/进程/文件系统隔离 | **明确不接**，直到独立安全轨完成 |
| 通用执行 + 工程执行 | 多 job 计划基础设施已在 | 通用 job 不存在，故通用腿无法进入任务图 | A1 落地后可用现有多 job `orchestrate`；补黄金路由/e2e |
| 通识直答 + 工程执行 | Guide 可能在计划块前写自然语言 | 四姿态没有 formal mixed，直答正文不是可审计的独立执行单元 | 若这是产品必须项，需另扩路由合同；本票不可宣称已支持 |

### 2.2 输入合同不是“任意输入”

Agent 契约的 `input.type` 只有 `params | file_upload | none`（
`contracts/agent.schema.json:87-95`），但三者的真实边界不是“参数或附件二选一”：

- `none` 不接 `inputs`，也不接附件；
- `params` 接结构化 `inputs`，同时可接零个到 API 全局上限 64 个已登记上传件（
  `backend/app/api/tasks.py:83-125`）；创建门逐件校存在性与 `kind=input`，但**没有**按包声明的
  附件数量或后缀约束；
- `file_upload` 的最终执行输入必须且只能有一件，并按包内 `allowed_extensions` 校验。仅当批量
  下游声明由依赖 resolver 注入文件时，创建期可先为零件，Runtime 执行前仍重验恰好一件。

创建与最终执行的约束分别见 `backend/app/api/tasks.py:513-607` 和
`backend/app/runtime/runtime.py:1230-1284`。Guide 还要求当前段每个附件恰好被绑定或忽略一次：
`none` 不得绑定、`file_upload` 恰好绑定一件且后缀匹配；`params` 没有数量分支，因此可绑定多件
（`agents/guide_agent/workflow.py:787-904`）。平台在创建与执行链上分别完成存在性、种类、完整性、
来源和密级 gate；Runtime 随后把最终核验文件记录交给 workflow 的 `context["files"]`（
`backend/app/runtime/runtime.py:1230-1423/1430-1489`）。Guide 的 16K/24K 预览只是规划上下文，
不是 workflow 的全量输入来源。

所以，“大一统通用包”的问题不是现有合同禁止 `params + 多附件`，而是它会把文本、文件、表格
和脚本的解析语义与风险预算塞进同一 workflow。若 A1 后续接附件，包自身必须 fail-closed 地钉死
允许数量、文件类型、逐件/总字节、完整读取或截断策略，以及 `source_text` 与附件同时出现时的
优先级；或者另补平台级声明式门。需要平台原生“恰好一件+后缀白名单”时才应选择
`file_upload`，不是因为 `params` 读不到附件。

另一个不能省略的来源边界是：Guide 投影到 `params.source_text` 的文本不是用户原文的字节级
绑定。若验收要求“逐字翻译/摘要这一份原件”，应绑定已登记上传件，并以 file id、size、sha256
与 classification 钉住来源；这个上传件既可配给 `params`，也可在恰好一件时配给
`file_upload`。workflow 必须从核验后的 `context["files"]` 读取，而不是把 Guide 预览当原件。

**首个黄金任务选择“粘贴文本 → Markdown 摘要”仍最小**：不改内核、不加依赖、不依赖附件
解析。无输入文件时运行时分级派生为 `internal`；有上传件时则由文件记录派生，全部 internal
才是 internal，任一非 internal/未知即 sensitive（`backend/app/runtime/runtime.py:333-349`）。
因此首片只接**内部非敏感粘贴文本**；敏感或要求原件绑定的材料应走带 classification 的上传件，
但不必因此强拆成另一个 `file_upload` 包。

### 2.3 “混合路由”当前到底支持什么

事实链：

1. Guide 将所有非 disabled 的 job Agent 纳入候选；interactive 仅允许审定 allowlist，且不进
   task batch（`agents/guide_agent/workflow.py:261-310`）。
2. `orchestrate` 可含 1—5 个 job 成员，并允许后项用 `after` 引用更早成员；非法成员、重复、
   第六个成员或任一输入不完整都会整份关闭（`workflow.py:599-784`）。
3. `/tasks/batch` 在同一事务里全有全无创建整组任务（`backend/app/api/tasks.py:974-1006`）。
4. [ADR-0033](../adr/ADR-0033-conversation-first-auto-routing-agent-shell.md)要求多 Agent 方案只有
   整份可执行才可开工，附件必须恰好分区，信息不足回同一会话追问（`:46-70`）。

因此可以精确分三档：

- **job + job：已具合同。** A1 落地后，“通用文本草稿 + FTA/FEA 等工程执行”可组成一份
  `orchestrate` 计划；是否有真实产物依赖再决定 `after`，不得为了展示编排而虚构依赖。
- **通识直答 + job：无 formal mixed。** 通识直答没有计划块；`orchestrate` 是另一决策姿态。
  计划块前的自然语言只是一段可见说明，不是独立、版本化、可验收的“通识腿”。
- **interactive + job：无同轮合同。** `delegate` 是独占姿态，目标 interactive 不进入 batch。

“混合路由”适合作为新包的**配套验收项**，不适合作为不新增能力包的替代方案。

---

## 三、三种接法候选对比

> owner 已裁“接”，所以候选 C 仅作反事实/回退成本对照；除非 owner 明确重开旧裁决，
> 当前实际裁量应集中在 A 的切片与 B 的合同边界。

| 维度 | A：新增有界通用能力包 | B：只做混合路由 | C：不接并收窄 Destination |
|---|---|---|---|
| 能否满足原“走通一个通用任务” | **能**，前提是至少一个 job 真产生任务/事件/产物并过人审 | **不能单独满足**；没有通用 job，路由只能直答或拒绝 | 不能；只能修改终点定义以承认不执行 |
| 与 owner 既有裁决/#53 | 一致，但须收窄 #53 的三风险同包范围 | 可作为 A 的配套，不能替代 A | 冲突；只有 owner 明确翻案才可采用 |
| 实现量（估算） | A1 1.5—2.5 人日；A2 3—5 人日；源码草稿另 1.5—2.5 人日 | 0.5—1 人日（prompt/合同或仅 eval，取决于是否扩 formal mixed） | 0.5—1 人日（Destination/Guide refusal/eval/留痕） |
| 测试与取证（估算） | A1 1—2 人日；A2 2—3 人日；均含 package/unit/eval/route/e2e/截图 | 0.5—1 人日；但只证明路由，不证明通用执行 | 0.5 人日；证明直答/refuse，不应拍成执行成功 |
| 新依赖 | A1 无；A2 可复用现有 `openpyxl`，无；docx/pdf 不在本切片 | 无 | 无 |
| 宪法影响 | 可合规：Gateway/Registry/Task/Event/limitations/eval/版本化/人审全在 | 不改内核纪律；但若扩 formal mixed，会改路由公共合同 | 诚实，但撤销“接”的产品方向，需 owner 留痕 |
| `verify_all` 影响 | 新增后端/package/tool/Guide/e2e 用例；阈值不放宽，全套必跑 | Guide 合同/eval/e2e 增量；全套必跑 | 文档+Guide refusal/eval；全套仍必跑 |
| 主要风险 | 大一统包能力漂移；敏感文本分级；LLM 草稿误信；新包合入即被路由 | 把“能拆”误报为“能做”；formal mixed 仍空缺 | 终点被改成“说明/拒绝”，与用户期待及既有裁决不一致 |

**成本口径说明：**以上人日是基于仓内既有 Agent Package 七件套、eval、路由合同、e2e 与
截图同批的工程估算，不含 owner 评审等待、真实内网模型可用性和 CI 排队；不是交付承诺。
任意代码执行没有给“小包人日”——它是独立多模块安全项目，不能用一个 Agent Package 的
估算掩盖。

### 3.1 候选 A 的推荐分片

#### A1：`general_text_draft_agent`（推荐候选，不定稿）

建议只覆盖一族同风险操作：`summarize | translate | markdown_draft`，首个黄金任务先钉
`summarize`。边界：

- `mode=job`，模型只经 Model Gateway；`tools=[]`、`knowledge.enabled=false`，零新依赖；
- 输入先用 `params`：`task_kind`、`source_text`、可选 `instructions/title/target_language`，
  schema 设字符/枚举上界；首片显式拒绝附件，源文本以“数据不是指令”fence 注入并中和
  sentinel。以后若接文件，可继续使用同一 `params` 包，但须另验附件数量、类型、大小、读取
  完整性、来源优先级与密级；
- 输出固定一个 `.md` 草稿 + 结构化摘要（源文本 digest、字符数、task kind、
  `finish_reason`、`truncated`），不把模型正文解析成确定性事实；
- 文件头强制“AI 生成草稿 / 未核验 / 需人工复核”，异常收尾显著标记或诚实 failed；
- `requires_human_review: true`。这不是偏好项：Registry 已强制
  `job + model.profile != none => requires_human_review is True`，不满足即拒载（
  `backend/app/runtime/registry.py:205-223`）。若想让通用草稿自动 completed，必须另立
  治理 ADR/契约变更，不能在 #53 偷渡。

`fta_agent` 已提供最接近的实现先例：模型自由文本原样存 `.md`、强制水印、异常收尾显式
标记、返回 success 后由 Runtime 进入 `waiting_review`（
`agents/fta_agent/workflow.py:1-16/73-119`）。A1 应复用这套纪律，不复制 FTA 业务字段。

#### A2：通用表格变换（推荐后置）

建议新建**确定性**工具，而不是让 LLM 直接写工作簿：

- 白名单操作 DSL：如选择/重排/重命名列、空值规范化、确定性排序；未知操作 fail-closed；
- 文件只从经 File Store 核验的输入路径读，只向任务 `output_dir` 写；禁止覆盖源文件和任意
  绝对输出路径；临时文件成功后原子替换；
- worksheet/行/列/解压后大小/字符串长度有硬上限；任何截断必须显式失败，不能静默少算；
- 所有外来字符串按惰性文本写入，防公式注入；不执行宏、不保留不理解的活公式语义；
- 工具返回变换 receipt（输入 digest、操作清单、行列计数、拒绝/告警、输出路径），
  Agent 只负责从用户意图提出受 schema 约束的计划，并由确定性工具执行；
- 由于 A2 的计划若由 LLM 产生，job 仍应停 `waiting_review`；若未来做到完全确定性
  `profile=none`，是否免审也要按用途/`usefulness_level` 单独裁，不能靠 truthiness。

项目已依赖 `openpyxl`（`pyproject.toml:8-18`），所以 A2 可做到**零新依赖**；但新工具的
契约、安全限制和测试仍是实质工作，不能把“依赖已在”写成“能力已在”。

#### 源码草稿与代码执行必须拆开

- **源码草稿可候选：**只输出 `.py` 或 `.md`，顶部写“未运行、未测试、不可直接用于生产”，
  `tools=[]`，任务停人审；不得把生成代码 import/exec/subprocess，也不得声称测试通过。
- **代码执行不接：**当前 Agent workflow 由 `importlib` 在主进程加载（
  `backend/app/runtime/runtime.py:421-427`）；Tool Registry 同样 `import_module` 后在线程内调用
  Python adapter，超时线程无法强杀、可能继续运行（`backend/app/tools/registry.py:140-183`）。
  `tool.yaml` 虽声明 `max_parallel_jobs/retry/require_workspace_isolation/allow_shell_command/
  save_raw_files`，当前 Registry 调用路径只消费 `timeout_seconds`；其余主要是包作者承诺，
  不是沙箱执法。
- [ADR-0039](../adr/ADR-0039-nemoclaw-openshell-sandbox-execution-spike.md)已记录当前执行面无容器
  隔离/egress/进程限额（`:9-18`），并因 proxy-only egress 假绿拒绝吸收 OpenShell 组件（
  `:77-85`）。因此只能运行**仓内审计过的确定性 adapter**，绝不能运行用户或模型生成代码。

### 3.2 候选 B 的准确定位

最低成本 B 只需给 Guide 增补以下黄金探针：

1. 纯通用执行 → A1 单 job；
2. 通用执行 + 工程执行且互不依赖 → 两 job 并行；
3. 通用产物确为工程输入 → 合法 `after`；
4. 通识解释 + 工程执行 → 在 formal mixed 未扩前，不得声称“双腿均有合同”；
5. interactive 专家 + job → 不得硬塞同一 plan；
6. 任一通用腿未注册/输入不全 → 整份澄清或拒绝，DB 零部分写入。

如果 owner 的“混合任务”只指**多个可执行 job**，现有结构够用，B 是测试/路由校准；如果
指“直答 + delegate + job 可在同轮组合”，那是路由 schema 与会话运行时的新公共接口，
成本不再是 0.5—1 人日，应另立设计票。

### 3.3 候选 C 的可达边界

若 owner 明确撤销 2026-08-05 的“接”裁决，可以诚实收窄为：

> 非航空通用场景首轮会话零行话摩擦：概念类需求可直接解释；执行类需求若无已注册能力，
> 则明确拒绝并给出可行动的重述/拆解出口；工程场景触发时，可信面按既有规则自动浮现。

这句话可达，但它**删除了“走通一个通用任务”**，不能再用 Guide 给建议或 refusal 冒充任务
完成。由于它与 owner 已裁方向和 #53 冲突，本报告不推荐在无新 owner 留痕时采用。

---

## 四、宪法、发布隔离与诚实纪律影响

### 4.1 A1/A2 必须逐条满足的宪法合同

对照[系统宪法](../00_FLAi-OS_Constitution.md)：

| 铁律 | A1/A2 机械落点 |
|---|---|
| 模型只经 Gateway（`:48-53`） | manifest 只声明 profile；workflow 只调用 `context["model_gateway"]`，不出现具体模型名/直连 SDK |
| 工具只经 Registry（`:52-53`） | A1 零工具；A2 只调用 manifest 白名单内新注册工具 |
| 任务进 Task Center/Event（`:54-55`） | 必须是 job；产物由任务输出目录注册；关键步骤有 event/tool_run，不拿 Guide 正文当交付 |
| 限制/知识 default-deny（`:56-57`） | `limitations>=1`；A1 knowledge 关闭；禁止“大概什么都能写”的万能表述 |
| 诚实高于绿色（`:58-60`） | AI 草稿/未验证/截断/拒绝随产物本体；mock 不得参与黄金成功样板 |
| 人是唯一签发者（`:61-64`） | LLM job 固定 `requires_human_review:true`，成功态先到 `waiting_review` |
| 资产版本化（`:65-66`） | agent.yaml/prompt/schema/workflow/changelog 同批，行为变更升 semver |
| 每包有 eval（`:67-68`） | 正常、失败、注入、越界至少覆盖；线上失败回灌 |
| 外部内容是数据非指令（`:69-70`） | A1 source fence + sentinel 中和；A2 单元格只作数据，不产生指令或公式 |
| 不绕架构（`:71-73`） | 不在 Guide 内直接写文件，不绕 Task/Tool Registry，不执行用户代码 |

### 4.2 `draft/admin_only` 不是当前 job 执行隔离

当前 17 包全是 `draft/L0`，但观察到的 job 路径并不把它们当成“不可路由”：

- Guide job 候选只排除 `status=disabled`，不按 `draft/trial/released`、`visibility` 或
  `allowed_roles` 过滤（`agents/guide_agent/workflow.py:261-310`）；
- `create_task` 对 job 同样只拒绝 `disabled` 与 interactive（
  `backend/app/api/tasks.py:741-773`）；interactive handoff 才另查 allowlist/business_user。

所以把一个半成品 A1 以 `status:draft`、`visibility:admin_only` 合入默认 `agents/`，**不能视为
发布隔离**。候选安全做法二选一，留 owner/施工票定：

1. 在隔离 `agents_dir` 完成 package/unit/eval/route/e2e，全部证据齐后再原子合入；或
2. 先修 job 的 Registry/Guide/API 准入门，再允许半成品包进主目录——这会触及平台核，
   不应偷偷塞进 #53。

本报告推荐 1：#53 作为完整、可验的最小包原子落地，而不是先放一个 draft 空壳。

### 4.3 诚实展示的最小形状

A1 成功不是“模型说完”，而是同时满足：

- 任务/事件/模型调用有记录；
- `.md` 产物本体有 AI 草稿水印、源 digest、任务类型、截断/异常收尾状态；
- 任务停 `waiting_review`，completed 只来自具名人审；
- UI 继续遵守 completed 中性、绿只给 REAL 核验、teal 只给人签；
- 无法做、材料超限、目标为执行任意代码时，明确 failed/refuse，不生成“看似完成”的空壳。

### 4.4 输出合同与人审证据仍有现存边界

新增包不能只写出漂亮的 `output_schema.json` 就宣称运行时已替它守门：当前 Runtime 通用路径
只检查 workflow 外层 `status == "success"`，随后登记 `output_dir` 中的文件；Agent manifest 的
`output.formats` 与包内 `output_schema.json` 尚未由生产 Runtime 统一强制（
`backend/app/runtime/runtime.py:946-1027/1491-1527`）。因此 A1/A2 首片至少要在 workflow 内
自校验实际文件名、格式、字节数、结构化 receipt 与 digest；进入 trial 前是否补中央格式白名单、
总输出字节上限和 schema gate，应作为施工票的显式前置裁量，不能把包级测试冒充平台级执法。

同样，现有 `execution_evidence_digest` 绑定 Agent 包快照、任务参数与输入文件，但未绑定 Tool
adapter 代码、Tool run 和最终输出文件哈希（`backend/app/runtime/runtime.py:803-842`、
`backend/app/storage/repos.py:641-683`）。所以 A1/A2 可以诚实说“经过既有具名人工复核闸”，
不能升级表述为“最终产物已由完整密码学证据链签发”。若 owner 要求后一种承诺，须先补平台核，
不属于纯 Agent Package 小片。

---

## 五、#53 的范围对账与 owner 真正要裁的点

[task「通用执行样板包（脚本/表格/翻译）」（#53）](https://github.com/kogamishinyajerry-ops/flai-os/issues/53)当前写“脚本/表格/翻译起步各一，
设计+实现同票”，基线还是旧 16 包。它与本盘点的关系建议按下表处理；本报告不替 owner
编辑、关闭或拆票。

| 裁量点 | 已知事实 | 候选（推荐在前，不替 owner 定稿） |
|---|---|---|
| Q1 首个黄金任务 | “接”已裁；但三项同包风险不同 | **粘贴内部非敏感文本 → Markdown 摘要 → 人审**；翻译随后；或 owner 另选翻译首发 |
| Q2 #53 是否拆票 | A1/A2/代码执行分别是 LLM 草稿、确定性文件工具、安全项目 | **#53 收窄为 A1，A2 与源码草稿另票**；或 #53 作为总票、下面拆子票 |
| Q3 脚本含义 | “写脚本”既可指源码草稿，也可指生成后执行 | **只产未运行/未测试草稿**；任意执行从 #53 排除并转独立沙箱安全线 |
| Q4 表格时序 | 现有 Excel 工具专用；`openpyxl` 已在但通用合同不在 | **A2 后置**；如必须同票，仍须独立 tool package + 安全/负向测试，不改旧工具 |
| Q5 复核策略 | 当前 Registry 强制所有 LLM job 人审 | **沿用 `waiting_review`**；若要 completed-neutral，另立治理 ADR，不在 #53 破例 |
| Q6 输入形态 | `params` 可同时接结构化参数和零/多附件，但无内建数量/后缀门；`file_upload` 给出最终恰好一件+后缀白名单；两者的上传件都进入文件分级链 | **首片 params + 非敏感粘贴文本上限+显式零附件**；后续可在同包补数量/类型/大小/完整读取/密级测试，只有 owner 要原生单文件合同才另选 `file_upload` |
| Q7 mixed 的定义 | 多 job 已支持；通识/direct/delegate + job 无正式混合 | **本票只验多 job**；若要多姿态同轮合同，另立路由设计票 |
| Q8 半成品隔离 | draft/admin_only 不阻止 job 路由/API 创建 | **隔离 agents_dir 开发，验收齐再合入**；或先修平台准入门 |

---

## 六、可机械验收的施工计划

### 6.1 A1 包级验收

至少包含并验证：

1. `agent.yaml/prompt.md/input_schema.json/output_schema.json/workflow.py/README.md/
   changelog.md/eval_cases/` 齐全，Registry 扫描零 error；
2. manifest 为 job、非具体模型名、`tools=[]`、knowledge default-deny、
   `requires_human_review:true`、limitations 明写不做工程结论/事实核验/代码执行；
3. 正常 fake-gateway 输出产生唯一 `.md`，水印、源 digest、task kind 在产物本体，任务终态
   `waiting_review`；`model_call`/task events/输出文件记录齐；
4. 空内容、上游异常、未知 `finish_reason`、长度截断、超字符预算均诚实 failed 或显著不完整，
   不落空壳成功产物；
5. source 中的 `<<END_SOURCE>>`、伪 system prompt、路径/Markdown/HTML 注入都只当数据；
6. 未支持 `task_kind`、脚本执行、docx/pdf，以及首片合同外的任何附件请求，由 A1 workflow/
   refusal 边界 fail-closed 拦住，DB 零部分写；不得把它误记为 `params` 平台能力限制；
7. 人工批准后才 completed；拒绝后 failed；completed 中性色和人签 teal 既有锚不退化。

### 6.2 A1 eval / 路由 / e2e 最小集

建议至少 5 个 approved eval 或等价自动化 case：

| Case | 输入 | 机械 oracle |
|---|---|---|
| G1 正常摘要 | 有界中文源文本 | `waiting_review`；`.md` 存在；水印+digest 在场；tool_runs=0 |
| G2 翻译（若首版收） | 明确源/目标语言 | `waiting_review`；产物标翻译草稿；不声称核验 |
| G3 空/异常收尾 | gateway 空内容或 `finish_reason=length/content_filter/畸形值` | failed 或不完整横幅；绝不静默完整 |
| G4 注入源文本 | source 内伪指令/伪 fence | prompt 结构仍闭合；指令不改变 task kind/输出合同 |
| G5 越界 | “执行这段 Python 并联网下载” | Guide `refuse`；无 task、无 tool_run、无输出文件 |

路由/e2e 另验证：

- 主对话自然语言输入，无 Agent/模型/工具选择器；Guide 自动形成 A1 完整方案；
- 点一次开始后 batch 回包 agent/version/digest/operation_id 全对账；
- 状态坞出现待审，打开签发卡，产物可下载；批准后状态与人签留痕一致；
- 混合执行金标准：A1 + 一个工程 job 可完整建两项；任一成员缺输入则整批零写；
- 真实内网模型至少跑一轮黄金任务和一轮越界拒绝，并保存输出/截图；stub 只能验证壳，不能替代真实路由裁决。

### 6.3 A2 额外负向集

- 缺表头、重复/超长列名、空簿、多 sheet、隐藏 sheet、公式、外部链接、宏型后缀；
- zip bomb/超解压量、超行列/超字符串预算；
- `= + - @` 等公式注入前缀、控制字符、伪路径、输出路径逃逸、源文件覆盖；
- 未知/重复/冲突操作、部分失败、保存中断；
- receipt 的 input/output digest、行列计数与实际文件逐项一致；任一不一致 fail-closed。

### 6.4 验证命令与门禁

施工票至少要跑：

```bash
# 定向快反馈（文件名由实际施工确定）
uv run --no-project --with pytest --with jsonschema --with pyyaml \
  --with fastapi --with httpx --with python-multipart --with 'pydantic>2' \
  --with jieba --with openpyxl \
  python -m pytest -q \
  backend/tests/test_general_text_draft_agent.py \
  backend/tests/test_guide_auto_routing_contract.py

# 最终唯一全门禁：build + bundle + 三 testpaths pytest + node + 全部 e2e
bash scripts/verify_all.sh
```

`verify_all.sh` 当前固定跑 frontend build、bundle 预算、`tests + tools_impl + backend/tests`
全量 pytest、Node tests 与 21 个 e2e 脚本（`scripts/verify_all.sh:45-108`）。新增能力不放宽阈值，
也不能只跑 backend/tests 漏掉工具/契约测试。若 A1/A2 改任何用户可见状态、产物卡或文案锚，
实现 + 自动化 + 截图必须同批。

---

## 七、Destination 可达改写

### 7.1 与既有“接”裁决一致的建议句（推荐候选）

> 非航空通用场景首轮会话零行话摩擦，并从主对话走通至少一个受控通用内容任务：系统
> 自动路由到已注册能力，生成带“AI 草稿 / 未核验”标识的 Markdown 产物，任务停在
> `waiting_review`，由具名用户放行；超出已注册能力（含任意代码执行、未支持文档格式）时
> 明确拒绝并给出可行动出口。进入工程场景后，依据卡、人签与审计链按既有规则自动浮现。

这句话可用 A1 的单一黄金任务机械验收，同时没有把表格、docx/pdf、代码执行提前宣布完成。

### 7.2 如果 owner 明确选择 C 的收窄句

> 非航空通用场景首轮会话零行话摩擦：概念类需求可直接解释；执行类需求若无已注册能力，
> 则明确拒绝并给出可行动的重述、拆解或登记出口。进入工程场景后，依据卡、人签与审计链
> 按既有规则自动浮现。

必须同时留痕：该句删除“走通一个通用任务”，并撤回既有“接”裁决/#53 方向；不能在文字上
收窄，汇报时仍声称平台已有通用执行能力。

---

## 八、风险、未核项与本票边界

| 风险/未核项 | 当前判断 | 收口条件 |
|---|---|---|
| 新包合入即被 Guide/API 使用 | **已证风险**：draft/admin_only 非 job 隔离门 | 隔离开发后原子合入；或另修准入门 |
| LLM 草稿被当正式内容 | 高 | 产物本体水印 + waiting_review + 异常收尾 + 人签 e2e |
| 无附件的 params 文本缺少独立密级污点 | **已证边界**：任务会派生为 internal；params 一旦绑定上传件仍继承文件分级 | 首片粘贴文本限内部非敏感；敏感材料绑定有 classification 的上传件，params/file_upload 均可 |
| params 附件无内建数量/后缀白名单 | 高 | A1 workflow 自验数量、类型、逐件/总字节和完整读取策略；或另补平台级声明式门 |
| Guide 投影 `source_text` 不具字节级原文绑定 | 高 | 精确转换绑定已登记上传件及 file digest；可用 params 多文件或 file_upload 单文件，workflow 只读 `context["files"]` |
| “mixed 已有”过度表述 | 高 | 只声称 multi-job；direct/delegate+job 另立 formal mixed 合同 |
| 通用表格复用专用工具 | 高 | 新 tool id/schema/adapter/tests；旧工具契约不改 |
| 公式/宏/外链/压缩炸弹 | 高 | A2 负向集全红转绿并进入 verify_all |
| 用户/模型代码执行 | 不可接受 | 真沙箱、egress/FS/process 强制、超时可终止、负向金丝雀、owner ADR |
| 翻译/摘要质量如何自动判真 | 部分不可确定 | 自动化只判合同/不越界；语义质量由人工 review + 固化 eval 样本 |
| 真实模型路由稳定性 | 当前仓库静态盘点未核 | 内网黄金任务与拒绝探针实跑留痕 |
| docx/pdf | 当前不支持 | 新依赖/解析安全/输出格式另裁，不进入 A1/A2 默认承诺 |

本报告只新增一个研究文档，不宣称上述候选已实现，也不修改 [task「通用执行样板包（脚本/表格/翻译）」（#53）](https://github.com/kogamishinyajerry-ops/flai-os/issues/53)
或 map Destination。下一步应由 owner 先裁 §五 Q1—Q8 的范围；裁后再让施工票写入真实文件名、
测试名、e2e 场景和退出条件。

---

## 九、本票验证（2026-08-08）

- 在全新隔离副本 `/tmp/flai-os-58-verify.ifEErj` 对同一代码基线运行
  `UV_OFFLINE=1 bash scripts/verify_all.sh`：frontend build、bundle budget、全量 pytest、
  Node 与 21 个 E2E 全部通过；无失败项。
- 明细：pytest **1800 passed / 2 skipped**；Node **306 passed / 0 failed**；21 个 E2E 脚本
  全绿；同步入口 JS/CSS gzip **137,931 / 20,674 B**，最大路由闭包 JS/CSS gzip
  **196,505 / 29,471 B**，既有预算未放宽。
- `git diff --check` 与本地相对链接存在性检查单独覆盖本报告。全量门只证明本 research 文档
  没有带来代码回归；由于本票没有实现 A1/A2，也没有新增通用任务 E2E，**这次全绿绝不构成
  “通用执行已可用”的证据**。
- 本地 CodeBuddy CLI `2.133.0` / `glm-5.2` 以 plan 权限、仅 `Read`、禁会话持久化完成只读互审：
  **VERDICT: PASS，P0/P1=0**。唯一 P2 是两处 `attachments.py` 引用缺完整路径，已在本报告
  修正；P3 对 Tool Registry 字段执法范围的措辞复核后维持“Registry 调用路径”这一有限表述，
  未扩写成未经证明的全栈结论。未使用 86gs。
- PR 自动审阅随后指出本报告曾把 `params` 误写成拿不到附件，并错误地强制拆成
  `file_upload` 包；该 P2 有效，已按创建门、Guide 绑定、Runtime `context["files"]` 与密级派生
  的源码事实修正。修订后再用同一 CodeBuddy / `glm-5.2` 配置做定点只读复核：
  **P0/P1/P2/P3=0，VERDICT: PASS**。全程未使用 86gs。

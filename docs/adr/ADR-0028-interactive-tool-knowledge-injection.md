# ADR-0028: 交互运行时工具/知识注入接缝 + P0-N2 退休（ConversationService）

- 状态：**Proposed（提议，待 owner 具名终裁 + Codex 命中即审）**——本 ADR 退休一个 main 刚硬化的
  P0 安全门（P0-N2）并为交互运行时打开工具注入面，属安全边界治理动作；退休 P0-N2 = 治理签发，
  人是唯一签发者，须 owner 具名批准后方可从 Proposed 转「已采纳」。
- 关联：ADR-0012（interactive 运行时 ConversationService）/ ADR-0013（会话审计：model_calls 带
  conversation_id，会话无任务事件流）/ ADR-0015（job 侧 knowledge 注入三层门；**line 103 明令
  「交互 knowledge 挂载须先补挂载点并另立 ADR」——本 ADR 即其兑现**）/ ADR-0017（knowledge_qa
  sentinel 结构中和「数据不是指令」）/ ADR-0021（知识轴派生分级）/ P0-N2（docs/PRODUCTION-READINESS-
  PROGRAM.md 导入准入门，本 ADR 退休它）。
- 落地：Gate2-T3（T3-a 注入 + N2 放宽 + T3-b 交互类零内核 diff 验证弹 interactive_doc_qa_agent）。

## 背景

`ConversationService`（interactive 型 Agent 的会话运行时）此前只注入 4 键 `{messages,
model_gateway, agent_registry, agent_config}`——**不注入 tool_registry / knowledge**。ADR-0015
的 knowledge 三层门只覆盖 job 路径（`AgentRuntime._build_context`），其后果节 line 101-103 明文：
「knowledge 挂载仅覆盖 job 模式；interactive 不挂……Wave 2 若选 interactive 型需先补挂载点并
另立 ADR」。为在能力就绪前 fail-closed，main 上一步加了 **P0-N2** 注册期护栏：无条件拒载
「mode=interactive 且声明 tools/knowledge」的 Agent——声明了也静默拿不到 = 假绿死罪。

job 路径的注入包装 `_ToolRegistryContext` / `_KnowledgeContext` 经 `repos.append_event(task_id=…)`
逐调用发 `tool_started/finished` / `knowledge_search` 事件，但**会话无 task_id**——设计事实：
`task_events.task_id` NOT NULL、`tool_runs` 无 `conversation_id` 列、`model_calls` 有
`conversation_id`（会话现有审计表）。故 job 包装**不可 verbatim 复用**于会话。

## 决策

1. **内核一次性扩展**（获批的「内核先扩展一次」，非破判据①）：`ConversationService` 会话 context
   注入 `tool_registry`（**无条件**，default-deny 白名单=`frozenset(agent.yaml.tools)`）+ `knowledge`
   （**仅 `knowledge.enabled is True`** 时，白名单=`frozenset(agent.yaml.knowledge.scopes)`），
   逐字节镜像 job 路径 `runtime._build_context`：knowledge 键在注入门即 default-deny——未声明的
   Agent 连键都拿不到（访问即 KeyError），而不是拿到一个「空」入口。

2. **会话变体包装 `_ConvToolRegistryContext` / `_ConvKnowledgeContext`（DRY option A）**：会话变体内
   **复制那 1 行白名单检查**（`if x not in frozenset: raise ToolNotAllowedError/KnowledgeScopeDeniedError`），
   **绝不改 job 包装**（`_ToolRegistryContext`/`_KnowledgeContext` 一字不动，守「判据①零内核 diff 的
   job 骨架不受影响」）。安全逻辑与 job 逐字节相同；唯一差异是审计出口（见 3）。knowledge 命中经
   `asdict` 交 workflow，出处四钥（scope_id/chunk_id/source/fingerprint）随行（docs/06 §4）。

3. **审计出口 = option (b)（会话逐调用 tool/knowledge 事件流 = V0.2+ 债）**：default-deny 白名单
   **照常强制**（安全核心不变，这是 Codex 命中即审真正把关的）；会话逐调用 tool/knowledge 留痕
   **降级**走 `logger` + 既有 `model_calls`（已带 conversation_id）。**不**为此加 `tool_runs.conversation_id`
   列或新建 knowledge 会话审计表（option (a)，schema 改动较广）——会话 tool 调用 `conn=None` 即不落
   无归属列的孤儿 `tool_runs` 行（工具自身 input/output 契约校验、超时执行不受影响）。此降级与
   conversation.py 既有「会话无任务事件流、留痕落 model_calls」一致（ADR-0013）。

4. **mis-wire fail-closed（镜像 `runtime._execute` 1b）**：Agent 声明 `knowledge.enabled` 而
   `ConversationService` 未装配 `KnowledgeService` = 装配缺陷 → `post_message` 诚实抛、**本轮零消息
   落库**（抛在落库前，与 LLM 失败路径同款事务性）。生产装配（main.py）恒传 `knowledge_service`，
   本闸为 fail-closed 兜底。判定 `is True`/`is None`，绝不 truthiness。

5. **退休 P0-N2 注册期护栏**：能力已由 (1)-(4) 布线，合法交互 tools/knowledge 声明放行。移除而非
   窄化——`AgentRegistry` 只持 `agents_dir`+`schema_path`，无 tool/scope registry 引用，`_load_one`
   结构上无法区分「畸形（不存在的 tool/scope）」与「合法」，故「仅拒未被接住的声明」落不到注册期。
   畸形拦截由**已存在且 mode-agnostic** 的机制原地保住（**非移除防御，退休一层冗余**）：
   - 畸形 SCOPE → `reconcile_agent_scopes`（knowledge/scopes.py，装配期对账，仅 gate on
     `knowledge.enabled is True`，与 mode 无关）→ `deregister`；
   - 畸形 TOOL → 调用期 `ToolNotRegisteredError`（**backend/app/tools/registry.py:108-109**），会话
     白名单放行（agent 声明了）→ `tool_registry.call` → 诚实抛，与 job 路径注册期同样无 tool 存在性
     校验、对称；
   - `knowledge.enabled` 但服务未装配 → (4) 执行期 fail-closed。
   **焊死时序**：N2 移除**必须**与 (1) 注入同批（先布线后放宽），否则重开「声明了却空手产结论」的
   假绿窗——故 N2 移除硬 blocked_by T3-a。

6. **副作用工具边界 —— 代码 fail-closed 已强制（T3-fix，Codex C3-P1-2/P1-3 命中即审）**：交互工具
   注入为交互运行时打开「LLM 可在会话中途驱动调工具、无逐轮人签闸」的面。对**数据类**工具（纯读/
   纯算、无外部副作用）此与 job 路径对称（job 侧工具调用亦非逐次人签，人签的是任务签发/判决），未破
   「人是唯一签发者」。但**有副作用/不可逆/敏感输出**的工具进交互面，LLM 即可无 review gate 触发实际
   动作、或把 sensitive 输出原样落会话消息泄漏。Codex R0 逮的正是「本 §曾只写文档、代码没强制」——
   **本轮 T3-fix 已把该边界从文档声明升级为代码 fail-closed 强制**：

   - **`interactive_safe` 工具元数据字段（`contracts/tool.schema.json`，default-deny）**：optional bool，
     **缺省=false=拒**。仅**纯数据类**工具（纯读/纯算、无外部副作用、`output_classification=internal`）
     方可显式标 `true`。
   - **注入期 fail-closed 强制（`ConversationService.post_message`，镜像既有 knowledge mis-wire 闸）**：
     交互 Agent 声明的**每个**工具必须 ① `interactive_safe is True` ② `output_classification == "internal"`
     ③ **`safety.allow_shell_command is not True`**（★Codex R1-P1-3 跨字段拒：即便误标 interactive_safe，
     shell 能力工具也绝不放行——LLM 会话中途可无人签触发 shell）——任一不满足（含未注册取不到元数据 /
     副作用 / sensitive 输出 / shell 能力）**落库前** `raise`（零消息落库、workflow 从未被调、工具零执行），
     错误点名工具 + 原因。判定 `is True`/`==`/`is not True` 显式，绝不 truthiness。
   - **现役 7 工具逐个核对结论（安全边界具名核对，非仅核 default-deny 白名单）**：
     | 工具 | interactive_safe | 判据 |
     | --- | --- | --- |
     | `cfd_result_read` | **true** | 纯读 CFD 产物、`run_id` 受控句柄（regex+可信根+sidecar 非裸路径）、零 shell、internal |
     | `mock_echo` | **true** | 纯回显 Mock、无文件系统访问、无副作用、internal |
     | `performance_disk_mock` | **true** | 确定性纯代数 Mock、无副作用、internal |
     | `excel_case_parser` | **不标=拒（★R1 撤回）** | 输入是**裸 file_path 绝对路径**、adapter 直开无 File Store 容器/大小/哈希校验——交互面直调可读任意服务端文件泄漏进会话（Codex R1-P1）。经 workflow 调用时安全仅因 `_open_input_files` 完整性闸；直调面无此闸。改收 `file_id` 受控句柄后方可重标 |
     | `cfd_solve_launch` | **不标=拒** | 起 Docker 真求解、`allow_shell_command=true`、detached 进程 |
     | `excel_summary_writer` | **不标=拒** | 写 result_summary.xlsx（外部态副作用），非数据类 |
     | `monitor_adapter_recon` | **不标=拒** | `output_classification=sensitive` + 起子进程侦察 |

   现役被判 safe 的均为纯数据类，与 job 路径对称，未破「人是唯一签发者」。judged 样本
   `interactive_doc_qa_agent` 本就 `tools=[]`，此闸对其空转（零行为变化）；两现役交互 Agent
   （guide_agent/interactive_doc_qa_agent）均 `tools=[]`，本闸对存量零影响，仅约束未来声明工具的交互 Agent。

   - **R1 多轮/检索/审计加固（Codex R1 命中即审）**：①**多轮 replay 中和**——`ConversationService`
     经 `history_separated` 键把每轮**分离结构**（user_text/attachments_block）传 workflow，RAG workflow
     逐 prior **用户**轮 `_neutralize_sentinels(user_text)`、保留 runtime 造的可信 `<<ATTACHMENT>>` fence
     （首轮伪造的 `<<KNOWLEDGE>>` 块不再第二轮起裸露冒充语料，R1-P1）；②**零命中再检前置指代闸**——
     `_is_referential_followup` 只对指代式跟进（"第二个呢"）借上文扩展关键词，**自足完整问句**（换话题的
     "法国的首都"）走确定性零命中、绝不错召回上一话题命中（R1-P2）；③**工具返回失败态成对留痕**——
     `_ConvToolRegistryContext.call` 对 `{"status":"failed"}` 返回记 warning（非无条件「成功」），交互路径
     审计不失真（R1-P2）。

   - **R2 假绿闸/指代收紧/错误契约（Codex R2 命中即审，owner 授权超 cap R3 修）**：①**引用校验假绿
     闸**——RAG workflow 新增 `_grounding_status`：解析答复中的 `[source · chunk]` 复合引用键、对照本轮
     检索命中判 grounded；无有效引用 → 置顶 **amber 未核横幅** + 出处表表头改判「检索命中，不代表答复
     已被支持」；引用了命中外的键（疑似虚构来源）→ 编造警示横幅列具体键 + 整体不 grounded。旧行为
     `_compose_answer` 无条件附全部命中当出处表=无据幻觉被烘托成 grounded（假绿，R2-P1）。刻意**标注
     而非硬抛**：诚实「语料未覆盖」拒答本就无引用，硬抛会把诚实拒答一起吞掉；信任色锁 amber=未核恰是
     此语义。启发式正则非语义理解（格式偏离判未核=fail-safe 方向），V0.2 可升级。②**指代闸锚定化**——
     `_is_referential_followup` 弃「长度≤6 或子串含标记」粗判（"法国首都？"因短、"土耳其/第一次/其他国家"
     因子串全被误判指代式，R2-P2），改**锚定模式**：句首指代/承接词（^）、「…呢」省略式收尾（$）、整句
     裸序数续问（^$）、ASCII 指代词（词边界）四类才判真。③**资源失败错误契约**——交互工具/知识失败
     此前逃逸成裸 HTTP 500；`post_message` 现按异常类型分桶映射：永久性（未注册/未白名单/entrypoint
     加载失败/scope 未注册/被拒/源未接入/摄取失败）→ **503 配置错**（绝不谎报可重试）；临时/契约
     （入出参 schema 不过/工具超时）→ **502 可重试**；均零落库（R2-P2）。

7. **第二交互 Agent 的 UI 可达性 = V0.2 产品化债（诚实边界，本轮不扩前端 scope，Codex C3-P1-1）**：
   `interactive_doc_qa_agent` 是**判据①零内核 diff 的机制证据**（证 `git diff backend/app` 为空，经
   ASGI/API 验证），**非产品化用户面 agent**。前端 `AgentPortal.startConversationFor` 弃选中 agent、
   `GuidePage` 硬编码 `guide_agent`——故 `guide_agent` 外的交互 Agent **UI 暂不可达**。UI 路由（透传
   selected `agentId`、carry 到会话页）是前端 V0.2 产品化，**本轮 T3-fix 不扩 scope**（避免碰 T2 前端面
   + 判据①）。诚实边界：本 agent 经 API 验证可达、UI 不可达，不假装可达；任意交互 agent 的 UI 路由是
   V0.2 债。此点在 `agents/interactive_doc_qa_agent/README.md` 同步显式标注。

## 后果 / 诚实边界

- **人是唯一签发者不破**：注入给 workflow 的是**数据**（工具输出、检索命中），LLM 不建/不签/不派
  任务；`ConversationService` 无建任务路径（conversation.py:21）；`recommendation` 仅草案，人在
  tasks 端点签发。T3-b 样本（interactive_doc_qa_agent）`recommendation` 恒 None——只会话答问。
- **假绿死罪杜绝**：注入门 default-deny（未声明无键）+ 调用白名单 + mis-wire fail-closed 三闸；
  knowledge 命中带出处（KnowledgeHit 构造强制 source/fingerprint 非空），零命中诚实标注不作答，
  模型空内容诚实失败——绝不「声明了却空手产结论」。
- **会话逐调用 tool/knowledge 事件流缺失 = V0.2+ 债**：安全核心（default-deny 白名单）全保，
  审计粒度诚实标为后续（logger + model_calls 兜底）。补 `tool_runs.conversation_id` + knowledge
  会话审计路径待 V0.2。
- **交互调用期无主体身份核对**（DECLARED-NOT-VERIFIED）：ADR-0015:42-45 的密级 visibility 门是
  **agent 级静态、非 user 级**；会话 `created_by` 是自由文本。交互 RAG 若未来指向 restricted scope，
  「调用期无主体身份核对」边界照旧适用——内网真实 restricted 语料前，**用户鉴权层是硬前置**。
  T3-b 用 public_internal demo scope（ecm_frr_demo）时此点 moot，但通用交互-knowledge 挂载携同一
  DECLARED 边界。
- **副作用工具边界代码强制（T3-fix，Codex C3-P1-2/P1-3 已闭环）**：决策 6 的边界不再仅文档声明——
  `interactive_safe` default-deny 字段 + 注入期 fail-closed 强制已布线，现役 7 工具逐个核对定级（4 数据类
  放行 / 3 副作用或 sensitive 拒）。副作用/敏感工具即使被交互 Agent 声明，`post_message` 也在落库前
  `raise`、零消息落库、工具零执行。
- **待 Codex 命中即审同步阻塞项**（交付主 session）：(a) 退休 P0-N2 安全门；(b) ~~交互工具注入面的现役
  工具副作用属性核对~~ **已由 T3-fix 代码 fail-closed 强制 + 逐工具定级闭环（决策 6）**；(c) 审计出口降级
  口径（决策 3）。owner 具名终裁前，本 ADR 保持 Proposed，T3 分支停在 merge 前。

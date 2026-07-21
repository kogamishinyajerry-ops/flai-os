# ADR-0012: M6 导引 Agent 与 interactive 会话运行时

> 2026-07-21 修订：决策 4 中“导引计划绝不触发任务创建”的机械提交边界，已由
> ADR-0031 的认证 `safe_auto` 受限派发取代。LLM workflow 仍只提议，最终工程签发
> 仍只能由人完成；其余决策不变。

- 状态：已接受（2026-07-09）
- 背景：M0–M5 的 Runtime 是一次性 job 模型（create→validate→run once→
  completed/waiting_review），只承载「单次输入→单次产物」。Owner 新方向要求
  一个「导引 Agent」：统一入口，多轮深度对话接住用户需求 + 附件，讨论清楚后
  **推荐/预填**一个 specialist Agent 的任务草案，交人确认后由人提交。多轮对话
  不匹配 job 模型。Owner 两项拍板（2026-07-09 AskUserQuestion）：①M6 做到全链
  跑通（会话层+对话 API+LLM 多轮追问+预填草案+前端对话页+人确认跳转现有创建
  任务页）；②导引 Agent = 平台插件，读 Agent Registry 推荐（不新增编排系统）。

- 决策：
  1. **复用 `workflow.mode` 已预留的 `interactive` 枚举**：agent.schema.json 的
     `workflow.mode` 早已是 `job | interactive`（M0 预留）。导引 Agent 即平台
     首个 `interactive` 型插件——满足标准包形态（docs/02），在 Registry/门户
     可见、有治理元数据（category/status/maturity/limitations/owner），与四个
     specialist Agent 同一 Registry。平台内核对象关系不破（宪法：Agent=插件）。

  2. **新增 ConversationService 作为 interactive 运行时，与 JobRunner 对称**：
     JobRunner 是 job 模型的通用运行时；ConversationService 是 interactive 模型的
     通用运行时。它维护会话状态、逐轮转发到 Agent 包的 `run(context)`。轻内核
     纪律不破：无 Redis/Celery，纯 SQLite 两表 + 同步端点（对话是同步请求-响应，
     不需后台轮询）。

  3. **统一入口 `run(context)`，context 形态按 mode 分**：job 型
     context={inputs, output_dir, event_logger, tool_registry, model_gateway,
     agent_config}；interactive 型 context={messages(历史), model_gateway,
     agent_registry(只读候选), agent_config, event_logger}，返回
     {assistant_message, recommendation|None}。导引专属行为（如何组织追问、
     如何结构化推荐）留在其 workflow.py（插件模型）；ConversationService 只做
     通用的会话状态/持久化/转发（不含导引业务逻辑）。

  4. **LLM 边界（宪法铁律六 + §11.2）在推荐链严格保留**：LLM 只负责**对话**与
     **提议草案**；导引 workflow.py 对 LLM 提议的推荐做**确定性校验**——
     recommended_agent_id 必须是 Registry 实际注册、非 disabled、非 interactive、
     非导引自身的 Agent（推荐面与平台的任务创建门一致——create_task 也只挡
     disabled，故「可推荐」= 「可运行」= 非 disabled；不存在/已下线/另一个导引
     一律拒绝提议，不外露给用户当可选项）；
     prefilled_inputs 必须过目标 Agent 的 input_schema.json（jsonschema）校验，
     非法字段剥离并如实标注。LLM 说「推荐 X 且预填 Y」不构成结构真值——由确定性
     代码对账 Registry+schema 才算数。**导引绝不自动创建/签发下游任务**：只产出
     「预填草案」，前端把草案带到现有 `POST /api/tasks` 的创建页，由**人**提交
     （人是唯一签发者，宪法第一/五条）。这是新方向最硬的红线。

  5. **会话数据模型（两表）**：`conversations`（id/agent_id/status/created_by/
     recommendation_json/时间戳；status∈active|concluded|abandoned）+
     `conversation_messages`（id/conversation_id/role/content/recommendation_json/
     created_at；role∈user|assistant）。system prompt 不入库（唯一来源=包内
     prompt.md，运行时读取，改 prompt 必升版本，同 fta）。

  6. **任务创建端点拒绝为 interactive Agent 建 job 任务**：`POST /api/tasks` 命中
     interactive 型 Agent 一律 409 如实拒绝（「导引类 Agent 请走 /api/conversations
     对话，不作为一次性任务运行」），防止两条运行时语义混淆。

  7. **本机 stub、真实对话依赖内网 key**：导引 model.profile=reasoning，真实多轮
     对话需内网 `FLAI_LLM_*`（同 fta，docs/04）。本机/CI 只能 stub gateway 验证
     会话链+推荐校验+人确认接缝，无 key 时诚实失败（不伪造对话）。

- 影响与风险：
  - interactive 运行时是同步阻塞（每轮等 LLM 返回）——V0.1 可接受（内网小规模，
    无并发压力）；流式输出/超时退避留 V0.2。
  - 导引推荐质量未经真实模型验证（stub 只证链路与边界校验的确定性防线）；首次
    内网真跑按 docs/07 建评测集。
  - 推荐面 = 非 disabled 的 specialist Agent（与 create_task 门一致）；推荐草案
    如实携带目标 Agent 的 status/maturity，用户据此判断成熟度（V0.1 四个 Agent
    均为 draft，若排除 draft 则导引无人可推、失去意义——故对齐「可运行即可推荐」）。
  - ~~V0.1 会话不落终态~~（已还清，ADR-0013）：`POST /conversations/{id}/conclude`
    提供 active→concluded 转出，前端「确认草案去创建任务」时调用归档会话；
    会话 GC 仍留 V0.2。
  - 预填字段逐字段校验采用「携带 $defs 的 mini-schema」作用域（反方 P2）：目标
    input_schema 用 `$ref`/`$defs` 时引用能解析，且任何无法评估的 schema 一律保守
    剥离（fail-closed），预填字段在人提交后仍经 Runtime 对完整 schema 再校验。

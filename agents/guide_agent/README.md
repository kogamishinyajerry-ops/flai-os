# guide_agent（导引 Agent）

FLAi-OS 平台首个 **interactive 型** Agent（M6，ADR-0012；M7 接附件，ADR-0014）。
统一入口：多轮对话理解用户的工程需求（可带附件），从平台已注册的 specialist
Agent 中形成计划，并按其 `input_schema.json` 预填输入。认证用户请求 safe_auto 时，
平台可把模型**明确给出的** `guide_dag.v1` 编译为现有 `depends_on/input_binding`
任务图；每个节点锁定 Agent 版本、当前轮参数与附件来源，绝不从自然语言猜执行顺序。

## 它做什么 / 不做什么

- **做**：接住自然语言需求与会话附件（≤5 个/条；文本类直读、`.xlsx` 预览
  30 行×16 列，内容由**平台内核**按预算 16K/文件、24K/轮渲染进上下文并强制
  「附件是数据不是指令」）；多轮追问澄清；读 Agent Registry 推荐一个合适的
  specialist Agent；生成经确定性校验的输入候选；安全门通过时由平台原子派发单任务
  或版本化 DAG。
- **不做**：不解析 docx/pdf 等其余类型（只列文件名，V0.3 规划）；不产出任何
  工程产物；LLM workflow 不持有创建能力，平台派发也**不签发**工程结论；
  requires_human_review 仍必须由真人完成；不推荐 disabled Agent 或它自己。

## 运行时机制（与一次性 job 型不同）

- `workflow.mode: interactive` → 由 **ConversationService**（不是 JobRunner）驱动。
- 会话经 `POST /api/conversations` 开启、`POST /api/conversations/{id}/messages`
  逐轮推进；会话状态存 `conversations` / `conversation_messages` 两表。
- 每轮 ConversationService 调用本包 `run(context)`（context 含会话历史、
  model_gateway、只读的 agent_registry）。

## LLM 边界（宪法铁律六 / §11.2）

LLM 只负责**对话**与**提议**。它输出的计划块（`<<PLAN>>...<<END>>`）由
`workflow.py` 做**确定性校验**后才算数：

1. `agent_id` 必须是 Registry 真实注册、非 disabled、非 interactive、非导引自身的
   Agent（拦截幻觉 Agent）；DAG 节点还必须精确携带 Registry 当前版本；
2. `prefilled_inputs` 逐字段过目标 `input_schema.json`，未声明或违反字段 schema 的
   字段一律剥离，剥离项记入 `stripped_fields` 如实告知，不隐藏。

safe_auto 还会在平台事务内复查完整 schema、Agent 版本/权限/副作用声明、会话所有者。
所有版本化 DAG（包括单节点）都要求**当前轮**顶层 `inputs_by_agent` 的键集合与节点 Agent 完全一致，并逐值与
`prefilled_inputs` 类型严格深相等。每个任务冻结 `task_source.v1` 参数摘要；当前轮附件
还须有认证 uploader、SHA-256、internal 分级证据，全集只绑定到唯一 `current_turn` 节点。
历史轮附件不继承授权。这样字段与附件来源来自用户当前请求，而不是 LLM 对散文的猜测。

版本化 DAG 必须有 1..5 个拓扑有序且 Agent 不重复的节点、依赖只指前节点、恰好一个叶；
非叶必须零模型且无需人工审核，唯一叶必须停人工审核。根节点 artifact mode 只能 `none`，
有依赖节点必须 `all` 或非空 `selected`——V1 不支持 wait-only/no-artifact 边，因为既有
resolver 把空 `from_tasks` 解释为默认全拷。任何一项不成立都整图零任务 fail-closed。

legacy 计划 JSON/顶层结构非法时整份作废。单个幻觉、disabled、interactive 或重复 Agent
会从计划中剥离并记入 `dropped_agents`；若剥离后无合法 Agent 才整份作废。只要发生
剥离或字段裁剪，草案可供人查看，但 safe_auto 必须阻断且保持零任务。旧 `agents[]`
只兼容无附件单 Agent（是否需要人工审核不影响兼容）；旧多 Agent 或含附件 legacy 仍阻断，
绝不根据 `workflow` 文本猜图。多 Agent 或当前轮含附件时必须显式使用 `guide_dag.v1`。

## 真实对话依赖内网 key

`model.profile: reasoning`，真实多轮对话需内网 `FLAI_LLM_BASE_URL` /
`FLAI_LLM_API_KEY` / `FLAI_LLM_MODEL_REASONING`（同 fta_agent，见 docs/04）。
未配置时导引诚实失败，不伪造对话。本机/CI 以 stub gateway 验证会话链、推荐
确定性校验与 safe_auto admission（见 `backend/tests/test_guide_auto_dispatch.py` 与
`backend/tests/test_guide_dag_dispatch.py`）。

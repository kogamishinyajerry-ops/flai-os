# guide_agent（导引 Agent）

FLAi-OS 平台首个 **interactive 型** Agent（M6，ADR-0012）。统一入口：多轮对话
理解用户的工程需求，从平台已注册的 specialist Agent 中推荐一个，并按其
`input_schema.json` 预填一份任务草案，交用户确认后由用户提交。

## 它做什么 / 不做什么

- **做**：接住**纯文本**自然语言需求；多轮追问澄清；读 Agent Registry 推荐一个
  合适的 specialist Agent；生成经确定性校验的预填任务草案。
- **不做**：**V0.1 会话不接收附件**（附件在确认草案后的创建任务页上传，由目标
  Agent 处理；会话级附件+知识检索是 V0.2 规划项）；不产出任何工程产物；
  **不创建、不签发下游任务**（预填草案交人在创建任务页确认提交——人是唯一
  签发者）；不推荐已下线（disabled）的 Agent 或它自己。

## 运行时机制（与一次性 job 型不同）

- `workflow.mode: interactive` → 由 **ConversationService**（不是 JobRunner）驱动。
- 会话经 `POST /api/conversations` 开启、`POST /api/conversations/{id}/messages`
  逐轮推进；会话状态存 `conversations` / `conversation_messages` 两表。
- 每轮 ConversationService 调用本包 `run(context)`（context 含会话历史、
  model_gateway、只读的 agent_registry）。

## LLM 边界（宪法铁律六 / §11.2）

LLM 只负责**对话**与**提议**。它输出的推荐块（`<<RECOMMEND>>...<<END>>`）由
`workflow.py` 做**确定性校验**后才算数：

1. `agent_id` 必须是 Registry 真实注册、非 disabled、非 interactive、非导引自身的
   Agent（拦截幻觉 Agent）；
2. `prefilled_inputs` 逐字段过目标 `input_schema.json`，未声明或违反字段 schema 的
   字段一律剥离，剥离项记入 `stripped_fields` 如实告知，不隐藏。

任一硬校验不过（JSON 非法 / agent_id 幻觉）→ 整个推荐作废（fail-closed），用户
只看到对话文本，不会拿到一张非法的预填草案卡。

## 真实对话依赖内网 key

`model.profile: reasoning`，真实多轮对话需内网 `FLAI_LLM_BASE_URL` /
`FLAI_LLM_API_KEY` / `FLAI_LLM_MODEL_REASONING`（同 fta_agent，见 docs/04）。
未配置时导引诚实失败，不伪造对话。本机/CI 以 stub gateway 验证会话链、推荐
确定性校验与人确认接缝（见 `backend/tests/test_m6_guide_conversation.py`）。

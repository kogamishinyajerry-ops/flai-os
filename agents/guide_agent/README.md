# guide_agent（导引 Agent）

FLAi-OS 平台首个 **interactive 型** Agent（M6，ADR-0012；M7 接附件，ADR-0014；
会话优先自动路由见 ADR-0033）。工程师只有两种原始输入：输入自然语言，或上传
附件。Guide 在同一对话里理解需求、追问缺失信息，并自动路由一个或多个 specialist
Agent 及其模型、工具与 Workflow；整份方案达到可执行条件后，工程师只需在原对话轴
点击一次开工确认。

## 它做什么 / 不做什么

- **做**：接住自然语言需求与会话附件（可仅上传附件；≤5 个/条；文本类直读、`.xlsx` 预览
  30 行×16 列，内容由**平台内核**按预算 16K/文件、24K/轮渲染进上下文并强制
  「附件是数据不是指令」）；多轮自然语言追问；制度/标准类问题在同一主对话自动
  转交已审定的 interactive 专家；执行型需求则根据 Registry 与输入契约自动编排一个
  或多个 job Agent。只有整份任务方案的必需输入全部通过确定性校验时才显示开工确认；
  人在原对话轴点击后，由平台原子创建整批任务。
- **不做**：当前不解析 docx/pdf 等其余类型（只列文件名，后续规划）；不产出任何
  工程产物；**不替人点击开工、不作关键工程判断、不签发结果**；不要求工程师填写
  参数表、编辑 JSON 或选择 Agent/模型/工具/Workflow；不推荐已下线（disabled）
  的 Agent 或它自己。

## 运行时机制（与一次性 job 型不同）

- `workflow.mode: interactive` → 由 **ConversationService**（不是 JobRunner）驱动。
- 会话经 `POST /api/conversations` 开启、`POST /api/conversations/{id}/messages`
  逐轮推进；会话状态存 `conversations` / `conversation_messages` 两表。
- 每轮 ConversationService 调用本包 `run(context)`（context 含会话历史、
  model_gateway、只读的 agent_registry）。

## LLM 边界（宪法铁律六 / §11.2）

LLM 只负责**对话**与**提议**。它输出的计划块（`<<PLAN>>...<<END>>`）由
`workflow.py` 做**确定性校验**后才算数：

1. `delegate` 只能命中审定的制度/标准 interactive 专家，运行时再次复核不可变包、
   mode、状态、附件密级与模型调用归因；`orchestrate` 成员必须是 Registry 真实注册、
   非 disabled、非 interactive、非导引自身的 job Agent（拦截幻觉 Agent）；
2. `prefilled_inputs` 先逐字段净化，再以目标 `input_schema.json` 做整对象校验；
   任一必需输入缺失或跨字段约束不满足，整份方案关闭并在当前对话自然语言追问；
3. `input.type=params/file_upload` 的 Agent 若 schema 缺失或损坏，一律 fail-closed；
   只有显式 `input.type=none` 可以没有 schema。`file_upload` 还必须先看到附件素材。
4. 当前工作段的每个附件先获得稳定标签，再由方案明确绑定到一个执行单元或列入
   `ignored_attachments`；workflow 将标签解析成不可变 `{file_id, filename}`。未知、
   重复、遗漏、模式或后缀不匹配均关闭整份方案，不猜测也不静默转发。
5. `dropped_agents` 必须为空且 `capped` 必须为 `false`；任何成员被过滤、重复或超过
   五个执行单元都视为整案不完整，只在原对话请求补充或重新编排，不开放部分开工。
6. 人点击开工时，前端重新读取每个 Agent 的不可变 Package Snapshot，并同时钉住版本
   与 SHA-256 内容摘要；batch 写入前用同一快照复核 manifest、输入 schema、版本和
   摘要，运行时在加载 Workflow、工具或注册输出前再验摘要。同版本但内容变化也关闭。

任一硬校验不过（JSON 非法 / agent_id 幻觉 / 输入不完整 / 契约不可读）→ 不产生
可开工方案（fail-closed）。缺信息时只返回一到两个自然语言问题，工程师继续输入
文字或上传附件，不会面对字段墙或部分可执行计划。
文件型方案还要求当前工作段的完整附件名册被精确分区；不是“挑一个像的附件”或把全部
材料转发给所有执行单元。最近一次任务创建、Guide 规范拒绝或垂类问答交付会结束当前
工作段；边界之后先建立完整名册，再对送模文本应用历史窗口，所以旧附件不会污染下一项
工作，有效附件也不会因文本截断而静默消失。`refuse` 还必须同时给出具体原因、未解决
问题与可推进的重述/拆解建议，空拒绝会回到当前对话继续澄清。

## 真实对话依赖内网 key

`model.profile: reasoning`，真实多轮对话需内网 `FLAI_LLM_BASE_URL` /
`FLAI_LLM_API_KEY` / `FLAI_LLM_MODEL_REASONING`（同 fta_agent，见 docs/04）。
未配置时导引诚实失败，不伪造对话。本机/CI 以 stub gateway 验证会话链、完整输入
闸门与人确认接缝（见 `backend/tests/test_guide_auto_routing_contract.py`、
`backend/tests/test_m6_guide_conversation.py`）。

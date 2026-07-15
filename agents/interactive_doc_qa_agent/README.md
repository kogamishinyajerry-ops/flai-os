# interactive_doc_qa_agent（交互文档问答 Agent）

多轮会话内的检索增强问答（RAG）样板——平台首个 **interactive 型**消费 knowledge 内核的
Agent（Gate2/ADR-0028，T3-b「交互类零内核 diff 验证弹」）。

## 定位

它把 `knowledge_qa_agent`（job 型批量问答）的检索纪律搬到会话运行时（`ConversationService`）：
逐轮读会话历史 → 取最新用户问 → 在 `agent.yaml.knowledge.scopes` 钉死的单 scope 白名单内
检索 → 命中语料经 sentinel 结构中和后以 `<<KNOWLEDGE>>` fence 注入（数据不是指令）交推理
模型生成带出处的归纳答复；零命中显式标注、不调模型。

## 存在意义 = 判据①（交互类零内核 diff）的证据

本包是**证据而非业务能力**：交互运行时的 tool/knowledge 注入接缝由 T3-a 一次性扩展
（`backend/app/runtime/conversation.py` + `main.py`），此后新增交互类工具/知识 Agent 只加
`agents/` 包即可声明式取用——**加本包 `git diff backend/app` 必须为空**。这把判据①（零内核
diff）从 job 数值类延伸到交互类（真交互零 diff 样本 n=1）。

## 红线

- **绝不创建/召集/签发任何任务**：`ConversationService` 无建任务路径，`workflow.run` 返回的
  `recommendation` 恒 `None`（草案都不产）——人是唯一签发者，LLM 不进判决链。
- **答复只依据检索命中的语料**：零命中显式标注「语料零命中」、不调模型（语料没有的东西让
  LLM 编是最直接的幻觉源），绝不语料外作答。
- **检索命中经内核 default-deny 白名单**（`agent.yaml.knowledge.scopes`，内核
  `_ConvKnowledgeContext` 层强制），绕不过；scope 未注册/密级不符经装配期 `reconcile_agent_scopes`
  对账，不注册即不可访问。

## 诚实边界

- 绑定语料 `ecm_frr_demo` 是**合成演示语料**（源 COMAC_FDE k01，DECLARED-NOT-VERIFIED）：
  答复内容不反映任何真实工程事实；真实 ECM/EM/FRR 语料待内网接入后另建知识范围。本包证的是
  **机制**（交互类零内核 diff + 检索纪律），非业务价值。
- **UI 暂不可达 = V0.2 产品化债（ADR-0028 决策 7，Codex C3-P1-1）**：本 agent 是**判据①零内核 diff
  的机制证据**（证 `git diff backend/app` 为空，经 **API/ASGI 验证**），非产品化用户面 agent。前端
  `AgentPortal.startConversationFor` 弃选中 agent、`GuidePage` 硬编码 `guide_agent`——故 `guide_agent`
  外的交互 agent **在当前 UI 点不到**。透传 selected `agentId`、carry 到会话页的 UI 路由是前端 V0.2
  产品化，本轮 T3 **不扩前端 scope**。诚实标注：本 agent **经 API 验证可达、UI 不可达**，不假装可达。
- 交互 Agent 不进人签闸（无 `waiting_review`）：答复是辅助归纳、非结论也非放行/适航依据，
  判定权在工程师。
- 检索按关键词词面匹配（非语义检索）：换词提问可能漏检。

## 依赖

- 运行时：`context["knowledge"]`（T3-a 注入）+ `context["model_gateway"]`（profile=reasoning）。
- 真实多轮问答依赖内网模型服务（`FLAI_LLM_*`）：未配置时诚实失败，不伪造答复。

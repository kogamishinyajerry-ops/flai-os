# guide_agent changelog

## 0.1.0（2026-07-09，M6）

- 平台首个 interactive 型 Agent（ADR-0012）：多轮对话导引 + specialist Agent 推荐。
- 由 ConversationService 驱动（非 JobRunner）；会话状态存 conversations /
  conversation_messages 两表。
- LLM 边界：推荐块经 workflow.py 确定性对账 Registry + 目标 input_schema.json
  后才作为预填草案返回；幻觉 agent_id / 非法字段一律 fail-closed 剥离或作废。
- 红线：导引不创建、不签发任务，预填草案交人在创建任务页确认提交。
- system prompt 唯一来源 = 包内 prompt.md（改 prompt 必升版本）。

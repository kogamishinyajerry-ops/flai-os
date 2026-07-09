# guide_agent changelog

## 0.1.1（2026-07-09，审计诚实降级 + 硬化，ADR-0013）

- **诚实修复（能力声明对齐实现）**：agent.yaml/README 此前声称「接住上传附件」，
  但 V0.1 全链路（输入契约/API/前端）均不支持会话附件——删除该虚假声明，改为
  显式 limitation（附件在创建任务页上传；会话级附件+知识检索列 V0.2 规划）。
- 运行时硬化（平台侧，非本包代码）：单轮事务化落库+乐观并发检查；模型调用
  归因（model_calls.conversation_id）；历史窗口截断；conclude 端点。
- workflow：`_split_recommendation` 保留推荐块之后的文本（此前静默丢弃）；
  身份归因改由运行时注入，workflow 不再手工传 agent_id。

## 0.1.0（2026-07-09，M6）

- 平台首个 interactive 型 Agent（ADR-0012）：多轮对话导引 + specialist Agent 推荐。
- 由 ConversationService 驱动（非 JobRunner）；会话状态存 conversations /
  conversation_messages 两表。
- LLM 边界：推荐块经 workflow.py 确定性对账 Registry + 目标 input_schema.json
  后才作为预填草案返回；幻觉 agent_id / 非法字段一律 fail-closed 剥离或作废。
- 红线：导引不创建、不签发任务，预填草案交人在创建任务页确认提交。
- system prompt 唯一来源 = 包内 prompt.md（改 prompt 必升版本）。

# Changelog · interactive_doc_qa_agent

## 0.1.0 — Gate2/ADR-0028（T3-b 交互类零内核 diff 验证弹）

- 首版：平台首个 interactive 型消费 knowledge 内核（`context["knowledge"]`，T3-a 注入接缝）
  的 Agent。多轮会话内在 `ecm_frr_demo`（合成演示语料，public_internal）做关键词检索，命中
  语料经 sentinel 结构中和后以 `<<KNOWLEDGE>>` fence 注入交推理模型生成带出处答复；零命中
  显式标注、不调模型。
- 红线：`recommendation` 恒 `None`（绝不产任务草案/召集计划，人是唯一签发者）；答复只依据
  检索命中语料（零命中不作答）；检索经内核 default-deny 白名单（agent.yaml.knowledge.scopes）。
- 存在意义 = 判据①（交互类零内核 diff）证据：加本包 `git diff backend/app` 为空——内核由
  T3-a 一次性扩展，之后交互类工具/知识 Agent 零内核再增 diff。

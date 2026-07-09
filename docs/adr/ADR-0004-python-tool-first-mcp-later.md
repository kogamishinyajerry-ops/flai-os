# ADR-0004: 工具短期 Python Adapter，长期 MCP 化

- 状态：已接受（任务书 §6.4/§8 定版，2026-07-08）
- 背景：工具调用能力决定平台是「聊天助手」还是「工程智能体平台」；但 MCP 生态
  在内网的准入与运维成本未侦察（软件白名单/进程管理）。
- 决策：V0.1 全部工具用 Python Adapter（tool.yaml `type: python_adapter`，
  entrypoint 进程内调用）；跨 Agent 高复用工具成熟后升 MCP Server——tool.yaml
  的 `type` 翻牌为 mcp_adapter，**id 与 input/output 契约不变**，调用方零改动。
  两种 type 都必须先注册再调用。
- 替代方案：第一天全 MCP（被否：内网准入未知+V0.1 过度设计）；永远进程内
  （被否：多 Agent 并发共用重工具时进程内会成瓶颈）。
- 影响与风险：进程内工具崩溃可能连带 worker——V0.1 以 adapter「绝不抛裸异常」
  契约缓解，M1 Job Runner 再加超时隔离。

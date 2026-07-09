# hello_agent

## 用途

M0 阶段的 **Golden Sample**：一个能通过 `agent.schema.json` 校验、结构最简的
0-LLM Agent Package。新开发者写新 Agent 时，复制本目录改字段即可起步，
而不必从零摸索契约字段。

## 边界（Limitations 摘要，权威版见 agent.yaml）

- 仅用于验证平台闭环（Registry 注册 / Tool 调用 / 事件日志 / 产物落盘），
  无业务含义，禁止用于生产业务场景。
- 0-LLM：`model.profile = none`，不具备任何自然语言理解或推理能力。
- 依赖 `mock_echo`（`mock=true`）：其输出不代表任何真实工程结果。

## 包结构

| 文件 | 作用 |
| --- | --- |
| `agent.yaml` | 唯一权威元数据，Registry 注册凭据 |
| `prompt.md` | prompt 版本化位置示例（本 Agent 无实际 prompt） |
| `workflow.py` | 标准入口 `run(context)` |
| `input_schema.json` / `output_schema.json` | I/O 契约 |
| `eval_cases/` | 回归评测用例 |
| `changelog.md` | 版本变更记录 |

## 怎么跑

**M0 阶段：无平台 Runtime，workflow.py 由 `tests/test_hello_agent_workflow.py` 用
stub tool_registry/event_logger 直接驱动（eval_cases/case_001.json 即其断言来源）；
M1 起改由平台 Runtime 按 agent.yaml 加载执行。**
M1 平台 Runtime 落地后，预期跑法（待 Runtime 实现后校准本节）：

```bash
# 示例：由平台 CLI 触发一次 job 态运行（具体命令待 M1 Runtime 定稿）
flai-os run hello_agent --input '{"name": "世界"}'
```

也可在 M1 后直接单测 `workflow.run()`：手工构造一个提供
`tool_registry.call("mock_echo", ...)` 能力的最小 context 字典调用即可，
无需依赖完整平台。

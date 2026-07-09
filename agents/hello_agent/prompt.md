# hello_agent · Prompt

## 说明

本 Agent 为 **0-LLM 示例**：`model.profile = none`，运行时不发起任何模型调用，
`workflow.py` 内没有 prompt 拼装、没有 system prompt、没有模型请求。

本文件的唯一作用是**演示 prompt 版本化的存放位置**：
凡是 `model.profile != none` 的 Agent，其 system prompt / few-shot 示例 /
prompt 模板均应放在包内 `prompt.md`（或按需拆分为 `prompt/*.md`），
且每次改动必须同步升 `agent.yaml` 的 `version` 并记 `changelog.md`
——prompt 是 Agent 行为契约的一部分，不是可以静默漂移的散文。

## 本 Agent 的实际 prompt 内容

（空。0-LLM 示例无 prompt。）

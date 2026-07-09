# ADR-0002: Agent 一律封装为配置驱动的 Agent Package

- 状态：已接受（2026-07-08）
- 背景：散落在代码里的 Agent（函数+Prompt 硬编码）不可版本化、不可治理、
  不可多人协作——上一代平台的核心教训。
- 决策：每个 Agent = `agents/<id>/` 标准包（agent.yaml + prompt.md + workflow.py +
  input/output_schema.json + eval_cases/ + README + changelog），agent.yaml 必须过
  `contracts/agent.schema.json` 校验才能注册；新增 Agent 零平台核改动。
- **重要澄清（任务书内部不一致的裁决）**：任务书 §9 示例用 `status: L0_POC`，
  而 §7.1 的状态枚举是 disabled/draft/trial/released——两者语义不同轴。裁决：
  拆成正交双字段——`status`（运行生命周期：draft/trial/released/disabled，管
  「现在能不能被谁用」）+ `maturity`（成熟度治理：L0/L1/L2/L3，管「治理上走到
  哪级」）。contracts/agent.schema.json 已按此定版，反例测试钉死混用。
- 替代方案：单字段混装（被否：一个字段两种语义必然漂移）。
- 影响与风险：包字段扩展必须先改 schema+ADR（additionalProperties=false 故意
  收紧）；换来的是全平台 Agent 元数据永远机器可校验。

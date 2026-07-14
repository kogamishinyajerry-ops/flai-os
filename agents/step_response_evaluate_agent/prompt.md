# step_response_evaluate_agent · Prompt

**本 Agent 不调用任何模型**（`agent.yaml` `model.profile: none`，Runtime 已用
`_NoModelGatewayContext` 物理封死 gateway）：workflow 为纯确定性 oracle（二阶
系统超调量仿真解 vs 闭式解析解的容差判定），无 LLM 参与。本文件是 docs/02 标准
包形态的强制件，作为占位存在——不含任何生效指令。

评估的全部数字（仿真超调、闭式解析 Mp_ref、相对误差、是否在容差内）均来自包内
确定性计算；即便未来启用 LLM 做工程叙事，也须遵守「LLM 只叙事确定性数字、绝不
自算/覆盖任何数字」的铁律（参照 cfd_evaluate_agent 的 rogue-number 防御），并
升版本、记 changelog。

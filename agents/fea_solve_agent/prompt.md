# fea_solve_agent · Prompt

**本 Agent 不调用任何模型**（`agent.yaml` `model.profile: none`）：workflow 为
纯确定性有限元求解（Euler-Bernoulli 梁一阶固有频率，直接刚度法 + 广义特征值
Cholesky 二分），无 LLM 参与。本文件是 docs/02 标准包形态的强制件，作为占位
存在——不含任何生效指令。

若未来需要 LLM（如求解前的建模参数叙事确认、或结果的工程语义解读），启用本
文件并升版本、记 changelog；届时须遵守「LLM 只叙事确定性数字、绝不自算/覆盖
任何数字」的铁律（参照 cfd_evaluate_agent 的 rogue-number 防御）。

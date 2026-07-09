# control_logic_agent · Prompt

本 Agent 为 **0-LLM 纯结构化生成型**（`model.profile: none`）：workflow 是
确定性规则展开 + BFS 图算法，运行时不发起任何模型调用，无 system prompt。

本文件是 docs/02 标准包形态的强制件，作为占位存在。若未来引入 LLM 环节
（如对不可达态给出自然语言修复建议），prompt 固化于此并升版本——届时输出
仍只进「叙事/建议」通道，结构结论的判定权保持在确定性代码（宪法第四条）。

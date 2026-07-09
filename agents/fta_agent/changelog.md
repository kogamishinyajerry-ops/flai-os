# fta_agent 变更记录

## 0.1.0（M5，2026-07-09）

- 初版：FTA 辅助草案生成——首个真实走通 Model Gateway（profile=reasoning）
  与 waiting_review 人工放行链的 Agent（ADR-0011）。
- LLM 边界：草案原样存档+强制水印；requires_human_review=true；
  上游失败诚实 failed 不伪造草案。
- system prompt 固化于 prompt.md（运行时读取，无内嵌副本）。

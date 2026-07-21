# fta_agent 变更记录

## 0.2.0（2026-07-21）

- 显式声明无副作用的会话自动执行能力：完整输入与用户显式 JSON 字段映射深相等、
  且无附件时，平台可自动创建并入队 FTA 草案任务。
- `requires_human_review=true` 不变；自动化最多推进到 `waiting_review`，工程结论
  仍必须由人签发。
- 原 `admin_only` 权限不放宽；safe-auto 会用认证账户角色同时核对 `visibility` 与
  `allowed_roles`，当前仅 admin 可走该自动路径。

## 0.1.0（M5，2026-07-09）

- 初版：FTA 辅助草案生成——首个真实走通 Model Gateway（profile=reasoning）
  与 waiting_review 人工放行链的 Agent（ADR-0011）。
- LLM 边界：草案原样存档+强制水印；requires_human_review=true；
  上游失败诚实 failed 不伪造草案。
- system prompt 固化于 prompt.md（运行时读取，无内嵌副本）。

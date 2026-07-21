# control_logic_agent 变更记录

## 0.2.0（2026-07-21）

- 显式声明 `automation.session_execution=true`、`effect=none`：在完整输入、
  无附件、无计划降级且与用户显式 JSON 字段映射深相等时，允许认证导引会话自动创建并入队任务。
- 自动执行只替代机械创建动作；本 Agent 仍不获得 review/签发能力。
- 原 `admin_only` 权限不放宽；safe-auto 会用认证账户角色同时核对 `visibility` 与
  `allowed_roles`，当前仅 admin 可走该自动路径。

## 0.1.0（M5，2026-07-09）

- 初版：纯结构化生成样板（零 LLM 零工具）——状态机规范化展开 +
  BFS 不可达态分析，产物 control_logic.json / control_logic.md。
- 语义校验失败诚实 failed 并一次列出全部问题（ADR-0011）。

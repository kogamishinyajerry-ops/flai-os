# M6 收口审查记录（可追溯存档）

> 同 M1–M5 存档纪律。M6 主体 = commit 0116651（导引 Agent + interactive 会话
> 运行时，ADR-0012）。收口 R2 = 本记录随附 commit，处置双审查 8 findings +
> tamper 自证。

## 验证口径

M6 未新增第三方依赖（改动全用既有 import），无启动脚本漂移。审查回归全经
`create_app` 真实装配 + `ConversationService`/`JobRunner` + 真 SQLite + API in-process
（TestClient 即真 ASGI app）。诚实失败路径用**真实** ModelGateway + 清空
FLAI_LLM_*（fail-closed 不触网络）。全量测试 **275 passed**（M6 前 258 + 本轮
17 条 M6 用例：R0 的 12 + R2 新增 5）。真浏览器 e2e `m6_guide_acceptance.py` 5/5
绿（截图 docs/reviews/m6-guide-shots/）。

## 反方架构审查（异构 subagent 十问 + 敌意输入实测，2026-07-09，CHANGES_REQUIRED）

审查亮点：亲手对 `_validate_recommendation`/`_clean_prefilled_inputs` 打类型混淆/
注入/畸形块/`$ref` 一批敌意输入，端到端复现 P2；确认三条宪法红线全守住，无 P1。

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| P2 | P2 | `_clean_prefilled_inputs` 逐字段对**孤立子 schema** 校验，字段用 `$ref`/`$defs` 时 jsonschema 抛引用错误（**非** ValidationError 子类）逃逸成未处理 500，违反「剥离记名」契约。当前 5 Agent 不触发但是核心边界的真实契约破口 | 修：抽 `_field_valid`，在「携带原 schema `$defs`/`definitions`」的 mini-schema 上校验（引用解析回文档根），且**任何**校验异常一律判不合法→剥离（fail-closed）；单测 `$ref` schema 合法保留/非法剥离/不 500 + tamper 自证 |
| P3-1 | P3 | 会话级 recommendation 在「撤回轮」（本轮无推荐）不清空，与「以最后一次为准」注释矛盾，读会话级字段的消费者拿陈旧草案 | 修：去掉 `if recommendation is not None` 守卫，每轮都写（含 None）；单测「推荐轮→追问轮」后会话级 recommendation 清回 None |
| P3-2 | P3 | conversations.status 定义 concluded/abandoned 但无 API 转出，会话恒 active | 记录为 V0.1 已知限制（ADR-0012 影响与风险 + agent.yaml 已有「会话不落终态」口径），不伪装成已实现；终态转出/GC 留 V0.2 |
| P3-3 | P3 | interactive 路径把裸 gateway 传进 workflow，model_calls 落库 task_id/agent_id 全 NULL，无法归因会话 | 修：workflow 调 chat 时带 `agent_id=agent_config["id"]`，model_calls 可归因到导引（与 Codex P3 同一处，一并修） |
| P3-4 | P3 | post_message 不复检会话 Agent 是否仍 interactive/未 disabled，运行期改定义后语义错位 | 修：post_message 补 `disabled or not is_interactive` 复检→409；单测中途下线 Agent→409 |
| P3-5 | P3 | guide input/output schema 在 interactive 路径是「文档」非「oracle」，结构漂移无人察觉 | 修：单测断言 `_validate_recommendation` 返回值过 output_schema.json（把契约变 oracle） |

## 86gs 治理审（异源 Codex，`codex review --commit 0116651`，2026-07-09）

**P1 零。** 3 findings（2 P2 + 1 P3），与反方互补不重叠：

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| 1 | P2 | guide_agent 注册为 interactive 后仍在创建任务选择器/门户可选，用户选中只撞 409 死路 | 修：agents API 投影加 `mode`（前端路由信号）；TaskCreate 选择器过滤 interactive；AgentPortal 对 interactive 显示「开始对话」→ 导引入口；单测 API 暴露 mode |
| 2 | P2 | 失败轮**非幂等**：用户消息在 workflow 调用**前**落库，502 后重试同一句 → 历史堆重复 user 行 | 修：改为**事务性**——内存拼「历史+本轮 user」喂 workflow，仅成功才把 user+assistant 原子落库，失败零落库；单测「502→零落库→重试仍零落库」+ tamper 自证 |
| 3 | P3 | interactive model_calls 落库 task_id/agent_id 全 NULL，无法归因 | 修：同反方 P3-3，workflow 调 chat 带 agent_id |

## Tamper 自证（收口前，R2 两处核心新防御逐一咬合）

`cp` 备份→篡改→跑对应测试变红→`cp` 还原（绝不 git checkout）：

| 防御 | 篡改 | 变红测试 | 证据 |
|------|------|----------|------|
| $ref 字段校验（反方 P2） | `_field_valid` 退回孤立子 schema + 只接 ValidationError | `test_clean_prefilled_inputs_handles_ref_schema` | `$ref` 值触发 `_WrappedReferencingError` 逃逸→测试红 |
| 事务性单轮（Codex P2） | user 消息挪回 workflow 前落库 | `test_gateway_failure_502_transactional_no_partial_write` | 失败留孤儿 user 行→roles≠[]→红；成功路径不受影响 |

R0 的 LLM 边界三防御（agent_id 候选校验 / 字段剥离 / interactive-guard）tamper 咬合
见 commit 0116651 记录。两处 R2 防御篡改后全部还原（`grep TAMPER`=0，防御行在位），
还原后全量 **275 passed**。

## 收口判定

- P1：**零**（两路审查均无 P1）。三条宪法红线（人是唯一签发者 / LLM 不进判决链 /
  诚实失败 fail-closed）经反方敌意实测确认全守住。
- P2/P3：Codex 3 条 + 反方 6 条全处置（含 1 条 P3-2 显式记为 V0.1 限制，不伪装实现）。
- round cap：R0（0116651）+ R1（本记录随附收口 commit），未触第 3 轮。
- 结论：**M6 收口**。

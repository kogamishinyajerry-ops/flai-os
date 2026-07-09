# M8 协作工作台 审查存档（ADR-0016）

M8 分五阶段（P1 视觉地基 / P2 编排官 / P3 协作会话数据模型 / P4 工作台 UI /
P5 收口）。每阶段全绿 + tamper 实证 + 复跑既有 e2e。异源 Codex 治理审按「命中即审」
覆盖两个安全相关后端面：**P2 导引编排官的 LLM 边界确定性门**、**P3 协作会话数据
模型（迁移 + 悬空引用校验 + 会话视图）**。

## 自证（tamper 咬合，每处「全绿」都配一次「必红」）

| 防线 | tamper | 结果 |
|---|---|---|
| P2 orchestrate 逐个 Agent 白名单校验（fail-closed） | 移除 `agent_id not in candidate_map` 拒绝 | 幻觉召集/注入剥离/all-hallucinated-failclosed 三测齐红 |
| P3 迁移 #3 补列 | 移除 `ALTER TABLE tasks ADD COLUMN conversation_id` | 存量库升级测试红（列未补） |
| P3 悬空引用校验（先于副作用） | 移除创建前会话存在性检查 | nonexistent-conversation-404 测试红（变 200 建了任务） |

均 cp/mv 备份还原（非 git checkout），还原后复跑全绿。

## 异源 Codex 治理审（86gs gpt-5.4 xhigh）

> 环境注记：`codex review --commit` 子命令在本机非 TTY 下静默挂起（0 输出 >5min），
> 改用 codex-relay skill 记载的 `codex exec` 定向审查兜底（同 relay 同额度池）。

### P2 导引编排官（commit 4709d30）

**1 finding：[P1] 多 Agent 计划在离开 GuidePage 去创建首个任务后无法回到计划继续
召集剩余 Agent（GuidePage.vue createOneTask）** —— 复核为**「单 commit 审查范围
外」的 over-framing，最终交付（含 P4）已解决**：

- 审查针对 4709d30（P2）孤立 diff，彼时确无「回到计划」的落点，codex 判断正确；
- **P4（commit 83f2f4b）正是这条的解**：计划快照持久化在 `conversations.
  recommendation_json`，协作工作台会话视图 `/workbench/:sessionId` 从中重建**全
  roster**，未召集的 Agent 显式「尚未召集 + 去创建此任务」；TaskDetail 对带
  conversation_id 的任务给「← 返回协作会话」入口，WorkbenchHome 罗列会话——三条
  路径都能回到计划继续召集剩余 Agent；
- **grounded 反证**：`m8_collab_chain_acceptance.py` ⑤ 实测——创建 fta 任务后经
  TaskDetail 返回会话，control_logic 仍显示「尚未召集」、进度 1/2、其「去创建此
  任务」按钮在场。即「first agent only」退化在最终态**不发生**。

处置：无需改代码（P4 已解）；本条记录为「审查方按 commit 边界 over-frame，跨阶段
已闭合」的实证（宪法：审查 finding 必 grounded 复核，审查方亦会误框定）。

### P3 协作会话数据模型（commit a282116）

审查确认三处安全关键点**正确**：①迁移 #3 确在 `BEGIN IMMEDIATE` 写锁内探测补列，
重复启动并发安全且幂等；②`tasks.py` 的 conversation_id 存在性校验发生在任何任务
写入/状态迁移/事件之前，悬空引用 fail-closed；③会话成员路由仅读，不创建/签发任务。

**1 finding：[P3] 会话成员视图硬编码 limit=500 无分页 → >500 成员静默丢最旧
（conversations.py:163）** —— grounded 复核坐实（`list_tasks` 按 created_at DESC
取前 500，>500 时最旧成员经此路由不可达；「完整成员视图」名不副实）。虽场景不现实
（计划上限 5 Agent、任务人工逐个签发），但**静默截断读作「完整」正是诚实纪律的红线**，
且修复廉价——**处置：改为分页取尽**（循环 offset 直到短页，成员受人工签发约束通常
一次即止，边界正确性靠取尽保证）；补 `test_conversation_tasks_view_paginates_beyond_500`
（建 501 成员断言全返回），**tamper 实证**：回单页硬顶 → 测试红（返回 500 非 501）。

处置验证：pytest 399/399（+1 pagination 回归）· tamper 咬合 · 复跑 5 套 e2e 全绿。

## 收口

P1 由 P4 跨阶段闭合（grounded 反证），P3 已修 + 回归咬合。M8 异源 Codex 审 **P1/P2
净零、1 P3 已修**，审查环收口。数据模型迁移安全 / LLM 边界 fail-closed / 人是唯一
签发者三条经审查方独立确认守住。

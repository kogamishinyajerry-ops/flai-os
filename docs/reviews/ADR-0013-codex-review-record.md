# ADR-0013 硬化 commit 异源审查记录（Codex R1→R2）

- 对象：`1d34906`（ADR-0013 深度审计后的诚实修复与全仓硬化）
- 通道：86gs `codex review --commit`（治理审查 baseline，gpt-5.4 xhigh）
- 触发：审核 gate fail-closed 改动 = 安全边界，宪法「命中即审」同步阻塞

## R1（2026-07-09）：1 P1 + 2 P2，全部坐实全部修复

| # | 级别 | Finding | grounded 复核 | 处置 |
|---|------|---------|----------------|------|
| 1 | P1 | `init_db` 迁移 check-then-ALTER 无锁，API+Runner 双进程首启老库时输家撞 duplicate column | **坐实**：`main.py:62` 与 `jobs/runner.py:135` 确各自调 `init_db`；迁移块确无锁 | `BEGIN IMMEDIATE` 锁内复查；trace 卡点确定性竞态测 + 8×3 并发扫；tamper 拆锁双测齐红 |
| 2 | P2 | 后端改「失败零落库」但 GuidePage 乐观 user 气泡不回滚——幽灵消息+重试堆泡 | **坐实**：`GuidePage.vue:130` 乐观 push，catch 注释明言「保留」 | catch 回滚气泡+还原草稿；m6 e2e 新增失败轮检查（7/7）；tamper 拆回滚 e2e 红 |
| 3 | P2 | 事件分页取尽后，详情页 2s 轮询每次从 0 全量重翻，事件越多越重 | **坐实**：`TaskDetail.vue` loadTask 每轮调全量 `listTaskEvents` | offset 增量拉取（append-only+id ASC 前提已核）+ baseline 身份守卫；M2 e2e ④ 即该路径验收 |

处置 commit 验证链：pytest 293 绿（+2 竞态回归）· M2 e2e 8/8 · M6 e2e 7/7（+2 失败轮检查）
· 三处 tamper 全部咬红后还原复绿。

## R2：待处置 commit 复审

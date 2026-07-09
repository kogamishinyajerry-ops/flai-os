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

## R2（2026-07-09，审 56c7aff）：P1 清零；1 P2 + 1 P3，坐实修复

| # | 级别 | Finding | grounded 复核 | 处置 |
|---|------|---------|----------------|------|
| 1 | P2 | 增量轮询的 baseline 守卫只护 events：stale 轮仍写 `task.value`/清 `loadError`。放行/取消后的全量重载若先落地并停轮询，stale 轮可把状态钉回 waiting_review 且不再续轮——直到手动刷新 | **坐实且后果更重**：waiting_review 不满足 schedulePoll 续轮条件，钉死为持久态 | 交错即**整包作废**（task/events/loadError 都不动，early return；schedulePoll 依更新后状态决策）。UI 层在途竞态无确定性 e2e 手段，守卫以审查+推演验证——诚实残差 |
| 2 | P3 | 竞态测试夹具用 `DROP COLUMN`（需 SQLite ≥3.35），超出仓声明环境下限 | **坐实**：仓只声明 Python 3.10+，旧 SQLite 链接的解释器上夹具先崩 | 夹具改 rebuild-rename（CREATE AS SELECT + DROP + RENAME，全版本支持）；新夹具下重做 tamper：拆锁齐红→还原复绿 |

处置 commit 验证链：pytest 293 绿 · M2 e2e 8/8 · M6 e2e 7/7 · 迁移 tamper 咬合在新夹具下重取证。

## R3（2026-07-09，审 7532ca6）：P1/P2 清零；1 P3 按 verbatim 例外落地

- [P3] stale 轮的**失败**路径漏守卫：catch 无条件写 `loadError`，被淘汰快照的
  错误横幅可盖住更新状态且 waiting_review/终态下不再自愈。复核属实（baseline
  守卫只在成功路径）。修复=逐字落地 Codex 建议（catch 加同款 baseline 守卫，
  `baseline` 声明提至 try 外），宪法 verbatim 例外直接落地不再走 R4。
- 收口判定：三轮 P1 全程为 1（R1 迁移竞态）且当轮即清；R2 起 P1=0；R3 P2=0。
  验证链全绿（pytest 293 · M2 8/8 · M6 7/7），审查环终止于 cap 内。

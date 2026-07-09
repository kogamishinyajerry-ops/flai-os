# M5 收口审查记录（可追溯存档）

> 同 M1/M2/M3 存档纪律。M5 主体 = commit d19abad（平台泛化验证：
> control_logic_agent 结构化生成型 + fta_agent 推理辅助型，三类 Agent 同一
> Runtime）。收口 R2 = commit（本记录随附）修双审查 6 findings + tamper 自证。

## 真环境验证口径

M5 未新增任何第三方依赖（改动全用既有 import），故无 M3 式「pyproject↔启动
脚本↔README 跑测命令」依赖漂移风险。审查回归全经 `create_app` 真实装配 +
`JobRunner` 真轮询 + 真实 SQLite + review 端点 in-process 走通（TestClient 即
真 ASGI app，非桩），backfill/截断/换行三条修复路径均被真实代码路径覆盖。
fta 失败路径用**真实** ModelGateway + 清空 FLAI_LLM_* 环境变量，fail-closed 抛
ModelUpstreamError（不触网络）验证诚实失败链。

全量测试：**257 passed**（M5 前 254 + 本轮 3 条新增回归）。

## 反方审查（异构 subagent 十问 + 自制 payload 独立复核，2026-07-09，APPROVE）

审查方法亮点：亲手写四组边界状态机验 BFS 不可达分析；穷举所有 `completed`
赋值点确认 waiting_review 无绕过；真跑 fail-closed 确认磁盘零残留。**P1 零。**

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| A | P2 | README 里程碑表 M5 行仍写「待开始」——收口后状态未同步，读者误判 M5 未完成 | 修：改「完成」 |
| B | P2 | README 已知限制清单未同步 fta「真实草案依赖内网模型 key」债，环境依赖对读者不透明 | 修：新增第 9 条明示 FLAI_LLM_* 三变量 + 无 key 时 fail-closed 行为 |
| C | P3 | 审核员缺「批判性阅读草稿」判断锚点，易把 AI 草案一键批准 | 修：草案尾部加平台撰写「放行前审核指引」（纯文档提示，完整性/真实性/逻辑门/边界四条，不加代码过滤、不代替人工判定） |

过关项（有实证）：BFS 不可达分析对四组手写状态机全对；waiting_review 唯一出口=
review API 无旁路；requires_human_review 链真实走到（不是 completed）；上游失败
诚实 failed + 磁盘零伪造草案；LLM 草案强制水印 + 原样存档未删改。

## 86gs 治理审（异源 Codex，`codex review --commit d19abad`）

**P1 零。** P2×2 + P3×1：

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| 1 | P2 | fta collect_samples 在人工审核结论前落库、review API 从不回填 `samples.accepted_by_engineer`——批准/拒绝草案都存成同一无标签「成功」样本，污染下游 eval/复用 | 修：执行时留 NULL（结果未定）；review 端点 approve→回填 True / reject→回填 False（`repos.set_sample_review_outcome`）；事件消息标注回填条数；approve+reject 双向回归 + tamper 自证 |
| 2 | P2 | fta 忽略 `finish_reason`——`length` 截断时不完整草案静默进 waiting_review，审核员误当完整批准 | 修：检测 `finish_reason=="length"`→草案顶部显著截断横幅 + `fta_draft_truncated` 事件 + summary `truncated` 标注三处同步告警；截断草案仍存档（有部分价值）但停 waiting_review 不静默；截断回归 + 非截断负向断言 + tamper 自证 |
| 3 | P3 | control_logic `_md_escape` 只挡 `\|` 不挡换行——schema 允许状态名/条件为任意字符串，含 `\n` 时 md 表格断行整表错位 | 修：换行（`\r\n`/`\r`/`\n`）归一为空格再写单元格；换行回归（含表格 `\|` 边界计数完整性）+ tamper 自证 |

## Tamper 自证（收口前，三防御逐一咬合实证）

用 `cp` 备份→逐个篡改防御→跑对应测试确认变红→`cp` 还原（绝不 git checkout）：

| 防御 | 篡改 | 变红测试 | 证据 |
|------|------|----------|------|
| Codex-1 样本回填 | `set_sample_review_outcome` WHERE 改永不匹配 | `test_fta_e2e_..._approve` + `test_fta_reject_marks_sample_not_accepted` | 回填失效→review 端点 500→2 测试红 |
| Codex-2 截断告警 | `truncated` 恒 False | `test_fta_truncated_draft_flagged_not_silent` | 横幅缺失→「草案不完整」not in draft 红 |
| Codex-3 换行归一 | `_md_escape` 退回只挡 `\|` | `test_control_logic_md_normalizes_newlines_in_cells` | md 实际输出 `温度过高\n且压力超限 \|` 断行→红 |

三防御全部咬合；篡改后全部还原（`grep TAMPER` 残留=0，关键防御行在位）；
还原后全量 **257 passed**。

## 收口判定

- P1：**零**（两路审查均无 P1）。
- P2/P3：Codex 3 条 + 反方 3 条全处置，均落地代码/文档 + 回归测试 + tamper 自证。
- round cap：R0（d19abad）+ R1（本记录随附收口 commit），未触第 3 轮。
- 结论：**M5 收口**。

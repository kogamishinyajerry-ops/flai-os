# ADR-0017 knowledge_qa_agent（Wave 2）审查记录

> 首个 knowledge_qa 类 Agent：批量问题 → 内核检索 → LLM 归纳草案（带出处）→
> waiting_review。本记录存档治理审三轮全程与 tamper 证据（宪法：声明 ≤ 证据）。

## 验证环总览

| 环 | 执行者 | 裁决 | 处置 |
|---|---|---|---|
| SPEC witness 自证（1-8） | 主控 | 10 witness 全绿（7b56aac） | 含真仓装配冒烟/注入中和/截断 banner/诚实失败双向/无 key fail-closed |
| Codex 治理审 R0 | codex（gpt-5.6-sol ultra） | **CHANGES_REQUIRED：1 P1 + 4 P2** | 五条 grounded 复核全成立 → R1 修复 cd2ba61 |
| Codex 复审 R2 | codex | **CHANGES_REQUIRED：2 P2** | 两条复核成立 → R2 修复 1d69d25 |
| Codex 复审 R3（cap 末轮） | codex | **无 P1，1 P2**（版本治理） | verbatim 例外直接落地 8b6dc34，轨道收口 |
| tamper 环 R1 | 主控 | 6/6 咬合（T1-T5b） | 下详 |
| tamper 环 R2 | 主控 | T10 咬合 | 下详 |

## Codex R0 findings（1 P1 + 4 P2，全采纳 → cd2ba61）

1. **P1 问题文本未中和**：questions[] 伪造 `<<KNOWLEDGE>>` 块可冒充平台检索
   语料，绕过 scope-only 保证 → question 同语料一样过 `_neutralize_sentinels`。
2. **P2 演示数据无命中级合成标记**：BM25 命中的是行不是文件头 → 两份 CSV
   每行首列「数据性质=合成演示数据（非真实记录）」+ 草案头部 scope 声明行。
3. **P2 引用键不唯一**：同名文件 chunk 编号碰撞 → 行内引用改 `[source · chunk]`
   复合键（prompt.md 升版）。
4. **P2 无 prompt 预算**：hit 文本无界 × top_k ≤10 × 问题可近 256KB → 单命中
   4000 字符截断（显式标记）+ questions maxLength 2000，聚合上界 ≈42K 字符。
5. **P2 只盯 finish_reason=length**：content_filter 部分输出静默过审 → 白名单
   判定（非 stop 一律亮"草案不完整"banner，原始值透出）。

## Codex R2 findings（2 P2，全采纳 → 1d69d25）

1. **P2 非标量 finish_reason 炸任务**：JSON 数组/对象进 frozenset 成员测试
   TypeError，任务 failed 且不亮 banner → 非 str 先挡，判异常收尾不炸。
2. **P2 changelog 缺 0.1.1 条目**：02 标准 §6 强制审计轨迹 → 补条目。

## Codex R3 finding（1 P2，verbatim 落地 → 8b6dc34）

- **P2 版本复用**：R2 行为变更沿用已占用的 0.1.1——tasks/feedback 只持久化
  agent_version，前后执行形态审计不可区分 → 升 0.1.2，changelog 拆分
  0.1.1（纯 R1）/0.1.2（R2）。cap 末轮无 P1，纯机械修复走 verbatim 例外
  不再开轮，轨道按宪法收口。

## tamper 记录（逐条注伤 → witness 必红 → 还原绿；脚本 tamper_r1/r2.py）

| # | 篡改 | 该咬的 witness | 结果 |
|---|---|---|---|
| T1 | 问题不过中和 | test_question_injection_neutralized | 咬合 ✓ |
| T2 | 撤单块 4000 预算 | test_per_hit_prompt_budget_truncates | 咬合 ✓ |
| T3 | 白名单回退成只盯 length | test_content_filter_finish_flagged_incomplete | 咬合 ✓ |
| T4 | 撤 questions maxLength | test_question_over_max_length_rejected | 咬合 ✓ |
| T5a | 撤草案 scope 声明行 | test_synthetic_marker_reaches_prompt_scope_line_in_draft | 咬合 ✓ |
| T5b | 撤两份 CSV 行级合成标记 | 同上 | 咬合 ✓ |
| T10 | 撤非标量 finish_reason 防线 | test_non_scalar_finish_reason_flagged_not_crash | 咬合 ✓ |

## 测试证据（全部真跑）

- 包内 witness：`backend/tests/test_knowledge_qa_agent.py` 16 passed（10 SPEC +
  5 R1 + 1 R2）。
- 全量：428 passed（2026-07-09，工作树含并行 M8 session 未提交改动；本包与
  内核相关 76 测试独立跑过全绿）。
- 内核零改动纪律：Wave 2 三个 commit 均不触碰 backend/app/（R1/R2 内核修复
  属 Wave 1 补跑审轨道，见 ADR-0015 审查记录）。

## 残差（显式标注）

- 真实 LLM 归纳质量 DECLARED-NOT-VERIFIED：本地 stub 只验调用链与防线，
  真实业务价值待 EAR/M4 内网闸门解锁后用真实 ECM/EM/FRR 语料评估。
- eval 真值集（evals/knowledge_qa/）随内网真语料建设，当前仅 eval_cases 冒烟。
- changelog 条目本身无自动化 witness（注册层不校验 changelog 内容）——
  治理靠审查流程约束，已记 retro 侯选。

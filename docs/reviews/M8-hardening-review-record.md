# M8 异源硬化轮 · Codex 5.6-sol 三轮审查存档（2026-07-09）

codex 原生二进制恢复并升级 gpt-5.6-sol/ultra 后，用户指令「深度配合 codex 联合开发优化」。
对已交付的 M8（编排官+协作工作台）/ M7（会话附件）/ Wave1（Knowledge 内核）三笔做异源
安全审 → grounded 复核 → 修复 → 复审，round cap=3，R2 收于 APPROVE。**谁写另一方审**：
codex 出 findings，主控（Fable-5）grounded 复核并写修复，codex 复审修复。

## R0：codex 5.6-sol 安全审（8×P1 + 1×P2，CHANGES_REQUIRED；确认 R5 守住）

主控对每条独立 grounded 复核后判：**核心红线（人是唯一签发者 / LLM 不进判决链 / 外部
内容不自动执行）全程未破**——所有"绕过"最终都撞两道真闸：人工签发 + 任务创建时 Runtime
对完整 schema 再校验。故 8 条 P1 全降级；但其中 6 条是真实 P2 缺口（#3/#7/#8 是敌意输入×
契约维，主控独立审确实漏掉，异源价值所在）。

| # | 不变量 | codex 评 | 复核后 | 处置 |
|---|---|---|---|---|
| 1 | R1 | P1 | P2 | `_field_valid` 漏根层 allOf/if/not/dependentSchemas → 加 `_partial_object_valid` 整体复验 |
| 2 | R1 | P1 | P2 | 计划无字节顶 → `_MAX_PLAN_BYTES` + 审计列表条数/长度顶 |
| 3 | R2 | P1 | P2 | 会话 concluded 后仍可挂任务（打脸「结束协作只读」claim）→ API 校验 active 否则 409 + 单 Agent conclude 后置 |
| 4 | R3 | P1 | P3 | 预算耗尽摘要把文件名拼到 fence 外 → 只出受信计数 |
| 5 | R3 | P1 | 已知残留 | fence 内附件仍能影响合法计划 → R3 核心未破（不自动执行，人签兜底，ADR-0014 已披露）；两阶段架构记 V0.2 |
| 6 | R4 | P1 | 交并发作者 | symlink 让 restricted 语料伪装 public → knowledge lane，并发作者未提交改动已在 ingest 加 resolve 检查 |
| 7 | R6 | P1 | P2 | task 创建接口可返违 task.schema 响应（空 name/created_by、重复 file_id）→ 三 field_validator |
| 8 | R6 | P2 | P2 | 兜底事件 `agent_id:null` 违 event 契约 → `_decode_event` NULL 省略 |
| 9 | R6 | P2 | P3 | 分页并发非一致快照 → keyset 记 V0.2（codex 纠正：非"不可达"，只是需异常大会话） |
| R5 | — | OK | OK | 迁移三 ALTER 同 BEGIN IMMEDIATE + conclude 只改 conversations（双方一致） |

## R1：codex 复审 6 修（CHANGES_REQUIRED，但验证大部分）

- **#1/#4/#7/#8 判 OK**；**#6/#9 接受延后**；**#5 codex 改口 accept V0.2**（「不是当前附件指令
  自动执行的 P1 授权绕过」——主控 grounded push-back 获异源认同）。
- 仅两条需修：
  - **#2 WEAK**：(a) `len(raw)` 数字符非 UTF-8 字节（CJK 17K 字≈51K 字节绕顶）；
    (b) 无 schema 早退路径绕过 stripped 收界；(c) 限额内深嵌套 JSON 抛未捕获 RecursionError。
  - **#3 BROKEN**：active 检查与 INSERT 非原子，并发 conclude 可挤在中间。

## R2：修复 + APPROVE

- **#2** → `len(raw.encode("utf-8"))` 字节闸 + `_bounded_stripped()` 两路统一收界 +
  except 纳 `RecursionError`。
- **#3** → `BEGIN IMMEDIATE` 写锁包「复查 active + create_task INSERT」与 conclude 串行化
  （set_task_status 自带事务，故本事务只包这两步，提交后再迁 queued；BEGIN 在 try 外、
  except 内 ROLLBACK）+ **确定性竞态测**（仿迁移竞态测：trace 停在 INSERT、rival 短 timeout
  抢锁归档；修好→rival 被锁拒、任务落 active 会话；未修→任务落已归档会话，不变量破）。
- **codex R2 VERDICT: APPROVE**——#2/#3 均 [OK]；确认字节闸先于 json.loads、RecursionError
  真被捕获、两 stripped 出口统一；#3 BEGIN IMMEDIATE 正确串行化，ROLLBACK 结构安全，
  竞态测终止且咬住移除锁。

## Tamper 咬合证据（10 witness，全部 RED→GREEN 还原 byte-identical）

R1 六修：①根组合器复验 ②计划字节顶 ③concluded→409 ④文件名不出 fence ⑦请求校验
（唯一性 + 非空白两 kind）⑧event NULL agent_id 省略。
R2 四修：①字节非字符（CJK 绕过）②深嵌套 RecursionError 不崩 ③早退路径 stripped 收界
④原子 BEGIN IMMEDIATE（竞态测：移除锁 → 任务落已归档会话 RED）。

## 验证

- 非 knowledge 全套 **343 passed**（含 11 条本轮新回归闸）。
- 真机 e2e：collab-chain **7/7**（含 conv 归属创建 + 结束协作归档只读）· M6 单 Agent **10/10**
  （conclude 后置不破单 Agent 流）· orchestrator **4/4**。

## 并发工作纪律

全程用户在另一终端并行改 knowledge（HEAD 7b56aac→cd2ba61→3655f34 多跳）。主控本轮改动
（guide_agent/workflow · api/tasks · runtime/attachments · storage/repos · GuidePage · TaskCreate
+ 三测试 + ADR-0016）与 knowledge lane 完全 disjoint；跑测撞用户 mid-edit 的 knowledge 假红
时用 `--ignore-glob='*knowledge*'` 隔离取干净信号；#6 交并发作者收口，不越界代改。
codex 原始三轮输出留会话 scratchpad（本记录为入仓权威摘要）。

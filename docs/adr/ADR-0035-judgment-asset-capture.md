# ADR-0035：判断资产采集与人机意见物理隔离

- 状态：Accepted（M4 前仪器；不解锁 P2.5–P2.8）
- 日期：2026-07-19
- 关联：ADR-0007、ADR-0008、ADR-0019、ADR-0025、`docs/COMPOUNDING-M4-REBASELINE.md`

## 背景

既有人工签发只在任务事件中保存 `approve/reject + 自由评论 + reviewer 显示名`。
它足以证明任务经过人工动作，却会丢失「为什么驳回」、精确 username 与机器顾问意见的
配对关系。历史数据无法可靠反推这些事实；若等 M4 运行数月后再装仪器，缺失判断不可
回溯补采。

同时，FLAi-OS 的宪法边界不变：LLM 只可提供候选意见，人是唯一签发者。为了统计方便
把两类记录塞进同一 actor/action 表，会让机器意见在结构上接近 `approve/reject` 判决链，
因此不可接受。

## 决策

### 1. 三张只追加账本，机器意见与人工判决物理隔离

- `task_review_advice` 只记录机器顾问候选：真实 `model_call_id`、advisor/model 快照、
  `clear | concerns | abstain`、结构化疑点与同任务 `evidence_file_ids` 指针。指针只可
  引用任务冻结输入或权威输出中的真实文件；空数组诚实表示本条意见没有可定位文件，
  不得用自由文本路径冒充稳定证据。它没有任务状态迁移能力，也不使用
  `approve/reject` 词汇。
- `task_human_decisions` 只记录具名人工终裁：exact username、显示名快照、
  `approve | reject`、结构化理由、可选说明与可空 `paired_advice_id`。一项任务最多一条
  人工终裁。
- `task_review_event_witnesses` 对每条 `review_approved/review_rejected` 保存逐字快照：event
  内部整数身份、公开 id、task/agent、类型、level、message、payload 与时间。新事件只允许
  `structured_v1`，且由同一 INSERT 的 `AFTER` trigger 原子追加；切换前事件只可在首次严格
  代际安装时封存为 `legacy_pre_instrumentation`，运行时不能再制造 legacy。
- 三表禁止 UPDATE、DELETE 与任何 UNIQUE 冲突上的 `INSERT OR REPLACE`；旧记录只能追加，
  不能被“修正”为更好看的结论。`model_calls` 与三张判断账本的内部 rowid 必须为正；默认
  `NEW.rowid=-1` 只作 SQLite 自动分配 sentinel，不参与冲突匹配，显式非正身份直接拒绝。
- 一旦 model call 已被 advice 引用，该 model call 同样禁止 UPDATE、DELETE、冲突
  INSERT/REPLACE，以及由未见证 sibling 发起的 `UPDATE OR REPLACE` 身份碰撞，避免在
  `recursive_triggers=OFF` 下隐式逐出被见证行，再用伪造 sibling 占回同一 id。
- 空账本可由 `init_db` 收敛受管对象；非空账本启动前必须已经通过完整 schema witness。
  若 trigger/index 缺失或变成 no-op，启动直接失败并保留现场，不能自动修复后冒充历史
  一直受只追加保护。health/readyz 还逐轮扫描三张账本、被引用 model call 的正内部身份与
  persisted provenance；
  drop guard、改数据、恢复同一 trigger SQL 不能仅靠结构回绿。

### 2. 驳回原因冻结为六类

`source_doubt | method_error | conclusion_overreach | insufficient_evidence |
classification_issue | other`，分别显示为数据源疑点、方法错误、结论越界、证据不足、
密级问题、其他。

- reject 必须选择一类；`other` 必须有非空说明；说明上限 2000 字符。
- approve 不得携带驳回原因。
- 两个既有签发入口共用同一前端合同，服务端与仓储层再次独立校验，避免旁路。

### 3. 人工终裁仍在既有原子事务内

同一个 `BEGIN IMMEDIATE` 必须同时完成：

1. 校验任务仍为 `waiting_review` 与配对 advice 属于同一任务；SQLite 的
   `BEFORE INSERT` witness 也要求 decision 写入当刻任务仍为 `waiting_review`，
   防止绕过 repository 留下与状态机矛盾的终裁事实；
2. 追加 `task_human_decisions`；
3. 迁移任务状态并回填 sample 标签；
4. 追加既有 `review_approved/review_rejected` 见证事件。

任一步失败则全部回滚。K1 只继续认首次严格代际已逐字封存的切换前 review event，避免把
真实历史已签任务错误封死；切换后新事件
payload 固定为六个且仅六个唯一键：`reviewer/reviewer_username/comment/decision_id/
reason_code/paired_advice_id`，不改变事件类型与状态机。SQLite 写门要求结构化 review event
与 decision 精确一致且一项 decision 只能有一条 signer event；重复 JSON key、额外 key、
孤立 decision id、第二条 signer event 或切换后无 `decision_id` 的 review event 均零写拒绝。
事件落库后由 `task_review_event_witnesses` 同步封存 exact bytes 与内部 id；删 trigger 后改写
event 的 id/time/message/payload，再恢复同名 SQL，deep witness 仍然为红。
独立 `audit.log` 同样只记录这三个受控字段，不记录自由评论或机器疑点正文。

### 4. 配对是 provenance，不是正确性

机器 advice 必须绑定同任务的一次真实成功 model call；禁止按时间猜“最近一次调用”。
`advisor_id/model_profile/model_name` 必须与该 model call 的 provenance 做 null-safe 精确
比对，不能拿真实 call id 给伪造的模型快照背书。现有 `model_calls` 没有 agent version
列，因此 `advisor_version` 仍由冻结 manifest 的调用方提供，不能宣称已由调用记录反证。
`paired_advice_id` 可空，且只能精确指向同任务 advice。配对仅证明两条记录被明确关联，
不证明人阅读过意见，更不证明模型正确。

`provenance_integrity` 会重放本代际可验证的持久合同：advice 与 model call 的 task、success、
advisor/profile/model 精确一致；doubts/evidence 的类型、枚举、长度、去重与文件存在性有效；
decision 与 task 终态、同任务 paired advice，以及唯一 exact review event payload 双向一致；
逐事件 witness 与 event 的内部 id、task/agent/type/level/message/payload/created_at 逐字一致。
reviewed terminal 的 `updated_at/finished_at/error_message` 也必须可由 decision 精确重建：两类
时间等于 decision 落账时刻，approve 清空 error，reject 使用固定结构化渲染。进入
`waiting_review` 时可更新一次 `updated_at`，离开后这些字段随其它 provenance 一起冻结。
advice、decision 与 structured event witness 的时间必须是 TEXT，且只接受 UTC 秒级或六位微秒
两种 canonical ISO 字节编码；空格/任意分隔符、非六位小数、BLOB、无时区或非 UTC 值都不能
进入受信窗口。三张判断账本同时执行 FK 与 CHECK integrity 检查。
任何一项不成立，部署自检、health、readyz
与使用报告均 fail-closed；报告只给 `unknown_untrusted_judgment_ledger`，不得继续输出 measured
人签计数。

M4 前没有真实 R0 advisor runtime，因此本批只安装可信写入 seam，不生成夹具式生产记录。
在真实 advisor 接入前，人机一致率分母为零时必须报告“未知/无可比样本”，不得报 0%。

### 5. 历史数据不伪回填

- 不从旧自由评论推断 reason code；
- 不从显示名反推 username；
- 不给旧 reject 统一灌 `other`；
- 不从旧 review event 补造 human decision 或 advice。

首次严格代际安装会把当时存在且无 exact decision 的 `review_*` 事件逐字封存；只有这些
sealed event 可继续承担历史 K1 见证。报表把它们单列为 `legacy_unstructured`，可信
approved/rejected 只按 `task_human_decisions.action` 统计；同一任务上同时存在 legacy 与
structured event 也不得互相吞并或重复计入可信人签。结构化覆盖率只从真实 decision/event
记录起算。

## 后果与边界

- reject 请求合同有意收紧：缺原因返回 422 且零写；approve 兼容原路径。
- 机器顾问记录不进入自动批准、自动拒绝、自动发布或任务状态迁移。
- 本 ADR 不实现角色轴、点名签收件箱、评审梯子 R1+ 或 P2.5；这些仍受 N10 + M4 双门冻结。
- 自由说明与机器疑点可能包含敏感内容；当前不新增读取端点。未来读取必须经过任务分级
  gate，不能把存储完成冒充为已授权展示。
- live probe 对判断账本执行 O(N) persisted provenance 扫描；在库外不可回拨见证落地前，
  这是防结构假绿的有意成本。
- API 与 worker 可能并发启动；`init_db` 获取唯一 schema-convergence 写锁时使用 30 秒有界
  busy budget，拿锁后立即恢复普通运行时写入的 5 秒预算。这样深审超过 5 秒不会让并发启动者
  直接崩溃，也不把所有在线请求的锁等待无界放大。
- 当前 task manifest 不能反推 evidence 在 advice 创建时是否属于该任务：advice 可能早于
  `waiting_review`，manifest 随后合法演进。当前只验证 evidence file 仍存在；要验证历史成员
  关系需保存 advice-time manifest snapshot。
- `advisor_version` 仍无法由 `model_calls` 反证；若高权限写者同时改写 model call、advice、
  decision、task event 与 task，使整套本地状态重新自洽，state-based anti-join 也无法找回原值。
  关闭这些边界需要不可变规范快照与库外锚定 digest/hash chain。
- 仓内曾存在但未部署的“两张判断表、无逐事件 witness 表”中间开发代际，不会被自动补表洗绿；
  `init_db` 对该 residue fail-closed。若保留了这类开发库，需要人工取证迁移或重建，不能把
  当前首次切换 backfill 套到已经开始写入的中间代际。

## 验证

- 请求负例：reject 缺/未知原因、approve 带原因、`other` 空说明、超长说明、伪造身份；
- 原子性：decision/event/sample/task 任一写入失败时整组回滚，并发双签只成功一次；
- provenance：foreign advice、失败 model call、跨任务配对均拒绝且零写；
- 不可变性：三表 UPDATE/DELETE/主键或 UNIQUE 冲突 REPLACE、model-call sibling
  `UPDATE OR REPLACE` 全部失败；判断账本/model call 非正 rowid 拒绝且不投毒后续正常写；
  drop/mutate/restore 后 model call、advice、decision/task/event 的 deep witness 仍红；
- event 固定点：一 decision 一 signer event；孤立事件、重复事件、重复/额外 JSON key 与终态
  时间/错误字段漂移均令 provenance 红；切换后伪 legacy 零写，切换前 legacy 原样封存且不补造
  decision；event 内部 id/time/message/payload 改写与 BLOB decision 时间均令 witness 红，Python
  解码不得与 SQLite witness 分裂；
- 部署：persisted provenance 损坏令 local selfcheck 与 health 见证失败、readyz 503；正常
  approve/reject、无 paired advice 以及 advice 后 manifest 合法演进仍保持绿色；
- 并发启动：schema lock acquisition 使用独立有界预算，完成锁获取后恢复普通 5 秒预算；
- 报告与概览：可信 approve/reject 只读 decision；legacy 单列；judgment witness 红时
  `usage_report.py` 返回 unknown，`/stats/overview` 返回“未知（判断账本不可信）”；
- UI：TaskDetail 与 StatusCenter 共用六类合同，approve 直签，reject 必须先过结构化校验。

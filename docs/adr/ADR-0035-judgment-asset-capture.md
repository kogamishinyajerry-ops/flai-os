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

### 1. 两张只追加表，物理隔离

- `task_review_advice` 只记录机器顾问候选：真实 `model_call_id`、advisor/model 快照、
  `clear | concerns | abstain` 与结构化疑点。它没有任务状态迁移能力，也不使用
  `approve/reject` 词汇。
- `task_human_decisions` 只记录具名人工终裁：exact username、显示名快照、
  `approve | reject`、结构化理由、可选说明与可空 `paired_advice_id`。一项任务最多一条
  人工终裁。
- 两表禁止 UPDATE、DELETE 与任何 UNIQUE 冲突上的 `INSERT OR REPLACE`；旧记录只能追加，
  不能被“修正”为更好看的结论。
- 一旦 model call 已被 advice 引用，该 model call 同样禁止 UPDATE、DELETE 与冲突
  REPLACE，避免事后改写 task/status/model provenance 使 advice 悄然失真。
- 空账本可由 `init_db` 收敛受管对象；非空账本启动前必须已经通过完整 schema witness。
  若 trigger/index 缺失或变成 no-op，启动直接失败并保留现场，不能自动修复后冒充历史
  一直受只追加保护。

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

任一步失败则全部回滚。K1 继续认既有 review event，避免把历史已签任务错误封死；新事件
payload 只增加 `decision_id/reason_code/paired_advice_id`，不改变事件类型与状态机。
独立 `audit.log` 同样只记录这三个受控字段，不记录自由评论或机器疑点正文。

### 4. 配对是 provenance，不是正确性

机器 advice 必须绑定同任务的一次真实成功 model call；禁止按时间猜“最近一次调用”。
`advisor_id/model_profile/model_name` 必须与该 model call 的 provenance 做 null-safe 精确
比对，不能拿真实 call id 给伪造的模型快照背书。现有 `model_calls` 没有 agent version
列，因此 `advisor_version` 仍由冻结 manifest 的调用方提供，不能宣称已由调用记录反证。
`paired_advice_id` 可空，且只能精确指向同任务 advice。配对仅证明两条记录被明确关联，
不证明人阅读过意见，更不证明模型正确。

M4 前没有真实 R0 advisor runtime，因此本批只安装可信写入 seam，不生成夹具式生产记录。
在真实 advisor 接入前，人机一致率分母为零时必须报告“未知/无可比样本”，不得报 0%。

### 5. 历史数据不伪回填

- 不从旧自由评论推断 reason code；
- 不从显示名反推 username；
- 不给旧 reject 统一灌 `other`；
- 不从旧 review event 补造 human decision 或 advice。

旧 `review_*` 事件继续承担历史 K1 见证；报表需把它们单列为
`legacy_unstructured`，结构化覆盖率只从新表真实记录起算。

## 后果与边界

- reject 请求合同有意收紧：缺原因返回 422 且零写；approve 兼容原路径。
- 机器顾问记录不进入自动批准、自动拒绝、自动发布或任务状态迁移。
- 本 ADR 不实现角色轴、点名签收件箱、评审梯子 R1+ 或 P2.5；这些仍受 N10 + M4 双门冻结。
- 自由说明与机器疑点可能包含敏感内容；当前不新增读取端点。未来读取必须经过任务分级
  gate，不能把存储完成冒充为已授权展示。

## 验证

- 请求负例：reject 缺/未知原因、approve 带原因、`other` 空说明、超长说明、伪造身份；
- 原子性：decision/event/sample/task 任一写入失败时整组回滚，并发双签只成功一次；
- provenance：foreign advice、失败 model call、跨任务配对均拒绝且零写；
- 不可变性：两表 UPDATE/DELETE/主键或 UNIQUE 冲突 REPLACE 全部失败；
- UI：TaskDetail 与 StatusCenter 共用六类合同，approve 直签，reject 必须先过结构化校验。

# ADR-0033：稳定会话 Owner 与结构化澄清 Question

- 状态：Accepted
- 日期：2026-07-19
- 范围：P2.3

## 背景

会话原先只保存 `created_by` 展示名。展示名允许重复，若据此判权，两个不同
`username` 的同名用户可以读取、发言、结束或引用彼此会话。与此同时，Guide 的澄清
只能作为普通 assistant 文本展示；前端若从问号或 `recommendation=null` 猜控件，既
不稳定，也容易把普通回答错误接入 task review。

FLAi-OS 的红线要求：唯一签发者是人；LLM 不进入判决链；权限与生命周期必须
fail-closed；不可变身份与回答事实不能靠 UI 约定维持。

## 决策

### 1. 会话 owner 使用认证 username

- 迁移 #14 为 `conversations` 增加 nullable `created_by_username`。
- 新会话同时保存展示名 `created_by` 与认证 principal 的 exact `username`。
- 所有普通用户会话读取、发言、结束、model-call/task 聚合及显式
  `conversation_id` 引用只按 exact username 判权。
- foreign、legacy NULL 与真实不存在统一返回 404；不从 display name 猜测或回填。
- non-NULL owner 不可变；同 id 的 `INSERT OR REPLACE` 也由 SQLite trigger 拒绝。
- 仓储创建调用必须显式传非空 owner；普通仓储入口对 `None`、空串与纯空白一律
  fail-closed。只有显式的 pre-P2.3 raw seed/迁移路径可以保留历史 NULL 事实。

### 2. Question 是独立的普通澄清聚合

Guide 只有输出唯一完整 `<<QUESTION>>...<<END_QUESTION>>` envelope 时，平台才创建
Question。普通问句永远只是文本。Question v1 只支持：

- `single_choice`：2–6 个冻结选项，标签经 `strip().casefold()` 后必须唯一，界面固定另给
  自定义文本逃生口；
- `free_text`：无选项。

模型只能提议 `kind/prompt/description/options`。问题 id、选项 id、接收 username、
revision、TTL、状态与时间全部由服务端生成。Question 与 PLAN 互斥；显式 envelope
一旦损坏，整轮 502 且零消息、零 Question 写入。平台在拆解任一 envelope 前先验证
原始回复的完整 sentinel 拓扑；重复、未闭合、嵌套或两类 envelope 共存均不得被“只取
第一块”降级接受。

### 3. 公开消息 id 与存储

迁移 #15：

- `conversation_messages.message_id = msg_<32hex>` 成为稳定公开引用；内部自增 id 只
  用于插入顺序。legacy 行在迁移写锁内一次性回填，重复 init 不改写。
- `conversation_questions` 保存冻结规格、exact `asked_to_username`、revision 1、
  prompt message、服务器时间、一次性 resolution tuple 与回答/回复 message id。
- 不持久化可漂移的 `status`。投影顺序固定为：`answered`；显式 `superseded`；
  显式或 `now >= expires_at` 的 `expired`；否则 `pending`。
- 同会话、同接收人在任一时刻最多一个 unresolved Question。规格不可更新，行不可
  DELETE/REPLACE；resolution 只能从全 NULL 一次性闭合。
- `asked_to_username` 必须逐字等于会话 `created_by_username`；TTL 必须逐微秒等于
  `created_at + 24h`。仓储与 SQLite trigger 双层守门，模型和客户端不能设置、转派或延长。
- Question 时间统一规范化为 UTC、六位微秒的 RFC 3339 字符串；SQLite 使用固定宽度
  字符串精确比较，不借 `julianday()` 的毫秒舍入判定回答边界。
- `question_output_schema.json` 是 Agent 包完整性与评测冻结的一部分；缺失、损坏或同版本
  漂移均不得注册或复用旧评测证据。

### 4. Answer API 与冲突语义

唯一写入口：

`POST /api/conversations/{conversation_id}/questions/{question_id}/answer`

请求只含 exact integer revision 1（JSON `true` 不等于 1）、稳定 `submission_id` 与严格 payload（冻结 option id 或非空
文本）。answerer 只从登录 principal 派生；请求中的额外 actor、review、action 或
状态字段一律 422。

- missing/foreign/legacy：404，零 LLM、零写入；
- 非法形状/未知选项：422，零 LLM、零写入；
- concluded、expired、superseded、不同 submission 的重复回答：409；
- 同一 submission + 同一规范化 payload：幂等 200 replay，复用原 message ids，
  不再次调用模型或写入；
- 同一 submission + 不同 payload：409。

pending Question 存在时，普通 `/messages` 返回 409，防止绕过结构化回答。Question
过期后可继续普通对话；平台在下一次写事务中把旧 unresolved 事实闭合为 expired。
人工 conclude 会在同一事务把尚未到期的 pending Question 闭合为 superseded，避免终态
会话继续投影一个看似可回答的问题。

### 5. 原子边界

模型调用仍在 SQLite 事务外，避免持写锁等待内网模型。提交时使用
`BEGIN IMMEDIATE`，重新检查 exact owner、会话 active、消息 baseline、Question
pending 与精确期限，然后在一个事务内：

1. 写 canonical user answer message；
2. 写 assistant response message；
3. CAS 闭合旧 Question；
4. 可选创建下一 Question；
5. 更新会话 recommendation 快照。

任一步失败全部回滚。并发回答可以浪费一次模型调用，但最多一个事务提交；输家没有
半条消息或半个回答。模型失败时原 Question 保持 pending。

### 6. 治理与 UI 语义

Question answer 不导入或调用 task review，不改变 task、task event、sample 或 gate。
问题卡使用 clay 工作槽；过期/状态不明用 amber；真实请求失败用 red。不得使用 green、
teal、批准、驳回、签发或推荐选项语义。卡片必须支持键盘、390px、暗色、focus 与
reduced-motion，并在状态不确定时先 resnapshot。一个可信 snapshot 最多只能带一个
`pending` Question；否则整包拒绝。pending Question 独占当前会话写轴，composer、附件与
Agent 入口全部不可写；到期后按精确时间投影自动解锁。程序化滚动同样服从
`prefers-reduced-motion`。同 revision 的 terminal resolution 不接受迟到 pending 或相互
矛盾的 terminal 覆写。

### 7. 存储与部署可信门

P2.3 的启动、health、readyz、本地部署自检与远端部署自检共用同一组五键 witness：

- `conversation_table_shape`；
- `message_table_shape`；
- `question_table_shape`；
- `required_indexes`；
- `required_triggers`。

身份表只接受 fresh P2.3 与真实 M6/M7 `ALTER TABLE` 历史产生的有限有序列变体；Question
表按完整 SQL 与 `table_xinfo` 精确校验。三张表当前冻结 8 个受管索引与 28 个受管
trigger；未知列、约束、表 suffix、索引或 trigger 一律令 witness 为 false，并让启动或
readyz fail-closed。同名但漂移的受管对象只在迁移写锁内按 canonical DDL 修复。历史审计
还会拒绝重复/非法会话身份、孤儿消息、非法稳定 id，以及 Question 规格、大小写折叠后
重复选项、时间、TTL、resolution link、顺序或唯一性毒数据。后续迁移若新增任何列、
索引或 trigger，必须在同一提交显式升级本合同。

## 后果

- 会话隐私不再依赖可撞名展示字段；存量 ownerless 会话不会被冒认，但普通用户也
  无法直接访问，未来若需要认领必须另做显式 CAS-on-NULL 管理流程。
- Question/Answer 获得可恢复、可重放、可审计的稳定事实轴，同时保持人签链完全独立。
- 每次回答仍可能进行一次同步模型调用；网络超时由稳定 submission id 支持安全重试。
- 部署自检必须同时咬合 P2.3 runtime generation 与上述五键 schema witness；旧 API、旧
  数据库或运行中 schema 漂移不能复用早期任务归因标志获得假绿。
- 本决策不包含搜索、消息/产物深链或会话生命周期写语义。P2.4 只负责只读搜索
  projection 与稳定深链；标题、重命名、真正归档、审计和并发更新属于 P2.6。P2.4 不得
  为寻址修改本 ADR 冻结的 P2.3 schema witness。

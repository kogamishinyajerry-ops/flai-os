# ADR-0036：逐权威产物的 lower-bound 结果遥测

- 状态：Accepted（M4 前仪器；不解锁课题空间、评审梯子或 P2.5–P2.8）
- 日期：2026-07-19
- 关联：ADR-0018、ADR-0021、ADR-0025、ADR-0035、`scripts/usage_report.py`

## 背景

`review_approved` 能证明产物经过人工签发，却不能证明签发后发生了什么。过去只能统计
“签发了”，无法区分产物是否被完整交付、是否流入下一轮任务；更不能把这些流转信号
冒充“采用了”或“产生业务价值”。历史访问与管道事实不能可靠回溯，M4 真实工作开始后
才安装仪器会永久丢失第一段观察窗口。

本 ADR 只安装最小采集口，不增加服务、队列、公开端点或用户操作。它同时把既有状态机的
隐含前提落成物理约束：`waiting_review` 是审阅包的**封印点**，不是仍可换包的普通中间态；
进入后 exact output manifest 与其逐件 file record 不再可改写，通用状态 setter 也不能充当
人工签发出口。这不是新增业务状态，而是防止“用户看 A、点击却签 B”以及签后追加未签产物。

## 决策

### 1. 一张只追加 ledger，三种事件

`artifact_outcome_events.event_type` 只允许：

- `capture_started`：该**逐件权威产物**从此进入 instrumentation cohort。它只表示采集器
  生效，不是 outcome，不进入下载/流转结果分子；
- `full_download`：一次完整的普通 200 GET 正文已由 ASGI `send` 成功交付；
- `pipeline_handoff`：某件产物在 resolver 本次事务中被新增到 exact downstream task 的
  `input_file_ids`。

每行都必须同时绑定：

1. `origin='user'` 的 source task；
2. `kind='output'`、属于 source task、且 exact file id 在其 `output_file_ids` 的文件；
3. 同 source task 的 exact `review_approved.event_id`；该 event 必须有
   `task_review_event_witnesses.witness_kind='structured_v1'` 的逐字封存，其 payload 内的
   `decision_id` 还必须精确指向同任务 `task_human_decisions.action='approve'`；
4. 批准落账时 source task 与 source file 的 exact JSON witness。两份 witness 覆盖所有持久
   列，并显式纳入 SQLite 内部 `rowid`；task 另纳入签发落定后的 `updated_at`。后续
   download/handoff 逐字复制唯一 capture 的两份 witness，不从可能已变化的父记录重新推导 cohort。

SQLite trigger 独立重验上述 witness，并要求 capture 快照与当时父记录逐字相等；外键、
事件形态 CHECK、下载字节相等、下游依赖与输入清单也在 DB 层 fail-closed。事件形态另有
canonical `BEFORE INSERT` trigger 重验白名单、schema version、SQLite storage class 与逐类型
nullable/actor/bytes 约束；id、snapshot、时间与 actor/downstream 必须真实存为 TEXT，计数/字节
必须存为 INTEGER。`created_at` 只接受 writer 实际产生的两种 canonical UTC 字节编码：
`YYYY-MM-DDTHH:MM:SS+00:00` 或六位微秒版本；空格/任意分隔符、非六位小数、BLOB 等即使
`julianday()` 可解析也拒绝，避免报告用字节窗口时漏计。连接级
`PRAGMA ignore_check_constraints=ON` 也不能写入伪造事件；deep witness 同样扫描历史坏形态。
ledger 禁止 UPDATE、DELETE、主键/显式 rowid 冲突 REPLACE。
内部 rowid 必须为正，显式 `rowid=-1` 不能利用 SQLite 的自动 rowid sentinel 绕过保护。
`capture_started` 对 file 全局唯一；`pipeline_handoff` 对 file+downstream 精确幂等；对应
conflicting-insert guard 使用完全相同的键（不把 `review_event_id` 错加回旧唯一语义）；
`full_download` **不去重**，同一用户两次真实完整交付必须保留两条事实。

一旦产物已被 ledger 见证，其 file 记录禁止 UPDATE、DELETE、conflicting INSERT/
`REPLACE`，以及由未见证 sibling 发起、在 `recursive_triggers=OFF` 下隐式删除 victim 的
`UPDATE OR REPLACE`；source/downstream task 同样覆盖 conflicting UPDATE。source task 必须保持
`completed + origin=user + exact output_file_ids`；已见证 handoff 的 downstream 必须保留
对应依赖/输入。所有 terminal task（包括零产物人签、确定性完成、失败、取消）冻结 id、
status、exact output manifest，并拒绝删除/冲突替换；人工审阅包与已见证 source 另冻结更广的
provenance。只有未进入人工审阅、未被 outcome 见证的其它 terminal task 才可继续既有
metadata/classification 维护。后续更正应产生新任务/新产物，不得改写旧证据。

任务进入 `waiting_review` 的同一条状态写即冻结 manifest；同 statement 不能一边换清单一边
进入审核。清单引用的 file row 从等待审核起禁止 UPDATE/DELETE/REPLACE/冲突 UPDATE，批准或
驳回后由 decision witness 继续冻结；也禁止向已封印任务后加或迁入 output file。等待态任务
本身禁止删除、换 id、冲突替换；agent id/version、origin、inputs、classification、依赖、owner
等任务 provenance 从进入等待态起也不可换包，decision 后继续冻结。签发出口唯一允许
`updated_at/finished_at/error_message` 按 exact decision 同语句落定；之后三者不可改写。
`waiting_review` 的任何
出口在 DB 层必须同时看到 action/status
匹配的 `task_human_decisions` 与 payload 精确绑定其 `decision_id` 的 review event；仓储层通用
`set_task_status` 明确拒绝该出口，只有 `apply_human_review` 可以完成原子迁移。

### 2. cohort 只从新人工批准开始，不历史回填

`apply_human_review(approve)` 的既有 `BEGIN IMMEDIATE` 先写 decision 与 exact
`review_approved`，再通过 DB 出口 witness 把任务转成 terminal，最后为进入审核时已经冻结的
每件 user-origin 权威输出追加一条
`capture_started`。marker 与人签状态迁移、decision、sample 回填、review event 同事务；
trigger 还会重验 event payload 的 exact `decision_id` 与 approve decision；任一 provenance
不成立则批准整体回滚。

禁止：

- 扫描旧 `review_approved` 补 marker；
- 在首次下载或 handoff 时反向补 marker；
- 为 eval、未签产物、确定性自动完成产物伪造 marker；
- 把 `capture_started` 计为下载、流转或采用。

因此上线后尚无新签发权威产物时，报告必须是
`unknown_no_instrumented_artifacts`，不能以全局 0 冒充“无人使用”。确定性
`profile=none + requires_human_review=false` 的合法上游没有 review/capture：原管道继续
流转，但不写 outcome，保持 lower-bound 的诚实性。

### 3. full_download 只认完整 200 GET 的可观测边界

下载请求一进入 handler，必须在 classification、权威根、open、size+sha256 等任何可能阻塞的
完整性工作**之前**快照当时已存在的 exact capture/source/review witness；没有快照就不安装
写账 callback。审批若发生在本请求的完整性 gate 期间，对本请求也已经太晚，只能由下一次请求
进入 cohort。宁可保守漏计，也不能把“请求中途才签发”追认为签后交付。随后下载仍完整经过既有
classification 与完整性 gate；只有满足全部条件才在正文发送后使用入口快照追加 `full_download`：

- 请求没有 `Range` header，且走普通 GET；即使 `If-Range` 令 Starlette 回退 simple 200，
  只要原请求带 Range 仍不记录；
- 非 HEAD、非 preview、非 206 单/多 Range；
- 每个正文 `send`（包括文件大小恰等 chunk 后的最终空 terminator）都成功返回；
- 实际发送字节数 exact 等于权威文件 `size_bytes`。

客户端中断、读取/发送异常、短正文或失败响应均不写。最终 `send` 返回后才打开独立 DB
连接写账；此时若 DB 锁冲突或写入失败，HTTP 正文已经交付，不能倒写为失败响应，只追加
无异常正文的 `artifact_outcome_capture_failed / post_send_db_failure` audit warning。

诚实边界：ASGI `send` 成功是服务端可观测的“正文已交给传输栈”，不是证明某个人阅读、
采用或保存了文件，也不能对抗传输栈在成功返回后才暴露的网络丢失。

### 4. pipeline_handoff 与 resolver 既有事务原子

`enqueue_dependent_task` 在同一 `BEGIN IMMEDIATE` 内先计算 `newly_piped`、写下游
`input_file_ids`，再为其中已有 `capture_started` 的每件产物追加 handoff，最后写既有
dependency event 并 COMMIT。

- 只记录本次真正新增的 exact file id；下游原来已有该文件不冒充新 handoff；
- downstream 必须也是 `origin='user'`，其 `depends_on` 含 source task，且更新后的
  `input_file_ids` 含 exact source file；
- 任一 handoff 写失败，入队、输入合并与 dependency event 全部回滚；
- resolver 的 created 状态复查与 DB 精确唯一键共同保证 file→downstream 幂等。

这使 `pipeline_handoff` 只能解释为“产物已流入真实 user-root 工作链”，不能解释为下游
Agent 已打开文件、已理解内容或业务已采用。

### 5. 混版部署与 schema 假绿 fail-closed

pipeline writer 属于独立 worker 的新必需行为，故 `WORKER_GENERATION` bump 为带
`+adr36-outcome-flow` 的新代际。`/api/readyz` 必须同时满足：心跳新鲜、generation exact
匹配、outcome canonical schema witness 全部 `is True`；`deploy_selfcheck.py` 同时检查
本地库、活 API schema map 与 worker 代际，拒绝“新 API/DB + 旧 worker”静默漏记。
API 另暴露 exact `OUTCOME_TELEMETRY_GENERATION`；当前 `v8` 代际同时见证 request-entry
snapshot、signed task/file snapshot、逐事件 review witness 与 canonical UTC。仅有旧版布尔 axis、但仍在 post-send
阶段才发现 capture 的存活进程，不能借新 DB schema witness 冒充已升级，部署门同样拒绝。

`outcome_schema.py` 用完整规范化 DDL、PRAGMA table/FK/index metadata 和 trigger SQL
校验表、所有索引与受管 trigger，并以 `provenance_integrity` anti-join 复核已持久化的
source/file/review/decision/capture/downstream 关系；capture 中保存的 task/file signed snapshot
还必须与当前父记录精确相等，包括内部 rowid 与 task updated_at。因此只暂时移除父级 guard、
改写 rowid、SHA/path 或任务 provenance、再
恢复同一 trigger SQL，deep witness 仍会变红。只看表名、列集合或同名 no-op trigger
均不算证据；额外 UNIQUE index 也会失败，因为它可能把重复真实下载折叠掉。仅在 task event、
decision、waiting/terminal task 均不存在时，无证据的空 pre-snapshot ledger 才可在写锁内
丢弃旧空表并创建当前 exact 表；一旦 review 证据存在就要求人工迁移。非空 ledger 绝不补造 witness，
若结构或可验证 provenance 不 exact，启动保留现场并
失败。表已删但 files/tasks 上仍有受管 guard residue 同样失败，不能静默建一张新空表洗掉
信号。exact `review_approved` 的三条 append-only guard 加一条正 rowid guard，共四条
task-event trigger，也属于 outcome canonical witness；没有 outcome table 的合法旧库不能仅因
这些共享 guard
被误判为 residue，可完成首次收敛。outcome table 一旦存在且已有 task event、decision 或
waiting/terminal 证据，shared parent 与 review-seal triggers 在任何 DROP/replay 前必须 exact；
即使 outcome ledger 仍为空，同名 no-op 也不能被重启洗回绿色。非空 outcome 则继续要求完整
schema + deep provenance 原样通过，失败保留现场。

深 provenance anti-join 在 `init_db`、部署自检、离线报告以及每次 `/health`/`readyz` 执行。
不得复用裸的启动布尔或 SQLite `schema_version` cookie：具备直连写权限的进程可在 drop guards、
改父记录、恢复 SQL 后把 cookie 回拨，导致结构全绿而历史 provenance 已坏。当前选择每轮 O(N)
深审以守住“假绿死罪”；扫描同时拒绝 outcome、task event、file、task 的非正内部 rowid。
未来只有在引入不可回拨、DB 外部的证明后才可安全优化探针成本。

Outcome 的 `provenance_integrity` 还合取 human-decision/review-event-witness 两张表的 exact shape
与 canonical trigger 集；每条 capture 再逐字段绑定 event witness 的内部 id、task/agent/type/
level/message/payload/created_at、`structured_v1` 与 decision id。机器 advice 的质量/provenance
仍由独立 judgment axis 负责，不能反过来把不相关的 advice 损坏误标为 outcome schema 损坏。
因此删掉 signer witness、或把其 append-only trigger 换成同名 no-op 后，不能继续追加 download/
handoff，也不能让 outcome axis 独立报绿。

### 6. 报告口径

`usage_report.py` 只有在 outcome 与 judgment 各自 canonical schema + deep provenance witness
全绿后才读对应读数；可信 approved/rejected 只从 `task_human_decisions.action` 统计，封存的
`legacy_unstructured` 只单列为切换前历史记录，不并入可信人签。判断账本红时不再输出人签
measured 计数。`/stats/overview` 消费同一 judgment witness；见证红时返回
“未知（判断账本不可信）”，前端呈现为 `—`，不把不可信 event 行数冒充已签任务。整份报告显式开启
一次只读事务，固定在同一 WAL snapshot；tasks、reviews、decisions、conversations、model calls、
feedback 与 outcome 等所有时间窗口查询同时受 `created_at <= generated_at` 精确微秒上界约束；
completed 时延还要求 `finished_at <= generated_at`，未来完成时间不能污染当前 median。
若唯一/最早 capture 来自报告时点之后，
报 `unknown_future_capture_timestamp`，不把未来事实计进当前报告。随后找 user-origin 最早
`capture_started`，并公开：

- `observation_started_at`（cohort 的最早 marker）；
- 用户请求窗口起点与 `effective_window_start = max(requested, observation_started)`；
- `requested_window_fully_covered`，明确采集若在 14 天窗口中途启用，并未覆盖整窗；
- 每类 event 数、distinct artifact/source task；full download 另报 distinct actor **计数**，
  pipeline 另报 distinct downstream task。

固定解释为：`full_download = delivered, not adopted`；
`pipeline_handoff = flowed, not read/adopted`。username 只用于具名不可抵赖的 ledger，报告不
列用户名。schema loose/损坏、无 cohort 或起点时间不可验证时都报“未知”，不编 0。

## 后果与边界

- 新人签批准多一次按输出数线性的小事务写入；这是 M4 前装仪器的有意成本。
- `/health` 与 `/readyz` 当前随 outcome/父级证据规模执行 deep provenance，可能形成 O(N) 运维
  成本；在不可回拨外部见证落地前，这是可信度优先的显式取舍，不以缓存布尔制造假绿。
- 完整下载的 DB 写在响应后，故故障只形成漏计下界，不影响已交付文件；audit warning 为
  运维提供漏计信号，但不补造 outcome。
- 非空旧 outcome ledger 若缺少本 ADR 的新父级 guards/decision witness，会拒绝自动升级；
  当前代码尚未部署到 M4，故按取证式 fail-closed 处理，不静默宣称旧保护窗口可信。
- sensitive 文件仍受既有下载 gate；遥测不授予任何读取权限。管道继续沿用既有签发、
  origin、分级合成与 runtime 消费闸。
- 本 ADR 不证明 adoption、业务复用、阅读、下载后的传播或任务结果质量，也不建立角色轴。
- SQLite 同库机制不能对抗高权限写者同时移除父级与 ledger guards、改父记录并同步重写 ledger
  快照后再完整恢复 schema；也不能对抗完整删除 ledger 表及全部相关 guards、删除整库或回滚
  备份后不留任何本地 residue。这些是单一本地数据库的不可检测边界，需依靠离线备份、文件
  权限与外部审计。
- 不提供历史 fake backfill，也不新增查询 API。当前唯一聚合面是本地只读报告与部署探针。

## 验证

- provenance 负例：foreign/non-user/unsigned/非权威 output、错误/缺失 decision 或逐事件 witness
  绑定、错误 bytes、空白/BLOB actor、非 canonical UTC、坏下游、父级 orphan、关闭 CHECK 后的
  未知 event/schema/shape poison；
- append-only：UPDATE、DELETE、主键 REPLACE、`recursive_triggers=OFF` 父级 REPLACE 与 sibling
  `UPDATE OR REPLACE`、显式 rowid REPLACE 与 `rowid=-1`；task-event/file/task 非正 rowid 不得投毒
  后续自动插入；terminal exact manifest/status/delete/replace；
- review seal：waiting_review 后换 manifest、改/删/替换 file、late insert/move、通用 setter/raw
  UPDATE 无 decision+event 出口均失败；task origin/agent/inputs 等 provenance 前后均冻结；approve
  只 capture 原封印包；逐事件 witness 与 review event 的内部 id/time/message/payload 任一漂移
  或 witness guard 变同名 no-op 均令 judgment/outcome 见证为红，切换后无 decision 的伪 legacy
  直接零写；
- download：HEAD、preview、Range、Range+If-Range simple 200、中断、exact-chunk final
  terminator 失败、post-send DB 失败、重复完整 GET、下载开始后才签发不追认；
- pipeline：exact newly-piped、preexisting input 不记、写失败全事务回滚、确定性无 capture
  仍可正常流转；
- deployment：含 task-event parent/review seal 在内的同名 no-op trigger、额外 UNIQUE index、
  missing-table residue、旧 API/worker generation 均令 local check/health/readyz fail-closed；合法
  pre-outcome task-event 旧库可首次收敛，空 pre-snapshot ledger 可安全重建；guard drop→父级改写
  →SQL 恢复后，或只改父级内部 rowid 再恢复 guard，signed snapshot 均令 health/readyz deep 仍红；
- report：单一 WAL snapshot、所有时间窗口的生成时点上界、未来/不可解析 capture、同秒微秒边界、cohort
  起点、窗口中途启用、event 与 distinct 分列、decision-only 可信人签、legacy 单列、判断见证红时
  report/stats 诚实未知、无 cohort 与 loose schema 诚实未知。

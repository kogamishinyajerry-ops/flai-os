# ADR-0036：逐权威产物的 lower-bound 结果遥测

- 状态：Accepted（M4 前仪器；不解锁课题空间、评审梯子或 P2.5–P2.8）
- 日期：2026-07-19
- 关联：ADR-0018、ADR-0021、ADR-0025、ADR-0035、`scripts/usage_report.py`

## 背景

`review_approved` 能证明产物经过人工签发，却不能证明签发后发生了什么。过去只能统计
“签发了”，无法区分产物是否被完整交付、是否流入下一轮任务；更不能把这些流转信号
冒充“采用了”或“产生业务价值”。历史访问与管道事实不能可靠回溯，M4 真实工作开始后
才安装仪器会永久丢失第一段观察窗口。

本 ADR 只安装最小采集口，不增加服务、队列、公开端点或用户行为。信任供给、签发状态机、
分级 gate 与“人是唯一签发者”均不改变。

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
3. 同 source task 的 exact `review_approved.event_id`。

SQLite trigger 独立重验上述 witness；外键、事件形态 CHECK、下载字节相等、下游依赖与输入
清单也在 DB 层 fail-closed。ledger 禁止 UPDATE、DELETE、主键/显式 rowid 冲突 REPLACE。
`capture_started` 对 file+review 唯一；`pipeline_handoff` 对 file+review+downstream 精确幂等；
`full_download` **不去重**，同一用户两次真实完整交付必须保留两条事实。

一旦产物已被 ledger 见证，其 file 记录不可更新；source task 不得再移除该权威输出或改成
非 user origin；已见证 handoff 的 downstream 也不得移除对应依赖/输入。后续更正应产生新
产物，不得改写旧证据。

### 2. cohort 只从新人工批准开始，不历史回填

`apply_human_review(approve)` 的既有 `BEGIN IMMEDIATE` 在追加 exact
`review_approved` 后，为当时冻结的每件 user-origin 权威输出追加一条
`capture_started`。marker 与人签状态迁移、decision、sample 回填、review event 同事务；
任一 provenance 不成立则批准整体回滚。

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

下载仍先经过既有 classification、权威根、size+sha256 完整性 gate。只有满足全部条件才
在正文发送后尝试追加 `full_download`：

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

`outcome_schema.py` 用完整规范化 DDL、PRAGMA table/FK/index metadata 和 trigger SQL
校验表、所有索引与受管 trigger。只看表名、列集合或同名 no-op trigger 均不算证据；额外
UNIQUE index 也会失败，因为它可能把重复真实下载折叠掉。空 ledger 可由 `init_db` 收敛
受管对象；非空 ledger 若结构不 exact，启动保留现场并失败。表已删但 files/tasks 上仍有
受管 guard residue 同样失败，不能静默建一张新空表洗掉信号。

### 6. 报告口径

`usage_report.py` 只有在同一个 canonical schema witness 全绿后才读数。它先找 user-origin
最早 `capture_started`，并公开：

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
- 完整下载的 DB 写在响应后，故故障只形成漏计下界，不影响已交付文件；audit warning 为
  运维提供漏计信号，但不补造 outcome。
- sensitive 文件仍受既有下载 gate；遥测不授予任何读取权限。管道继续沿用既有签发、
  origin、分级合成与 runtime 消费闸。
- 本 ADR 不证明 adoption、业务复用、阅读、下载后的传播或任务结果质量，也不建立角色轴。
- SQLite 同库机制不能对抗“完整删除 ledger 表及全部相关 guards、或删除整库/回滚备份”后
  不留任何本地 residue 的攻击；这是不可检测边界，需依靠离线备份、文件权限与外部审计。
- 不提供历史 fake backfill，也不新增查询 API。当前唯一聚合面是本地只读报告与部署探针。

## 验证

- provenance 负例：foreign/non-user/unsigned/非权威 output、错误 bytes、空白 actor、坏下游；
- append-only：UPDATE、DELETE、主键 REPLACE、显式 rowid REPLACE；
- download：HEAD、preview、Range、Range+If-Range simple 200、中断、exact-chunk final
  terminator 失败、post-send DB 失败、重复完整 GET；
- pipeline：exact newly-piped、preexisting input 不记、写失败全事务回滚、确定性无 capture
  仍可正常流转；
- deployment：同名 no-op trigger、额外 UNIQUE index、missing-table residue、旧 worker
  generation 均令 local check/health/readyz fail-closed；
- report：cohort 起点、窗口中途启用、event 与 distinct 分列、无 cohort 与 loose schema 诚实未知。

# ADR-0040：会话状态、标题与归档可见性的可信生命周期

- 状态：Accepted（P2.6 已实现）
- 日期：2026-07-20
- 范围：会话生命周期 API、SQLite 投影/事件账本、Question 收口与部署见证
- 关联：ADR-0012、ADR-0013、ADR-0033、ADR-0034

## 背景

P2.6 之前，会话只有 `active → concluded` 状态写入，没有标题、归档列表或并发版本。
`conclude` 直接更新投影，无法证明是谁在什么版本执行了动作；重复点击、多个页面与并发请求
也没有统一 CAS。若把“归档”复用成 `concluded`，则用户只是整理列表也会意外关闭对话及普通
Question；若把 `completed` 或归档涂绿，又会违反信任色与“人是唯一签发者”的红线。

本决策把业务状态、标题和列表可见性拆为三个可核验的轴，并用同库 append-only ledger
约束全部变更。它只管理普通会话，不进入 task review、人工签发或 LLM 判决链。

## 决策

### 1. 三轴正交，归档不可逆但不结束会话

会话投影新增：

- `title TEXT NULL`：可重复重命名；
- `lifecycle_revision INTEGER NOT NULL DEFAULT 0`：所有生命周期动作共享的 CAS 版本；
- `archived_at TEXT NULL`：`NULL` 为可见，非 `NULL` 为已归档。

`status` 本切片只使用 `active|concluded`。`archive` 只把 `archived_at` 从 `NULL` 写为事件时间，
不改变 `status`、不关闭 Question，也不禁止后续消息、回答或重命名；`conclude` 只把
`active` 变为 `concluded`，不改变可见性。因而存在 active-visible、active-archived、
concluded-visible、concluded-archived 四种合法组合，四种组合都可重命名。v1 不提供
unarchive；重复 archive 必须显式冲突，不能把不可逆动作伪装成幂等成功。

列表入口固定为：

```text
GET /api/conversations?visibility=visible|archived
```

默认 `visible`，两类列表都只按认证 principal 的 exact username 取数。归档不是删除；owner
仍可通过 direct GET 读取，也可从 archived 列表恢复入口。foreign、legacy NULL owner 与不存在
统一 404，不以 display name 猜测。

### 2. 所有动作使用严格请求与同一 CAS

写入口为：

```text
PATCH /api/conversations/{id}/title
POST  /api/conversations/{id}/conclude
POST  /api/conversations/{id}/archive
```

三个请求都必须携 `lifecycle_revision`。只接受 JSON exact integer；布尔、字符串与浮点数在
Pydantic 边界 422 且零写入。额外字段同样 422。版本过期、同标题、重复 conclude、重复 archive
或非法状态迁移均 409，事件与投影零写入；成功恰好追加一个事件并把 revision 加一。

重命名先计算 Python `str.strip()` 并要求结果与原值完全相等（服务端不静默规范化），再要求
1–60 个 Unicode code point，并拒绝 Unicode category `Cc`、`Zl`、`Zp`。SQLite trigger
独立重验等价约束，防内部调用或原始 SQL 绕过。
标题可包含普通非 ASCII 文本，但不能承载换行、段落/行分隔符或控制字符。

所有成功响应以及 create、GET、list、message/answer 的嵌套 conversation 投影恒含：
`title`、`status`、`lifecycle_revision`、`archived_at`。客户端必须用返回的新 revision 更新本地
快照；409 后重新读取权威投影，不自行猜测动作结果。

### 3. 单一 append-only 事件写缝与触发器投影

`conversation_lifecycle_events` 每行保存：事件 id、conversation、`renamed|concluded|archived`、
新 revision、exact actor username、动作前的 status/title/archived_at、重命名后的 title 与
canonical 六位微秒 UTC 时间。`UNIQUE(conversation_id, lifecycle_revision)` 固定事件顺序；
actor 必须逐字等于会话 owner，prior snapshot 必须逐字等于当前投影。

仓储层只有 `append_conversation_lifecycle_event` 可以产生生命周期事实。它接收调用方期望的
当前 revision，写入 `expected + 1`；不自行开启或提交事务。SQLite `AFTER INSERT` trigger
根据事件类型更新投影，`BEFORE UPDATE` projection guard 要求该 exact next event 已存在，且
新 title/status/archived_at/revision/updated_at 与事件逐字一致。因此直接 UPDATE、同 id
INSERT/REPLACE、event UPDATE/DELETE/冲突 REPLACE 均失败；ledger 只能增长。

`ConversationService` 对每个动作使用 `BEGIN IMMEDIATE`，在锁内重读 exact owner 与 revision，
再调用唯一事件写缝。两个同 revision 并发请求最多一个提交，输家读取到新 revision 后返回
409。任一事件或投影失败都回滚整个事务，不留下半态。

### 4. conclude 与普通 Question 同事务，archive 不碰 Question

`conclude` 在同一 `BEGIN IMMEDIATE` 中按以下顺序执行：

1. 复核 owner、revision 与 `status='active'`；
2. 以同一 canonical 时间关闭 unresolved Question；未到期为 `superseded`，已到期保留真实
   expiry 语义；
3. 追加 concluded 事件，由 trigger 更新会话投影；
4. COMMIT。

事件写入或投影应用失败时，Question 闭合也回滚并继续保持原事实。`archive` 完全不调用
Question close seam；归档 active 会话的 pending Question 仍可回答。LLM 不参与 rename、
conclude 或 archive，也不能生成 actor、revision 或时间。

### 5. legacy 不造历史，非空账本拒绝自动洗绿

迁移为存量 `conversations` 只增加 `title=NULL`、`lifecycle_revision=0`、`archived_at=NULL`。
既有 active/concluded 行原样保留，不从 recommendation、status 或时间戳反推标题/归档，也不
补造 lifecycle event。新建会话必须从 active、null title、revision 0、visible 开始。

空账本可在 `init_db` 写锁内收敛 canonical trigger；一旦任一投影出现 title/archive/正 revision，
或 ledger 有首行事件，启动必须在任何 DROP/replay 前验证完整现状。缺表、同名 no-op trigger、
loose table、事件链断裂、prior snapshot/actor/时间/最终投影不一致都保留现场并拒绝启动，不能
“修好后报绿”。

生命周期独立 witness 固定为五键：

- `projection_columns`；
- `event_table_shape`；
- `required_indexes`；
- `required_triggers`；
- `persisted_event_chains`。

`init_db`、`/api/health`、`/api/readyz`、本地部署自检与远端活进程自检共享同一实现，并要求
每键 `is True`。health 另暴露 `conversation_lifecycle_axis=true`；readyz 在任一键为假时 503；
部署门同时检查探针侧数据库和服务实际连接数据库，旧 API 或已破坏 schema 不能借早期 P2.3
代际标志假绿。P2.3 的 conversations exact table witness 同步显式纳入三个新增列，两个
projection trigger 纳入其受管集合；这是版本化升级，不放宽原 owner/identity/Question 合同。

## 边界与后果

- archive 是列表整理动作，不是任务完成、批准、签发或质量结论；UI 不得给 green/teal。
- concluded 仍不是 task review 决策；它只表示普通对话不再接收消息/回答。
- v1 不提供删除、unarchive、转移 owner、批量动作、自动标题或 LLM 命名。
- 每次 health/readyz 深读全部 lifecycle chain，成本为 O(events)。在获得不可回拨外部证明前，
  可信优先于缓存布尔；后续优化不得降低 persisted chain 见证。
- SQLite 同库 guard 不能对抗高权限写者同时删除表、全部 guard 与数据库备份痕迹；该边界需由
  文件权限、离线备份和外部审计补足。

## 验证

- strict wire：bool/string/float/负 revision、额外字段、首尾空白/空白/超长/控制/换行标题均
  422 零写入；
- 状态矩阵：四种 status/visibility 组合可重命名；archive 不改 status/Question，conclude 不改
  visibility；重复与 stale/no-op 409 零写入；
- 原子性：conclude 正常关闭 pending Question；事件 seam 注入失败时 Question、事件、投影全部
  回滚；
- 并发：同 revision 两请求恰一个成功；foreign exact owner 始终 404；
- 防绕过：raw projection UPDATE、conversation/event REPLACE、event UPDATE/DELETE 均失败；
- 迁移/部署：legacy active/concluded 保留 null/0/null 且事件数为零；非空 ledger 篡改拒绝重启；
  同名 no-op trigger 令 local check、health witness、readyz 与 remote generation gate fail-closed。

# ADR-0032：任务权威快照、连续事件游标与断连调和

- 状态：Accepted
- 日期：2026-07-19
- 关联：`docs/design/JERRYAGENT-UX-MAPPING.md`、`contracts/task_live_snapshot.schema.json`

## 背景

任务详情原先并行读取 task 与 event tail，并以浏览器中 `events.length` 作为 SQLite
`OFFSET`。这个实现能降低正常轮询流量，却不能证明 task 与 events 来自同一数据库快照，
也不能识别删除、压缩、错锚或漏段。暖失败又保留旧值但不标旧，使用户无法区分“当前
已核对”与“最后一次成功看到”。

JerryAgent 的可迁移原则是 `authoritative snapshot → exact revision tail → gap 时丢弃增量
→ full snapshot reconnect`。FLAi-OS 保留 HTTP 轮询和现有 channel pool，不引入 SSE，
也不把 UUID、数组下标或 SQLite 全局主键冒充每任务 sequence。

## 决策

1. 保持既有 `GET /api/tasks/{id}` 与 `GET /api/tasks/{id}/events` 响应不变，新增
   `GET /api/tasks/{id}/live-snapshot`，版本固定为 `task-live-snapshot/v1`。
2. v1 sequence 是单个 task 的 append-only event log 中一基序数；`event_id` 是精确锚点。
   非零 `after_sequence` 必须同时携带该位置的 `anchor_event_id`，否则 422。
3. task、当前 cursor 与 event tail 必须在同一 SQLite read transaction 中读取。游标超前
   或锚点不符时返回 `resync_required=true`、零 delta；客户端必须丢弃可疑增量并以
   sequence 0 重取。
4. 前端先完整验证 schema、base、连续 sequence、event identity、task identity 和最终
   cursor，再原子落地整批。缺号、重排、重复、跨 task、未知 schema 或最终 cursor 不符
   都不得部分追加。
5. 每个 task channel 使用 resync generation。显式重同步或暖失败发生在旧请求飞行期间
   时，旧请求不能清除较新的 sequence-zero 请求。
6. sequence-zero replace 只表示“按最新权威快照调和”，不是用户在线亲历的状态迁移。
   它不得广播普通 transition、补播完成盖章或触发签发提醒；只有 exact cursor 上的连续
   delta 可以广播迁移。
7. channel 投影 `connection`、`lastSuccessAt`、`stale`、`resyncing` 和错误。冷失败不
   渲染假空态；暖失败保留最后真实快照但以 amber 明示；恢复后先完整重取。隐藏标签页的
   主动跳过不算断连。依赖 conversation task ledger 判定“尚未召集”的写动作同样必须
   等当前权威快照；cold unknown 与 warm stale 都不得凭旧的“尚未召集”负结论开放重复创建。
   暖态旧账仍可只读展示并明示过期，但恢复 connected 前不授权创建。
8. 终态 task 在有订阅者时以 30 秒低频核对，避免永久保留伪 connected，并接收完成后的
   feedback/audit events。带外核对失败必须重排 timer 到断连 5 秒节奏，不能继续等待旧的
   30 秒 tick。`connected` 只表示最近一次核对成功，不表示持久 socket 存在。
9. 敏感 task/event 继续复用统一 classification gate；新 envelope 不得成为内容旁路。
10. live-snapshot、tasks 列表、conversation 头与 conversation-task ledger 这四类 channel
    authority 的响应与浏览器请求都使用 `no-store`；缓存命中不得冒充新鲜同步成功。

## 追加、删除、压缩与版本边界

v1 的稳定性依赖 `task_events` 只追加：SQLite 的
`trg_task_events_no_update` / `trg_task_events_no_delete` trigger 机械拒绝事件更新与删除，
`trg_task_events_no_conflicting_insert` 还在约束检查前拒绝 `INSERT OR REPLACE`/主键冲突
改写；不是只靠调用方约定。未来如需 compaction，迁移必须显式更换这些 trigger，并新增
stream generation 和新 schema 版本，令旧 cursor fail-closed 并强制 resnapshot；不得在
v1 下静默改变 ordinal 含义。SQLite 内部 `id` 永不公开。

本版本返回 cursor 后的完整 tail，没有新增分页。若单任务事件规模要求分页，必须先定义
page cursor 与 snapshot transaction 的一致性规则，再升级合同；不能把分页窗口缺失当作
“没有更多事件”。

## 后果与诚实边界

- 获得可机械检测的 gap 与精确恢复，同时保留旧客户端和旧 API。
- sequence 的计算仍是 `COUNT + OFFSET`，大事件流会增加读成本；这是当前无 Redis/Celery、
  SQLite 轻内核下的明确取舍，不宣称高吞吐事件总线。
- tasks/conversation 列表仍是周期性权威快照，没有事件级 cursor；它们在暖恢复后的第一次
  调和会抑制 transition，避免把离线期间变化冒充在线亲历。
- 断连提示使用 amber“未核”槽；不改变 Task.status，也不产生 REAL 绿或人签 teal。

## 验证

- 后端：`backend/tests/test_task_live_snapshot.py` 与 `backend/tests/test_contract_parity.py`。
- 前端纯状态机：`frontend/tests/live_snapshot_core.test.mjs`。
- 浏览器：`frontend/e2e/batch_a_livefeed_acceptance.py` 扩展冷/暖断连、gap、sequence-zero
  恢复和非亲历 transition 断言。
- 全量门：`UV_OFFLINE=1 bash scripts/verify_all.sh`。

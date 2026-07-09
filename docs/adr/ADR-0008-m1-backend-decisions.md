# ADR-0008: M1 最小后端四项技术裁决

- 状态：已接受（2026-07-08）
- 背景：M1 实现最小后端核心底座，需要在「轻内核」约束下定四件事。
- 决策：
  1. **存储 = stdlib sqlite3 + 仓储函数层，不引 ORM**。九表 DDL 手写（含 M2 用的
     feedback 表先建）；连接 per-operation（WAL 模式），claim 任务用
     `BEGIN IMMEDIATE` 事务原子化 queued→validating，单 worker 轮询下无双抢。
     理由：SQLAlchemy 对 V0.1 是过度设计（宪法/任务书 §15），且内网 wheels 面最小。
  2. **workflow 自定义事件统一折叠为 `agent_log`**。业务 workflow 的 event_logger
     可发任意类型字符串，Runtime 一律折叠为枚举内的 `agent_log`，原始类型进
     `payload.workflow_event_type`——事件枚举不随业务 Agent 膨胀，docs/05
     「禁止私自使用未注册 event_type」由结构保证而非约定（event.schema.json 枚举
     已同步扩此一枚）。
  3. **工具超时 = 线程 join 超时 + 诚实标注**。Python 线程无法强杀：超时后
     Registry 停止等待、tool_run 记 failed（error_message 注明「已放弃等待，
     线程可能仍在后台运行」），绝不假装工具被干净终止。真隔离（子进程/作业对象）
     留给 M3 批量场景按需引入。
  4. **后端默认端口 8620**（冷门位防冲突；被占换端口，永不挤占已有进程）；
     取消语义 V0.1 只支持未开跑任务（created/queued→cancelled）；
     waiting_review 只能由人工放行动作转出（docs/05 强制规则，cancel 也不例外）；
     running 中取消返回 409 如实拒绝——「能取消正在跑的任务」是 M3 Job Runner
     增强项，现在不假装支持。
- 替代方案：ORM（否，见上）；子进程级工具隔离（否，V0.1 过度）；事件枚举全开放
  （否，违 docs/05）。
- 影响与风险：sqlite 并发上限低（V0.1 单 worker 无碍）；泄漏线程是已知债，
  tool_runs 有痕可审。

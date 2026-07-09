# ADR-0009: API 契约对账修订（反方审查 R1）

- 状态：已接受（2026-07-08）
- 背景：M1 后端反方审查 R1 发现 API 实际响应与 `contracts/*.schema.json` 存在
  多处漂移，且部分安全/健壮性缺口未覆盖测试。本 ADR 记录本轮修订，覆盖
  P1（路径穿越/契约漂移）、P2（事件语义/竞态/限额/TBD 校验）与 P3（测试缺口）。
- 决策：
  1. **`task.schema.json` 补 `inputs` 属性**：params 型任务的结构化输入此前一直
     在 API 响应里，但契约未声明（`additionalProperties:false` 下即校验失败）。
     顺带发现 `name`/`started_at` 同样漂移——两者在业务上合法为 `null`（未命名/
     未进 running），但 schema 原先只允许 `string`，一并改为 `["string","null"]`。
  2. **事件对外唯一键收敛为 `event_id`**：`repos._decode_event` 剔除 sqlite
     自增主键 `id`（`d.pop("id", None)`），杜绝内部实现细节泄漏进 API 响应。
  3. **新增常驻契约咬合测试** `backend/tests/test_contract_parity.py`：用
     TestClient 走真实 `POST /api/tasks`、`GET /api/tasks/{id}`、
     `GET /api/tasks/{id}/events`，逐条 `jsonschema.validate` 对账两份契约，
     防止未来任何一方（API 字段 / schema 声明）单方面漂移。
  4. **上传安全加固**：`files.py` 落盘文件名先 `Path(filename).name` 净化
     （空/`.`/`..` 一律兜底 `unnamed`），再断言落盘路径 `resolve()` 必须落在
     `uploads_dir` 内，否则 400——防 `../../evil.txt` 路径穿越。同时加
     `FLAI_MAX_UPLOAD_MB`（默认 100）上传限额，分块累计超限即 413 并清理
     半成品文件/目录，不留残留。
  5. **`task_created` 事件语义**：改为 `created→queued` 状态迁移完成后再发，
     payload 携带 `status_from`/`status_to` 双态见证；docs/05 §6 补「两处文档化
     原子例外」（`created→queued` 由创建动作原子完成、`queued→validating` 由
     Job Runner claim 原子完成），除此之外状态变化无事件一律判违规。
  6. **竞态与兜底**：`set_task_status` 读-验-写整体包 `BEGIN IMMEDIATE` 事务
     （与 `claim_next_queued` 同一手法，防 TOCTOU 双写）；`JobRunner.run_once`
     捕获 `IllegalTransitionError`（cancel 竞态）记 warning 事件后继续，其余
     异常尽力置任务 failed 并记录、绝不上抛；`run_forever` 循环体再兜一层。
  7. **`trial`/`released` 状态禁 `TBD`**：`AgentRegistry._load_one` 落地
     `agent.schema.json` owner 字段注释早已承诺的校验，命中即排除进 `.errors`。
  8. **`input_file_ids` 缺失引用**：`_build_context` 由静默跳过改为发一条
     `warning` 事件后再跳过，遵循「无事件=没发生」的另一面——数据缺失也要留痕。
- 影响与风险：`task.schema.json`/`event.schema.json` 均为 breaking 收紧+放宽
  混合（新增可选属性向后兼容；`name`/`started_at` 允许 null 是放宽，不破坏
  现有消费方）；上传限额默认 100MB，内网大文件场景如超限需调
  `FLAI_MAX_UPLOAD_MB` 环境变量。
- 验证：`test_contract_parity.py`（5 用例）+ 各模块新增测试，全量 160 项绿
  （较审查前 142 项净增 18 项）。

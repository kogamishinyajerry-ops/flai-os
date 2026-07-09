# 05 任务与事件标准

> 依据：执行任务书 §4.5 / §8.2。契约文件：`contracts/task.schema.json`（已存在）、`contracts/event.schema.json`（对齐本文档字段口径，另路编写中）。
> 核心原则：**无事件 = 没发生**。任务生命周期的任何变化，若没有对应 `task_event`，视为未发生，不得以任务表 `status` 字段单独作为证据。

## 1. 任务状态机（十态）

```text
created queued validating running waiting_review
parsing analyzing completed failed cancelled
```

| 状态 | 含义 | 谁能写入 |
|---|---|---|
| `created` | 任务已建，尚未入队 | Task Center（`POST /api/tasks`） |
| `queued` | 已入队，等待 Job Runner 拾取 | Task Center |
| `validating` | 正在按 `input_schema.json` 校验输入 | Job Runner |
| `running` | `workflow.py` 执行中（通用执行态） | Agent Runtime |
| `parsing` | 执行中的细分子态：解析输入文件/表格（Agent 按需使用） | Agent Runtime / workflow.py |
| `analyzing` | 执行中的细分子态：结果分析/汇总产出（Agent 按需使用） | Agent Runtime / workflow.py |
| `waiting_review` | 等待人工审核放行（`agent.yaml.workflow.requires_human_review=true` 时的强制关口） | Agent Runtime 置入；**只能人工动作转出**（`POST /api/tasks/{id}/review`，body={action: approve\|reject, reviewer: 必填非空, comment?}） |
| `completed` | 任务成功终态 | 见下方合法来源 |
| `failed` | 任务失败终态 | 任一非终态均可转入 |
| `cancelled` | 用户主动取消 | Task Center（`POST /api/tasks/{id}/cancel`） |

## 2. 合法转移表

| From | 合法 To | 触发方 |
|---|---|---|
| `created` | `queued`, `cancelled` | Task Center / 用户取消 |
| `queued` | `validating`, `cancelled` | Job Runner 拾取 / 用户取消 |
| `validating` | `running`, `failed`, `cancelled` | 校验通过 / 校验失败 / 用户取消 |
| `running` | `parsing`, `analyzing`, `waiting_review`, `failed`, `cancelled` | workflow.py 按业务阶段推进 |
| `parsing` | `analyzing`, `running`, `failed`, `cancelled` | 解析完成进入分析 / 无分析阶段回到通用执行 / 解析失败 |
| `analyzing` | `waiting_review`, `completed`, `failed`, `cancelled` | 需人工判决 / 无需人工判决直接终 / 分析失败 |
| `waiting_review` | `completed`, `failed` | **仅人工放行动作**（`review_approved` → completed；`review_rejected` → failed），API 落点=`POST /api/tasks/{id}/review`。禁止任何自动化路径转出。 |
| `completed` | — | 终态，禁止再转移 |
| `failed` | — | 终态，禁止再转移 |
| `cancelled` | — | 终态，禁止再转移 |

**强制规则**：`completed` 的唯一合法来源是 `waiting_review`（人工批准）或 `analyzing`（无需人工判决时的自动终结）。`running` 不得跳过 `analyzing` 直接进入 `completed`——即使 Agent 没有独立的"分析"业务逻辑（如 hello_agent），`workflow.py` 也必须在产出结果后显式将状态迁到 `analyzing`、再迁 `completed`，作为"结果已产出"的显式节点，不得省略。此规则与 `contracts/task.schema.json` 对 `status` 字段的描述一致。

## 3. 事件结构

事件对象结构（任务书 §4.5 示例）：

```json
{
  "event_id": "evt_xxx",
  "task_id": "task_xxx",
  "agent_id": "performance_disk_agent",
  "event_type": "tool_started",
  "message": "开始调用性能盘",
  "payload": {},
  "created_at": "2026-xx-xx"
}
```

对应 `task_events` 表字段（任务书 §8.2）：

| 表字段 | 对应事件对象字段 | 说明 |
|---|---|---|
| `id` | `event_id` | 主键；API/JSON 输出层用 `event_id` 别名，DB 层用 `id`，两者同一值 |
| `task_id` | `task_id` | 关联任务 |
| `agent_id` | `agent_id` | 产生事件的 Agent |
| `event_type` | `event_type` | 见第 4 节清单 |
| `level` | — | `info` / `warning` / `error`，事件对象序列化时并入顶层或 `payload.level`（以 `event.schema.json` 最终定义为准） |
| `message` | `message` | 人类可读一句话摘要，禁止空字符串 |
| `payload_json` | `payload` | 结构化明细（如工具入参摘要、模型 token 用量、错误堆栈脱敏后文本） |
| `created_at` | `created_at` | ISO 8601 时间戳 |

事件只增不改不删：一旦写入，禁止 UPDATE 或 DELETE（审计要求）。任何"修正"通过写一条新事件表达，不得回填旧事件。

## 4. 事件类型清单

| event_type | 触发时机 | 建议 level |
|---|---|---|
| `task_created` | 任务创建 | info |
| `validation_started` | 开始校验输入 | info |
| `validation_failed` | 输入校验未通过 | error |
| `case_generated` | 生成标准化 case（批量类 Agent） | info |
| `tool_started` | 开始调用某个已注册工具 | info |
| `tool_finished` | 工具调用成功返回 | info |
| `tool_failed` | 工具调用失败（单 case 失败不等于任务失败，见 §5） | warning/error |
| `model_call` | 一次模型网关调用完成（成功或失败均记） | info/error |
| `review_requested` | 任务进入 `waiting_review`，请求人工审核 | info |
| `review_approved` | 人工批准，转 `completed` | info |
| `review_rejected` | 人工拒绝，转 `failed` | warning |
| `summary_generated` | 汇总结果/报告生成完成 | info |
| `task_completed` | 任务进入 `completed` 终态 | info |
| `task_failed` | 任务进入 `failed` 终态 | error |
| `task_cancelled` | 任务被用户/管理员取消，进入 `cancelled` 终态 | info |
| `feedback_received` | 用户提交任务反馈 | info |
| `warning` | 不归属以上类型的告警（须在 message 写明来源） | warning |
| `error` | 不归属以上类型的错误（须在 message 写明来源） | error |
| `agent_log` | Agent workflow 自报的过程日志——workflow 内 event_logger 发出的**任何**自定义类型均由 Runtime 统一折叠为本类型，原始类型进 `payload.workflow_event_type`（枚举不因业务 Agent 膨胀，ADR-0008） | info |

新增事件类型须先扩展 `event.schema.json` 枚举并记 ADR，禁止 Agent 私自使用未注册的 `event_type` 字符串。

## 5. 单 case 失败处理原则

批量类 Agent（如性能盘）中，单个 case 失败只产生 `tool_failed` 事件并在该 case 的样本记录中标注失败，**不得**直接把整个任务判 `task_failed`。任务级失败仅在：输入校验失败、Agent Runtime 抛未捕获异常、或全部 case 均失败（由 Agent 自身业务规则判定并写明于 `agent.yaml.limitations`）时触发。

## 6. 违规判定（供架构审查用）

### 两处文档化原子例外

以下两处状态迁移由动作本身原子完成（迁移与见证同一次调用内发生），不要求
迁移前后各配一条独立事件，但迁移必须被同批写入的事件显式见证，不判违规：

1. **`created` → `queued`**：由 `POST /api/tasks` 创建动作原子完成（同一请求
   内建任务后立即入队）。`task_created` 事件在状态已迁至 `queued` 之后写入，
   `payload.status_from`/`payload.status_to` 显式携带 `created→queued` 双态
   见证——事件本身既报告"任务已创建"也见证了紧随其后的入队动作。
2. **`queued` → `validating`**：由 Job Runner `claim_next_queued` 原子完成
   （sqlite `BEGIN IMMEDIATE` 事务内直接迁移，不经过 API 层单独一步）。紧随
   其后写入的 `validation_started` 事件即是该次迁移的见证。

除以上两处，任务状态变化若查不到对应事件，一律判违规——不得援引"迁移很快/
由动作原子完成"为由绕过留痕。

- 任务状态变化但查不到对应事件 → 判违规（无事件=没发生）。
- `waiting_review` 被自动化逻辑直接转 `completed`（未经 `review_approved` 事件）→ 判严重违规，等同绕过人工判决红线。
- 事件被后续代码 UPDATE/DELETE → 判违规。

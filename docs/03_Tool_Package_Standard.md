# Tool Package 标准

> 依据：《FLAi-OS_Fable5_执行任务书》§4.3、§6.4、§10。字段以 `contracts/tool.schema.json` 为准（本文档是该 schema 的人话说明，两者冲突以 schema 为准，发现冲突先改 schema 再改本文档）。

## 1. 包目录形态（强制）

```text
tools_impl/
  <tool_dir>/
    tool.yaml            # 元数据 + 契约，唯一注册入口
    adapter.py            # entrypoint 指向的执行函数
    input_builder.py      # 标准化输入 → 工具原生输入（如生成性能盘输入文件）
    output_parser.py      # 工具原生输出 → 标准化结果
    tests/                # 单元测试，至少覆盖正常/异常路径
    README.md             # 能力边界、调用方式、已知限制
```

核心四件（tool.yaml / adapter.py / tests/ / README.md）**一律强制**；
`input_builder.py`/`output_parser.py` 对**文件型工具**（需生成原生输入文件、解析原生
输出文件的，如性能盘）强制，对无独立转换步骤的纯函数工具（如 mock_echo）可省略——
省略时转换逻辑不得散落 adapter 之外。结构完整性由 `tests/test_contracts.py` 校验。

Tool Registry 只认这个目录形态；`tool.yaml` 缺失或 schema 校验不通过的目录不注册。**Agent 不得绕过 Tool Registry 直接 import `adapter.py`。**

## 2. tool.yaml 字段说明（对照 `contracts/tool.schema.json`）

| 字段 | 类型 | 语义 |
|---|---|---|
| `id` | string | 全局唯一工具 ID，Registry 主键，重复即拒 |
| `name` | string | 展示名 |
| `version` | semver | adapter/解析器任何行为改动必须升版本——`tool_runs` 表按版本追溯 |
| `type` | enum | `python_adapter`（V0.1 唯一实现）/ `mcp_adapter`（长期演进槽位，先占枚举） |
| `description` | string | ≥10 字，说清工具做什么 |
| `entrypoint` | string | 形如 `tools_impl.performance_disk.adapter:run` |
| `mock` | bool（可选，默认 false） | 见第3节 |
| `input_schema` | object | 内嵌 JSON Schema，`type` 必须是 `object`；Registry 调用前强制校验，不合格拒调 |
| `output_schema` | object | 内嵌 JSON Schema；必含 `status`（`success`/`failed`）；解析类工具必含 `raw_output_path` |
| `runtime.timeout_seconds/max_parallel_jobs/retry` | object | 调用超时/并发上限/重试次数 |
| `safety.*` | object | 见第4节三开关 |
| `owner.maintainer/business_owner` | object | 责任人，可先填 `TBD`（schema 不强制非空校验，但注册进 `released` Agent 前应补全） |

## 3. `mock` 字段的诚实语义

- `mock: true` 表示本工具是 Mock 实现，**不触真实工程程序**（例如 `performance_disk_mock` 只是造数据，不调用真实性能盘）。
- 凡 `mock=true` 的工具，其每一次调用在以下位置都必须如实标注 `mock=true`，绝不可让下游误认为是真实结果：
  - `task_events` 的 `payload`；
  - `tool_runs` 表记录；
  - `samples.jsonl` 中每条样本；
  - Agent 输出报告（如 `task_report.md`）中的显式声明；
  - **对外分发的表格产物**（如 `result_summary.xlsx`）：数据 sheet 带 `mock`
    末列（逐行如实转写）+ 追加「声明」sheet 写入 mock 声明文本——表格最容易
    脱离任务上下文单独传播，水印必须随文件本体走（M3 反审新增第五落点）。
- 里程碑4 用真实 Tool Adapter 替换 Mock 时，仅新增一个 `mock=false` 的工具包（如 `performance_disk`），Agent 的 `agent.yaml.tools` 改指向新 id；**不得原地把 Mock 工具的 `mock` 字段改为 false 冒充真实**——那是切换实现，不是翻牌一个字段。

## 4. safety 三开关

| 开关 | 默认 | 语义 |
|---|---|---|
| `require_workspace_isolation` | true | 每次调用必须在独立工作目录内执行，禁止写共享路径；违反即视为工具实现缺陷 |
| `allow_shell_command` | **false** | 默认禁止 shell 调用；若某工具确需 `true`，必须先写 ADR 说明理由与边界，Registry 加载时对 `true` 且无对应 ADR 引用的工具应告警 |
| `save_raw_files` | true | 原始输入/输出文件必须落盘并写入 `tool_runs.raw_input_path`/`raw_output_path`，供人工与后续样本库追溯 |

## 5. 先注册再调用原则

- Tool Registry 启动/扫描时对 `tools_impl/*/tool.yaml` 做 schema 校验，只有校验通过的工具才进入可调用列表。
- 统一调用入口：

```python
class ToolRegistry:
    def call(self, tool_id: str, payload: dict, context: dict | None = None) -> dict:
        ...
```

- 调用前强制用 `input_schema` 校验 `payload`；不合格直接拒调并写 `event_type=tool_input_invalid`，不进入 `adapter.py`。
- Agent 只能调用自己 `agent.yaml.tools` 白名单内、且已在 Tool Registry 注册成功的工具 id；两个条件缺一即拒。

## 6. 原始输入输出必落盘可追溯

- 每次工具调用对应 `tool_runs` 一行记录：`tool_id/tool_version/status/input_json/output_json/raw_input_path/raw_output_path/error_message/started_at/finished_at`。
- `raw_input_path`/`raw_output_path` 指向 `data/task_runs/<task_id>/` 下的具体文件，禁止只存内存对象、不落盘。
- 失败调用同样要记录（`status=failed` + `error_message`），不能因为失败就不写 `tool_runs`。

## 7. Python Adapter → MCP 演进路线

| 阶段 | 形态 | `tool.yaml.type` | 契约（id/input_schema/output_schema） |
|---|---|---|---|
| 短期（V0.1起） | Python 函数封装，`entrypoint` 直接指向 Python 可调用对象 | `python_adapter` | 保持不变 |
| 长期（工具被多个 Agent/多个运行时复用后） | 迁移为 MCP Server，Tool Registry 通过 MCP Adapter 转发调用 | `mcp_adapter` | **id 与 input_schema/output_schema 不变**，只翻牌 `type` 字段与内部 `entrypoint` 实现 |

- 演进原则：对 Agent 和 Tool Registry 调用方而言，`tool_id` 与出入参契约是稳定接口；`python_adapter → mcp_adapter` 只是内部实现替换，不应触发任何 Agent 侧代码修改。
- 何时演进：单个工具被 ≥2 个 Agent 复用、或需要跨语言/跨进程调用时，优先评估 MCP 化；具体 MCP Server 部署方式待内网侦察。

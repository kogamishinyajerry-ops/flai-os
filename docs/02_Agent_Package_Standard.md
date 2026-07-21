# Agent Package 标准

> 依据：《FLAi-OS_Fable5_执行任务书》§4.2、§7.6、§9。字段以 `contracts/agent.schema.json` 为准（本文档是该 schema 的人话说明，两者冲突以 schema 为准，发现冲突先改 schema 再改本文档）。

## 1. 包目录形态（强制）

```text
agents/
  <agent_id>/
    agent.yaml          # 元数据 + 契约，唯一注册入口
    prompt.md           # Prompt 版本化文本，禁止把 Prompt 硬编码在 workflow.py 里
    workflow.py          # 统一入口 run(context)
    input_schema.json    # 输入 JSON Schema
    output_schema.json    # 输出 JSON Schema
    eval_cases/          # 回归评测用例（见 07_Eval_Standard.md）
    README.md            # 面向使用者：能做什么/不能做什么/怎么用
    changelog.md          # 每次 version 变更必须追加条目
```

Agent Registry 只认这个目录形态；缺失 `agent.yaml` 或 schema 校验不通过的目录，一律不注册、不报错崩溃，仅在 Registry 日志中标记为无效包。

## 2. agent.yaml 字段说明（对照 `contracts/agent.schema.json`）

| 字段 | 类型 | 语义 |
|---|---|---|
| `id` | string | 全局唯一，蛇形小写，Registry 主键，重复即拒 |
| `name` | string | 门户展示名 |
| `version` | semver | 任何 prompt/workflow/schema 改动必须升版本并写 `changelog.md` |
| `execution_digest` | sha256(可选/条件强制) | 绑定 prompt/workflow/实际 input/output schema 的路径与字节；`automation.session_execution=true` 时强制。Registry 以 `agent_execution_files.v1` 规范计算并逐字比对，部署先后写入造成的任一中间态均拒绝注册 |
| `status` | enum | 运行生命周期：`draft`(仅开发者可见) / `trial`(试用角色可见) / `released`(正式) / `disabled`(下线) |
| `maturity` | enum | 治理轴：`L0`/`L1`/`L2`/`L3`，见第3节；与 `status` 正交 |
| `category` | enum | `tool_automation` / `knowledge_qa` / `structured_gen` / `reasoning_assist` |
| `summary` | string | 门户卡片一段话 |
| `description` | string(可选) | 长描述，须写明价值边界与是否强制串联其他 Agent |
| `owner.department/maintainer/business_reviewer` | object | `trial` 及以上状态禁止 `maintainer`/`business_reviewer` 为 `TBD` |
| `model.profile` | string | 模型画像名（`reasoning`/`fast`/`vision`/... 或 `none`），**禁止出现具体模型名** |
| `model.fallback_profile` | string(可选) | 主 profile 不可用时的降级画像 |
| `knowledge.enabled/scopes` | object | default-deny 白名单，`enabled=true` 时 `scopes` 至少 1 项，禁止 `*` 通配 |
| `tools` | string[] | 工具白名单，每项必须是 Tool Registry 已注册 id，default-deny |
| `automation.session_execution/effect` | object(可选) | 会话级受限自动执行声明；缺失即拒绝。首版仅 `session_execution=true`、`effect=none` 且零工具的 job Agent 可被平台自动创建/入队；**绝不代表自动签发** |
| `input.type/allowed_extensions/schema` | object | `file_upload`/`params`/`none` |
| `output.formats/schema` | object | 输出格式与 schema 文件名 |
| `workflow.entrypoint` | const | V0.1 固定 `workflow.py` |
| `workflow.mode` | enum | `job`(异步任务) / `interactive` |
| `workflow.requires_human_review` | bool | true→任务须经人工放行才能转 `completed`；**凡输出工程结论类判断，必须为 true**（对应宪法：LLM 不做最终工程结论） |
| `permissions.visibility/allowed_roles` | object | `admin_only`/`department_trial`/`all`；角色枚举 `admin`/`agent_developer`/`business_user` |
| `logging.*` | bool ×5 | 是否落盘 inputs/outputs/tool_logs/model_calls/feedback |
| `data_asset.collect_samples/sample_fields` | object | 是否沉淀 `samples.jsonl` 供后续黑盒建模 |
| `limitations` | string[] | **强制 ≥1 条**，声明本 Agent 不适用范围 |

### status × maturity 正交语义

| 轴 | 回答的问题 | 取值 |
|---|---|---|
| `status` | 现在能不能被调用/谁能看见 | draft → trial → released（或随时 disabled） |
| `maturity` | 治理走到哪一级、准入条件满足到哪 | L0 → L1 → L2 → L3 |

两轴独立组合：例如一个 Agent 可以 `status=trial` 且 `maturity=L1`（试用中、内部试用级）；`maturity` 不会因为 `status` 变化自动升降，必须走 L0-L3 准入评审。

### L0-L3 准入条件表

| 级别 | 准入条件（全部满足才能声明该级） |
|---|---|
| L0 | 能跑通最小样例；有 `README.md`；有运行日志（Event Log 可查） |
| L1 | 有固定 `eval_cases/` 测试集；`changelog.md` 有版本记录；对已知异常路径有处理（不裸抛异常崩任务）；有反馈入口（`POST /api/feedback` 可用） |
| L2 | 有明确 `business_reviewer`（非 TBD）；经过专家审核签字（记录方式待内网侦察，暂记于 `changelog.md`）；输出稳定（同输入多次运行结果一致或差异可解释）；已知问题有闭环跟踪 |
| L3 | 有治理策略（权限/审计要求满足部门规范）；`permissions` 精确到位；有维护责任人排班；有培训材料（面向业务用户的使用手册） |

## 3. `limitations` 强制规则

- `contracts/agent.schema.json` 对 `limitations` 设 `minItems: 1`，Registry 加载时对空数组直接拒绝注册。
- 至少应包含：不做什么范围、不替代谁的判断、不与哪些 Agent 强制串联、LLM 不做哪类确定性工作。

## 4. workflow.py 统一入口约定

```python
def run(context):
    """Run agent workflow.

    context 字段：
    - task: 当前任务记录（id/agent_id/agent_version/status ...）
    - inputs: 已解析的输入参数（对照 input_schema.json）
    - files: 已上传文件的路径/元信息列表
    - model_gateway: ModelGateway 实例，只能通过 profile 调用，禁止绕过
    - tool_registry: ToolRegistry 实例，只能调用 agent.yaml 中 tools 白名单内的 id
    - event_logger: 事件记录器，关键步骤必须调用（见 05_Task_Event_Standard.md）
    - output_dir: 本次任务输出落盘目录（由 File Service 分配）
    - agent_config: 本 Agent 的 agent.yaml 解析结果
    """
    ...
```

- `workflow.py` 内**禁止**：直接 import 具体模型 SDK、直接 shell 调用外部程序、绕过 `tool_registry` 直调工具函数、写文件到 `output_dir` 之外的路径。
- 单 case 失败必须捕获并记录 `event_type=case_failed`，不得让整个任务崩溃（除非任务级致命错误）。

## 5. 新增 Agent 的完整步骤（零平台核改动）

1. 在 `agents/` 下新建 `<agent_id>/` 目录，按第1节形态建齐文件。
2. 填写 `agent.yaml`，跑 `contracts/agent.schema.json` 自校验（Registry 启动时也会校验）；若声明 `automation.session_execution=true`，须在 prompt/workflow/schema 定稿后写入与 Registry 同算法的 `execution_digest`，且这些文件任一变更都要同步更新摘要与 `version`。
3. 写 `input_schema.json` / `output_schema.json`。
4. 实现 `workflow.py` 的 `run(context)`，只调用已注册的 `model_gateway` profile 与 `tool_registry` 工具 id。
5. `tools` 字段列出的每个工具 id 必须已在 `tools_impl/` 注册（见 `03_Tool_Package_Standard.md`），否则 Runtime 拒绝执行。
6. 在 `eval_cases/` 放至少 1 组最小样例（正常路径）。
7. 写 `README.md`（能力边界、使用方式）与 `changelog.md`（`0.1.0` 首条记录）。
8. 重启/触发 Registry 重新扫描，确认 `GET /api/agents` 可见。
9. **全程不修改 `backend/app/` 任何平台层代码**——若发现必须改平台层才能接入，先暂停并说明架构缺口。

## 6. changelog 纪律

- 每次 `version` 升级，`changelog.md` 追加一条：日期、旧版本→新版本、改动摘要、改动类型（prompt/workflow/schema/tool依赖）。
- `status` 或 `maturity` 变更同样记入 `changelog.md`（即使 `version` 未变），保留治理轨迹。
- 禁止直接覆盖历史条目，只能追加。

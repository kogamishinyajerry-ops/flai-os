# 04 Model Gateway 标准

> 依据：执行任务书 §4.4 / §7.4。宪法条款：所有模型调用必须经过 Model Gateway；Agent 绝不直连具体模型。

## 1. 核心原则

| 条款 | 内容 |
|---|---|
| 画像制 | Agent 只在 `agent.yaml` 声明 `model.profile`（如 `reasoning`），绝不写模型名（如 `glm-5.1`）。 |
| 网关唯一入口 | 所有对模型的调用必须经 `ModelGateway` 类方法，禁止 Agent/Tool 直接 `import` 模型 SDK 或直连内网模型 HTTP 端点。 |
| 升级零改动 | GLM-5.1 → 5.2（或任何模型替换）只改 `profiles.yaml` 映射，Agent 代码、prompt.md、workflow.py 零改动。 |
| Fail-closed | 上游模型不可达/超时/返回异常 → 如实抛错并落库，绝不静默降级为其他模型、绝不编造回答顶替。 |
| 全量留痕 | 每一次调用（无论成功失败）必须落一条 `model_calls` 记录 + 一条 `task_event`（`event_type=model_call`）。 |

## 2. Profile 分类

| profile | 用途 | 对应任务书能力槽位 |
|---|---|---|
| `reasoning` | 复杂推理、长链条分析（性能盘异常摘要、FTA 辅助推理） | GLM-5.x（推理档） |
| `fast` | 轻量任务（字段别名识别、简单提示） | 小尺寸快速模型（待接入） |
| `vision` | 多模态图纸/报告/试验数据理解 | 多模态模型（待接入） |
| `code` | 代码库辅助、工具适配代码生成辅助 | 代码模型（待接入） |
| `embedding` | RAG 向量化 | Embedding 模型（待接入） |
| `rerank` | 检索结果重排 | Rerank 模型（待接入） |
| `none` | 0-LLM Agent（`agent.yaml.model.profile=none`），网关不参与 | — |

新增 profile 必须先在 `profiles.yaml` 注册，禁止 Agent 侧自造 profile 名后倒逼网关兼容。

## 3. 接口形态（任务书 §7.4）

```python
class ModelGateway:
    def chat(self, profile: str, messages: list[dict], **kwargs) -> dict: ...
    def embed(self, profile: str, text: str, **kwargs) -> list[float]: ...
    def vision(self, profile: str, image_path: str, prompt: str, **kwargs) -> dict: ...
```

| 方法 | 输入 | 输出（约定字段） | 备注 |
|---|---|---|---|
| `chat` | `profile`, `messages`（OpenAI 风格 role/content 列表） | `content`, `token_usage`, `model_name`, `finish_reason` | 对应 `reasoning`/`fast`/`code` |
| `embed` | `profile`, `text` | `vector: list[float]`, `model_name` | 对应 `embedding` |
| `vision` | `profile`, `image_path`, `prompt` | `content`, `token_usage`, `model_name` | 对应 `vision` |
| （预留）`rerank` | `profile`, `query`, `candidates` | `ranked: list` | M1 不实现，接口占位 |

`**kwargs` 用于透传 `temperature`/`max_tokens` 等非契约字段；网关不得因 kwargs 缺失而报错，未识别 kwargs 按各 backend 默认值处理。

## 4. Profile → 模型映射配置

- 文件：`backend/app/model_gateway/profiles.yaml`（M1 里程碑实现，本文档为该文件的行为契约）。
- 结构建议（示例，非最终字段冻结，字段以 M1 实现代码为准）：

```yaml
reasoning:
  backend: glm
  model_name: glm-5.1-4bit   # 升级到 5.2 时只改这一行
  endpoint: TBD_内网侦察
fast:
  backend: TBD
  model_name: TBD
```

- 一个 profile 可配置主模型 + `fallback_profile`（取自 `agent.yaml.model.fallback_profile`）；fallback 仍须走网关、仍须落 `model_calls`，且必须在 `response_summary` 中标注实际命中的是 fallback，不得让调用方误以为主模型响应。
- 内网端点协议、鉴权方式、请求/响应报文格式：**待内网侦察**，M1 阶段以 Mock backend 占位，`model_name` 如实写 `mock`。

## 5. Fail-closed 条款（不可协商）

1. 上游不可达（网络错误/超时/鉴权失败/模型返回非 2xx）→ `ModelGateway` 必须抛出结构化异常，携带 `profile`、`model_name`、`error_message`。
2. Agent Runtime 捕获该异常后：任务状态置 `failed`，`error_message` 写入任务表，**绝不**自动切换到另一 profile 或编造一段"看起来正常"的回答顶替。
3. 唯一允许的自动切换是显式配置的 `fallback_profile`（用户/Agent 作者主动声明的降级路径），且必须在事件与调用记录中如实标注为 fallback。
4. LLM 输出绝不能被当作确定性计算结果使用（宪法条款）；网关只负责传输与记录，不做业务判断。

## 6. 调用留痕：`model_calls` 表（任务书 §8.4）

| 字段 | 说明 |
|---|---|
| `id` | 主键 |
| `task_id` | 关联任务 |
| `agent_id` | 发起调用的 Agent |
| `model_profile` | 本次调用使用的 profile 名 |
| `model_name` | Profile 映射解析后的实际模型名（含 mock 标注） |
| `request_summary` | 请求摘要（禁止落全量敏感 payload，摘要化） |
| `response_summary` | 响应摘要 |
| `token_usage_json` | token 用量（若上游不提供，写 `null` 并在 message 说明，禁止编造数字） |
| `created_at` | 调用时间 |

每次调用同时产生一条 `task_event`（`event_type=model_call`），事件结构与类型清单见 `docs/05_Task_Event_Standard.md`。两者是同一次调用的两个视角：`model_calls` 面向审计明细，`task_event` 面向任务时间线。

## 7. 违规判定（供架构审查用）

- Agent/Tool 代码中出现具体模型名字符串（除 `profiles.yaml` 外）→ 判违规。
- 存在调用未落 `model_calls` 或未落 `task_event` → 判违规（"无事件=没发生"，见 05）。
- 上游失败后返回了看似正常的内容而未标记异常 → 判假绿，严重违规。

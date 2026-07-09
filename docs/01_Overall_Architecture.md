# FLAi-OS 总体架构

> 依据：《FLAi-OS_Fable5_执行任务书》§3、§5。本文档是架构契约，不是介绍文章——任何实现违反本文档的分层职责，视为违宪，须先改本文档（走 ADR）再改代码。

## 1. 一句话定位

FLAi-OS = 内核（Registry/Runtime/Gateway）+ 插件（Agent/Tool 标准包）+ 资产库（contracts/evals/data）。内核只做调度与契约校验，不含任何业务逻辑；业务逻辑全部封装在 Agent Package 与 Tool Package 内。

## 2. 架构图（原样收录，禁止在实现中省略任一层）

```text
                   工程师 / 部门 AI 应用负责人
                              |
                              v
                    Web UI 工程智能体门户
                              |
                              v
                        FastAPI Backend
                              |
        +---------------------+----------------------+
        |                     |                      |
        v                     v                      v
  Agent Registry         Task Center           Admin Console
        |                     |                      |
        v                     v                      v
  Agent Runtime       Job Runner / Event Log   Version / Permission
        |
  +-----+---------+----------+----------+----------+
  |               |          |          |          |
  v               v          v          v          v
Model Gateway   RAG       Memory      Tool       File Service
                Service   Service     Registry
  |                         |          |
  v                         v          v
GLM 5.x / 小模型 / 多模态   Obsidian / Codebase Memory / Run Memory
                                      Python Adapter / MCP Adapter
                                                   |
                                                   v
                              性能盘 / Excel / Python脚本 / 后续专业工具
```

## 3. 「槽位不可删」原则

- V0.1 允许某层是最小实现或 Mock 实现（例如 RAG Service、Memory Service、Admin Console 可以先是空壳/桩代码）。
- **禁止**因为某层暂时用不上就在代码结构或架构图中删除该层——后续能力必须挂载在预留槽位上，不能推倒重来。
- 判断新增代码该挂哪一层时，先查本图；查不到位置，先补本文档再写代码（说明架构本身有缺口，需走 ADR）。
- Mock/最小实现必须在代码与文档中如实标注（如 `mock=true`），不得让调用方误以为是真实实现。

## 4. 各层职责表

| 层 | 职责 | V0.1 状态 |
|---|---|---|
| Web UI 工程智能体门户 | 工程师使用入口：Agent 列表、任务创建、任务详情、历史、反馈 | 里程碑2 交付 |
| FastAPI Backend | 唯一后端入口，聚合以下所有子模块的 API | 里程碑1 交付 |
| Agent Registry | 扫描 `agents/*/agent.yaml`，用 `contracts/agent.schema.json` 校验，暴露 `GET /api/agents` | 里程碑1 |
| Task Center | 任务创建/查询/取消，关联 Agent 版本、模型版本、工具版本、输入输出文件 | 里程碑1 |
| Admin Console | 版本与权限管理 | V0.1 最小占位，不做复杂权限 |
| Agent Runtime | 加载 Agent Package，构造 context，执行 `workflow.py`，捕获异常，更新任务状态 | 里程碑1 |
| Job Runner / Event Log | SQLite 任务表轮询 + 任务生命周期事件记录 | 里程碑1 |
| Model Gateway | 屏蔽具体模型，统一 `chat/embed/vision` profile 接口，记录 model_calls | 里程碑1 最小接口，真实模型接入待内网侦察 |
| Tool Registry | 扫描 `tools_impl/*/tool.yaml`，用 `contracts/tool.schema.json` 校验，统一 `call(tool_id, payload, context)` 入口 | 里程碑1 |
| RAG Service | 检索增强生成，接 Obsidian/知识库 | V0.1 占位槽位，不实现 |
| Memory Service | Knowledge/Engineering/Run 三类记忆 | V0.1 占位槽位，不实现 |
| File Service | 上传/下载、原始输入输出落盘、与 task_id 关联 | 里程碑1 |
| 具体模型（GLM 5.x 等） | 内网 GPU 部署，Agent 绝不直接调用 | 接入方式待内网侦察 |
| 具体工具（性能盘等） | 封装在 Tool Package 内，Agent 绝不直接调用 | 里程碑3起逐步接入 |

## 5. 仓库目录结构与职责（依据 §5）

| 目录 | 职责 | 备注 |
|---|---|---|
| `docs/` | 系统宪法、架构、各标准文档、ADR | 第一天起必须存在 |
| `contracts/` | 全部 JSON Schema（agent/tool/task/event/model_profile/knowledge_scope） | 唯一 SSOT，字段变更先改此处 |
| `backend/app/` | FastAPI 应用：`api/ core/ runtime/ model_gateway/ knowledge/ memory/ tools/ jobs/ storage/ governance/` | 每个子目录对应架构图一层，不得跨层写业务逻辑 |
| `frontend/` | Vue 3 + Vite + Element Plus | `src/api` 集中所有后端调用 |
| `agents/` | Agent Package 集合，每个子目录一个 Agent | 见 `02_Agent_Package_Standard.md` |
| `tools_impl/` | Tool Package 集合，每个子目录一个 Tool | 见 `03_Tool_Package_Standard.md` |
| `evals/` | 每个 Agent 对应的回归评测集 | 模型/Prompt/Workflow 改动后必跑 |
| `data/` | `uploads/ outputs/ task_runs/ vector_store/ memory_store/ samples/` | 唯一文件落盘根，禁止散落他处 |
| `logs/` | 运行日志 | 与 task_events 表互补，不替代 |
| `scripts/` | 启动/初始化/打包脚本 | Windows 环境，PowerShell 优先 |
| `tests/` | 跨模块集成测试 | 单模块测试放各自 `backend/tests` |

## 6. 数据流向铁律

- 工程师请求 → Web UI → FastAPI → Task Center 建任务 → Agent Runtime 执行 → 期间一切模型调用经 Model Gateway、一切工具调用经 Tool Registry → 产出写入 File Service → 全程写 Event Log。
- 任一环节绕过其所属层（如 Agent 直连 GLM、Agent 直接 shell 调用性能盘），即为违宪，见 `docs/00_FLAi-OS_Constitution.md`。

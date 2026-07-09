# FLAi-OS Kernel V0.1

二所工程智能体运行底座。当前处于 **M0（系统宪法与核心契约）完成态**。

## 是什么 / 不是什么

| 是什么 | 不是什么 |
|---|---|
| Agent 注册与运行底座 | 单纯 ChatGPT 内网版 |
| 模型接入网关（Model Gateway） | 单独的性能盘工具 |
| 工程工具调用框架（Tool Registry） | 临时 Demo |
| 企业知识与记忆系统入口 | 大模型直接问答系统 |
| 任务过程与数据资产沉淀系统 | 让大模型假装懂全部飞机设计流程的万能专家 |
| 部门共建智能体的方法论载体 | 性能盘 Agent 本体（性能盘只是第一个业务样板） |
| Agent = 平台插件，非独立系统 | 允许 Agent 绕过 Runtime/Registry 私自调模型调工具的地方 |
| LLM 负责理解/组织/解释/辅助生成 | LLM 负责确定性计算、硬规则校验、数值判断 |
| 契约先行：agent.yaml/tool.yaml 先过 schema 校验才能注册 | 允许字段方言，各 Agent 自创字段绕过契约 |
| 长期资产（docs/contracts/agents/tools_impl/evals）| 一次性代码堆砌 |

完整十条见 `docs/00_FLAi-OS_Constitution.md`。

## 架构一图

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

## 目录导航

| 目录 | 用途 |
|---|---|
| `docs/` | 系统宪法、架构标准文档、`docs/adr/` 架构决策记录 |
| `contracts/` | 核心 JSON Schema（agent/tool/task/event/model_profile/knowledge_scope） |
| `agents/` | Agent Package（配置驱动插件，每个含 agent.yaml） |
| `tools_impl/` | Tool Package（工具封装，每个含 tool.yaml） |
| `evals/` | 各 Agent 的评测集，改动后跑回归 |
| `backend/` | FastAPI 后端（app/ 分层见 M1 实现） |
| `frontend/` | Vue 3 + Vite + Element Plus 前端 |
| `data/` | uploads/outputs/task_runs/vector_store/memory_store/samples |
| `scripts/` | dev/init/release 脚本，`.sh`（本机）+ `.ps1`（内网 Windows）成对 |

## 里程碑

| 里程碑 | 目标 | 状态 |
|---|---|---|
| M0 | 系统宪法与核心契约：任何人看完文档知道 FLAi-OS 是什么/怎么写 Agent/Tool | **完成** |
| M1 | 最小后端核心底座：Hello Agent 可通过后端完整运行 | 待开始 |
| M2 | Web UI 原型：工程师可通过网页跑 Hello Agent | 待开始 |
| M3 | Mock 性能盘 Agent：上传 Excel→批量跑→汇总→样本沉淀（不接真实性能盘）| 待开始 |
| M4 | 真实性能盘 Tool Adapter：替换 Mock，保持调用链不变 | 待开始 |
| M5 | 平台泛化验证：接入 control_logic_agent、fta_agent 验证非性能盘专用 | 待开始 |

## 开发口径

- 后端：Python 3.10+ / FastAPI / SQLite / Pydantic v2 / JSON Schema / pytest。
- 前端：Vue 3 + Vite + Element Plus（已定版，不用 React）。
- 脚本成对：本机 dev 用 `scripts/*.sh`；内网 Windows 用 `scripts/*.ps1`。
- 模型调用一律经 Model Gateway，禁止 Agent 直连具体模型。
- 工具调用一律经 Tool Registry，禁止 Agent 绕过调用未注册工具。

## 三条命令（占位，M1 完成后填真实命令）

```bash
# 待 M1 实现：启动后端
bash scripts/dev_start_backend.sh   # 当前为 NOT-IMPLEMENTED 占位

# 待 M1 实现：跑测试
pytest

# 待 M2 实现：起前端
bash scripts/dev_start_frontend.sh  # 当前为 NOT-IMPLEMENTED 占位
```

## 参考

- 执行依据：`FLAi-OS_Fable5_执行任务书.md`（外部文档，不入本仓）
- 系统宪法：`docs/00_FLAi-OS_Constitution.md`
- 架构决策：`docs/adr/`

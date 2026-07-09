# FLAi-OS Kernel V0.1

二所工程智能体运行底座。当前 **M0-M3 已收口**（审查存档见 `docs/reviews/`），下一里程碑 M4（真实性能盘 Tool Adapter，内网）。

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
| M1 | 最小后端核心底座：Hello Agent 可通过后端完整运行 | **完成** |
| M2 | Web UI 原型：工程师可通过网页跑 Hello Agent | **完成** |
| M3 | Mock 性能盘 Agent：上传 Excel→批量跑→汇总→样本沉淀（不接真实性能盘）| **完成** |
| M4 | 真实性能盘 Tool Adapter：替换 Mock，保持调用链不变 | 待开始（需内网环境） |
| M5 | 平台泛化验证：接入 control_logic_agent、fta_agent 验证非性能盘专用 | **完成** |
| M6（增补） | 导引 Agent：多轮对话推荐 specialist Agent + 预填任务草案（interactive 会话运行时，ADR-0012/0013） | **完成** |

## V0.1 已知限制（诚实清单，非缺陷否认）

1. **任务 inputs 为 JSON 直填**：创建任务页按 Agent 输入契约手写 JSON；按
   `input_schema.json` 自动生成结构化表单是 M4 项。
2. **前端 bundle ~1MB**：Element Plus 全量引入未做按需 tree-shaking；内网静态
   托管场景（无公网带宽约束）接受此体积。
3. **零前端单测**：前端验证靠 `frontend/e2e/m2_acceptance.py` 真浏览器走查 +
   后端 200+ 项 API 契约测试兜底；组件级单测暂缺。
4. **feedback.message 无长度上限**：追加式日志表，事件 payload 摘要已截 200，
   落库全文不限长。
5. **孤儿文件/任务产物残留窗口**：附件已改为提交任务时才上传（选中/移除不产生
   服务端残留），但「附件上传成功后 createTask 失败」仍会留下无主文件；同理，
   批量任务 `samples.jsonl` 写出后若汇总表写出失败（任务判 failed），已写的
   产物残留在 `task_runs_dir` 内且不被注册为输出文件。两类残留的 GC 是 M4 项。
6. **TaskDetail 轮询无退避**：固定间隔轮询，`waiting_review` 等长驻状态停止轮询
   后靠「刷新」按钮手动更新。
7. **任务列表为「最近任务流」分页语义**：`limit/offset` 往回翻页（每页 100，
   「加载更多」append），不提供总数计数（无 COUNT 查询）。
8. **报告纯模板化，无 LLM**：批量任务的 `task_report.md` 为纯 Python 字符串
   模板生成；LLM 摘要报告（失败归纳/修表建议）是 V0.2 项（ADR-0010）。
9. **fta_agent / guide_agent 真实模型调用依赖内网 key**：二者均需
   `FLAI_LLM_BASE_URL` / `FLAI_LLM_API_KEY` / `FLAI_LLM_MODEL_REASONING` 指向内网
   模型服务。本机/CI 无 key 时走 fail-closed（fta→任务 `failed`+`model_call`
   error 事件；导引→本轮 502 且零落库可重试），只能桩测调用链，无法真实产出
   ——这是环境依赖，非缺陷。**平台至今未跑过任何真实业务**（性能盘是 mock、
   模型是桩），泛化能力已证，真实业务闭环待 M4+内网 key。
10. **导引会话不接附件、分析深度有限**：会话只收纯文本（≤16000 字符/轮），不接
    知识库、不调工具——推荐依据只有对话内容与 Agent 注册表；附件在确认草案后的
    创建任务页上传。会话级附件+知识检索是 V0.2 规划项。
11. **会话历史发模型前截窗**：最近 40 条/60K 字符（全量历史仍完整落库可查），
    超窗信息对模型不可见；「超窗摘要」是 V0.2 项。
12. **全局无鉴权**：所有 API（含文件下载、人工放行）不做身份认证，内网可信环境
    权衡 + 任务书 §15「不要一开始做复杂权限系统」；具名字段（created_by/reviewer）
    是留痕不是认证。权限体系是 V0.2+ 项。
13. **无卡死任务回收**：worker 在 `validating`/`running` 中途崩溃，任务永卡该态
    （单 worker 轮询无心跳/reaper）；V0.1 靠人工识别，reaper 是 V0.2 项。
14. **Memory 子系统未实现**：docs/06 三类记忆（Knowledge/Engineering/Run）只有
    标准文档与 `backend/app/knowledge|memory/` 空槽位；失败任务现已沉淀 samples
    行（validation_status=failed，ADR-0013）作为最小落点，「失败→评测用例」的
    自动管道是 V0.2 项。

## 开发口径

- 后端：Python 3.10+ / FastAPI / SQLite / Pydantic v2 / JSON Schema / pytest。
- 前端：Vue 3 + Vite + Element Plus（已定版，不用 React）。
- 脚本成对：本机 dev 用 `scripts/*.sh`；内网 Windows 用 `scripts/*.ps1`。
- 模型调用一律经 Model Gateway，禁止 Agent 直连具体模型。
- 工具调用一律经 Tool Registry，禁止 Agent 绕过调用未注册工具。

## 三条命令（M1 已实现）

```bash
# 1. 初始化数据库（幂等，可重复执行；首次启动前跑一次）
bash scripts/init_db.sh

# 2. 启动后端（uvicorn backend.app.main:app，默认端口 8620，被占则设
#    FLAI_BACKEND_PORT 换端口，绝不挤占已有进程）
bash scripts/dev_start_backend.sh

# 3. 启动 Job Runner（单独进程轮询 queued 任务并驱动 Agent 执行）
bash scripts/dev_start_worker.sh
```

内网 Windows 部署用同目录下同名 `.ps1`（头注 DECLARED-NOT-VERIFIED，本机未测，行为与 `.sh` 保持一致）。

跑测试：

```bash
uv run --no-project --with pytest --with jsonschema --with pyyaml \
  --with fastapi --with httpx --with python-multipart --with "pydantic>2" \
  --with openpyxl python -m pytest -q
```

前端（M2）：

```bash
# 开发模式：vite dev server 端口 8621，/api 代理到 127.0.0.1:8620
cd frontend && npm install        # 首次
bash scripts/dev_start_frontend.sh

# 内网部署模式（免 node）：构建产物由后端静态托管
cd frontend && npm run build      # 产出 frontend/dist/（不入库）
# 之后只需起后端——frontend/dist 存在时 FastAPI 自动托管 SPA，
# 浏览器直接访问 http://127.0.0.1:8620/
```

## 参考

- 执行依据：`FLAi-OS_Fable5_执行任务书.md`（外部文档，不入本仓）
- 系统宪法：`docs/00_FLAi-OS_Constitution.md`
- 架构决策：`docs/adr/`

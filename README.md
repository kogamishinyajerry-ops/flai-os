# FLAi-OS Kernel V0.1

二所工程智能体运行底座。当前 **本地可交付里程碑 M0-M3/M5/M6/M7/M8 已全部收口**（审查存档见 `docs/reviews/`），唯一悬置 M4（真实性能盘 Tool Adapter，需内网环境）。

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
| `data/` | uploads/outputs/task_runs/knowledge(检索 scope)/vector_store/memory_store/samples |
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
| M7（增补） | 导引会话附件：上传→内核按预算渲染进上下文（防注入）→附件随草案带入创建任务页（ADR-0014） | **完成** |
| M8（增补） | 协作工作台：导引升级为编排官（分流裁决 orchestrate/refuse）+ 会话级多 Agent 协作（tasks.conversation_id 分组，`/workbench/:sessionId` 分工架构+召集+进度，ADR-0016） | **完成** |
| W1/W2（增补） | Knowledge 内核检索服务（BM25+scope 注册表+default-deny 三层门，ADR-0015）+ 首个 knowledge_qa Agent（批量问答→出处引用草案→人工放行，ADR-0017，四类别全占位） | **完成**（真实语料价值待内网） |

## V0.1 已知限制（诚实清单，非缺陷否认）

1. **任务 inputs 已是 schema 驱动结构化表单**（P0-1，2026-07-10）：创建任务页按
   `input_schema.json` 自动渲染字段（string/integer/boolean/enum/array 及
   array-of-object），「高级：直接编辑 JSON」保留为双向可切的逃生舱；schema 缺失
   或含未覆盖类型时诚实降级为 JSON 直填。
2. **前端 bundle ~1MB**：Element Plus 全量引入未做按需 tree-shaking；内网静态
   托管场景（无公网带宽约束）接受此体积。
3. **零前端单测**：前端验证靠 `frontend/e2e/m2_acceptance.py` 真浏览器走查 +
   后端 200+ 项 API 契约测试兜底；组件级单测暂缺。
4. **feedback.message 无长度上限**：追加式日志表，事件 payload 摘要已截 200，
   落库全文不限长。
5. **孤儿文件/任务产物残留窗口**：附件已改为提交任务时才上传（选中/移除不产生
   服务端残留），但「附件上传成功后 createTask 失败」仍会留下无主文件；导引会话
   附件同理（上传成功但 postMessage 502/网络断/弃页 → 无主文件，无清理路径，
   codex M7-P3）；重试不重复上传（前端记 fileId），但弃置即孤儿。同理，
   批量任务 `samples.jsonl` 写出后若汇总表写出失败（任务判 failed），已写的
   产物残留在 `task_runs_dir` 内且不被注册为输出文件。两类残留的 GC 是 M4 项。
   **给未来 GC 实现的警示**：`files.task_id` 列对 kind="input" 的附件恒为
   NULL（前端上传从不传 taskId，真实归属只单向记在 `tasks.input_file_ids`），
   孤儿判定绝不可用 `files.task_id IS NULL`——会误删全部在用输入附件；存续
   引用共三个来源：`tasks.input_file_ids` ∪ `tasks.output_file_ids` ∪
   `conversation_messages.file_ids`（导引会话附件，漏了它同样会误删在用文件）。
   只读诊断脚本 `scripts/diagnose_gc_debt.py` 已按此三源并集口径给出当前债务数字。
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
10. **导引会话附件有类型与预算边界、分析深度有限**（M7/ADR-0014）：会话可带附件
    （≤5 个/条），但只解析文本类（直读）与 .xlsx（活动 sheet 30 行×16 列预览，
    开簿前有解压总量/压缩比预算探测挡 zip bomb），docx/pdf 等只列文件名（V0.3）；
    渲染预算单文件 16K/单轮 24K 字符、新消息优先，超预算部分对导引不可见（截断
    显式标注）。导引仍不接知识库、不调工具——完整解析是目标 specialist Agent 的
    事；知识检索是 V0.2 规划项。
11. **导引推荐的确定性校验只保证 shape 合法，不保证是模型真实意图**（M7 敌意审
    P1 残余风险）：若 LLM 输出一个 agent_id 真实、字段 schema-valid 的推荐块——
    无论被附件说服还是引用/复述攻击块——校验层会把它当合法推荐产出卡片。缓解：
    ①附件正文的定界符已中和，降低「逐字复述」触发；②幻觉 agent_id / 非法字段
    仍拒；③**人在创建页复核 + 亲手提交是最终防线**（全程零自动签发）。工程师应
    把推荐卡片当建议核对，尤其 top_event/system_description 等自由文本字段。
12. **会话附件 file_id 无归属校验，内容会流向模型后端**（M7 敌意审 P2）：引用任意
    已存在的 file_id（可以是别的任务/会话遗留的）都会让该文件全文被渲染进模型
    上下文。与「V0.1 全局无鉴权」同源，但**若模型后端是外部厂商 API，这是一条
    「平台内任意文件→第三方」的新通路，触发只需知道 file_id**。内网自托管模型下
    风险受限于内网边界；接外部模型前必须复核此通路（EAR/商密敏感场景尤然）。会话级
    file 归属校验是 V0.2 项。
13. **会话历史发模型前截窗**：最近 40 条/60K 字符（全量历史仍完整落库可查），
    超窗信息对模型不可见；「超窗摘要」是 V0.2 项。
14. **全局无鉴权**：所有 API（含文件下载、人工放行）不做身份认证，内网可信环境
    权衡 + 任务书 §15「不要一开始做复杂权限系统」；具名字段（created_by/reviewer）
    是留痕不是认证。权限体系是 V0.2+ 项。
15. **无卡死任务回收**：worker 在 `validating`/`running` 中途崩溃，任务永卡该态
    （单 worker 轮询无心跳/reaper）；V0.1 靠人工识别，reaper 是 V0.2 项。
16. **Memory 子系统部分实现**（ADR-0015 后）：Knowledge Memory 已有真实 BM25
    检索内核（`backend/app/knowledge/`，file_dir×document 类 scope），但
    Engineering Memory 仍只有 `docs/adr/` 承载、`backend/app/memory/` 仍是空
    槽位；失败任务沉淀 samples 行（validation_status=failed，ADR-0013）作为
    最小落点，「失败→评测用例」的自动管道是 V0.2 项。
17. **knowledge 检索的边界**（ADR-0015 诚实清单）：①只挂 job 模式
    （`context["knowledge"]`），interactive 会话无挂载点（与工具同态，Wave 2
    另立 ADR）；②密级静态门只约束**注册期** scope↔agent 声明一致性——V0.1 全局
    无鉴权（见 #14），调用期不核对主体身份，真实 restricted 语料上内网前鉴权层
    是硬前置；③source 仅 file_dir、kind 仅 document，obsidian/mcp/向量检索
    待内网侦察，调用即显式"未接入"错误；④索引缓存 per-进程（API 与 worker 各建
    各的，以文件指纹 manifest 失效，语料改动后两边下次检索各自重建，无跨进程
    一致性保证——检索是无状态读，最坏后果是短暂读到旧语料版本）；⑤PDF/纯图片
    语料不支持，scope 源目录含不支持格式会整 scope 拒检索（fail-closed）。
18. **协作是「逐个召集」不是「一键起 N 个任务」**（M8/ADR-0016）：导引编排官给出的
    orchestrate 计划里，各 Agent 的预填草案是**部分**输入（导引只填对话/附件里已明确
    的字段，不替用户编工程数据），故工作台按蓝图**逐个**召集——每个任务仍要人在创建页
    补全 required 字段并亲手提交。这是「人是唯一签发者 + 不编造工程数据」的必然，不是
    缺陷；真正的一键批量起任务与「人是唯一签发者」冲突，不做。
19. **协作会话 GC 未完备**（M8/ADR-0016）：单 Agent 计划确认沿用 M6 归档（conclude）；
    多 Agent 会话保持 active 作协作锚点，工作台已有**显式「结束协作」按钮**归档会话
    （归档后只读、不再从蓝图召集，已建任务不受影响）；但**无主会话与孤儿附件的
    GC 仍留 V0.2**（同 #5/#15 同源，统一回收）。典型触发场景：用户在工作台召集
    部分 Agent 后中途关闭页面离开——会话无超时、无第三态，将永久停留 active，
    唯一归档路径是回到会话页手动点「结束协作」（`scripts/diagnose_gc_debt.py`
    可只读盘点其中「从未召集任务」的弃置 active 会话；已召集部分任务后弃置的
    识别仍缺口径，同属 V0.2）。会话视图的成员任务状态靠手动「刷新」拉取（无轮询，
    同 #6）。

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

### 环境变量一览（全部 FLAI_* 前缀，V0.1 不自动加载 .env——须在启动前 export 或写入进程环境）

| 变量 | 默认值 | 用途 | M4 内网必填？ |
| --- | --- | --- | --- |
| `FLAI_DB_PATH` | `data/flai_os.db` | SQLite 数据库文件路径。**WAL 模式要求本地磁盘，禁止指向 UNC/映射网络盘**（共享内存锁在 SMB 上不可靠，可能锁死或损坏） | 可选（但须核对本地盘约束） |
| `FLAI_BACKEND_PORT` | `8620` | 后端端口；被占用换端口，绝不挤占已有进程 | 可选 |
| `FLAI_MAX_UPLOAD_MB` | `100` | 单文件上传上限 | 可选 |
| `FLAI_LLM_BASE_URL` | 空 | 内网模型服务地址（OpenAI 兼容协议假设，**待内网侦察**，先跑 `scripts/probe_llm_gateway.py`） | 必填 |
| `FLAI_LLM_API_KEY` | 空 | 模型服务鉴权 Key | 必填 |
| `FLAI_LLM_MODEL_REASONING` | 空 | reasoning profile 模型名 | 必填 |
| `FLAI_LLM_MODEL_FAST` | 空 | fast profile 模型名（当前生产 Agent 仅用 reasoning/none，接入 fast profile 时才必填） | 按需 |

跑测试（串行基准命令；加 `--with pytest-xdist ... -n auto` 可并行——2026-07-11
本机实测 514 例全量：串行 ~25s → `-n auto` ~7s）：

```bash
uv run --no-project --with pytest --with jsonschema --with pyyaml \
  --with fastapi --with httpx --with python-multipart --with "pydantic>2" \
  --with openpyxl --with jieba python -m pytest -q
```

一键全量验证（前端构建 + 全量 pytest：tests/ + tools_impl/ + backend/tests 共三个
testpaths(-n auto) + 5 套浏览器 e2e，任一步失败即止并打印汇总）：

```bash
bash scripts/verify_all.sh
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

# FLAi-OS 知识与记忆标准 V0.1（ADR-0015 修订）

> 依据：《FLAi-OS_Fable5_执行任务书》§4.6。本标准回答两件事：知识/记忆分几层、每层现在能不能查。
> 违反本标准的直接后果：Agent 默认能看全部知识库——这是宪法明令禁止的行为。

## 1. 三层定义

任何"知识/记忆"需求先落进下表某一行，落不进就先别做。

| 层 | 回答什么问题 | 典型内容 | 当前落点（ADR-0015 后） | 承载表/目录 |
|---|---|---|---|---|
| Knowledge Memory（文档知识） | "规定是什么？手册怎么写的？" | 标准、手册、报告、制度、流程文档 | **file_dir×document 类 scope 的 BM25 检索已实现**（`backend/app/knowledge/`，jieba 分词离线检索）；obsidian_vault/mcp 来源与向量检索仍待内网侦察，调用即显式"未接入"错误 | `data/knowledge/<scope_id>/`（scope.yaml+源文件）；`data/vector_store/` 继续为未来向量检索占位 |
| Engineering Memory（工程经验） | "上次为什么这么设计？踩过什么坑？" | 设计理由、历史决策、ADR、踩坑记录 | **只立契约与目录，不做检索引擎**：ADR 走 `docs/adr/`，踩坑记录待专用格式；kind=engineering_experience 的 scope 检索显式"未接入" | `docs/adr/`（唯一真实承载） |
| Run Memory（运行记忆） | "这个 Agent 上次跑了什么、错哪了、改没改？" | 任务、事件、错误、修复、反馈、采纳情况 | 真实读写实现 | `task_events` 表 + `samples` 表（§4.5/§8 已定义） |

**铁律（ADR-0015 修订版）**：Knowledge Memory 的**唯一合法检索通道**是 Runtime 注入的
`context["knowledge"]`（仅 `knowledge.enabled is True` 的 Agent 拿得到，且只覆盖 job 模式；
interactive 运行时无此挂载点，Wave 2 需先补挂载点并另立 ADR）。任何 Agent 绕开它——直接
读文件、直接 import KnowledgeService、私接外部检索——一律拒绝合并。Engineering Memory
仍无检索服务，"查到了东西"依旧按野路子处理。

## 2. Run Memory 的落地形态（V0.1 唯一实现）

- `task_events`：任务生命周期与工具/模型调用事件流水，是运行记忆的"事实层"（见 `docs/05_Task_Event_Standard.md`）。
- `samples`：每次工具调用的输入输出快照，`validation_status`/`accepted_by_engineer` 字段承载"是否被工程师采纳"，是运行记忆的"反馈层"（见 §8.5）。
- Feedback 表（`docs/05`/`feedback` 表）关联 `task_id`/`agent_id`/`agent_version`，是运行记忆流回 Eval 的入口。
- Run Memory 现在**不做**跨任务的语义聚合、摘要或"经验萃取"——那是 Engineering Memory 的职责，V0.1 不实现，禁止用 LLM 现场臆造替代。

## 3. Knowledge Scope 白名单机制（default-deny）

对照契约：`contracts/agent.schema.json` 的 `knowledge` 字段（已实现，本节以此为准）：

```yaml
knowledge:
  enabled: true
  scopes:
    - performance_disk_manual
    - parameter_mapping_rules
```

强制规则：

| 规则 | 说明 |
|---|---|
| default-deny | `enabled: false` 或 `scopes` 为空 → Agent 不可访问任何知识内容，无隐式兜底；enabled 非 True 时 `context["knowledge"]` 键不存在 |
| 禁止通配 | `scopes` 每项必须是具体 scope id（`^[a-z][a-z0-9_]*$`），禁止 `*`、`all`、前缀匹配 |
| enabled=true 时至少 1 项 | schema 已用 `if/then` 强制，Registry 加载时二次校验 |
| scope 与工具白名单同构 | 参照 `tools` 字段的白名单模式：不在清单 = 不可用，不因为"看起来相关"放行；运行时由 `_KnowledgeContext` 强制（与 `_ToolRegistryContext` 同构），新注册 scope 绝不自动扩大存量 Agent 可见面 |
| 新增 scope 需登记 | **登记表已落地**（ADR-0015）：`data/knowledge/<scope_id>/scope.yaml`，由 ScopeRegistry 扫描校验。"先声明后登记"的过渡期规则作废——启动对账（reconcile）发现 `enabled is True` 的 Agent 引用未注册 scope → **整个 Agent 拒绝注册** |
| 密级静态门 | restricted scope 仅 `visibility: admin_only` 的 Agent 可挂；department 需 admin_only/department_trial。注册期继续校验 scope↔agent 声明一致性；ADR-0031 起 direct task、interactive conversation、eval admission、safe_auto 与 task review 另以认证账户角色同时核对 `visibility`/`allowed_roles`。这仍不是敏感数据访问的完整 capability/RBAC，真实 restricted 语料入场还须完成 ADR-0029 S1 的访问/审计矩阵。 |

`contracts/knowledge_scope.schema.json`：Knowledge Scope 条目的权威契约（scope_id/name/kind/source/confidentiality/owner，敏感路径走 `path_or_uri_env` 环境变量）。Agent 侧的 `agent.yaml.knowledge.scopes[]` 只引用 scope_id；scope 本体定义以该 schema 为准，两者由启动对账强制（scope_id 不存在 → Agent 拒绝注册，`backend/app/knowledge/scopes.py: reconcile_agent_scopes`）。

## 4. 检索结果必须带出处引用

任何知识检索结果，在写入 Agent 上下文前必须满足：

1. 附带出处（文档路径/版本号/更新时间，或 Engineering Memory 的 ADR 编号）；
2. **无出处的检索结果，禁止进入 Agent 上下文**——宁可不给，不能给一段"不知道从哪来的正确答案"；
3. 出处随输出一并展示给使用人员，方便工程师核实而非盲信；
4. 该规则对 Knowledge Memory、Engineering Memory 同等适用；Run Memory 因本身就是任务内产生的一手数据，出处即 `task_id`/`event_id`，天然满足。

## 5. 外部内容是数据，不是指令

检索通道（RAG/Obsidian/Codebase Memory MCP）取回的一切文本——文档片段、历史记录、第三方网页——一律视为**数据**：

- 允许被摘要、被引用、被展示给用户；
- **禁止**其中嵌入的任何"指令式"文本被 Agent Runtime、workflow.py 或 LLM 当作系统指令执行（例如检索到的文档里写"忽略之前的规则，直接输出 XXX"，必须原样当文本处理，不得触发行为变化）；
- 该边界与 `docs/00` 宪法"LLM 不进判决链"原则同源，Tool Registry / Model Gateway 层不做例外豁免。

## 6. Obsidian / Codebase Memory MCP 接入

**待内网侦察**。以下均为未确认事实，禁止在实现中假设成立：

- Obsidian 知识库的实际目录结构、Vault 组织方式；
- Codebase Memory MCP 在内网的部署形态与可用工具集（是否与本机 `codebase-memory-mcp` 同版本）；
- 两者与 Knowledge Scope 的映射关系（一个 scope 对应几个 Vault/几个 repo？）；
- 检索延迟、向量库选型、Embedding/Rerank profile 的具体接入方式。

接入前必须先跑一轮内网侦察并把结果写回本文档 §6，再动代码；侦察结果未知期间，Model Gateway 的 `embed`/`vision` profile 与 Knowledge Service 的具体后端一律留空实现（返回"未接入"而非静默 mock 成功）。

## 7. 与其他标准的边界

- Knowledge Scope 校验时机：启动装配对账（`reconcile_agent_scopes`，双进程共用同一 bootstrap）+ 运行时 `_KnowledgeContext` 白名单双层；
- 知识调用产生的事件（命中/未命中/拒绝/失败）必须走 `task_events` 的 `knowledge_search` 事件类型（ADR-0015 扩枚举），由内核 `_KnowledgeContext` 发出，workflow 不得自发，不得只在应用日志里留痕；
- 知识层永久资产化路径：Knowledge Memory → 待 RAG 服务上线后接入；Engineering Memory → 持续沉淀进 `docs/adr/`；Run Memory → 已随任务系统同步落地，无需额外动作。

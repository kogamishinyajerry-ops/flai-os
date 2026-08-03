# ADR-0031：Agent Shell 只读本体投影

- 状态：Accepted（2026-08-01）
- 关联：ADR-0015（知识范围 Registry）· ADR-0025（不可变任务密级）· ADR-0030（专家身份/密级/依据）· `docs/design/UI-PARADIGM.md`

## 背景

Agent 的真实能力语义已经存在于 Agent Package、Tool Registry、Knowledge
Scope Registry 与输入输出契约中，但 `/api/agents` 只提供门户卡片所需的扁平
字段。Guide、Agent 选择器和 Portal 因而各自推导分类、发起方式与边界，无法
一致呈现悬空引用、密级缺省和 mock 真相。继续为 CFD、CAD 等领域新增页面会
放大这种语义分叉。

## 决策

新增唯一深接口：

```python
AgentShellCatalog(agent_registry, tool_registry, scope_registry).snapshot()
```

它固定一次 `AgentRegistry.snapshot_view()`，只读取当前已注册的 Agent、工具、
知识范围与包内快照文件，生成版本化 `agent_shell.v1` 投影；薄路由
`GET /api/agent-shell` 原样返回该投影。Registry 和 Agent Package 仍是事实源，
投影无写能力、无执行能力、无授权裁决权。

每个 Agent 只使用有业务含义的嵌套关系：

- `identity`：稳定身份与人话摘要；
- `classification`：AI 工作类型、专业域、专长与有用性阶梯；
- `capability`：输入、输出、工具白名单、知识范围白名单及引用解析状态；
- `trust`：生命周期、成熟度、不适用边界、可见性声明、密级、人工复核与依据纪律；
- `launch`：`job → task`、`interactive → conversation`，其他值为 `unknown`。

输入输出 schema 只从 `AgentPackageSnapshot.files` 读取；投影仅给出文件名、
可读状态与字段计数，不透出真实路径或整份 schema。工具与知识引用只在对应
Registry 中存在时标 `resolved`，否则标 `unresolved`。

## Fail-closed 语义

- 缺少 clearance：`effective=internal, source=defaulted`；非法值同样回到
  `internal`，但 `source=invalid_defaulted` 并写诊断。
- `requires_human_review`、`evidence.required`、`tool.mock` 只认字面布尔；
  truthy 坏值不得变成 `true`。
- 未知启动方式不得进入任务候选；畸形快照在 UI 中显示“投影不可用”，不得
  压成“0 个 Agent”。
- 投影不提供 `can_launch`、`available` 或角色授权推断。真正动作继续由既有
  create task / conversation / review API 的权威门判定。

## Agent Shell 消费方式

- Guide 桌面端在对话主线右侧渲染任务上下文轨道；移动端复用 composer 内
  Agent 入口。选择只预填草稿，不发送、不建任务、不签发。
- Portal 能力地图只渲染该投影的 facet 与诊断摘要；治理与团队动作不迁入本体层。
- CFD、CAD、系统计算等后续能力以 Agent Package 的 `domain + tools + scopes +
  I/O schema` 声明接入，不新增本体数据库或领域专用 Shell。

## 不采纳

- 不引入 RDF、Neo4j、图数据库或新的编排框架；当前关系规模与查询模式不需要。
- 不建立通用 nodes/edges API；它会丢失密级、人工复核和引用解析等领域语义。
- 不把 LLM 放入判决链，也不从 maturity/status 推断可信、可签发或已上线。

## 后果

Agent 发现与上下文呈现获得单一语义源，新增领域包可以批量标准化挂接；代价是
新增一份受 JSON Schema 与 API parity 测试约束的公共只读响应契约。任何字段
扩展必须保持 additive、显式版本化和未知态可表达。

# ADR-0036：Owner-scoped 功能/资产地图按需披露

- 状态：Accepted（2026-08-03）
- 关联：ADR-0031（Agent Shell 只读本体投影）· ADR-0033（会话优先工程师壳）· ADR-0034（资产候选账本）· ADR-0035（隔离 Skill Package）

## 背景

Agent Shell 已能回答“平台声明了哪些能力”，Candidate/Package 账本已能回答“一项
真实任务形成了哪些受治理资产”。如果为二者新增 `/map` 页面或第二套资产工作台，
会重新制造导航分叉、常驻面板和新的事实源；如果前端分别遍历任务、Candidate 与包，
又容易在 owner 缺失、摘要漂移或文件损坏时拼出假完整地图。

## 决策

新增唯一只读聚合接口：

```python
FeatureAssetMapCatalog(
    agent_shell_catalog=...,
    asset_candidate_ledger=...,
    contracts_dir=...,
).snapshot(conn, username=authenticated_username)
```

薄路由 `GET /api/feature-asset-map` 只从认证会话取得 username。功能部分复用同一次
`AgentShellCatalog.snapshot()`；资产部分先以 `tasks.created_by_username` 精确筛出当前
owner 拥有、且存在最新 Candidate Revision 的任务；Candidate 自报 owner 只作为漂移
探针参与发现，不能授予读取权。枚举、上限判定与逐项 Candidate 冷读固定在同一个
SQLite 只读事务快照内，再重新核验 Candidate、Bundle、Lineage、Package manifest 与
owner。聚合不直接相信前端 task id、Candidate 自报 owner、状态字段或缓存。

响应使用 `feature_asset_map.v1` 的领域结构：功能 facet、能力摘要、Candidate→Task
Pattern/Skill→隔离 Skill Package→尚未形成的 Workflow/Agent 阶梯。它不提供通用
nodes/edges，也不回传完整 Bundle、Lineage、会话原文、文件路径或 Skill 文件字节。

Guide 主会话挂载一个原生 disclosure。它默认收起，首次展开才读取接口；读取失败或
响应合同不完整时显示“地图暂不可用”，不渲染部分结果。Router 不新增 `/map`，披露区
没有输入框、选择器、执行、注册或晋级按钮。

## Fail-closed 与 owner 边界

- owner 只认认证会话 username 与任务不可变 `created_by_username` 的精确相等；NULL
  不猜测，Candidate/Lineage/Package owner 任一漂移使整份响应 503。
- 当前 owner 的最新 Candidate 逐项冷读；任一来源损坏不会被静默过滤成空资产。
- 单次最多聚合 100 项资产、200 项 Registry 能力；越界整体失败，不截断后宣称地图完整。
- Agent Shell 计数、未解析引用计数与实际投影必须一致；畸形投影整体失败。
- GET 前后不写 Candidate、Event、Package、Registry 或任务账本；响应固定声明
  `writes_database=false`、`executes_work=false`、`registers_asset=false`、
  `promotes_asset=false`。

## 信任语义

Candidate `accepted` 与 Package `approved` 只显示为对应的人审状态，使用 teal 人签语义；
它们不变成 REAL 绿色，也不表示已注册、已发布、已上线或可绕过开工/结果签发门。
Workflow/Agent 未达到证据门时明确显示 `not_formed`，不得用数量或界面存在推断形成。

## 后果

工程师可以在当前主任务里按需理解“平台现在声明了什么、我真正形成了什么”，而不学习
新页面或资产后台。代价是新增一份严格公共响应合同和一次完整冷读；当资产数量超过有界
投影时，后续必须以新的、显式完整性语义设计分页，不能先做静默截断。

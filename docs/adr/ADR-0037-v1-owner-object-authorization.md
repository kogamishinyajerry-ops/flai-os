# ADR-0037：V1 owner 对象授权与受信签发人边界

- 状态：Accepted（2026-08-03）
- 关联：ADR-0019（认证会话与签发者来源）· ADR-0025（不可变任务分级）·
  ADR-0033（会话优先工程师壳）· ADR-0034（Asset Candidate 账本）·
  ADR-0035（隔离 Skill Package）· ADR-0036（owner-scoped 功能/资产地图）
- 取代范围：取代“通过认证即可读写任意用户对象”的隐式旧口径；不改变任务
  状态机、签发证据绑定、资产摘要契约或全局治理 API 的现有平台作用域。

## 背景

ADR-0019 解决了“操作者必须来自真实 session，客户端不能伪造”，但单纯
通过认证不等于有权访问任意任务、会话、文件、Team 或资产草稿。当 ID 可猜或
可从审计链推导时，“先读状态/摘要，再判 owner”还会把他人对象是否存在、处于什么
状态或使用哪个 digest 变成侧信道。

同时，评测任务与用户任务并非同一资源语义：`origin=eval` 是全平台治理证据，
需要被受信签发人群体阅读；`origin=user` 是具体工程师的工作对象。V1 必须明确
这个例外，而不能用“所有任务都私有”或“所有认证人都可改”任一过度简化。

## 决策

### 1. 主体与通用拒绝语义

- 授权主体只来自服务端已验证 session 中的稳定 `username`。请求体、query、
  display name、旧字段或对象自报 owner 不予授权。未认证仍由 ADR-0019 返回 401。
- 资源不存在、属于其他 owner、owner 为 NULL/空白/非规范值、关系链损坏或
  归属无法证明时，对外统一返回泛化 404：`{"detail":"资源不存在或不可访问"}`。
  不使用 403/409/422 区分“真实存在但是他人的”。
- 所有状态、密级、摘要、包内容、验证错误与业务冲突判定都在 owner 授权通过后
  执行。因此跨 owner 请求不能用返回差异探测任务状态、Candidate/Package digest、
  附件分类或队伍是否可召集。owner 通过后，原有 403/409/422/503 领域错误仍如实保留。

### 2. exact-owner 用户对象

V1 以字节级精确相等比较 session username 与下列权威 owner 字段；不从显示名、
关联对象或存量内容回填 owner：

| 对象 | 权威 owner | 读取 | 变更 |
|---|---|---|---|
| user task (`origin=user`) | `tasks.created_by_username` | exact owner | exact owner |
| conversation | `conversations.created_by_username` | exact owner | exact owner |
| input file | `files.owner_username` | exact owner | exact owner/受控引用 |
| output file | 关联 task 的 `created_by_username` | 随 task 可读策略 | exact task owner |
| team blueprint | `teams.owner_user` | exact owner | exact owner |
| asset draft/preview | 来源 conversation owner | exact owner | 不写永久资产 |
| Asset Candidate | `asset_candidates.initiated_by_username` + 来源 task/conversation | exact owner | exact owner signer |
| Skill Package | `skill_packages.owner_username` + Candidate 来源链 | exact owner | exact owner signer |

任何 legacy NULL 都是“归属不可证”，而不是“认证用户共享”。V1 不做在线猜测归属或
自动迁移；如未来需要恢复存量对象，必须通过独立、可审计、由人授权的迁移流程。

### 3. 列表在分页前授权

列表 API 必须把 owner/可读 cohort 条件写入 SQL `WHERE`，然后才执行
`ORDER BY ... LIMIT ... OFFSET ...`。禁止先取全局窗口再在 Python 中过滤，因为他人更新的
记录会挤占当前 owner 的页面并暴露全局数量/时序。该规则适用于 task、conversation、
team 及任何后续新增的 owner-scoped 列表。

task 列表的 SQL 可读窗口为：

```sql
origin = 'eval'
OR (origin = 'user' AND created_by_username = :session_username)
```

`origin=user` 只取 owner 行；`origin=eval` 只取全局评测证据；`origin=all` 在 SQL
内取两者并集后才分页。

### 4. eval task 是 tenant-wide 只读治理证据

- 任一已认证 signer cohort 成员可读取 `origin=eval` 的任务详情、事件、模型/工具
  运行、feedback、delivery summary 与关联 output 证据。这是评测/晋级可复核性的显式
  例外，不是将 user task 开放为 tenant-wide。
- 读例外不授予变更权。cancel、review、feedback 创建、任务级资产操作或任何其他
  mutation 仍要求 exact task owner。因此 owner 为 NULL 的 eval task 可作为只读证据，但没有
  任何在线用户能通过 owner gate 修改它。

### 5. 附件与资产的整链授权

授权不只检查“本次请求新带的附件”。会话、任务与资产派生可能重放整个
历史 work segment，所以必须先证明：

1. conversation 属于当前 owner；
2. 历史全部 `conversation_messages.file_ids` 都是结构合法的列表；
3. 每个引用都指向当前 owner 的真实 input file；
4. task、Candidate、Package 的 owner 与来源 conversation/task 精确一致；
5. output file 仍能反向证明其权威 task 关系。

任一历史附件为 foreign、legacy NULL、缺失、类型错误或关系漂移，整条会话/任务/资产
操作都以同一泛化 404 关闭，不会因为“最新一条消息干净”而重新打开旧泄漏通路。

### 6. owner_signoff 与 human signer cohort

V1 的签发模型是 **owner_signoff**，不是独立审核者工作流：

- 只有当前对象 owner 可对 user task、Asset Candidate 和 Skill Package 执行对象级
  签发/变更；签发人来自当前 session，不接受客户端 `reviewer`/`actor`。
- creator 与 owner 是同一稳定 username 时，允许其显式自签。审计记录必须如实标记
  `self_review=true` 及 username 精确比较依据，不得把它包装成“独立复核”。
- V1 不实现 reviewer assignment、owner delegation、细粒度 RBAC、部门/职级/密级
  clearance 或双人职责分离。部署管理员只应为组织已授权人员激活账户，因为
  每个活跃账户都属于受信的 human signer cohort。

这是 V1 的明示产品边界，不是用 owner 隔离冒充组织授权或安全职责分离。

### 7. 全局治理 API 的边界

Agent 级 eval case/eval run、promotion 与 tenant-wide governance reporting 等全局治理 API
继续以“已认证且属于 human signer cohort”为门，不引入本 ADR 未定义的 admin/
reviewer 角色。它们对全局 Registry/评测/晋级账本的读写不得被误解为对他人 user
task、conversation、file、team 或个人资产的授权。

这意味着 V1 仍依赖“只为组织已授权签发人开通账户”的部署约束。未来如果需要
把全局治理动作限制给特定职责，必须单独引入角色、委派、撤销与审计契约，
不得悄然把用户对象 owner 当成全局 admin 角色。

### 8. UI 与功能/资产地图

本 ADR 只加固现有 API/资产链的授权语义，不增加角色后台、对象分享页或导航分支。
ADR-0036 继续有效：功能/资产地图只从当前 session 取 username，只在主会话内按需冷读，
任一 owner/摘要/文件/来源不成立就整体 fail-closed；**不新增 `/map` 页面**。

## 后果

- 用户对象不再只是“需要登录”，而是以稳定 username 默认私有；他人 ID、状态、
  digest 和历史附件无法被 API 当成存在性 oracle。
- eval 证据保持 tenant-wide 可复核，同时 mutation 仍关闭；列表分页不被他人数据
  污染。
- 代价是 legacy NULL 对象在线不可访问，且 V1 不支持共享、委派或独立审核者流程。
  这些不能用宽松回退解决，只能以新 ADR 和显式数据迁移/授权契约后续扩展。

## 验证契约

1. 每一类 user object 都有两个真实账户的跨 owner 敌意测试；foreign、missing 与
   legacy NULL 的响应状态/泛化 body 相同。
2. 拒绝路径业务表、事件、文件与外部副作用零写入，并证明 owner gate 早于
   状态/digest/分类评估。
3. task/conversation/team 列表用可观察的交错时序数据证明 SQL owner/cohort 过滤早于
   `LIMIT/OFFSET`。
4. eval task 对不同账户的详情/子证据/output 均可读，但所有 mutation 仍过
   exact-owner gate。
5. 任一历史 conversation attachment 的 foreign/NULL/缺失/畸形投影都关闭当前会话与
   资产派生操作。
6. 无认证请求仍是 401；owner 通过后的真实业务冲突仍保留精确 403/409/422/503；
   Router 无 `/map` 路由。

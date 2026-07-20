# ADR-0039：精确用户名签收路由与个人审核收件箱

- 状态：Accepted（P2.5 已实现）
- 日期：2026-07-20
- 范围：任务创建、个人签收投影与审核 UI 文案

## 背景

P2.5 之前，多个页面把最近 100 条全局任务中所有 `waiting_review` 都称为“待你签发”。
平台当时没有点名事实，也不知道“你”是谁；这既会漏掉窗口外任务，也会把全局队列
伪装成个人收件箱。现有 `task_human_decisions.reviewer_username` 只记录实际签发人的认证
身份，不能被复用成事前路由，否则会混淆请求人与裁决人。

## 决策

### 1. 点名是路由，不是授权

任务新增可空字段 `review_requested_from_username`：

- 只接受创建时点存在且活跃的精确 `users.username`；空白、首尾空格、超长、未知与
  停用用户均 422；显示名永不参与匹配；
- 只决定任务进入谁的个人收件箱，不授予资格、不形成独占义务，也不禁止其他已认证
  用户按现有政策签发；
- 实际签发人仍只由服务端会话写入 `task_human_decisions.reviewer_username`；请求人与
  实际签发人可以不同，二者可联表对账；
- `NULL` 表示未点名。存量任务与 eval 任务保持 `NULL`，禁止从 `created_by` 或
  display name 猜测回填；v1 不提供改派接口。

单任务、原子 batch 与团队 summon 使用同一顶层字段；批量入口一人覆盖整批。存储 trigger
复查活跃 exact username，并拒绝普通 UPDATE、冲突 INSERT/REPLACE 与
`UPDATE OR REPLACE` 身份覆盖改写路由。列、索引和四个 trigger 由独立 exact schema
witness 校验；已有点名事实时同名 no-op/缺失 guard 必须停机，不能重建后洗成绿。复合
部分索引只服务个人 `waiting_review` 查询，不改变任务状态机。

### 2. 个人收件箱由服务端按会话身份生成

只读入口为：

```text
GET /api/me/review-inbox?limit=50&offset=0&snapshot_id=<上一页快照>
```

客户端不能传目标用户名。成员谓词固定为：

```text
origin = 'user'
AND status = 'waiting_review'
AND review_requested_from_username = session.username
```

响应为 `review-inbox/v1`，含 `items`、`has_more`、可空 `next_offset`、`total` 与完整集合的
`snapshot_id`，使用 `Cache-Control: no-store`，每条任务仍经过既有 sensitive 遮蔽
chokepoint。后续页必须携同一快照；集合或投影在分页期间变化时服务端 409，客户端丢弃
本轮并从第一页重取（最多三轮）。envelope 任一字段缺失、类型错误、快照漂移、重复 id 或
终页计数不一致均 fail-closed，不能把截断列表或加载失败画成空收件箱。

候选人名册为 `GET /api/me/review-routing-users`，只返回活跃用户的 `username` 与
`display_name`。同名时选择器必须显示 `显示名（username）`；加载失败必须明示不可用，
不得伪装成零用户。

### 3. 只有精确个人投影可以使用个人化文案

StatusDock、状态中心、今日页、任务台和标题徽标只从个人收件箱计数，显示“点名请你签”。
全局任务窗口、会话团队摘要与未点名任务统一使用“待人工签发/待签发”。任务详情仍保留
既有签发动作：点名不是权限门；页头仅在 exact username 命中时显示个人化徽标。

个人 channel 以认证 username 分世代。登录身份变化时先清旧投影再重新取权威快照，断连
保留最后真实结果并标旧，绝不跨账号复用。

## 边界

- 本 ADR 不引入角色、审核资格、职责分离 403、通知服务、改派状态机或自动签发。
- 人仍是唯一签发者；LLM、Agent 与路由字段都不能进入裁决链。
- N10 仍延期且 `n=0`，M4/真实评审关系仍未验证。本地测试通过不证明组织政策或生产采用。

## 验收

- 同 display name 的 Alice/Bob 只按 exact username 隔离个人收件箱；
- 未点名、点名他人、eval 与已离开 `waiting_review` 的任务不进入本人收件箱；
- 未知/停用点名在单建、batch 与 summon 入口零任务写入；
- 原始 SQL 与 `recursive_triggers=OFF` 的冲突更新均不能改派；前代数据库保留历史事件后
  原位升级；同名 no-op guard 在已有点名事实时拒绝启动；
- 另一认证用户仍可签发并留下自己的真实 reviewer username；
- 名册只暴露两个安全字段；个人接口 `no-store`、快照一致分页且经过 sensitive 遮蔽；
- 全局 UI 不再出现“待你签发”，身份切换清旧投影，production build 与 Node 契约通过。

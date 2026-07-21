# ADR-0031：认证会话的受限自动执行（safe_auto）

> 2026-07-21 部分扩展：ADR-0032 已在严格版本化 `guide_dag.v1` 内实现
> 多 Agent DAG、当前轮附件来源绑定与同标签页跨刷新幂等。本 ADR 的
> “单 Agent/无附件”仍是 legacy `agents[]` 物化边界；本文其余正文保留为首版决策。

- 状态：已接受（2026-07-21，owner 明确要求协作方案可由智能体自动执行）
- 取代范围：仅取代 ADR-0012 决策 4、ADR-0016「红线守恒」中“每个任务必须由人
  进入创建页亲手提交”的机械步骤；LLM 不进判决链、人是唯一工程签发者、假绿禁止、
  fail-closed 与信任色规则全部保留。

## 背景

现有导引会生成方案，但用户仍需逐 Agent 打开创建页、搬运预填参数并点击提交。
这些动作不包含工程判断，却造成大量中断。另一方面，当前计划是扁平 `agents[]`，
输入允许不完整，附件存在已知回显注入残余，工具契约也未声明可重放副作用；因此不能
把任意 LLM 计划直接接到任务执行器。

## 决策

1. `POST /api/conversations/{id}/messages` 新增显式
   `execution_mode="safe_auto"` 与有界 `request_id`。授权来自已认证用户这一轮请求，
   不是从自然语言或 LLM 输出推断。API 默认 `plan_only` 保持旧调用方兼容；产品
   GuidePage 默认发送 `safe_auto`。

2. 新增深模块 `GuidePlanDispatch`，位于 guide 确定性校验之后、任何任务写入之前。
   普通 Agent workflow 不获得建任务能力；只有该模块能物化冻结计划，且不能新增节点、
   改目标、签发、验收或发布。

3. 首版只有以下条件**全部严格成立**才自动创建并入队：

   - `decision == orchestrate`，且恰好一个 Agent；
   - `dropped_agents == []`、`capped is False`、`stripped_fields == []`；
   - Agent 仍注册、未 disabled、`workflow.mode == job`，计划锁定版本与当前版本相同；
   - 完整 `prefilled_inputs` 通过目标 `input_schema.json`（含 required/组合约束）；
   - **当前 safe_auto 请求**中存在与完整输入深相等的顶层 JSON 对象，或顶层
     `{"inputs": {...}}` envelope；历史轮 JSON、示例/拒绝对象内嵌套的 JSON 都不
     构成本轮授权。只做叶值全文匹配会丢失字段/结构关系，故禁止模型交换字段或仅凭
     自然语言猜字段归属；
   - 本会话无附件；首版尚无逐 Agent 附件绑定、所有权 envelope 与来源字段；
   - Agent 显式声明 `automation.session_execution is True`、`effect == none`，且
     `tools == []`、`input.type == params`；
   - 当前认证账户角色同时满足 Agent `permissions.visibility` 与 `allowed_roles`；
     `admin_only` 仅 admin，`department_trial` 仅 admin/agent_developer，`all` 仍须在
     allowed_roles。原 Agent 权限不因自动化而放宽。

   当前显式开放：`control_logic_agent`（确定性、零模型/零工具）与 `fta_agent`
   （零工具，但产物强制 `waiting_review`）。其余 Agent 默认拒绝。

4. 预期阻断不伪装成系统故障：持久化为 recommendation 内的 `execution` 投影，状态为
   `blocked_input | blocked_source | blocked_policy | blocked_conflict | awaiting_plan |
   refused`，并给机器 code 与人读原因；任务数严格为 0，会话保持 active，用户直接在
   composer 补充。

5. 成功路径在一个 `BEGIN IMMEDIATE` 中原子写入：user/assistant 消息、推荐快照、
   task、`created→queued`、`task_created` 事件与 `conversation_dispatches` 幂等回执。
   任一步失败整批回滚。唯一键 `(conversation_id, request_id)`；同键同摘要重放既有
   task IDs，同键不同消息/身份返回 409。

   所有会话消息写入（含 `plan_only`）都必须匹配会话创建时冻结的
   `created_by_username`；存量无该身份的会话只保留兼容的 plan_only，不能 safe_auto。
   其他用户在模型调用前返回 403，不能先污染历史再借 owner 触发执行。

   账户新增 V0.1 `role` adapter。存量账户此前事实上拥有全部 API 能力，迁移时显式
   记为 admin 以保持既有权限；新账户默认 business_user，管理员可用
   `user_admin.py set-role` 变更。角色更新/停用与旧会话吊销同事务提交。

   Agent 调用权限统一走一个 default-deny predicate：当前角色必须同时满足
   `visibility` 与 `allowed_roles`。该门覆盖 direct task、interactive conversation、
   eval admission、safe_auto dispatch 与人工 task review；任务/评测提交事务内会重读
   `users.is_active/role`，长模型调用期间被降权或停用则整轮零落库。review 仍是认证真人
   显式 approve/reject，角色门只决定谁有资格签，不让 Agent 取得签发能力。

6. 自动执行只替代“创建与入队”。模块永不调用 review API、永不生成
   `review_approved`、永不写 completed、正式会议记录、责任事项验收或规则发布。
   `requires_human_review=true` 的任务仍只能停在 `waiting_review`，由认证真人签发。
   `completed` 仍不自动给绿；真人签发仍用 teal。

7. 首版不做任务级自动重试。现有工具契约没有 `automatic_retry_allowed`、稳定
   idempotency key 与 receipt；超时或失败保持真实状态，不重放可能的副作用。

## 明确不做

- 不从自然语言 `workflow` 猜多 Agent 依赖；多 Agent 计划返回
  `EXECUTABLE_GRAPH_REQUIRED`，零任务。
- 不把会话附件扇出给所有 Agent。
- 不通过前端脚本模拟点击 `/tasks/new`。
- 不新增 Redis、Celery、新数据库或第二套任务状态机。
- 不把三角色 adapter 冒充最终 capability/RBAC 模型；Agent 发布/晋升、样本策展、
  敏感数据访问与审计读取仍须另立并审批能力矩阵。本 ADR 只闭 Agent 调用、
  自动派发和任务签发的直接旁路。

## 后续演进门

开放多 Agent 自动协作前，必须先版本化结构化 node/DAG/input-binding/source-anchor
契约，并证明整图原子提交、同图 provisional output 边界与最终叶节点人签。开放附件前，
必须有不可变上传者身份、conversation binding、classification/egress 与逐节点文件槽。
开放自动重试前，必须补齐工具 effect、幂等键、receipt 和结构化 retryable failure。

## 验证

- invalid-first：缺必填、附件计划、模型补造事实、工具 Agent、多 Agent 图均零任务；
- 正例：完整 allowlisted 计划原子得到一个 queued 任务与一条 `task_created`；
- 幂等：同 request 重放零模型调用、零重复消息、零重复任务；异载荷同 key 409；
  当前官方单进程启动脚本中，重叠的同 key 请求也先按 key 串行化，输家不重复调模型；
  跨进程数据库副作用仍由 SQLite 唯一回执保证 exactly-once；
- 故障注入：事件写失败时消息、任务、事件、回执全部回滚；
- 授权负例：business_user 对 admin_only Agent 的 direct task、eval 与 review 均 403；
  模型生成期间降权/停用返回 403，消息、任务、回执均为零；
- 来源负例：旧轮存在完整 JSON、本轮只否定/讨论时仍 blocked_source、零任务；
- 既有 `plan_only` 与人工 review 回归保持不变。

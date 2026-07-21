# ADR-0032：版本化 Guide DAG、附件来源绑定与跨刷新幂等

- **状态**：Accepted（2026-07-21，用户明确要求实现）
- **前置**：ADR-0031（认证 safe-auto、单 Agent 原子派发）
- **范围**：Guide 会话中的无点击任务编排；不改变人工 review/正式工程签发红线

## 背景

ADR-0031 只允许单 Agent 自动创建。多 Agent 计划缺少机器可读依赖图时必须整体
阻断；附件也因缺少不可变上传主体和逐节点来源证据而不能进入自动任务。前端仅在
同一 Vue 实例内保存 `request_id`，浏览器硬刷新会丢失未知结果操作的幂等键。

## 决策

### 1. 只执行版本化 `guide_dag.v1`

Guide 不从自然语言 `workflow` 或旧 `agents[]` 猜依赖。可执行图必须显式声明：

- `contract == "guide_dag.v1"`；
- 1–5 个拓扑有序 `nodes`，`node_id` 与 `agent_id` 各自唯一；
- 依赖只指向此前节点，且 V1 恰好一个叶节点；
- 每节点锁定精确 `agent_version`、完整 `prefilled_inputs`、`depends_on`、
  `artifact_binding` 与 `attachment_binding`；
- 当前用户轮必须显式提供顶层 `{"inputs_by_agent": {...}}`：键集合与
  所有节点 `agent_id` 完全一致，每个值与该节点冻结 `prefilled_inputs`
  按类型严格深相等；历史轮、散文转述或只匹配叶值都不构成授权；
- 根节点只允许 `artifact_binding.mode == none`；有依赖节点必须为
  `all` 或非空 `selected`。现有 resolver 把空 `from_tasks` 解释为默认拷全部，
  V1 不改其公共语义，也不把“等依赖但不接产物”伪装成可表达；
- 任一 unknown version、剥离字段、版本/manifest 漂移、权限漂移、缺输入或图退化，
  整图零任务。

图编译到已有 `tasks.depends_on + input_binding`，不新增图表、状态机、队列或
编排服务。全部节点在同一个会话 `BEGIN IMMEDIATE` 中创建；根节点进入
`queued`，下游保持 `created`，由现有 SQLite resolver 推进。

为消除中间人工点击又不让未签 LLM 产物越界：

- 非叶节点必须 `model.profile == none` 且
  `requires_human_review is False`；
- 唯一叶节点必须 `requires_human_review is True`；
- 所有节点仍须 `automation.session_execution is True`、`effect == none`、
  `tools == []`，并通过当前认证角色门；
- Agent 永不写 review，最终叶节点仍停在 `waiting_review`，只接受真人具名签发。

### 2. 附件只按当前轮、当前主体、唯一节点绑定

新增不可变证据：

- `files.uploaded_by_username`：上传时从认证会话写入；存量 NULL 不反推；
- `tasks.source_binding_json`：任务 INSERT 时一次写入 `task_source.v1`，不提供
  覆盖 setter；
- 每条证据绑定 `conversation_id + request_id + file_id + sha256 +
  classification + uploaded_by_username + slot`。

`safe_auto` 在调用 Guide 模型前先验证本轮全部 `file_ids`：必须唯一、存在、
`kind=input`、未归属任务、`classification=internal`，且不可变上传 username
等于当前认证主体，并用已验文件句柄复核权威根、大小与实际 sha256。
提交写锁内再次复核同一证据，模型期间删除/篡改同样整轮回滚。legacy uploader、
外人文件、sensitive、output、已归属、缺失或完整性失配文件均零模型调用、零消息、零任务。

V1 禁止附件扇出和静默丢弃：有附件时图中必须恰好一个节点声明
`attachment_binding.mode == current_turn`，本轮附件全集只进入该节点一次；
无附件时所有节点必须声明 `none`。绑定进入任务 `input_file_ids` 与
`source_binding`，计划摘要和回执保留图摘要。

### 3. 浏览器 outbox 只恢复意图，SQLite 回执仍是事实源

前端在任何 safe-auto POST 前，把严格版本化记录写入并回读
`sessionStorage`：认证 username/role、稳定 `request_id`、原始 content、
不可变 `file_ids`、目标会话和最小文件展示信息。原始 `File`、cookie、token
及 token hash 绝不落浏览器记录。

- 存储不可用、记录畸形、未知版本或主体/角色漂移：零 POST，fail-closed；
- fresh 会话创建也使用同一稳定 key；`conversations.creation_request_id` 的
  owner 级唯一索引保证响应丢失后重试返回同一会话；
- 已绑定的 `conversation_id` 只允许 CAS-on-NULL，一旦绑定不得改写；
- reload 后先 GET 权威会话。若已见相同 `execution.request_id`，清 outbox；
  否则只用原载荷和原 ID 重发；
- POST 成功后仍需 canonical GET 确认回执可见才清除；GET 失败保留记录；仅当
  同页面、同主体、同会话且完整 intent 与 outbox 精确一致时，才可复用原
  `request_id` 重试；存储不可读、记录缺失或不匹配、路由漂移时锁住 composer；
- 409 不生成新 ID。服务端 `conversation_dispatches` 至少与会话同寿命。

### 4. 会话创建幂等

`POST /api/conversations` 接受可选 `request_id`。同一 owner、同 key、同
`agent_id` 返回原会话；同 key 不同 Agent 返回 409。索引为：

```sql
UNIQUE (created_by_username, creation_request_id)
WHERE creation_request_id IS NOT NULL
```

`/api/auth/login` 与 `/api/auth/me` 返回角色，供客户端检测恢复主体漂移；
浏览器字段不是授权凭证，后端仍以 HttpOnly 会话与提交点复核为准。

## 原子性与回执

同一 safe-auto 会话事务原子包含：当前 user/assistant 消息、recommendation、
整图 tasks、`task_created` 事件、来源绑定和 `conversation_dispatches`
回执。回执增加 `graph_version`、`graph_digest`、拓扑有序 `node_tasks`。
任一步异常全部回滚。

## 明确不做

- 未签 LLM 中间产物、多个叶节点、重复 Agent、跨会话/既存任务依赖；
- sensitive 附件、附件扇出、按语义猜文件槽、自动 review/promote/publish；
- 多进程模型 single-flight。当前进程内 keyed lock + SQLite receipt 保证本部署
  跨刷新幂等；扩为多 worker 前必须另立持久 claim 或 provider idempotency。
- `sessionStorage` 不承诺标签页关闭后的恢复；浏览器重启持久化需单独数据政策。

## 验证门

- invalid-first：未知图版本、前向依赖、多叶、非确定性中间节点、附件身份/分级/
  唯一绑定失败均零副作用；
- 正例：整图一次物化，根 queued、下游 created，resolver 自动推进，叶节点只到
  waiting_review；
- response loss + 新页面实例：原创建 key、原 dispatch key 重放，模型一次、
  每节点任务一次；
- `bash scripts/verify_all.sh` 全绿。

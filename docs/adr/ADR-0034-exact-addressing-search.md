# ADR-0034：精确寻址与只读服务端搜索

- 状态：Accepted（实现与阶段验收进行中）
- 日期：2026-07-19
- 范围：P2.4

## 背景

现有 QuickSwitcher 只先取有限数量的会话和任务，再在浏览器内做 substring 过滤。窗口外的
会话、消息与产物不可见；即使命中消息，也没有稳定消息锚可落点。Fable 批八候选虽包含
LIKE 搜索原型，却以可重复的 display name 代替认证 principal，缺少产物、稳定消息 id、
分页与失败投影，不能作为可信实现迁入。

P2.3 已冻结 exact `username` 会话 owner 与公开 `message_id`。P2.4 只在这些事实之上建立
只读寻址轴，不引入标题、重命名或归档写语义，也不新造侧栏或第二导航面。

## 决策

### 1. 一个请求只搜索一个 scope

公开入口为 `GET /api/search`，每次请求必须且只能选择一个 scope：

- `conversation`；
- `message`；
- `task`；
- `artifact`。

查询 `q` 先 `trim`，长度必须为 2～128；控制字符、空值、重复 scope、未知参数、越界
limit 与 scope 不支持的筛选一律 422。匹配是 literal substring：`%`、`_`、反斜线与引号
都没有通配含义。ASCII 字母大小写不敏感；非 ASCII 按 SQLite 原值精确匹配，不声称中文
分词、模糊搜索或 Unicode case folding。

`status`、`agent_id` 与 `task_scope=all|mine` 只允许用于 `task`/`artifact`。`mine` 按认证
username 精确收窄父任务，不接受客户端传 owner、username 或 display name。

### 2. 权限与投影逐 scope 固定

- `conversation`/`message`：只搜索 `created_by_username` 与当前认证 username 逐字相等的
  会话。foreign、legacy NULL 与不存在统一为空结果，不能形成 owner oracle。
- `task`：面向已认证用户搜索 `origin='user'` 的全站任务元数据；`mine` 才按 exact
  username 收窄。任务输入、错误、metadata blob、binding、文件 id、创建人身份与任何正文
  永不进入索引、匹配或响应。
- `artifact`：只投影 `origin='user'` 父任务的输出，并要求文件 id 精确属于该任务冻结的
  `output_file_ids`。输入文件、孤儿文件、评测文件与仅靠路径或上传者关联的文件均不得命中。
  响应只包含已经允许展示的文件名、大小、类型/密级等元数据；不返回路径、哈希、上传者、
  正文、预览或下载内容，也不自动发起下载。

所有 scope 只返回建立寻址所需的有界 projection 与稳定 typed id。会话不得合成标题，消息
不得泄露内部自增 id 或完整正文；任务和产物不得借搜索扩大既有内容读取权限。

### 3. 无迁移、无 FTS 依赖的有界扫描

P2.4 v1 使用参数化 SQLite literal scan 与确定性内存过滤/排序，不依赖 FTS5、trigram、
JSON1 tokenizer 或新的持久索引。每个源最多扫描 50,000 行，消息正文与产物 membership/
文件名的单源扫描字符预算为 16,000,000；超过任一容量上限即返回 503
`search_capacity_exceeded`，不得把截断结果或空数组伪装成完整搜索。COUNT、字符预算与
SELECT 固定在同一个 SQLite read transaction，避免并发插入越过容量门。

数据库/源查询失败同样返回 503。因为每个请求只有一个 scope，QuickSwitcher 可以并行请求
四组，并把单组 unavailable 明示出来；任一失败都不能被吞成该组“无结果”。搜索不调用
LLM、不写 task/event/audit，也不修改任何业务状态。

### 4. 稳定排序、快照与游标

排序先区分 exact id、id prefix、文本 prefix、文本 contains，再以时间倒序与稳定 typed id
收口。首页固定 `snapshot_at`；后续页只读取该快照内的候选，使用 keyset 而非 offset，避免
新插入记录令页间重复或漂移。

游标是 opaque、版本化且由服务进程随机 HMAC key 签名的 base64url payload，绑定 exact
principal、规范化查询、scope、筛选、limit、snapshot 与末项排序键。畸形、篡改、未来时间，
或跨用户、跨 query、跨 scope、跨筛选、跨 limit 重放一律 422。单实例 API 重启后旧的短生命
游标失效，客户端重新搜索；接口不返回 total，也不暗示未扫描源的精确总数。

响应使用 `search-page/v1` 严格 JSON Schema，返回 `has_more` 与可空 `next_cursor`。HTTP
响应必须带 `Cache-Control: no-store`，防止跨会话复用受 principal 约束的搜索投影。

### 5. 深链由客户端按 typed id 构造

服务端不返回可直接信任的任意 href。现有 QuickSwitcher 按命中类型构造：

- 会话：`/?c=<conversation_id>`；
- 消息：`/?c=<conversation_id>&m=<message_id>`；
- 任务：`/tasks/<task_id>`；
- 产物：`/tasks/<task_id>?file=<file_id>`。

Guide 在权威会话 snapshot 后定位稳定 `message_id`；TaskDetail 先确认 file 仍精确属于
`output_file_ids`，必要时展开已有产物列表，再定位文件卡。锚已过期或无权访问时必须明示
不可定位，不能静默聚焦父对象，更不能自动下载产物。

P2.4 复用现有 QuickSwitcher、Guide 与 TaskDetail，只使用既有暖纸、clay、amber/red 事实
语义、focus、移动端与 reduced-motion 合同；不新增右侧栏、常驻结果墙、信任色或视觉语言。

### 6. 与相邻阶段及 schema witness 的边界

- P2.3 的会话、消息与 Question 表、8 个受管索引、29 个受管 trigger 以及五键 schema
  witness 原样冻结；P2.4 不新增迁移、列、索引或 trigger。
- P2.4 只拥有搜索 projection、稳定寻址与只读深链。
- P2.5 才实现具名人签收件箱；搜索不得推断 reviewer 或产生签收状态。
- P2.6 才实现标题、重命名、归档、历史分组及其审计和并发写合同。
- P2.7/P2.8 的 Open Design 生产 adapter、候选比较、人工批准与精确摘要发布保持后置。

## 验收状态

合同已冻结，代码、契约测试、前端定位与部署自检正在本阶段收口。阶段完成前必须至少证明：

- 同 display name 的不同 username、foreign exact id 与 legacy NULL 均不能跨用户命中；
- task 输入/错误/正文从匹配与响应两侧都不可见，artifact 只认 exact output membership；
- literal 特殊字符、边界长度、非法筛选、游标串用、快照分页、50,000 行容量与源失败均
  fail-closed；
- QuickSwitcher 不出现 debounce 假空态，消息/产物深链能精确落点，失效锚显式报错；
- 搜索为只读、`no-store`，且 P2.3 schema witness 保持不变。

本 ADR 不宣称当前已通过完整浏览器验收或 `verify_all`；这些证据必须以 P2.4 最终工作树的
真实命令退出码另行记录。

## 后果

- 窗口外事实第一次可以按稳定 id 寻址，且 display name 不再进入权限判定。
- 无 FTS/迁移降低 Windows/离线部署差异，但 50,000 行上限意味着更大规模必须另开带迁移、
  tokenizer 与跨平台证据的索引版本，不能静默放宽或假装完整。
- 单 scope 请求增加前端并行编排，但换来可区分的加载、失败与空结果事实，避免一组失败污染
  其余结果。

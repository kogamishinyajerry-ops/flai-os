# ADR-0042：Open Design 候选比较、双闸具名事实与可恢复 PNG 发布

- 状态：Accepted（P2.8 v1；默认无发布目标，真实候选 fail-closed）
- 日期：2026-07-20
- 依赖：ADR-0037、ADR-0041

## 背景

P2.7 只生成候选包，不发布。它的产物来自不受信执行面，manifest 明示
`execution_trust=untrusted_generated`、`candidate_only=true`、
`release_effect=none`，并且当前生产分类固定为 `sensitive`。P2.8 需要让人比较候选，
但不能把“PNG 可被动解析”误当成“内容已脱敏”，也不能让候选批准自动变成发布批准。

## 决策

### 1. 接受面是 exact P2.7 manifest，不接受近似包

服务端只接受 `open-design-daemon-candidate-manifest/v1`，并逐项核对：task 的封印
metadata、唯一 manifest 文件、output membership、路径后缀、size、SHA-256、PNG 结构与
矩阵尺寸。`candidate_id` 固定为 `odc-` 加 32 位小写十六进制；`asset_slot` 固定为：

- `task_review_summary`
- `agent_activity_indicator`
- `workflow_monitor_sidebar`

每个任务只有一个逻辑候选，可含多个比较帧。可发布资产必须是 manifest 中被
`promotable_asset` 精确绑定的 passive-preview PNG；HTML、CSS、脚本及其他 raw source
永不进入发布路径。

### 2. confidentiality 与 execution trust 正交

所有 compare、frame、candidate decision、release request、release decision、publish
边界都重新检查 task/file 的持久 classification。结构扫描只证明 PNG 可被动解析，不会
降低 confidentiality。

当前 P2.7 生产包固定为 `classification=sensitive`，而 P2.8 v1 尚无角色轴、逐文件脱敏
证明或隔离 sidecar。因此真实 P2.7→P2.8 请求必须以 HTTP 403 和
`sensitive_candidate_requires_role_axis` fail-closed。P2.8 的内部 synthetic fixture 仅验证
状态机、账本和文件协议；不得据此声称真实端到端流水线已可运行。

### 3. 比较是不可变证据，workflow 是动态投影

`comparison_json` 与 `comparison_sha256` 一经写入不变。公开 envelope 的 `phase` 和
`workflow` 从 append-only ledgers 动态计算，不参与既有 comparison hash。phase 只有：

`candidate_pending / candidate_rejected / candidate_approved / release_pending /
release_rejected / publish_ready / published / rolled_back / manual_intervention`。

`workflow` 精确包含 `selection`、`release_request`、`release_decision`、`latest_publish`
四键。POST comparison 是 server get-or-create：刷新时返回既有、最新的权威流程证据，
不能依赖前端缓存恢复。未 selection 且目标前像漂移时可创建新 comparison；selection
之后任何目标漂移均返回 409，v1 要求重新生成 P2.7 任务并重新批准。

### 4. 候选批准与发布批准是两项具名人工事实

候选 selection 与通用 `task_human_decisions` 必须在同一 SQLite 事务写入，并引用同一个
caller-supplied decision ID。事务参与 primitive 失败时，selection、decision、事件和任务
状态全部回滚。客户端不能提供 actor；唯一权威是认证 session 的 exact username。

P2.8 本地驳回原因不扩展全局 task reason enum。候选驳回映射到全局
`reason_code=other`，comment 以 `design_selection_reason=<local_code>` 开头，再附规范化的
用户说明。本地 selection ledger 仍保存原始结构化原因。

release request 绑定 exact selection、comparison hash、candidate hash 与 target preimage。
release decision 是第二条独立 append-only 具名事实；同一 username 可以承担两个角色，
但两项动作、时间、ID 与证据不得合并。批准 release 只生成 hash-bound release package，
不会自动写文件。

### 5. 发布目标是服务端封闭且显式注入的 PNG allowlist

v1 合同只允许下列映射，客户端不能提交 target path：

| asset_slot | target_id | target path |
|---|---|---|
| `task_review_summary` | `open_design_task_review_summary_v1` | `frontend/src/assets/open-design/task-review-summary.png` |
| `agent_activity_indicator` | `open_design_agent_activity_indicator_v1` | `frontend/src/assets/open-design/agent-activity-indicator.png` |
| `workflow_monitor_sidebar` | `open_design_workflow_monitor_sidebar_v1` | `frontend/src/assets/open-design/workflow-monitor-sidebar.png` |

这些行是待部署方逐项提供当前帧、目标目录与权限证明后才能注入的 provisioning contract，
不是仓内已经存在的生产资产。`create_app` 默认使用空 `TargetRegistry`，不会猜测任何目标或
当前帧；因此即使未来候选通过分级门，未显式注入目标仍会 409 fail-closed。测试中的 registry
和 PNG 只验证状态机与文件协议，不能冒充生产目标已经配置。

目标前像可以是 absent。所有路径必须是无 symlink 的受控相对 PNG 路径；`.vue`、文本、代码
和目录不可能进入该接口。

### 6. SQLite 与文件系统采用可恢复 intent 协议，不宣称跨域原子事务

SQLite 与文件系统无法组成一个真实 ACID 事务。发布/回退因此按以下顺序执行：

1. 取得目标专属跨平台 OS 文件锁；
2. 再验具名批准、package hash、classification、candidate bytes 与 target CAS；
3. 先提交 append-only durable intent；
4. 写 sibling temp 并 fsync；存在前像时先写、fsync、复核 backup；
5. 最后一次 target CAS 后以 `os.replace` 原子替换，并复核 post-hash；
6. fsync 可用的平台目录，再 append commit 与 idempotent response。

回退恢复 verified backup；原目标 absent 时以同卷原子 move 移出 allowlisted target。每个
mutation 的 idempotency key 是 `(operation, authenticated username, request_id)`；相同请求
字节返回同一结果，不同字节复用 request ID 返回 409。

GET/POST 在投影前必须处理悬空 intent，且只读观察目标与绑定恢复工件，不自动猜写文件：

- 当前目标等于 intent after-image，且 intent 承诺的 backup 或同卷 quarantine 仍存在、可被动
  解析并精确匹配绑定 hash：append `recovered_commit`；
- 当前目标等于 intent before-image：append `abort`；
- 目标不可安全读取、after-image 的恢复工件缺失/漂移或其他组合：append
  `manual_intervention`。

`manual_intervention` 时 `workflow.latest_publish` 必须为 null，所有发布/回退动作停住；诊断
details 不能冒充已确认结果。

该协议要求 `target_root` 与同卷 quarantine 位于本机文件系统，并由部署 ACL 保证只有本服务
账号能写；OS 文件锁只协调遵守本协议的进程。最后一次 hash CAS 能缩小竞争窗，但不能把
pathname `os.replace` 升格为对无视锁的外部写者或父目录交换的原子 compare-and-swap。因此
共享盘/NFS、可被其他进程写入的源码树或不受控 symlink 父目录都不在 v1 支持面。

Windows 上 `os.replace` 保持同卷原子替换，但 Python 没有可移植的 directory fsync；该分支
属于 declared-not-verified，必须在 Windows 部署验收中单独验证，不能借 macOS 测试宣称。

### 7. 存储是 append-only 且有深见证

P2.8 六张表（comparison、selection、release request、release decision、publish event、
idempotency）禁止 UPDATE、DELETE、冲突 REPLACE 和非正 rowid。ID 的 prefix、总长度与完整
hex suffix 都在 SQLite CHECK 中验证；不能使用只约束首字符的宽松 GLOB。

通用 task review 防绕过以 `tasks.agent_id=open_design_daemon_candidate_agent` 为硬条件，
metadata 缺失也不能降级为普通 review。schema witness 同时检查 DDL digest、PRAGMA shape、
索引、触发器、行 hash 与引用完整性。

父表重建会由 SQLite 合法移除挂在该父表上的 P2.8 跨账本 trigger。只有六张 P2.8 表全部
存在、表形精确且完全空时，启动器才允许重建全部 P2.8 index/trigger；任一 P2.8 行已经存在
时，缺失或漂移对象一律停机，不以“修好后再报绿”抹掉潜在保护窗。

## 共享接线要求

本 ADR 对主线集成提出四个明确 seam：

1. bootstrap 安装并见证 P2.8 schema，health/readyz/deploy self-check 使用同一 witness；
2. 将现有通用 human-review 实现拆出“不自行 BEGIN/COMMIT、接受 caller decision_id”的事务
   primitive，注入 `DesignPromotionService`；现有 `repos.apply_human_review` 不可直接嵌套；
3. main 组装 service 与 API router；生产 target/frame registry 必须由部署显式注入，默认空
   registry 是安全停点；
4. P2.7 在进入 `waiting_review` 前把 review contract、generator kind、manifest SHA 投影进
   task metadata；封印后不得补写。

当前 bootstrap/witness、事务 primitive、main/router 与 metadata seal 均已接线；生产
target/frame registry、角色轴与逐文件降密仍明确缺失。因此可宣称“P2.8 状态机与默认关闭的
生产装配已完成”，不得宣称真实 P2.7→P2.8 或资产发布已打通。

## 后果

正面：人仍是唯一签发者；候选批准与发布批准可独立审计；刷新可恢复；文件崩溃窗口有
确定性 hash reconciliation；目标面保持极小。

代价：真实 sensitive 候选暂时全部 403；默认生产目标为空；发布合同只支持三项 PNG；跨域
协议比直接写文件复杂；非协作写者和 Windows durability 仍需部署治理/实机验证。后续只有在
角色轴、逐文件脱敏证明、隔离 sidecar、目标 provisioning 与独占写 ACL 获批后，才能解除
真实 P2.7→P2.8 的停点。

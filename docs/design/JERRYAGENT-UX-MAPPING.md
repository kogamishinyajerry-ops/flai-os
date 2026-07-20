# JerryAgent → FLAi-OS 可信交互映射

> 状态：P2.1 已落地断连投影与 task live-snapshot 连续游标；P2.3 结构化问题与 P2.4 只读寻址均已完成阶段收口；composer 持久化仍延期。
> 来源基线：`/Users/Zhuanz/projects/meta/jerryagent`，只读审计 HEAD
> `3c1adcb0cee0726993d21f1d6ffb729b241d39dc`；该工作树本身有用户未提交改动，
> 因而只把可在源码与测试中复核的行为当参考，不搬运整文件。

## 1. 借鉴的不是外壳，而是事实链与注意力模型

JerryAgent 的高价值成果有四层：

1. `RuntimeEventStore → reducer → snapshot/SSE` 让多个 UI 消费同一条事实链；没有真实
   子进程事件时不合成“正在运行”。
2. 事件 `sequence` 严格连续；回放遇缺口即停止，客户端重连以权威 snapshot 恢复。
3. 问题与批准是不同合同；ApprovalBroker 只有一个合法决定源，普通问题不伪装成批准。
4. composer 草稿按 runtime session 隔离，浏览器存储不可用时 fail-soft，只有真实提交后
   清理精确会话。

其 Desktop 研究还给出稳定的交互约束：一条阅读轴、一个 composer、卡片只用于异常对象，
运行细节渐进披露，只有当前待人决定的内容升格为重卡。FLAi-OS 已有自己的暖纸、clay、
信任色与双 Surface，不复制 JerryAgent 的 Swift、WebKit、loopback bridge 或视觉外壳。

## 2. 当前 FLAi-OS 的诚实映射

| JerryAgent 原则 | FLAi-OS 当前事实 | 本轮裁决 |
|---|---|---|
| 服务端投影是 SSOT | `liveFeed` 每轮替换 task snapshot，events 按 offset 追加 | 保留服务端事实；不在客户端合成 demo/运行态 |
| 严格 sequence + gap recovery | 旧 event API 仍只有 UUID；新增 task live-snapshot 以每任务序数 + exact event anchor 提供 additive cursor | gap/重复/跨 task/错锚整批拒绝并强制 sequence-zero resnapshot；旧 API 不改形 |
| 断连显式 stale | channel 投影 connection/lastSuccessAt/stale/resyncing；阅读面共用 amber 提示 | 冷失败零假数据；暖失败保旧快照并标旧；恢复先完整重取 |
| 问题与批准分离 | Guide 只从完整显式 envelope 创建普通 Question；Task `waiting_review` 才有 `/review` | Question/Answer 有独立合同、稳定消息锚与 exact username；批准仍只留在具名审核面 |
| 稳定事实可寻址 | P2.3 已提供 exact owner 与公开 `message_id` | P2.4 已用单 scope 服务端只读搜索补齐会话/消息/任务/产物，并以稳定 id 深链；不新增 dashboard 或侧栏 |
| 会话草稿隔离 | Guide 仍是内存草稿 | 本轮只冻结合同；sessionStorage 实现经故障注入后延期，不宣称已采用 |
| 一条阅读轴与渐进披露 | Guide 主轴、今日任务台、StatusDock、内联产物/签发已存在 | 继续收敛，不再新造平行 dashboard 或第二决定源 |

## 3. 已冻结、尚未采用的 composer 草稿合同

本轮曾实现浏览器持久化原型，但终审在 sessionStorage 全程不可用的故障窗中复现了连续
accepted 事务互相覆盖内存 tombstone、令已被服务端接纳的旧原文重新出现的风险。继续增加
单槽补丁会把网络接纳、草稿 CAS、跨会话迁移和跨实例 busy 生命周期纠缠在客户端；因此
该实现已整体撤出。当前 Guide 保持原有内存草稿，不提供刷新恢复，也不把原型测试绿冒充
产品能力。

以后重启此切片必须先批准 revision-indexed、多条目 accepted ledger（或更保守且不可覆盖的
tombstone）和 network outcome / draft ownership 分轴事件，再按以下合同重做：

- `principal` 必须是认证 `username`；可重名的 `display_name` 禁止参与键。
- 既有会话使用服务端返回的 `conversation.id + conversation.agent_id`。
- 新会话使用明确 `new + targetAgentId` 槽；create 成功后迁到真实 conversation 键。
- 任一轴缺失时不产生 anonymous/shared key；存储异常不阻塞输入与发送。
- 发送时先捕获精确 scope；`postMessage` 成功返回后才清该键。
- create 成功但 post 失败、网络失败或响应竞态都必须保留原始草稿。
- 发送期间切换用户、会话或 Agent，不得由旧异步续体清新上下文草稿。
- 附件 `File` 仍只在内存，不宣称跨刷新恢复。

## 4. P2.1 已采用的最窄运行时切片

P2.1 保持轮询、不引入 SSE，采用如下合同：

1. `liveFeed` 增加 `connection: idle | connected | disconnected`、`lastSuccessAt`、
   `stale` 与 `resyncing`；既有 task/event 公共响应不变。
2. 冷断连保持空值与错误；暖断连可保留最后真实 snapshot，但页面必须显示“旧快照”。
3. 新增 additive `task-live-snapshot/v1`；恢复连接后立即 sequence-zero 重取权威 snapshot，
   任何路径都禁止 demo fallback。
4. resync generation 防止在途旧请求吞掉显式全量重取；sequence-zero replace 抑制普通
   transition，避免把离线状态变化补播成亲历完成。
5. Node/contract/E2E 覆盖冷断连、暖断连、gap、并发 resnapshot 与零 fake 数据。

严格 cursor 的 append-only、删除/压缩、分页与版本边界由
`ADR-0032-task-live-snapshot-cursor.md` 冻结。未来若引入 compaction 或 SSE 必须升级 stream
generation/schema，不能静默复用 v1 ordinal。

## 5. P2.3 已采用的结构化澄清切片

P2.3 没有从问号或 `recommendation=null` 猜控件，而是建立独立的
`conversation-question/v1` 与 `conversation-answer/v1`：

1. Guide 只有输出单个、完整且拓扑合法的 `QUESTION` envelope 才能提议普通澄清；
   PLAN/Question 重复、嵌套、未闭合或共存全部 fail-closed。
2. 服务端生成 Question id、稳定 prompt `message_id`、确定性 option id、exact
   `asked_to_username`、revision 与 24h TTL；模型和客户端不能自报这些事实。
3. 单选、自定义文本与自由文本都走专用 Answer API。Answer 不调用 task review，不改变
   task、event、sample、gate 或签发状态。
4. 相同 submission 与相同规范化 payload 可安全 replay；不同提交、过期、结束或并发落后
   一律 409 并强制权威 resnapshot。模型失败时零消息落库，原 Question 保持 pending。
5. 回答、canonical user message、assistant response、旧 Question CAS 闭合、下一 Question
   和 recommendation 快照在同一 SQLite 事务提交；人工结束会话同步 supersede pending 问题。
6. QuestionCard 保持一条阅读轴，使用现有暖纸/clay/token；无 green/teal、批准、驳回、
   推荐默认项或第二决定源，并覆盖 390px、暗色、键盘 focus 与 reduced-motion。
7. 普通仓储入口拒绝 ownerless 会话；Question option 标签在模型、仓储与历史审计三层都
   按 `strip().casefold()` 唯一。一个 snapshot 最多一个 pending Question，pending 期间
   composer/附件/Agent 入口不可写，过期后按权威时间恢复单一写轴。
8. 启动、health、readyz 与部署自检共享精确五键 schema witness；未知列、约束、索引、
   trigger 或历史毒数据全部 fail-closed，不能以局部 runtime 标志获得假绿。

## 6. P2.4 已采用的只读寻址切片

JerryAgent 的可取之处仍是“稳定事实先于 UI 猜测”，不是复制其 Desktop 外壳。P2.4 按
[ADR-0034](../adr/ADR-0034-exact-addressing-search.md) 建立以下边界：

1. `conversation/message/task/artifact` 每次只查一个 scope；现有 QuickSwitcher 并行编排
   各组，单组失败明确显示 unavailable，不把 debounce 或源错误闪成“无结果”。
2. 会话/消息只按 exact username 搜索本人事实；同 display name、foreign 与 legacy NULL
   不能命中。任务只提供 `origin='user'` 的认证全局元数据，输入、错误和正文从匹配与响应
   两侧都排除；产物还必须是父任务 `output_file_ids` 的精确成员。
3. v1 不改 P2.3 schema witness，不依赖 FTS/分词或新索引。SQLite literal scan 每源上限
   50,000 行，超限或源失败返回 503；查询按 ASCII 大小写不敏感、非 ASCII 原值匹配。
4. opaque keyset cursor 绑定 principal、query、scope、filters、limit 与 snapshot。消息落到
   `/?c=<conversation>&m=<message>`，产物落到 `/tasks/<task>?file=<file>`；失效锚显式说明，
   不静默退回父对象或自动下载。
5. 只复用现有 QuickSwitcher、Guide、TaskDetail 与暖纸/clay/amber/red token，不增加新
   侧栏、常驻 workflow 墙或信任色。具名签收留在 P2.5；标题/重命名/归档写语义留在 P2.6。

该切片已在 `dfcf9ab` 完成代码、契约、前端深链与浏览器 acceptance，并进入后续全量
`verify_all` 基线。此处只声明本地实现已验收，不把它外推为真人可用性或 M4 事实。

## 7. 机械验收

composer 部分仍只冻结文档，不存在 persistence 交付声明。重启该切片时，invalid-first 测试必须至少覆盖：存储全程不可用下连续 accepted、
目标键 conflict/unreadable、fresh→created 多段迁移、A→B→A、身份切换、跨实例 busy
释放，以及服务端已接纳但草稿 CAS 被 supersede 的权威消息刷新。

P2.1 disconnected slice 已覆盖：

- warm failure 保留最后真实 snapshot 且 `disconnected=true`；
- cold failure 不渲染任务或模型生成 fallback；
- reconnect 以服务端 snapshot 整包覆盖本地投影；
- question bubble 不出现批准/驳回控件；
- task review 仍只有 `waiting_review` 可操作，并由现有后端原子迁移与审计守门。

P2.3 的机械门包含：同名 display name 的跨用户 404、legacy NULL owner 不冒认、布尔
revision 与非法 payload 422/零模型、Question/PLAN 畸形拓扑、精确到期边界、并发回答唯一
提交、SQLite UPDATE/DELETE/REPLACE 防篡改、真实 HTTP 投影套公开 JSON Schema、浏览器
刷新恢复/502 重试/409 resnapshot，以及 Question 全子树不借 REAL 绿或人签 teal。阶段
冻结证据为后端 P2.3/兼容回归 386/386、前端 Node 102/102、production build 通过与真实
浏览器 Question acceptance 22/22。最终工作树的 `UV_OFFLINE=1 bash scripts/verify_all.sh`
退出码为 0：pytest 1480/1480、Node 102/102、20/20 条浏览器 E2E 脚本全部通过。M2
精确 selector 曾连续 10 次 10/10；加入侧栏冲突真实负例与有限 timeout 审查后，又连续
3 次 11/11，最终全量门 11/11，拒绝用全局统计文案冒充当前任务终态。

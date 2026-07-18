# JerryAgent → FLAi-OS 可信交互映射

> 状态：Phase 1 完成只读映射；composer 持久化、事件序列、断连投影与结构化问题均未进入运行时。
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
| 严格 sequence + gap recovery | 公共 event 只有 UUID `event_id`，不暴露 SQLite 顺序或 revision | 不能把数组位置/UUID 冒充 sequence；本轮不做假 gap detector |
| 断连显式 stale | 冷启动错误可见；成功后轮询失败保留旧真值但没有统一 stale 标识 | 下一独立切片增加 connection/lastSuccessAt；旧快照必须标旧 |
| 问题与批准分离 | Guide 澄清是普通 assistant 文本；Task `waiting_review` 才有 `/review` | 不从 `recommendation=null` 猜 QuestionPanel；批准只留在具名审核面 |
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

## 4. 下一阶段的最窄运行时切片

先做断连诚实度，不立即上 SSE：

1. `liveFeed` 增加 `connection: idle | connected | disconnected` 与
   `lastSuccessAt`，不改变 task/event 公共响应。
2. 冷断连保持空值与错误；暖断连可保留最后真实 snapshot，但页面必须显示“旧快照”。
3. 恢复连接后立即拉一次权威 snapshot；任何路径都禁止 demo fallback。
4. Node/E2E 覆盖冷断连、暖断连、恢复、并发 refresh 与零 fake 数据。

严格 `seq gap` 另行裁决。若采用 JerryAgent 方案，必须先批准公开的单调 `revision/sequence`
和 snapshot cursor，定义删除/压缩、重放、分页与版本迁移，再实现 SSE 和 gap→resnapshot。
在此之前，offset 只能描述“追加尾段”，不能在 UI 或文档中宣称可检测缺口。

结构化澄清同理：先新增明确的 question kind、选项/自由文本回答合同与过期语义，再做
QuestionPanel。它仍不得复用 task review API，也不得让 LLM 获得签发权。

## 5. 机械验收

Phase 1 只验证本映射文档不越过当前运行时事实；仓内没有 composer persistence 测试或
交付声明。重启该切片时，invalid-first 测试必须至少覆盖：存储全程不可用下连续 accepted、
目标键 conflict/unreadable、fresh→created 多段迁移、A→B→A、身份切换、跨实例 busy
释放，以及服务端已接纳但草稿 CAS 被 supersede 的权威消息刷新。

后续 disconnected slice 至少应新增：

- warm failure 保留最后真实 snapshot 且 `disconnected=true`；
- cold failure 不渲染任务或模型生成 fallback；
- reconnect 以服务端 snapshot 整包覆盖本地投影；
- question bubble 不出现批准/驳回控件；
- task review 仍只有 `waiting_review` 可操作，并由现有后端原子迁移与审计守门。

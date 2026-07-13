# 工作台深度优化 · 四批宪章 + 批A「活的工作台」设计

- **状态**：批A Approved（owner 2026-07-13「按推荐继续」）；批B/C/D 为宪章级预告，各自开工前出独立 spec。
- **侦察依据**：4 路并行只读侦察（轮询机制/动效现状/信息架构/治理数据面），结论内嵌各节。

## 〇、四批宪章（总纲）

| 批 | 主题 | 核心交付 | 依赖 |
|---|---|---|---|
| **A（本 spec）** | 活的工作台 | liveFeed 多 channel 统一轮询 + 微反馈动效收口 + 骨架屏 | — |
| B | 今日工作台 + 交付叙事 | `/today` 新路由（待签发置顶/最近产物/Agent 动态/团队总量条）+ 任务交付卡 | A 的 liveFeed |
| C | 双轨奖励 | Agent 成长档案页（L0-L3/eval 通过率/晋升仪式）+ 工程师私有贡献页 | B 的 /today 挂入口 |
| D | 视觉精修 | 空态统一/动效尾款/响应式（暗色主题已有，出列） | A-C 落定 |

**跨批铁律**（继承平台宪法 + owner 两项拍板）：
1. 奖励/反馈的每个数字都来自**真实治理事件**（tasks/samples/promotions/eval_runs/feedback 既有表可算）——绝不虚构积分池。侦察实证：双轨 v1 零 schema 变更可算（Agent 四指标 + 工程师四指标）；诚实缺口两处（人名列为 display_name 非 username、活跃天仅登录/业务日期近似）在 C 批 spec 里显式标注口径。
2. 工程师侧激励**个人私有 + 团队总量**，无人际排名（owner 拍板）。
3. 信任色锁五槽不动；teal 仅人签；动效 token 纯时间性，带色动效只引用既有 `-rgb` 语义三元组（burst.js 范式）。
4. MOTION-SYSTEM.md 硬约束六条继续有效，新 token 只扩展不推翻。

---

## 一、批A 目标

三件事：**①轮询统一**（4 条异构 HTTP 轮询链收拢为 liveFeed 多 channel store）；**②微反馈收口**（动作有回声、状态变化有仪式、修 --ease-lift 疑似延迟 bug）；**③首载骨架屏**。批A 不改任何信息架构、不加路由、不动后端 API（纯前端批）。

**验收标准**：
- 全站仅剩 liveFeed 一个 HTTP 轮询源（SimMonitorFloat postMessage 推模型除外）；DevTools Network 实证同屏 listTasks 只有一条链。
- 跨会话人工放行后，打开着的 TaskDetail **无需手动刷新**自动出现终态（waiting_review 停轮缺陷修复,e2e 断言）。
- ADR-0013 全部防 stale 语义保留且有回归测试咬合（offset 增量/整包作废/换代守卫）。
- --ease-lift 问题实机验证后收口（确认 bug 则修，确认非 bug 则记录证据）。
- 既有 5 套 e2e 全绿 + verify_all 全绿；动效变化截图存证。

## 二、A1：liveFeed 多 channel store

**新文件** `frontend/src/stores/liveFeed.js`，泛化自 taskFeed.js 的成熟骨架（模块级单例 + 引用计数 acquire/release + inflight 去重 + 链式 setTimeout + document.hidden 跳过仍续轮 + 失败保旧值自愈）。

### channel 模型

```
channel = { key, fetcher, intervalMs, state: ref, epoch, refCount, timer, inflight }
acquire(key, opts) -> { state, release }   // 同 key 复用同 channel，refCount 归零停链
```

三类 channel（key 规范）：
- `tasks`（5s）：listTasks({limit:100})——taskFeed 原语义，消费方 TaskConsole 左栏/StatusDock/StatusCenter inbox（**合并 StatusCenter.refreshInbox 独立链**）。
- `task:<id>`（2s 活跃 / 8s waiting_review / 终态停）：getTask + listTaskEvents offset 增量游标 + modelCalls（seq 守卫原语义）+ artifacts（fingerprint 原语义）。消费方 TaskDetail 与 StatusCenter peek（**两套并行实现合一**）。
- `conversation:<id>`（5s）：getConversation + listConversationTasks。消费方 WorkbenchSession 与 GuidePage 方案卡 chip。WorkbenchSession 的 refreshLastWords（每 5s 对 ≤5 任务 offset:0 全量重拉）改为订阅对应 `task:<id>` channel 的事件尾——天然增量。

### 统一世代守卫

三种异构 idiom（baseline 数组身份 / epoch 计数器 / 每资源 seq）统一为 **channel 内单调 epoch**：每次 stop/restart/参数变更 epoch++，响应落地前比对 epoch 不符即整包作废（ADR-0013 R2「整包作废」语义的推广）。数组身份 baseline 与 artifactsFingerprint 的既有回归测试改写为对 epoch 语义断言，**测试意图不减**。

### waiting_review 翻转唤醒（修手动刷新缺陷）

`task:<id>` channel 在 waiting_review 时降频为 8s（不再停轮——原停轮理由是无人值守空转，降频即可兼顾）；终态仍停轮。另：`tasks` 清单 channel 观察到某 task 状态翻转时,若存在同 id 的 `task:<id>` channel,立即触发其一次带外补拉（事件驱动唤醒,不等下一 tick）。

### 事件总线（微反馈的数据源）

liveFeed 内置轻量 emitter：channel 数据落地时 diff 出**状态迁移事件**（`task-transition {id, from, to}`）广播。A2 的微反馈、B 批的今日工作台、C 批的晋升仪式全订阅此总线——一处 diff，多处消费。

### 迁移策略（外科，五个消费方逐个换轨）

taskFeed.js 保留为 `liveFeed.acquire('tasks')` 的兼容 shim（导出名不变，StatusDock/TaskConsole 一行不改先跑通），再逐个消费方直连新 API 并删 shim。TaskDetail/StatusCenter/WorkbenchSession/GuidePage 各自的轮询代码删除,改订阅。**每个消费方迁移是独立 commit + 对应 e2e 锚点复跑**。

## 三、A2：微反馈与动效收口

侦察实证现状：动效 token v1 已在 App.vue `:root`（--motion-fast/med/slow + --ease-out-soft/--ease-spring）、SSOT=docs/design/MOTION-SYSTEM.md（硬约束六条）、fx-* 工具类 + reduced-motion 降级块齐备。本批四件实事：

1. **--ease-lift 收口**：复合 token（含 0.18s 时长）配 `transition: all 0.16s var(--ease-lift)` 写法，按 CSS 语法第二时间值解析为 delay——**先实机验证一处**（DevTools computed transition-delay），确认 bug 则全站 ~20 处统一改 `0.16s var(--ease-out-soft)` 并删除该 token；确认非 bug 则在 MOTION-SYSTEM.md 记录证据留 token。
2. **CompletionSeal 盖章动效**（现全静态）：终态首次出现时横线自左向右拉出（--motion-slow）+ 状态词 fx-ink-in 浮现;completed 时刻接线既有 `burstNeutral`（burst.js 已有未接线）;failed 零彩色仅红字浮现。reduced-motion 全降级。**仅在「本次会话内观察到 running/waiting_review→终态迁移」时播放**（订阅 liveFeed 总线）,历史页面直开不播——仪式只属于亲历者。
3. **待签发即时回声**：liveFeed 总线捕获 `→waiting_review` 迁移时,StatusDock 待签发角标脉冲一次（既有 flai-work-pulse 复用）+ ElMessage 一条「XX 任务待你签发」（带跳转）。提交新任务成功后按钮到列表「飞入」动效（fx-rise 复用）。
4. **transition 族统一**：全站 ~40 处零散 transition 时长/缓动归一到 --motion-* 族（机械替换,逐处保留原视觉意图,hover 色过渡不覆盖 Element Plus 默认——侦察已标注回归判例）。孤儿资产 particleField.js/DraftingScene.vue 按 MOTION-SYSTEM「可整体拆除」条款删除,并修 MOTION-SYSTEM.md 里指向不存文件的 P1 条目。

## 四、A3：首载骨架屏

统一 `SkeletonBlock.vue` 小组件（暖白底 shimmer,reduced-motion 降静态灰块）。落点仅四处首载：TaskConsole 左栏、TaskDetail 主区、WorkbenchSession roster、AgentPortal 卡片栅格。轮询期间**绝不**回骨架（只首载,防闪烁）;失败态仍走既有 error/EmptyState,骨架不吞错误。

## 五、测试与验收

- **单测**：前端现状无单测栈（package.json 仅 vite 三脚本,已查实）——**不引入 Vitest**（轻内核纪律,新增依赖需 owner 批）。liveFeed 核心逻辑（epoch 作废/refCount 停链/翻转唤醒 diff）写成**纯函数模块** `liveFeedCore.js`（零 Vue 依赖）,用 `node --test` 原生跑器写断言（`frontend/tests/livefeed_core.test.mjs`,入 verify_all）。三个核心行为必须有 tamper 咬合（拆守卫必红）。
- **e2e**：既有 5 套全绿;新增 `frontend/e2e/batch_a_livefeed_acceptance.py`：①同屏双视图（TaskConsole+StatusCenter）网络请求合并断言（route 拦截计数 listTasks 单链）②waiting_review 放行后 TaskDetail 免手动刷新自动到终态③盖章动效元素出现（class 断言,不截帧）。
- **视觉存证**：关键微反馈 GIF/截图入 docs/reviews/。
- **审查**：命中「共享核心 store + 全站消费方改造」→ 完工后 Codex 治理审（86gs）+ 主控逐消费方 diff 亲核。

## 六、风险与边界

- 最大风险=五消费方换轨回归——以「shim 先行、逐个迁移、每步 e2e」控制爆炸半径。
- ADR-0013 语义是安全线：守卫变形（统一为 epoch）必须逐条映射旧测试意图,漏一条=假绿。
- 不动后端;不动路由;不动 GuidePage 对话逻辑;SimMonitorFloat 推模型不进 liveFeed。
- 孤儿资产删除若有隐藏引用（grep 全仓归零才删）。

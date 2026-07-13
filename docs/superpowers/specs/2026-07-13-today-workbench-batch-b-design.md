# 批B「今日工作台 + 交付叙事」设计 spec

- **状态**：待 owner 审（宪章级预告已随批A spec 批准；本 spec 为批B 独立细化）。
- **依赖**：批A liveFeed 已合并（main=15d747a）。
- **侦察依据**：2 路并行只读侦察（数据面=后端 API/表结构；前端面=路由/组件/深链），结论内嵌各节，file:line 证据在侦察记录。

## 〇、目标与边界

一句话：给工程师一个**开工即看**的 `/today` 页——待签发的事置顶、正在跑的活一眼可见、今天交付了什么有叙事卡、团队本周总量一条线——所有数字来自真实治理事件。

**继承跨批铁律**（批A spec §〇）：
1. 每个数字来自真实治理事件（tasks/task_events/promotions 既有表 + eval_cases 落盘文件）——绝不虚构积分池。
2. 工程师侧个人私有 + 团队总量，无人际排名（本批只做团队总量；个人私有贡献页在批C）。
3. 信任色锁五槽不动：**团队总量条与统计数字一律中性 ink 色**，不得借用五槽；teal 仅人签动作本身。
4. MOTION-SYSTEM 六条有效；新页面动效只用既有 token/fx-*。

**边界（本批不做）**：无新写端点（后端只加只读聚合）；零 schema 变更（reviewed_by 列等归因增强留给批C 裁决）；不动对话/工作台/详情页现有布局；SimMonitorFloat 不进 /today v1；无人际排名、无个人页。

## 一、信息架构与入口（含一个 owner 决策点）

新路由 `/today`（name: "today"）。页面五版块，自上而下：

1. **待签发置顶**：tasks channel（`acquireChannel("tasks")`，与 StatusCenter/StatusDock 同一份真值）filter `waiting_review`。卡片复用 StatusCenter `.sc-item` 型态：lamp + 名称 + agent + 等待时长；点击深链 `/tasks/:id`。空态=EmptyState「没有等你签发的任务」。
2. **进行中**：同 channel filter 活跃态（created/queued/running/validating）。行内 lamp 用 `taskLampColor` SSOT。
3. **今日交付（交付叙事卡）**：同 channel filter「今天落定」的终态任务（completed/failed/cancelled，按 finished_at 本地日切）。每条渲染**交付卡**（见 §二）。
4. **Agent 动态**：a) 最近晋升（新端点 `GET /api/promotions`，见 §三）——「performance_disk_agent 晋升 L0→L1 · 2 小时前」；b) 今日最活跃 Agent（tasks 窗口内按 agent_id 分组计数，客户端派生）。
5. **团队总量条**：一条横向四格（新端点 `GET /api/stats/overview`，见 §三）：本周完成任务 · 本周人签放行 · 累计固化 case · 本周晋升。四格全中性色，格内数字 + 小字口径说明。

**诚实口径条款**（三处必须上屏标注，不是埋文档）：
- 版块 1-4a 之外的客户端派生数字（今日交付计数/最活跃 Agent）基于「最近 100 条任务窗口」（listTasks limit=100 语义），页脚小字注明「基于最近 100 条任务窗口」。
- 「今日/本周」= 浏览器本地时区日切，前端把本地零点转 UTC ISO 传给 stats 端点（`?since=`），端点纯函数无隐藏时钟。
- 固化 case 数来自 `agents/*/eval_cases/` 落盘文件扫描（治理产物的真实存在形式），格内小字「累计（按仓内固化文件计）」。

**⚠️ owner 决策点——导航入口**：现顶导航范式是「对话唯一一级入口」（Phase 3 拍板，App.vue:212-217），其余全深链。/today 的入口两案：
- **A（推荐）**：NAV 加第二项「今日」——今日工作台正是值得一级入口的目的地页，藏成深链会杀死这页的存在意义；「对话+今日」双入口仍极简。
- B：不破范式，只在 StatusDock/状态中心加「今日」入口深链。
默认按 A 实施；spec 审阅时可改判。

## 二、交付叙事卡（版块 3 的卡片）

一张终态任务的**成果小结卡**，全部字段现成（侦察 §4 证实）：
- 头行：CompletionSeal 同款盖章行（复用组件，animate 恒 false——历史卡无仪式，仪式只属亲历者；今日页开着时若某任务当场翻终态，由 onTransition 总线让**那一张卡**播一次 seal-animate，语义与 TaskDetail 完全一致）。
- 主体：任务名 + agent_id·version + created_by + 用时（`taskElapsedMs`/`formatDuration` SSOT）。
- 产物条：`output_file_ids` 前 3 件（复用 StatusCenter `syncPeekArtifacts` 指纹模式，fileId 去重不重拉），超出显示「+N」；无产物不显示该条（不编「0 产物」）。
- 尾行（有则显）：模型调用小结（modelCallStats 口径：N 次调用 · token 合计，凑不出显式「未知」不记 0）；批量任务显 ok/failed 计数（batchSummary 事件流派生）。
- 整卡点击 → `/tasks/:id`。failed 卡状态词红、其余中性（信任色锁）。

## 三、后端新增（只读，两个端点，零 schema 变更）

### `GET /api/stats/overview?since=<iso>`（新文件 backend/app/api/stats.py）
纯只读聚合，SQL 直查 + 文件扫描，无缓存无后台任务（轻内核）：
```json
{
  "since": "<回显>",
  "tasks_completed": <COUNT tasks WHERE status='completed' AND finished_at>=since AND origin='user'>,
  "reviews_approved": <COUNT task_events WHERE event_type='review_approved' AND created_at>=since>,
  "curated_cases_total": <glob agents/*/eval_cases/case_*.json 计数（累计，不受 since 约束）>,
  "promotions": <COUNT promotions WHERE created_at>=since>
}
```
- `since` 必填且必须是合法 ISO8601，非法 422（fail-closed 不默认兜底窗口）。
- ISO8601 UTC 字符串按字典序可比，SQL 直接 `>= ?`——与 repos 现有写入格式一致（侦察 §3 证实）。
- `review_approved` 的确切 event_type 枚举以 `contracts/event.schema.json` 为准，实现时对齐，测试锚死。
- origin 过滤沿用 tasks API 默认语义（排除 eval 跑批），统计不混入评测任务。

### `GET /api/promotions?limit=20`（governance.py 加路由）
全局最近晋升（repos 新增 `list_promotions_all(conn, limit)`，`ORDER BY created_at DESC`；DDL 现成，侦察 §2 证实缺的只是不带 agent_id 约束的查询函数）。返回条目含 agent_id/from_maturity/to_maturity/created_at/approved_by。

两端点均挂 M11 鉴权（与其余 /api 一致），无写路径、无新依赖。

## 四、实时性接线

- 版块 1/2/3 全部由 tasks channel 驱动（5s 轮询已有，页面 acquire/release 与 TaskConsole 同纪律）；onTransition 总线让「当场翻终态」的任务卡播盖章仪式 + 从「进行中」平滑挪到「今日交付」（fx 用既有 token，无新 keyframes）。
- 版块 4a/5（promotions/stats）**不进 liveFeed 轮询**：进入页面拉一次 + onTransition 观察到 review_approved 相关迁移（to=completed 且曾 waiting_review）时补拉一次 stats——低频数据不配常驻链（轻内核纪律）。
- 首载四版块骨架屏（SkeletonBlock 复用，只首载）。

## 五、测试与验收

- **后端 pytest**：stats 端点 oracle 测试——夹具库种入已知事件集（N 完成/M 放行/K 晋升 + 临时 eval_cases 文件），断言四数字精确相等；since 边界（恰在界上/界前）对称测；非法 since 422；origin=eval 任务不计入。promotions 端点分页/排序/空库。tamper：把 event_type 过滤改掉必红。
- **e2e**（`frontend/e2e/batch_b_today_acceptance.py`，入 verify_all）：①/today 五版块渲染且待签发数与 StatusCenter 角标一致（同源断言）②跨会话批准一个任务→ /today 开着不动，12s 内该任务从「进行中/待签发」出现在「今日交付」且交付卡盖章仪式播放（亲历）③团队总量条数字与直查 API 相等（同源断言）④历史直开交付卡不播仪式。
- **视觉存证**：/today 全页截图（亮/暗）入 docs/reviews/。
- **审查**：命中「新 API 端点 + 治理数字上屏」→ 完工后 Codex 治理审（86gs）。

## 六、风险与边界

- 最大诚实风险=「窗口内派生数字」被误读为全量——三处口径标注是验收项不是装饰；stats 四格因为走 SQL COUNT 无截断问题。
- display_name 归因缺口（撞名算错账）本批不触碰（团队总量不归因到人）；批C 个人页前必须裁决 created_by_username 列（侦察已标注 api/tasks.py:317 已知隐患）。
- 时区口径：本地日切由前端算 since，跨时区团队各自看各自的「今天」——V1 接受，注明即可。
- 导航决策点见 §一；若 owner 选 B 案，验收①的入口断言相应改深链。

# 批C「双轨奖励」设计 spec

- **状态**：待 owner 审（宪章级预告已随批A spec 批准；本 spec 为批C 独立细化，owner 2026-07-14 三决拍板见下）。
- **依赖**：批A liveFeed / 批B stats·今日工作台 / 迁移 #9 created_by_username（均已合并 main）。
- **侦察依据**：1 路只读侦察（Agent 成长侧数据 + M10 治理面板现状 + 工程师归因可行性），结论内嵌各节。

## owner 三决（2026-07-14 AskUserQuestion）

1. **Agent 成长档案 = 扩展现有 M10 治理弹窗**（非新路由）——复用弹窗已 fetch 但只渲染最新一条的 eval/晋升历史。
2. **工程师个人贡献页 = 只做可精确归因的**——「我发起的任务」按 created_by_username 精确；签发/样本认可的个人归因（唯一身份只在 audit.log、无读 API）本批不做，缺口显式上屏。
3. **晋升 = 静态晋升史 + 亲历者动效**——本会话内亲历某 agent 晋升到账才播一次中性动效，历史直开不播。

## 〇、目标与铁律

一句话：给平台两类「谁在成长、成长了多少」的镜子——Agent 侧（能力成熟度公开可见）与工程师侧（个人贡献私有可见），数字全来自真实治理事件。

**继承跨批铁律**（批A spec §〇 + owner 拍板）：
1. 每个数字来自真实治理事件（agents.maturity / eval_runs / promotions / tasks.created_by_username / feedback 既有表 + eval_cases 落盘文件）——绝不虚构积分池。
2. 工程师侧**个人私有 + 团队总量，无人际排名**（owner 早批）：/me 只显示自己的数据，后端按 session username 服务端过滤，无法查他人；团队总量复用批B stats/overview。
3. 信任色锁五槽不动：成长/贡献数字与晋升庆祝一律中性 ink 色；teal 仅人签动作本身；completed/晋升不给绿。
4. MOTION-SYSTEM 六条有效；晋升动效复用批A burst.js（burstNeutral 中性）/seal 范式 + reduced-motion 降级。
5. **诚实缺口显式上屏**：L2/L3 只有 L0→L1 机器化把关（L2/L3 范围外，成熟度阶梯如实标）；工程师签发/样本个人归因待后续（唯一身份仅审计轨，页面明说不假装能算）；反馈按 display_name 近似归因（可撞名，标注口径）。

**边界（本批不做）**：不建 audit.log 读路径、不把 reviewer_username 落进 task_events（owner Q2 选「不碰审计边界」）；samples 不加归因列；Agent 档案不建 /agents/:id 新路由；不动 L0→L1 晋升机器判定逻辑（M10/ADR-0018 已定）。

---

## 一、轨1：Agent 成长档案（扩展 AgentPortal 治理弹窗）

**落点**：`frontend/src/views/AgentPortal.vue` 的 `openGovernance()` el-dialog（现 :103-191）。现状只渲染 `latestGovernanceRun`/`latestPromotion`（[0]），`governanceRuns`/`governancePromotions` 全量数组已在手——**摊开已有数据，不新起数据层**。

**新增/扩展版块**（弹窗内自上而下）：
1. **成熟度阶梯条**：L0→L1→L2→L3 横向进度，当前 `agent.maturity` 高亮；**L2/L3 标注「范围外（仅 L0→L1 机器化把关）」**——诚实地板，不暗示平台能自动晋 L2+。中性色，当前档用 clay 强调（clay 是工作/进行语义，非五槽信任色）。
2. **eval 通过率趋势**：`governanceRuns` 每条含现成 `total/passed/failed/skipped` 整数（eval_runs 表）。渲染最近 ≤8 次跑批的 passed/total 迷你条（中性墨，横向排列，hover 出具体数）；无跑批走 EmptyState。**通过率=passed/total，total=0 时显「无有效用例」不显 0%**（诚实：除零不编）。
3. **晋升史时间线**：`governancePromotions` 全部（现只显 [0]）→ 时间线卡，每条：`L{from}→L{to} · 相对时间(formatRelativeTime) · 签发人 {confirmed_by}`，可展开看 `checks_json` 五门机器判定快照。空态「尚无晋升」。
4. **该 agent 固化 case 计数**：新增只读端点 `GET /api/agents/{id}/curated_cases_count`（scout 证实是「一行 glob」量级：`glob agents/{id}/eval_cases/case_*.json`）→ `{count}`。弹窗显「已固化 N 个 eval case（按仓内固化文件计）」。

**晋升仪式（亲历者）**：operator 在弹窗内点「申请晋升 L1」→ 同步成功回调里，对新晋升卡播一次 `burstNeutral`（中性尘埃迸发，复用 batch A effects/burst.js）+ 晋升史时间线顶部新卡 `fx-ink-in` 浮现。**仅本次同步动作触发**（就在 promote 成功的 then 分支）——历史打开弹窗恒静态，零回归。reduced-motion 降级。

**后端**：仅新增 `GET /api/agents/{id}/curated_cases_count`（governance.py，只读，agent 404 语义对齐同区）。其余全复用现有端点。

---

## 二、轨2：工程师个人贡献页 `/me`（只精确归因 + 私有）

**新路由** `/me`（name: "me"），**深链非顶导航**（导航保持批B 的「对话+今日」双入口；/me 从侧栏底部身份区（现「Jerry」标识，App.vue）点击进入）。

**私有访问控制**：新端点 `GET /api/me/contributions?since=<iso>` **从 session username 服务端派生归因主键**（`request.state.user["username"]`），绝不接受 username 查询参数——杜绝「查他人贡献」。since 口径同批B（offset-aware ISO 必填、Z 归一化、OverflowError 422 fail-closed，复用 stats.py 的解析工具或抽共享）。

**版块**（自上而下）：
1. **我的贡献概览（精确）**：`/api/me/contributions` 返回 `{username, since, tasks_created, tasks_completed, tasks_waiting_review}`——SQL COUNT `tasks WHERE created_by_username = ? [AND status/finished_at 条件] AND origin='user'`。四格中性数字（本周发起/完成/待我跟进 + 累计发起）。
2. **我发起的任务（精确）**：`list_tasks` 加 `created_by_username` 过滤参数（照 origin 模式），端点走 `/api/me/tasks?limit=20`（同样 session 派生 username，非开放 query）→ 最近我发起的任务卡（复用 /today 任务卡型态，点击深链 /tasks/:id）。
3. **我的反馈（近似，显式标注）**：feedback 表只有 `created_by`（display_name，可撞名，无 username 列）。`/api/me/contributions` 附 `feedback_count_approx` = COUNT feedback WHERE created_by = <我的 display_name>。版块小字**明标「按显示名近似（可能与同名者混计）」**——诚实降级不假装精确。
4. **团队总量条（复用批B）**：`GET /api/stats/overview`（已有）——四格团队本周量。**无人际排名**：只做「团队本周 X」的氛围对照，绝不列他人数字/名次。
5. **诚实缺口条（显式上屏）**：一行灰字「签发/样本认可的个人归因待后续——签发唯一身份当前仅在审计轨留痕（人是唯一签发者红线的落点），无应用数据读路径」。**不假装能算**，把缺口摆明是本页的诚实义务不是装饰。

**后端新增（只读，零 schema 变更）**：
- `repos.list_tasks` 加 `created_by_username: str | None = None` 过滤参数（照 origin/status 既有模式，None=不过滤）。
- `GET /api/me/contributions?since=` + `GET /api/me/tasks?limit=`（新文件 `backend/app/api/me.py` 或并入 stats.py；username 一律 session 派生）。

---

## 三、测试与验收

- **后端 pytest oracle**：
  - me/contributions：夹具种「我发起 N 个（含完成/待审/eval origin 混入）+ 他人发起 M 个」→ 断言只计我的、origin='user'、since 边界；**私有实证**：登录 A 只能拿 A 的数（无 username 参数可越权查 B）。feedback_count_approx 按 display_name 计。
  - list_tasks created_by_username 过滤：精确计数 + tamper（拆过滤必红）。
  - curated_cases_count：种 agent 的 eval_cases 文件 → 精确计数；无目录=0。
- **e2e**（`frontend/e2e/batch_c_rewards_acceptance.py`，入 verify_all）：①打开 agent 治理弹窗→成长档案四版块渲染 + 晋升史摊开>1 条（造 2 次晋升）②弹窗内点晋升 L1 成功→新晋升卡 .promote-burst 动效出现（亲历）③/me 概览数字 === httpx 直查 /api/me/contributions（同源）④私有断言：另一账户登录看 /me 只见自己数据⑤诚实缺口条文案在屏。
- **视觉存证**：Agent 成长档案 + /me 亮/暗全页截图入 docs/reviews/batch-c-shots/。
- **审查**：命中「新 API 端点 + 治理/贡献数字上屏 + 私有访问控制」→ 完工后 Codex 治理审（86gs），逐条 grounded。

## 四、风险与边界

- 最大诚实风险=工程师页被误读为「全部贡献」——诚实缺口条（§二.5）+ 反馈近似标注（§二.3）是验收项非装饰。
- 私有访问控制是安全线：me 端点**必须** session 派生 username、拒绝 query 参数越权——e2e 私有断言咬合。
- 晋升动效只在同步 promote 成功回调触发，不接 liveFeed（晋升非轮询数据）；亲历语义=「你刚点成的这次」，比 batch A 的迁移亲历更简单。
- created_by_username 存量 NULL 行：/me 不会误计（NULL != 任何 username）；这些老任务的发起者无法归因是迁移 #9 已知诚实残差，不在本批补。

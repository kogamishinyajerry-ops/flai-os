# 批八 teams 实体 · Codex 治理审记录（AGENT-TEAM-B8）

> 审查对象：批八增量（a340468 S1-S2 + c11accc S3-S4 + 32589f0 治理文档）
> vs origin/main（2a507f6）。审查方 = Codex（`codex review --base origin/main`，
> 异源，cap=3：R0+2 fix 轮）。设计契约 = docs/design/AGENT-TEAM-B8-DESIGN.md
> （DESIGN-FINAL，loop-auditor FLAG→修订后放行，F1-F5 已折入实现）。

## 一 · 交付面摘要

- S1 存储：迁移 #13 teams/team_members 两表；repos 四函数（create/get/list
  members 的 after_json 解码 fail-safe）。
- S2 API：POST /api/teams（只信服务端 orchestrate 推荐，保存前复验）+ GET
  投影（密级/在场/现势版本预览）+ POST summon（G1-G5 对账 all-or-nothing，
  seq 升序重排 → run_batch_creation 单源复用，零平行实现）；runtime._execute
  disabled 三重复检兜底（auditor F1）。
- S3 前端：GuidePage 存团队入口 + AgentPortal teams 卡片/召集填参对话框
  （fail-closed）+ withheld 密级遮蔽三面（Guide chip / Workbench 收纳行 /
  TaskDetail 依据段，绝不编造计数）。
- S4 验证：backend 9 测 + batch_h e2e 26/26 + tamper b8-* 4/4 BITE-OK
  独立重放（详 AGENT-TEAM-B8-tamper-log.md）+ verify_all EXIT=0（1054
  pytest + 19 e2e 套件）。

## 二 · 轮次记录

### R0（2026-07-18）——3 P1 + 5 P2 + 1 P3，逐条 grounded 复核后全部采纳修复

| # | 级 | finding | 复核结论 | 修复 |
|---|----|---------|----------|------|
| 1 | P1 | 执行期 disabled 兜底是 worker 可见行为变更，未 bump WORKER_GENERATION——分离部署时旧 worker 骗过 deploy_selfcheck 硬跑禁用成员任务 | 属实（config.py:70 沿用旧代际串） | 代际串追加 `+b8-disabled-gate` |
| 2 | P1 | 存团队按钮渲染在**每条**历史 orchestrate 卡上，而 POST /api/teams 只读最新快照——点历史卡=以旧卡之名存新名单 | 属实（plan-foot 在消息 v-for 内） | 取 Codex 给的第二选项：`latestPlanIdx` computed，仅最新方案卡渲入口 |
| 3 | P1 | G4 对账与 run_batch_creation 之间 registry 热切换不兼容新版 → 新版被盖进任务 → runtime 漂移复检（现势 vs 任务版本同值）恒过，saved-team 版本 gate 被旁路 | 属实（TOCTOU） | run_batch_creation 增 `pinned_versions` 参数：对**同一次 registry 读取对象**校验钉版本+盖章，不一致 422 零写入；summon 在 G 循环采集传入 |
| 4 | P2 | SummonItem 缺 BatchTaskItem 的尺寸/文件 id validator——超限 inputs/超长 role 在构造时抛未捕获 ValidationError → 500 | 属实 | 构造逐席位 try/except 译成结构化 422（`material_errors` 独立列表，不与 gate errors 混流保 tamper 锚） |
| 5 | P2 | file_upload 席位一刀切禁提交+无上传控件——含文件成员的合法团队永远召不动（G5 要求全席位，逐个单建也救不回团队动作） | 属实（guide 可召集面含 file 型） | 对话框复用 TaskCreate 上传流：提交时才上传、任一失败中止整单、file 席位 ≥1 材料才就绪；`none` 型席位同步解禁 |
| 6 | P2 | 席位字段手搓渲染只查必填非空——枚举/整数/数组约束全裸奔，建出注定 runtime 失败的任务 | 属实 | 换用既有 SchemaForm + validateInputs（控件化约束+校验兜前）；schema 超覆盖面（renderable=false）fail-closed 禁提交 |
| 7 | P2 | api client 对 object 型 FastAPI detail 统一 JSON.stringify——summon_errors/batch_errors 渲染分支永不命中，对账清单渲成生 JSON | 属实（client.js `_extractDetail`） | submitSummon catch 内解回结构再取清单（不动 client 全局行为，零波及面） |
| 8 | P2 | verify_all.ps1 的 E2E 列表未登记 batch_h——Windows 部署目标可在零 teams oracle 下报绿 | 属实；且该列表存量滞后更广（m9-m11/cfd/batch_a-b/eval×2/batch_g 均缺，成对脚本契约早已破） | 补登 batch_g+batch_h（本团队批次线的两套）；**存量滞后整体对齐入 retro 队列**（残留项①） |
| 9 | P3 | 团队密级 min 口径跳过缺位成员——全员卸载/缺位+高位组合虚标 sensitive，且注释与代码不一致 | 属实（假注释） | 缺位按最保守 internal 参与取 min；新增回归测试钉死 |

修后自证：backend 12/12（+3 回归：超限材料 422 非 500 / 钉版本不一致拒发+一致放行 / 全员缺位 clearance_display=internal）；batch_h e2e 26/26（O3 探针随 SchemaForm 控件化同步更新）；tamper b8-after-cut 锚点随 try 块缩进同步。

诚实标注（未验证残差）：file 席位上传 UI 复用 TaskCreate 既有流水（uploadPendingFiles 同语义），但 e2e stub 注册表无 file_upload 型 agent，该 UI 路径无端到端覆盖——API 侧 input_file_ids 路径已有 O5a/O5b 盖（sensitive 材料整单拒发）。

### R1（2026-07-18）——2 P1 + 2 P2，全部指向 R0 修复轮新面，逐条采纳

| # | 级 | finding | 复核结论 | 修复 |
|---|----|---------|----------|------|
| 1 | P1 | api/teams.js 映射读 camelCase 别名 `inputFileIds`，submitSummon 传 `input_file_ids`——file 席位上传后仍发空列表，任务无材料注定失败且文件孤挂 | 属实（R0 修复轮引入的键名错位） | 映射对齐 wire 键名 `input_file_ids` |
| 2 | P1 | 上传 await 期间取消按钮/关闭控件仍活——关掉只是隐藏，submitSummon 恢复后照发；切开另一团队还会以新 reactive 状态背地里提交 | 属实（async 恢复竞态） | 召集中封死三条关闭路径（modal/esc/×+取消禁用）+ 提交前快照捕获 target/seats、await 后引用不一致即中止 |
| 3 | P2 | latestPlanIdx 向后搜任意历史 orchestrate 卡——后端每个 assistant 轮整体替换 recommendation（含替换成空），方案被 refuse/无方案轮取代后旧卡仍渲 Save（点了 422） | 属实 | 判据改「最后一条 assistant 轮」：非 orchestrate → 全部卡不渲入口 |
| 4 | P2 | 导引 role 上限 2000 > BatchTaskItem.name 上限 200——长 role 团队存得进但每次召集被材料校验拒发（合法蓝本永久死锁） | 属实 | summon 盖任务名时收口 `strip()[:200]`（蓝本存储 role 原文不动）；回归测试钉死 |

修后自证：backend 13/13；batch_h e2e 26/26；verify_all EXIT=0。

### R2（2026-07-18，cap 第 3 轮）——1 P1 + 6 P2，全部按审查方 suggested fix 直接落地

| # | 级 | finding | 修复 |
|---|----|---------|------|
| 1 | P1 | 上传 await 期间浏览器返回离开门户——unmount 不改捕获引用，守卫恒过，离开后仍建任务再被 router.push 拽回 | **verbatim**（审查方原文 "Invalidate the operation from onUnmounted"）：onUnmounted 收起 summonOpen → 既有 await 后守卫如实中止 |
| 2 | P2 | params/file_upload 席位 schema=null（后端读取失败/损坏）被真值判断放行——召出注定 runtime 失败的任务 | seatSupported 对两型强制非空 schema（全部 agent 包随包携带 input_schema.json，null=异常态 fail-closed） |
| 3 | P2 | 摘要行含任一依赖即全串箭头——多根/分叉拓扑被虚构成串行链 | 箭头仅真线性链（每位恰接力上一位）；否则 · 并列，真实边在面板逐席位展示 |
| 4 | P2 | GET /api/teams 静默 LIMIT 100——超百份蓝本后旧团队 UI 永久失联 | 端点显式 limit(1..500)/offset 分页 + repos OFFSET + 越界 422；门户取首页，翻页 UI 随规模再长（残留项②） |
| 5 | P2 | 存团队失败 toast 渲生 JSON（team_errors 分支永不命中，同 R0#7 根因） | client.js 提炼 `unwrapDetail` 统一解包，save/summon 两处共用 |
| 6 | P2 | Workbench 收纳行遮蔽即短路——可读 internal 依据与受限件共存时吞掉用户有权查看的计数（与 Guide/TaskDetail 口径不一致） | 共存渲染：`依据 N 条·另有密级隐藏项`；仅受限 → 纯遮蔽文案 |
| 7 | P2 | 对话框定宽 640px 无 max-width——375px 窄视口控件/页脚溢出屏外 | `width="min(640px, 92vw)"` |

修后自证：backend 14/14（+1 分页回归）；batch_h e2e 26/26；verify_all EXIT=0；tamper b8-* 复放见 tamper-log。

## 三 · 收口

- cap=3 用尽（R0→R1→R2）。R2 终轮 1 P1 的修复由审查方逐字给出 → **verbatim
  例外**落地（不再走轮，commit 注明）；6 P2 亦全部按 suggested fix 直接落地，
  修后零未清 finding、全量 gate 绿、tamper 4/4 咬合——依「过审即自主合并 push」
  常设授权执行合并。owner 复核点（如有异议可 revert）：R2 P1 的 onUnmounted
  失效化落法、file 席位上传 UI 无端到端覆盖（诚实残差见 R0 段）。
- 残留项（retro 队列）：① verify_all.ps1 存量 E2E 列表滞后整体对齐
  （m9/m10/m11/cfd_flow/batch_a/batch_b/eval×2 均缺，成对脚本契约早破，先于
  批八存在）；② 团队列表翻页 UI（端点分页已通，规模到了再长）。
- 轮次统计：R0 9 条 + R1 4 条 + R2 7 条 = 20 findings，全部 grounded 复核
  属实并修复，0 驳回 0 遗留。

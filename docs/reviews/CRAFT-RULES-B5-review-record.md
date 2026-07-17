# 批次五 craft rules（C1-C6）评审记录

> spec 锚点：`docs/design/UI-DESKTOP-CRAFT.md` §十四。实现 commit `df2cba7`（基线 `e39ba1b`，分支 `feat/uiux-craft-rules-b5`）。
> 参照系：Open Design craft 十二律（state-coverage / animation-discipline / anti-ai-slop / accessibility-baseline）——营销语法≠工作台语法，取校准规则不取皮。

## 一、改动面

| 域 | 文件 | 改动 |
|---|---|---|
| C1 超时纪律 | `frontend/src/api/client.js` | AbortController 硬超时；`ApiError.timeout` 分型；`DEFAULT_TIMEOUT_MS=20_000` |
| C1 | `frontend/src/api/conversations.js` / `files.js` | postMessage 180s / uploadFile 60s 显式放宽（诚实口径+余量，绝不放宽默认） |
| C1 | `frontend/tests/api_client_timeout.test.mjs`（新） | 挂起→超时分型 / 连接失败分型不混同 / 正常路径+契约常量，3 测 |
| C2 错误三问 | `frontend/src/views/TodayPage.vue` | feedError 补「（自动重试中）」（liveFeed 5s 轮询链=真声明）+role=alert；晋升/统计错误行补手动「重试」钮（fetch 一次性来源，不谎称自动重试） |
| C2 | `frontend/src/components/QuickSwitcher.vue` | 三源 grab+failed 计数→`.qs-degraded` 诚实降级条+空态文案切换（故障≠无结果） |
| C2 | `frontend/src/views/AgentPortal.vue` | 评测续跑失败如实上屏（governanceResumeError，role=alert） |
| C2 | `frontend/src/views/MePage.vue` / `FeedbackPage.vue` | el-alert 补重试钮（加载中禁用） |
| C3 clay 预算 | `GuidePage` / `WorkbenchSession` / `TaskDetail` / `TodayPage` / `App.vue` | 14 处常驻元素降灰（ink 系+hover 升 clay）；豁免集焊死=工作灯/选中态/主 CTA/状态聚合面 |
| C4 reduce 补洞 | `frontend/src/App.vue` | reduce 块补 `.sidebar`（!important 压 860px 块源序后位）+ `.el-drawer/.el-overlay` |
| C5 ring 试点 | `MePage`（me-stat/me-task-item）/ `StatusCenter`（sc-item） | 透明边框+1px box-shadow 环（布局零抖动）；晋升行 ellipsis+胶囊 max-width 溢出边界 |
| C6 外科 ARIA | `WorkLog.vue` | 折叠头 div→真 `<button>`+`aria-expanded` 携真态；CSS reset 保 craft ① 四边框断言面 |
| C6 | `QuickSwitcher` / `StatusCenter` | 关闭后焦点回还触发钮（focusReturnEl 模式） |
| 验收网 | `craft_desktop_acceptance.py` | ⑭a-⑭g 十探针（超时/重试/降级/census×2/reduce/ring/溢出/button/焦点回还） |
| 验收网 | `m8_collab_chain_acceptance.py` ⑤b / `m9_guide_loop_acceptance.py` ①b | clay 预算 computed 色直断计入原子套 |

## 二、首过验证（实现后、tamper 前）

| 门 | 结果 |
|---|---|
| `node --test`（frontend/，裸调用） | 24/24（含新增 3 超时测） |
| craft_desktop_acceptance | **99/99**（89 存量 + 10 新⑭；⑭g 首跑 strict-mode 双匹配 `.sb-foot-btn`，定点 `:not(.sb-theme)` 后全绿——探针自身缺陷，非产品缺陷） |
| m8_collab_chain | 8/8（含新 ⑤b） |
| m9_guide_loop | 10/10（含新 ①b） |
| 其余受影响套件（m2/m10/batch_b/m8_workbench 等） | 实现期逐套跑绿（dist 重建后） |

## 三、Tamper 战役（≥5 处必咬；每处 patch→`npm run build`→跑套件→git 恢复——亲证破坏进入被测制品）

| # | 靶点 | 篡改 | 咬合证据 | 恢复 |
|---|---|---|---|---|
| T1 | App.vue（census 回染） | `.nav-link`/`.today-section-head` 染 clay !important（模拟 accent 滥用回潮） | ⑭C3 /today+/me **双红**（97/99），FAIL 明细逐个列出回染元素；副产物：探明基线=2（brand-mark+sb-new 恰满 ≤2 预算，含义见 §六-b） | ✓ |
| T2 | client.js（超时机制撤除） | 删 `setTimeout(()=>controller.abort())` 触发线（signal 管线保留——最阴险变体） | 双层咬合：e2e ⑭C1 红（错误行永不出现）→ 后续 ⑭C2 重试点击 TimeoutError 崩（fail-closed，绝无假绿路径）；node 层 `✖ api_client_timeout.test.mjs`（pending-promise 诊断，永不绿） | ✓ |
| T3 | QuickSwitcher（降级条阉割） | `fetchDegraded.value = false` 永不亮 | ⑭C2 ⌘K 精确 1 红（98/99） | ✓ |
| T4 | MePage（ring 回退） | me-stat 回实线边框+去环影 | ⑭C5 精确 1 红，明细 `me=rgb(236,229,219)|none` 而 sc-item 完好（AND 合断有效） | ✓ |
| T5 | WorkLog（button 回退） | button→div+撤 aria-expanded | ⑭C6 精确 1 红 `tag=DIV None→None`；craft ① 边框断言面未连坐（CSS 类保留验证有效） | ✓ |
| T6 | App.vue（reduce 补洞撤除） | 删 `.sidebar { transition: none !important; }` | ⑭C4 精确 1 红 `sidebar=0.22s`——正是 860px 块源序盖回，实证 !important 的必要性 | ✓ |

每处恢复后 `git status --short <file>` 空输出核验；T6 后全量 verify_all 从干净源重建 dist。

## 四、verify_all 全量

全量各跑两轮，均 **EXIT=0**：
- 第一轮（tamper 战役全部恢复后、从干净源重建 dist 起跑）：① npm run build ✓ · ② 全量 pytest -n auto（三 testpaths）✓ · ①b node --test ✓ · ③ 17/17 e2e 套件全过（craft 99/99 含 ⑭ 十探针）· [失败]（无）
- 第二轮（3-lens 修复批 + 补咬全部恢复后终局）：同全段 ✓ · craft **102/102**（+⑭C6′/⑭C6″/⑭C2′）· [失败]（无）

## 五、3-lens 对抗审（ultracode 授权；sonnet ×3 只读：可用性工艺 / 红线诚实 / 回归风险）

三镜合计 **1 P1 / 7 P2 / 5 P3**（上传超时被可用性/回归两镜独立命中，互证）。逐条 grounded 复核后裁决（修复批 commit 见 §七 前言）：

| # | finding | 裁决 | 落地 / 证据 |
|---|---|---|---|
| rP1 | **跨模态焦点竞态**：SC 开着按 ⌘K，SC 关闭回还的 nextTick 排在 ⌘K 聚焦之后，焦点被抢回 dock pill（lens 静态追踪，自陈未实机验证） | **采纳（P1 属实）** | oracle 先行：新探针 ⑭C6′ pre-fix 红 `active=status-dock` =浏览器实证；修复=store 级 `suppressFocusReturn` 让位旗（QS 置位→SC watcher 跳过一次回还并复位）；post-fix 绿。QS 注释本就自陈「让位不是归位」——意图在注释里，实现没做，探针把契约焊死 |
| uP2-1 | 焦点回还在「选结果导航离开」路径回错方向（QS activate / SC goFullPage / retryFromPeek 先导航后 close→watcher 拽回触发钮） | **采纳** | ⑭C6″ pre-fix 红 `active=sb-foot-btn` 实证；修复=三处导航离场前 `focusReturnEl = null`（回还只属于 Escape/点遮罩类「放弃关闭」） |
| uP2-2 = rP2 | 上传超时 60s vs 后端上限 `FLAI_MAX_UPLOAD_MB=100`：慢链路大附件从「慢但能传完」变「直接判超时」（行为回归，双镜独立命中） | **采纳** | files.js 60s→**300s**（~0.33MB/s 地板覆盖内网最差链路），注释绑定后端契约与推导；真挂起仍会落地 |
| uP2-3 | AgentPortal 恢复失败无重试钮，文案指路「再次跑评测」=语义错位（那是起新评测，照点会多起一跑） | **采纳** | 行内「重试」钮 wire 到 `resumeInFlightRunIfAny`（幂等：失败后 latest 仍是 queued/running 旧态，复调即恢复轮询）；文案剪掉误导尾巴 |
| uP2-4 | agent-cta 降灰后描边用 hairline 在纸面近乎无边缘对比——行内唯一推进 CTA 与说明性灰字同权重 | **采纳** | 描边 hairline→`--ink-faint`（仍非 clay，预算不破；hover 满血 clay 不变）；m9 ①b 色断言不受影响 |
| hP2-1 | 三处 e2e 硬编码 clay RGB 字面量：将来调色即同时静默过期，census/⑤b/①b 全部失咬且不报错（oracle 腐烂） | **采纳（比建议更彻底）** | census/m8/m9 全改**运行时探针 span 解析 `var(--clay)`**（同 context 同主题等值比较；var 缺失→解析回退继承色→census 大面积误报=fail-loud）；T1′ 回染重咬实证咬合力保持 |
| hP2-2 | 「（自动重试中）」真声明（lens 溯源 liveFeed 证实为真）无任何探针锁定：reschedule 被改坏后声明变谎言且无警报 | **采纳** | 新探针 ⑭C2′：feed 挂起→标注在场+反矛盾+**轮询真二次开火**（hits 计数）；T7「出错停轮」投毒→`hits=1` 精确咬合 |
| uP3-2 | 超时文案「……请稍后重试」+「（自动重试中）」硬拼自相矛盾 | **采纳** | `feedErrorDisplay` computed 剥掉手动重试尾巴再挂自动标注；⑭C2′ 反矛盾断言（pre-fix 红原文即该拼接）锁死 |
| rP3 | `.el-overlay` reduce 归零的实际影响面（ElDialog/ElMessageBox 共 6 处）比注释宽；lens 已验证 Vue 对 duration=0 立即 resolve 不挂起 | **采纳注释修订** | App.vue 注释如实扩写影响面+不挂起结论；⑭d 只测了 drawer 分支→ElDialog/MessageBox reduce 覆盖进 retro 队列 |
| uP3-1 | convo-dot.plan 6px 空心环可辨识度接近下限（且比默认实心点更暗） | **视觉抽检后留痕** | 见 §五-b |
| uP3-3 | ring 试点与未改卡片（today-card/DeliveryCard）观感有缝 | **反采纳留痕** | spec §C5 已自陈刻意范围外（「叠加需重设计」），非疏漏 |
| hP3 | m8⑤b/m9①b 的 "(none)" 兜底理论空真值不可达（无兜底元素先抛异常） | ~~**记录在案**：无改动；lens 已证不可达~~ **勘误（Codex R0 P2 推翻）**：per-element 洞真实存在且已实际发生——m8 ⑤b 时点 chip-action 因人签流程（任务恒 waiting_review→走 chip-review 分支）**从未渲染过**，sentinel 一直把这个真覆盖空洞遮成绿。R1 修复：去 sentinel+在场先断言+running 翻转夹具（m9 同款渲染路径口径）让动作字真实上屏受审 | 见 §七 |
| — | lens-honesty 诚实边界自陈：只读授权未重放 tamper 链 | **记录在案** | tamper 证据链由主会话亲跑（§三、§五-c），职责分工如实 |

三镜「未命中/未见问题」维度同样入档：C3 降灰名单**真状态信号零丢失**（灯/字全在未动的 .status-lamp/.chip-lamp/.today-lamp 上）；~~check() 全 `is True`~~（**勘误**：Codex R0 P1 抓出 5 处新探针传裸比较——实质为 bool 无假绿，但违 `is True` 显式家规且本句构成 over-claim；R1 已全部收紧为 `(...) is True` 形态）；QS grab 归因无误报面；WorkLog button 无 form 祖先/无嵌套交互元素；后端接口均有界、20s 默认安全（评测轮询单次 GET 短请求）；scoped CSS 零类名泄漏。

### 五-b 视觉抽检（uP3-1）

**抽检通过，无需改动。** m9 实机截图里该会话 dot 实为 talk 类（侧栏列表在方案生成前拉取，recommendation 未回填）——不构成 ring 证据；改用同引擎 CSS 探针（真 token #a39d90/#6b6259 + 真 chromium 1x）并排渲染：6px 上 1.5px inset 环留 3px 孔，**空心形状与更深色值双重区分在 1x 都清晰可辨**，未出现「糊成灰点」。证据：scratchpad `dot_probe_1x.png`。诚实边界：探针是隔离 CSS 渲染（非满页视觉语境），P3 级抽检口径足够。

### 五-c 修复批补咬（oracle 变更后 tamper 表续真）

| # | 靶点 | 篡改 | 咬合证据 | 恢复 |
|---|---|---|---|---|
| （oracle 先行 pre-fix 红） | ⑭C6′ / ⑭C6″ / ⑭C2′反矛盾 | pre-fix 代码即「篡改态」 | 三探针首跑精确 3 红（99/102），FAIL 明细逐字命中预测（dock 抢焦/搜索钮拽回/矛盾拼接原文） | 修复即恢复 |
| T1′ | App.vue census 回染 | 同 T1（nav-link+section-head 染 clay） | 动态解析版 ⑭C3 双红（100/102），明细同 T1——oracle 重构后咬合力不减 | ✓（此轮 checkout 误抹未提交的 F9 注释，已当场发现重落——教训：**git-checkout 恢复只对无未提交改动的文件安全**） |
| T7 | liveFeed.js schedule 入口 | `if (ch.state.error.value) return`（出错停轮——「自动重试中」变谎言的最短路径） | ⑭C2′ 精确 1 红 `hits=1`（101/102），轮询未二次开火被当场咬住 | ✓ |
| （R1 oracle 先行红） | node body-hang 测试 / m8 ⑤b0 在场断言 | pre-fix 代码即「篡改态」 | body-hang 测试对修复前 client.js 咬合（文件级 ✖ 永不绿，独立复现 Codex P2）；m8 去 sentinel 后当场暴露 chip-action 从未渲染（wait 超时崩=fail-closed 咬合实录） | 修复即恢复 |
| T11 | QuickSwitcher 分级口径回退 | 空态/降级条退回旧单一文案 | ⑭C2（全失败措辞）+⑭C2″（部分口径防夸大）双红（102/104），FAIL 明细直指夸大文案原文 | ✓（cp 备份+cmp 核验——本文件有未提交改动，git-checkout 恢复禁用） |
| T12 | StatusCenter openAllTasks 出口回退 | 撤 closeForNavigation 回漏置空形态 | ⑭C6‴ 精确 1 红 `active=status-dock`（103/104），dock 抢焦当场复现 | ✓（同上 cmp 核验） |

## 六、反采纳与边界留痕（spec §十四 详述，此处摘要）

- a) **15s 「慢」提示层**：反采纳——20s 硬超时已是唯一诚实分界，多一层 15s 提示=噪声非信息。
- b) **census 预算口径**：≤2/屏 = 内容区常驻非状态语义 clay；T1 探明当前基线恰为 2（侧栏 brand-mark + sb-new 主按钮）——即**内容区新增任何常驻 clay 都会咬**，预算已满是设计事实非缺陷。
- c) **request-id 上屏**：反采纳（本批）——后端无结构化日志关联基建时，request-id=剧场道具；进 retro 队列并标注设计前置。
- d) **自动退避重连**：反采纳——一次性 fetch 来源配手动重试钮；自动退避在无用户感知下重试=对「后端故障」的粉饰风险。
- e) **aria-live 广撒**：反采纳——不可验证残差 + WebAIM 实测证据（过量 live region 反伤读屏用户）；只在错误行外科投放 role=alert。
- f) **AgentPortal pollEval 免超时豁免**：评测跑批时长无上界，硬超时=假失败制造机；豁免留痕并由续跑错误行（C2）兜底。

## 七、Codex 治理审（R0 起，cap=3）

### R0（gpt-5.6-sol ultra，read-only，diff e39ba1b..03d6f0c）：CHANGES_REQUIRED（1 P1 + 7 P2 + 3 P3）

| # | finding | 裁决 | R1 落地 |
|---|---|---|---|
| P1 | 5 处新探针 check() 传裸比较（census×2/reduce/溢出/worklog），与记录「全 is True」声明冲突 | **采纳**（实质 bool 无假绿，但违显式家规+记录 over-claim） | 5 席位全部 `(...) is True` 收紧；§五 声明勘误留痕 |
| P2 | client.js timer 在响应头到达即清除，body 读取不受 abort 保护——头到 body 挂=永久悬挂（Codex 已复现） | **采纳** | 整个 请求→头→body 纳入同一 abort 生命周期；新增 node body-hang 测试（oracle 先行：pre-fix 红→post-fix 80ms 落地绿） |
| P2 | SC openAllTasks 漏第四条导航出口置空 | **采纳** | 抽取 closeForNavigation() 统一三出口；新探针 ⑭C6‴；T12 咬合 |
| P2 | ⑭C6″ 仅排除旧按钮即绿（焦点被别处偷走也过）；建议导航后聚焦新页 main | **部分采纳** | 探针收紧为白名单断言（=body 默认落点）；router 级 roving-focus 属全局设计**反采纳入 retro**（单点实现制造不一致） |
| P2 | AgentPortal resume 失败解除 loading 后主「跑评测」未按旧 run 在跑禁用，后端允许并发→重复入队 | **采纳** | latestRunInFlight computed（queued/running 即禁）+title 指路行内重试；「已知在跑」与「本会话轮询中」分离 |
| P2 | GuidePage 附件顺序上传期显示「导引思考中」——300s 宽限下把网络耗时伪装成模型推理 | **采纳** | uploadPhase 分阶段真话「正在上传附件 X/Y（名）…」；上传收尾重锚 thinkingSeconds（秒数只算模型等待） |
| P2 | m9①b/m8⑤b "(none)" sentinel per-element 空真值洞；记录「不可达」与代码相反 | **采纳（比 finding 更深）** | 去 sentinel+在场先断言；实测暴露 chip-action 在 m8 从未渲染（人签流程恒 waiting_review）→ running 翻转夹具（m9 同款口径、订阅回读不 reload）让其真实上屏；§五 hP3 勘误 |
| P2 | QS 单源失败+其余真空 → 空态夸大成「搜索服务不可用」 | **采纳** | fetchFailedCount 分级：1-2 源=「部分」，3/3 才=「全部/服务不可用」；新探针 ⑭b′；T11 咬合 |
| P3 | ⑭C1+⑭C2′ 真实时钟 ~46.5s+固定等待在繁忙 CI 抖红 | **部分采纳** | repoll 固定 6.5s→条件轮询（250ms×48 上限 12s，更快更稳）；测试专用短超时后门**反采纳**（生产代码纯净性>套件时长） |
| P3 | .el-overlay-dialog/.el-dialog 的 dialog-fade 位移动画未被 reduce 归零，注释影响面再度 over-claim | **采纳** | reduce 块补两节点；注释修正；dialog reduce 探针入 retro |
| P3 | tamper/全量声明无 diff 内证据物 | **部分采纳** | 新增 `CRAFT-RULES-B5-tamper-log.md`（本会话逐字 FAIL 行+计数存档；诚实边界：会话转录摘录非独立重放）；隔离 worktree replay 脚本入 retro |

### 七-b R1 修复期新发现（超出 R0 findings 的真产品缺陷）

**StatusDock 遮挡工作台头栏动作**：⑤b 夹具引入的 +10s 让 dock pill 必然渲染，⑥「结束协作」点击被 `dock-pill-waiting` 拦截（playwright 拦截日志+截图铁证：pill 直接压在「结束协作/刷新」文字上）。此前 m8 全绿靠 5s 轮询时差侥幸未撞——**既有 latent 遮挡，非本批引入**。修复：`.wb-back-actions` 宽屏（≥861px）常驻让出 200px dock 带（行为可预期不随 pill 闪变）；m8 ⑥ 现在在 pill 确定在场的条件下过点击=结构性回归锁。窄屏布局重排+dock 带全页审计入 retro。

### R0 收尾验证

craft **104/104**（+⑭C6‴/⑭b′，⑭C6″ 白名单化）· m8 **9/9**（+⑤b0）· m9 **11/11**（+①b0）· m10 12/12 · node **25/25**（+body-hang）· verify_all 第三轮全量 **EXIT=0**（17/17 e2e，失败=无）

> 过程勘误留痕：第三轮 verify_all 首次触发时因 shell cwd 漂移（留在 frontend/）
> 脚本未找到，而 `| tail` 管道把退出码吃成 0、后台通知谎报 completed——被
> `git add` 的 pathspec 报错当场识破，已从仓根裸退出码重跑得真 EXIT=0。
> 教训（入 canon）：后台长跑命令必须绝对路径起跑 + 不许让管道尾命令持有退出码。

### R1 复审（commit 3d9cf75）：CHANGES_REQUIRED——10 RESOLVED / 2 PARTIAL

R0 十二项处置中 10 项判 RESOLVED（含 4/9 两处反采纳理由被复审确认成立）；2 项 PARTIAL 收口如下：

| # | R1 finding | 裁决 | R2 落地 |
|---|---|---|---|
| #5 | 新 POST 成功后首轮询失败：queued 从未写入本地 governanceRuns，finally 解锁→按钮重开=重复入队窗口仍在（「防重复入队」声明过宽） | **采纳（verbatim 思路）** | 入队即本地落行 `{status:"queued", ...queued}` unshift（服务端字段为准，loadGovernance 到达即覆盖）；入队后失败收敛到 resume 恢复链（governanceResumeError+行内重试上屏，latestRunInFlight 压钮）——两条失败路径同一恢复车道 |
| #12 | 200px 横向预留只够单 pill：待签+运行中+监控+core 合法组合 ~360px 仍可遮挡 | **采纳（换方案）** | 横向预留废弃，改**竖向让位**：`.wb-back { margin-top: 28px }`（行顶 56px > dock 带底 ~48px），与 pill 数量彻底解耦、任意组合不遮；数学入注释 |
| #11 | tamper 存档=会话摘录非独立重放 | P3 维持 PARTIAL | replay 脚本已在 retro 队列（R1 复审确认不阻塞） |

R2 验证：m10 12/12 · eval_queue ✓ · eval_snapshot ✓ · m8 9/9（竖向让位后 ⑥ 照常过点击）· verify_all 第四轮全量 EXIT=0。

## 八、残差与 retro 队列

- **本批未被 e2e 锁定的修复（诚实标注）**：AgentPortal latestRunInFlight 禁用（niche=resume 失败窗口，代码级验证）；GuidePage uploadPhase 分阶段提示（无附件上传 e2e 流）；.el-overlay-dialog reduce 归零（⑭d 只测 drawer 分支）——三者探针入 retro。
- router 级 roving-focus（导航后聚焦新页 main）——全局设计题，反采纳单点实现。
- 窄屏（≤860px）dock 带避让布局重排；dock 带全页遮挡审计（本批只修了工作台头栏这处实测碰撞）。
- tamper 隔离 worktree replay 脚本（P3c 完整形态）。
- request-id 上屏（前置：后端结构化日志关联）。
- summary 增量读（R2-P2b 后半）；⑪f″ 敏感夹具标题断言；agentNames 重试上界；TodayPage 待签行 elapsed 端锚；el-collapse reduced-motion 复核留痕（判「高度渐变非前庭触发」豁免）。

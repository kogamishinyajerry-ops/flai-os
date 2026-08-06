# map #46 批 2 备料:「商业级」范围盘点——品牌化/多语言/性能与稳定性档(票 #57)

> 基线:`origin/main` @ `6459031`(含 #51 词表 9edf707 与 #56 触发-浮现面 PR #59)· 分支 `kimi/map46-57-commercial-scope`
> 性质:research 盘点(plan, don't do)——零产品代码改动,本 diff 仅含本报告。裁决建议全部为候选,不替 owner 定稿(HITL)。
> 方法:静态代码/文档盘点(三路并行只读子代理,输出已逐条复核)+ 构建实测(bundle 预算面);未起体验栈实测,实测证据引用既有验收记录。
> 口径:差距以「Claude/Codex/Workbuddy 风格商业级面」为对照(启发式,未附对照组证据,同 #47 口径);每条差距给现状证据(file:line/实测)+候选施工方向+量级估计。
> 红线承接:信任色锁五槽/诚实地板句/诚实纪律/**折叠保 DOM** 不纳入「可交易项」(ADR-0039 主权层);凡差距项可能误碰红线的逐条标注。
> 关联:map #46 · #47(PR #50 行话审计)· #48(PR #49 可信内核盘点)· #51(PR #54 词表)· #56(PR #59 触发-浮现面)。

---

## 一、验证基线(本分支实测,2026-08-06)

| 项 | 实测 | 备注 |
|---|---|---|
| pytest 全量(三 testpaths) | **1800 passed, 2 skipped**(58.7s) | 与 #56 合并后基线一致 |
| node --test | **286 pass / 0 fail** | 含 #56 新增锚 |
| frontend `npm run build` | EXIT=0 | 2.75s |
| `check:bundle` | EXIT=0 | 主入口 JS gzip **136,309 B** / 预算 225,280 B(220 KiB),余量 39.5% |

本票为纯文档新增,以上数字仅作基线留痕,零冲击。

---

## 二、品牌化

### 2.1 命名体系:三套半叫法并存,无 SSOT

- `FLAi-OS`(平台名,主导):侧栏头 `App.vue:18`+副标「二所工程智能体运行底座」`:19`;登录门 `WelcomeGate.vue:14`;后端 FastAPI title `backend/app/main.py:286`;README:1。
- `FLAi`(助手人格名):气泡名 `GuidePage.vue:81`、`:140`/`:521`/`:1100`。
- 「智能导引/导引」(surface 叫法):`TaskCreate.vue:271`、`WorkbenchSession.vue:194`、`GuidePage.vue:1097`——与一级导航叫法「对话」(`App.vue:255`、`router/index.js:11`)并存。
- 副标变体(半套):静态 title `frontend/index.html:7` 作「工程智能体运行底座」(**脱「二所」**),与侧栏/登录门的「二所工程智能体运行底座」不一致;运行时 title 由唯一写手 `utils/titleBadge.js:7`(base=`"FLAi-OS"`)接管、`router/index.js:54` 合成——首屏静态 title 与路由后 title 是两套字面。

### 2.2 视觉身份:标识四套并立,无独立品牌色族,字体纯系统栈

- **标识**:
  - 侧栏/hero 同源:`App.vue:16`、`GuidePage.vue:9` → `components/artwork/FlaiBloom.vue:13`(clay 七瓣螺旋花 PNG)。
  - 登录门不同源:`WelcomeGate.vue:49` `welcome-badge.png`(漫画墨线「手执工牌」插画),与花瓣 mark 无视觉关联。
  - favicon 第三套:`public/favicon.svg:9-10` clay 渐变圆角方+白「F」;`:2` 注释自称「与侧栏 .brand-mark 同源」——**注释与现实不符**。
  - 样张第四套:`docs/design/design-system/shell-welcome-gate.html` 用 emoji 🛡+描边圆。
- **色板**:品牌主色=clay `#c15f3c`(`App.vue:328`),但 clay 同时是信任五槽的「正在发生」活性槽(`:322-326` 焊死注释)——**没有独立于信任色锁的品牌色族**(无辅助色/品牌渐变 SSOT);EP primary 映 clay(`:409-415`);暗色齐备(`:462-593`)。
- **字体**:纯系统栈(`App.vue:369-372` serif/sans/mono),`index.html` 零字体链路,全仓零 @font-face——**零商用字体授权风险**;代价=跨平台渲染不一致:Iowan/Songti SC 仅 macOS 系,目标机为内网低配 Windows(`MOTION-SYSTEM.md:35-36` 自述),serif 大标题在 Windows 回落默认宋体(**推断,未实测**)。
- **动效**:SSOT `MOTION-SYSTEM.md:14-41` 六条硬约束;tokens `App.vue:362-366`、fx-* 类 `:697-741`、reduced-motion 覆盖 `:743-779`(含 EP 补洞);文档↔生产逐条对照**未核**。
- **样张代际差(实证)**:`docs/design/design-system/` 9 张 HTML 仅 2026-07-15 一批(git log 7a351a9),此后未更新;`shell-welcome-gate.html` 标语仍「机器提议,人签发。」、地板句「…签发永远由你亲手完成。」——生产已为「平台提议,你拍板。」(`WelcomeGate.vue:8`)与「…最终放行由你亲手确认。」(`:15`),#51 后样张未跟进。`@dsCard` 标注在 frontend/scripts 零消费方(grep 无命中),仓外消费未核。

### 2.3 文案调性(#51 后抽查)

- **统一面**:全站第二人称「你」(「您」零命中);中英混排微则 `TYPOGRAPHY-NOTES.md:19-26` 抽查合规。
- **不齐面(逐条证据)**:
  - 政策句三处三种说法:hero `GuidePage.vue:13`「…后台**安排**所需能力。」/ composer `:619`「…后台**准备方案** · 开始与放行由你确认」/ 方案卡 `:463`「…后台**自动编排**所需能力;**开工**由你确认…签发权始终在你。」——`:463` 为 m6③ 红线逐字锚(`:458-460` 注释),#51 刻意未动,故旧词仍在方案卡可见面与新词并存。
  - 空态句号风格不统一:`TaskConsole.vue:88`(带句号)vs `App.vue:55`、`TodayPage.vue:77/107/148/162`、`StatusCenter.vue:52`(不带)。
  - 同字段跨页异名:`reviews_approved` 今日页「本周批准放行」(`TodayPage.vue:325`)vs MePage「本周签发」(`MePage.vue:139`)。
  - 批准 toast 两口径(#48 W4 复核仍在):`StatusCenter.vue:654`「已由当前登录工程师批准放行」vs `utils/taskJourney.js:133`「{reviewer} 已批准放行」。
- **遗留英文面**(#47 P2-2/P2-6 现状):
  - 裸 agent_id 副行 7 处模板:`TodayPage.vue:72/103/156/172-174`、`TaskConsole.vue:40/62/84`;人话名机制已有(`taskDisplayName`),副行未接。
  - raw event token:`WorkLog.vue:90` 展开态直出 `e.event_type`(`:69-71` 注释自述有意设计);**英文枚举源头在后端**——`backend/app/storage/repos.py:836`「人工批准放行(reviewer={reviewer}),任务转 completed」、`:848`、`:803` 直出 `WorkLog.vue:92`;前端翻译表 `format.js:48-68`(20 键,fallback `?? t` 裸显)。
  - role=alert 面 9 处抽查多为中文人话;`TodayPage.vue:378/387` 直拼 `err.detail || err.message`,可含英文网络原文(各 detail 来源未逐条核,标未核)。

### 2.4 品牌化差距清单(全部候选,HITL)

> 量级口径:单文案行≈分钟级;含 e2e/node 锚同步≈半天级;图形资产重绘另计。

| # | 差距(证据) | 候选施工方向 | 量级 |
|---|---|---|---|
| B1 | 命名无 SSOT、三套半叫法+副标变体(§2.1,散 ~10 文件) | 命名常量 SSOT 化 + owner 裁「二所」对外口径与 FLAi 人格名关系明文化 | ~12 处/8 文件,0.5-1 人日(裁决不计) |
| B2 | 标识四套并立、favicon 注释虚标(§2.2) | 定一枚主标识(花瓣或 F 方块二选一)重绘 favicon 并修注释;工牌插画留作氛围不作标识 | 1-2 枚资产+2-3 文件,0.5-1 人日 |
| B3 | 无独立品牌色族(`App.vue:322-348`) | A=明文化「品牌=材质语言(暖纸+墨线+插画)非色」(现状转正);B=增设品牌色族(**红线相邻,见 §五**) | A 0.5 人日文档;B token 层+全站色普查 3-5 人日 |
| B4 | 字体跨平台不一致(零授权风险✓)(`App.vue:369-371`) | 维持系统栈;或内嵌 OFL 开源字体(思源宋/黑类)——须过 bundle 预算与零依赖纪律,bundle 影响未核 | 1-2 人日+裁决 |
| B5 | 样张代际差(9 张 @2026-07-15 vs #51 后生产) | 样张刷新批,或降级标注为历史档案 | 逐张对账 1-2 人日 |
| B6 | 政策句三处不齐(`GuidePage.vue:13/:619/:463`) | hero/composer 先行对齐(非红线);`:463` 是否松弛须 owner 裁(m6③ 逐字锚) | 3-5 行 0.5 人日+锚同步 |
| B7 | 标点风格不统一+空态无品牌露出(§2.3) | 标点微规则入 `TYPOGRAPHY-NOTES.md`+批扫 | ~15-20 处 0.5 人日 |
| B8 | 后端事件 message 英文枚举直出(`repos.py:803/836/848`→`WorkLog.vue:92`) | message 人话化、`reviewer=`/枚举迁 payload 结构化字段(信息零删除);或前端 WorkLog 翻译层 | 3 处后端串+测试锚,1-2 人日 |
| B9 | 裸 agent_id 副行(7 处模板) | 副行接 `taskDisplayName`,id 收 title 悬浮(正范本 `GuidePage.vue:2771-2776`) | 0.5-1 人日 |
| B10 | 无版本/关于面(MePage 全页无产品名/版本) | MePage 加关于段或登录门脚注版本;措辞须守 README 诚实口径(`README.md:3-5`) | 1 面 0.5-1 人日 |
| B11 | 窄屏登录门副标缺席(`WelcomeGate.vue:100-103/:231-234`,<900px 品牌面整隐) | 窄屏补一行副标 | 极小(1 行+样式) |
| B12(未核) | role=alert 残留英文风险(`TodayPage.vue:378/387` err.message 直拼) | 逐条核 detail 来源后排版分层(不删信息) | 0.5-1 人日 |

---

## 三、多语言(i18n)

### 3.1 现状:零 i18n 框架,前后端均无本地化层

- 前端依赖仅 7 项(`frontend/package.json`),**无 vue-i18n**;`grep i18n frontend/` 0 命中,无自研 `t()`。唯一 locale 先例:Element Plus 中文化注入(`main.js:3-4` zhCn)——EP 侧换语言包只需换这一个 import,应用文案层不存在。
- 后端无本地化层:面向用户的 `HTTPException(detail="中文")` 22 处、runner 事件 message 中文 ~10 处、`raise 中文` 76 处(大部分内部);`str(exc)` 拼接面见 #47 P1-2。
- **天然切分点(已存在的键结构)**:`format.js:48-68` `EVENT_TYPE_LABEL`(后端 token→前端译,20 键)等 15 张枚举映射表;`router/index.js:11-26` meta.title 8 条——键空间结构已在代码里隐含,只是没有词典层。

### 3.2 硬编码中文规模(可复现统计)

统计口径:python 逐行匹配 `[一-鿿]`,按目录聚合;.vue script 与 .js 再分离「引号包裹字面量」与注释行。

- frontend/src 94 个 .vue/.js 文件,92 个含中文,共 **4691 行含中文(含注释)**。
- 分布:views 1894 / components 1152 / utils 834 / ui-lab 215(验收 fixture,非生产)/ stores 134 / api 150 / router 36。
- 分离注释后,**实际需抽取的用户可见文案 ≈ 1700 行量级**(模板 ~550 + 属性 ~68 + JS 字面量上界 ~1121,含日志/fixture,为上界估计)。
- Top 密面:`GuidePage.vue` 733、`TaskDetail.vue` 333、`App.vue` 250、`StatusCenter.vue` 229、`WorkbenchSession.vue` 175、`AgentPortal.vue` 159、`TodayPage.vue` 152。
- SSOT 集中面(utils 834 行 ≈ 18%,键密度极高)vs 散落面(views+components ≈ 65%,SFC 模板内联+toast 为主)——工作量主体在散落面。

### 3.3 抽取成本量级(三类)

- **模板文本**(~550 行/40 个 .vue,均 ~14 串):机械但碎;难点在键命名与去重(「待你签发」全站 40 处命中)、插值句拆 ICU 复合格式(「依据 N 条(X 已核验 · Y 未核)」);SFC 无官方 codemod。
- **属性**(~68 行 title/placeholder/aria-label):量少但必须绑 `:title`;密级 pill 收 title 的拼接串(`GuidePage.vue:2726-2735`)要保「缺项不占位」逻辑;aria 锚与 e2e `get_by_role` 耦合。
- **JS 字符串**(~1121 行上界):toast/confirm 是逐字锚重灾区(见 §3.6);拼接句需改写带参 t()。
- **SSOT 抽取容易度:高**——format.js 15 张映射表纯函数+node 直测,~0.5-1 人日,且可成为键体系种子。

### 3.4 日期/数字/单位本地化面

- 时间 SSOT 化已较好:`formatTime`(format.js:106-110)是**全 src 唯一 toLocaleString 调用点**(`:109`,"zh-CN", hour12:false);`formatRelativeTime:114-125`、`formatClockCompact:148-155`、`formatDuration:131-140`、`formatFileSize:264-270`、`formatTokens:181-196`(k/M 压缩)。
- 绕过 SSOT 的野格式点:`GuidePage.vue:2346-2349` 自拼 `HH:MM`(唯一)。
- 千分位/百分比 formatter:**不存在**(数字走压缩或原样);`Intl.*` 全站 0 调用;时区/12 小时制=未做(非做错)。
- 后端 message 含时间/人名拼接(repos.py:836 等),本地化须连同 §2.3 B8 一起处理。

### 3.5 候选方向与量级(全部候选,HITL)

- **框架两案**:
  - A=**vue-i18n 引入**:生态标准、复数/日期模块齐;代价=新依赖+runtime ~20-30KB gzip(bundle 预算面)。**与票红线「零新依赖」直接冲突,必须 owner 单独裁**,此处只陈述。
  - B=**轻量自研词典层**:模块级词典+ref(locale),复用纯函数 SSOT 测试范式,零依赖零预算冲击;缺 ICU 复数/日期骨架(现状本也没用,中文语境复数压力低)。框架本体 1-2 人日。
  - 两案**抽取成本相同**,差异只在框架与依赖裁决。
- **候选切片**(人日粗估,口径=串数×机械替换均速+锚迁移开销,含自测不含翻译审校):
  - 切片 1「SSOT 先行」:format.js 15 表+router meta+utils 键化 → **2-4 人日**。
  - 切片 2「壳层文案外搬」:40 个 .vue 模板+属性+script toast → **8-15 人日**(GuidePage/TaskDetail/App/StatusCenter 四巨头占一半)。
  - 切片 3「锚迁移随行」(不可省):e2e 25 文件 2683 行中文锚+node 32 文件 1074 行+backend/tests 87 文件 4835 行 → **3-6 人日**,策略=锚改断言 t() 键或双语文案表。
  - 后端本地化(detail 22+runner message ~10)若入范围:+**2-3 人日**。
  - **合计:全量中→可切换英文 15-28 人日;MVP(词典层+SSOT+壳层外搬,不翻后端)8-12 人日。**

### 3.6 红线提示:逐字锚波及清单(多语言化=锚连迁)

- 地板句「通识解释仅供参考;工程结论以确定性工具与人签为准」:源 `VerificationCard.vue:74`;锚 `trigger_surface_rules.test.mjs:76`、`m10_governance_acceptance.py:301-302`、`test_guide_auto_routing_contract.py:1235`(#56 刚加固)。
- 方案卡政策句「…开工由你确认…签发权始终在你」:源 `GuidePage.vue:463`;锚 `m6_guide_acceptance.py:257`。
- 签发卡背书句/授权链:源 `StatusCenter.vue:219/222`、`TaskDetail.vue:244/247/250`(peek+完整页同源)。
- signoffText「✓ 由 X 批准放行」:源 `format.js:241-242`;锚 `format_display.test.mjs:78`;「批准放行」全站 36 处命中。
- toast 逐字锚 `trust_color_messages.test.mjs` 全文。
- 纪律:多语言化只能「逐字等价搬运+锚随迁」,不得借抽取改写措辞语义(诚实纪律不可交易)。

---

## 四、性能与稳定性档

### 4.1 bundle 预算与现状(本分支实测)

- 预算定义(`frontend/scripts/check-bundle-budget.mjs:7-14`):单 JS chunk <500 KB 原始;入口同步闭包 JS gzip ≤220 KiB / CSS ≤40 KiB;每个动态路由闭包同档;唯一动态路由 chunk ≥7(防并回同步入口)。
- 实测:主入口 `index-*.js` 376,907 B 原始 / **gzip 136,309 B(余量 39.5%)**;入口 CSS gzip 20,592 B;动态路由 chunk 8 个;dist 总量 1,273,564 B。
- **预警项:GuidePage 路由闭包 JS gzip 206,057 B / CSS 34,148 B——已达路由预算 91.5% / 85.4%,余量仅 ~14 KB / ~5.9 KB,下一个中等功能即撞门。**
- 构成:无 echarts/markdown 库/moment;EP 按需引入(vite.config.js:11-20);markdown 自研(markdownLite.js)。大头=入口框架壳 376.9 KB + GuidePage 156.0 KB + 共享 EP 表单族 chunk 85.6 KB。**无明显可一刀切掉的胖依赖,可切的是结构(GuidePage 续拆)。**

### 4.2 首屏关键路径

- 全部 8 个页面组件动态 import(`router/index.js:11-28`),同步入口只有壳;**零 prefetch/preload**(grep 0 命中)。
- 同步闭包:vue+router+EP locale/消息族(main.js:1-14)+ App.vue 壳(侧栏/QuickSwitcher/WelcomeGate/StatusDock/StatusCenter/SimMonitorFloat 静态 import,`App.vue:136-152`)。
- 零 webfont(系统栈,§2.2),图标 inline SVG——首屏无字体阻塞。
- **无 splash/骨架**:`index.html:10` 空 `<div id="app">`,登录门前白屏到入口 JS 执行完;登录门内含 45 KB welcome-badge.png(`WelcomeGate.vue:49`)。
- 登录链路:`App.vue:209` fetchMe → WelcomeGate → 登录后 `:170-175` identityReady+loadConvos,`:103-104` 因 `:key` 整页重挂路由页(刻意设计,`:95-97` 注释)。

### 4.3 会话面性能

- GuidePage 对 messages 全量 v-for(`GuidePage.vue:41`),中段折叠=display:none 保 DOM(`:3393`)——**折叠保 DOM 是 #25 红线**(MAP32 A2),长会话 DOM 随轮数线性无界增长;后端会话接口全量返回消息(无分页,`runtime/conversation.py:320`)。
- 流式渲染:每 delta 触发 provisionalAssistant 拼接(`:1367`),MarkdownLite **每次全量重算**(MarkdownLite.vue:44 自述),无节流/无增量解析。
- 轮询:liveFeed 单例池——tasks 5s/conversation 5s(`stores/liveFeed.js:32/106`)、task 频道 2s 活跃/8s 待签/终态停轮(liveFeedCore.js:16-20);`document.hidden` 跳拍;events offset 增量;引用计数归零停链(`:202-206`)。StatusDock 另 5s。
- 虚拟滚动:**未找到**(0 命中)。已知观察项:MAP32 E2(首段过长豁免)/E5(滚动还原恒差 14px)仍开。

### 4.4 慢等待与超时语义

- 慢等待真话:≥3s 秒表(`GuidePage.vue:521`),**≥30s 慢等待句**「内网大模型推理较慢——复杂需求可能要一两分钟…原话会退回输入框,不会丢」(`:525`);thinkingSeconds 口径 `:1046-1048`。
- 超时:后端 `FLAI_LLM_TIMEOUT_S` 默认 120s(config.py:36-38);前端流式硬止血 180s(`api/conversations.js:52`);gateway 传输错误/502/503/504 重试 1 次(gateway.py:148-163);**流式已发 delta 后绝不自动重试**(`:193`);失败分层(ndjsonStream.js:13-35):仅服务端明说 persisted:false 才自动还稿可重试,其余「保存状态待核」禁重试要求对账——诚实纪律已商业级。
- **差距:TTFT(首 token)无任何测量/预算**(TTI/Lighthouse/FCP/LCP/TTFT grep 全 0 命中);`scripts/measure_llm_latency.py` 只测端到端 p99 且内网实测待目标机(README.md:239)。30s 档是自我声明口径,不是 SLA。

### 4.5 稳定性叙事(离线/内网)

- M4 离线打包:**预案,未施工**(`docs/M11-OFFLINE-PACKAGE-PLAN.md:3-4/58`,阻塞在 M4 对接方回复);Windows .ps1 未实机验证(仅 macOS AST 语法检查,HANDOFF-K3.md:43)。
- 内网真机复验挂账:延迟 p99(README.md:239)、worker 单实例锁与 O_NOFOLLOW Windows 分支(README.md:232-233、DEPLOYMENT-SUPERVISION.md:134)。
- 健康面:`/api/health`(main.py:302-372,liveness+治理代际轴+db_identity)、`/api/readyz`(:374-388,worker 心跳不新鲜返 503)、deploy_selfcheck 三形态齐备——**运维面已商业级**。
- 错误面分层(#51 P1-2 后):默认面人话+技术 detail 逐字折叠(`GuidePage.vue:32/:91-95` 等),已商业级。
- PWA/Service Worker:**未找到**(0 命中)——部署模型为内网同源直连,浏览器级离线未做。

### 4.6 性能与稳定性差距清单(全部候选,HITL)

| # | 差距(证据) | 候选施工方向 | 量级 |
|---|---|---|---|
| P1 | GuidePage 路由闭包已用预算 91.5%(§4.1) | 拆 GuidePage(方案卡/资产披露/DeliveryCard 族异步子 chunk);或 owner 裁提预算 | 1-2 人日,1-3 文件 |
| P2 | 零 TTI/TTFT 预算与测量;30s 慢等待句是唯一时间口径(§4.4) | **先 owner 裁「性能档」定义**(目标机 TTI/TTFT 及格线);再插桩 Performance API+首 token 计时 | 定义=owner 裁;插桩 2-4 人日 |
| P3 | 长会话 DOM 无界+流式全量重算(§4.3) | delta 节流(rAF 合批)/流式期纯文本 done 后富渲染;虚拟滚动**撞 #25 折叠保 DOM 红线,须 owner 先裁边界** | 节流 1-2 人日;虚拟滚动 3-5 人日+裁决 |
| P4 | 首屏无 splash/骨架(index.html:10) | index.html 内联极简骨架/品牌标(零依赖) | 0.5-1 人日 |
| P5 | 无路由 prefetch,高频页首点有网络等待 | /today 等加 hover/idle prefetch | 0.5 人日 |
| P6 | 离线打包停在预案,Windows ps1 未实机(§4.5) | 阻塞 M4 回复;到位后 wheelhouse 管线+真机验证;**「离线算什么级别」须 owner 裁** | M4 后 3-5 人日 |
| P7 | 内网 p99/Windows 锁分支未真机复验 | 目标机实测(measure_llm_latency.py 已有) | 0.5-1 人日+目标机窗口(外部依赖) |
| P8 | 无 PWA/浏览器离线 | 大概率不适用于内网同源部署;**是否需要须 owner 裁** | 若做 3-5 人日 |

---

## 五、给 owner 的裁决点汇总(候选,HITL 不代答)

1. **「性能档」定义先裁**(P2/P6/P8 共用前置):目标机 TTI/TTFT 及格线数值、离线交付级别(预案维持/离线安装包/全 air-gap 管线)、是否需要浏览器级离线。不定档则 P2 插桩与 P6/P8 无法排期。
2. **GuidePage 预算撞门处置**(P1):拆异步子 chunk vs 提预算——建议拆(预算纪律是既有防漂移机制)。
3. **多语言做不做/何时做**:MVP 切片 8-12 人日(SSOT 先行+壳层外搬)vs 全量 15-28 人日 vs 不做(内网单语种场景可论证);**若做,框架两案须先裁依赖红线**(vue-i18n=新依赖,零依赖纪律外;自研词典层=零依赖但缺 ICU)。
4. **品牌化主标识统一**(B2):花瓣 vs F 方块二选一;「二所」对外口径(B1)与 FLAi 人格名关系明文化。
5. **品牌色族**(B3):A 现状转正(品牌=材质语言非色)vs B 增设色族——**B 与信任色锁五槽弧段相邻,红线风险最高项**。
6. **政策句统一**(B6):hero/composer 可先行;方案卡 `:463` 政策句(「自动编排/开工…签发权」)是否松弛=m6③ 逐字红线锚,须 owner 裁。
7. **优先级建议(备料,不替裁)**:低成本高一致性收益项(B1/B6/B7/B9/B11+P4/P5 ≈ 4-6 人日)可作批 2 首票;P2 定档与多语言裁决为批 2 方向性前置。

## 六、证据边界与未核项

- 本报告以静态盘点+构建实测为主,**未起体验栈实测**;Windows 字体回落、动效文档↔生产逐条对照、role=alert 各 detail 来源、样张 @dsCard 仓外消费方为未核项(§二标注)。
- 中文行统计为字面量上界(未区分 UI 文案与 console/内部串),人日估计为粗估口径,不装精确。
- 行号锚自 `6459031`;三路子代理盘点输出未入库,关键结论已并入本报告并逐条复核源码。
- 红线自查:本 diff 仅本报告一个文件,信任色锁/诚实地板/诚实纪律/折叠保 DOM/依赖面零触碰。

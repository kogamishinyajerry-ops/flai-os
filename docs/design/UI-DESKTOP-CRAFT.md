# 桌面工艺批（Desktop Craft）——把全站工艺提到 Claude Desktop / Codex 桌面级（SSOT）

> 触发：owner「FLAi-OS 的 UI/UX 设计可以进行大刀阔斧的优化改进，参考 agent-ui-design
> 项目里最新学习到的 codex、claude desktop」（2026-07-15，ultracode）。
> 定位：UI-PARADIGM 定骨架（Phase 1-2）、UI-SIMPLIFICATION 做减法（Phase 3）、
> 本批做**材质与语法**——token 地基、披露语法、语义着色、空态纪律、结构 rail。
> 设计源（一手证据，均为 agent-ui-design 仓复刻资产与实机拉片）：
> `claude-code-desktop.style.md`（W16 语义着色/四级下钻/空态三级）·
> `codex-desktop.style.md`（环境 rail/问题卡/done 态）·
> `disclosure-grammar.md`（33 型式 + 数字格式表 + 两家哲学轴）·
> 实机拉片 R1-R6（[[reference_agentic_ui_live_traces]]）。
> **抄结构不抄元素**：借的是语法（权重/折叠/rail/空态分级），色板与人格仍是
> FLAi-OS 自己的暖纸 + clay + 信任色锁。

## 一、诊断（2026-07-15 grounded：8 reader 扇出 + 主控截图亲验 + 亲读）

**骨架已对，工艺不均**。对话轴（三连刀后）已达桌面级：fresh 门控入场、shimmer
旁白、秒表 tabular-nums、渐隐 mask、chip 化预填。差距集中在六处：

| # | 缺口 | 证据 |
|---|---|---|
| D1 | **token 声明与消费脱节**：`--fs-*` 6 档仅 1 处消费；`--radius-*` App.vue 自身 0 消费（写 9/10/11px 游离值）；**无 `--space-*`**；hover 三套并行；`:focus-visible` 几乎缺失（暗色下浏览器默认蓝 ring 撞暖色板）；z-index 全字面量 | token-layer reader 逐条 grep 证据 |
| D2 | **助手正文无 markdown 渲染**：GuidePage L61 纯文本插值，列表/加粗/代码 token 全糊成一段——离桌面级最大单项差距；MarkdownLite（零 v-html、纯插值转义）已存在未接入 | guide-axis reader |
| D3 | **空态装饰通胀**：今日页一屏三张大插画（进行中 0/交付 0/晋升 0 各一张）——kit9「空态三级：可行动数与视觉分量正相关」反例；纯数据空态该是一行安静文字 | 主控截图亲验 |
| D4 | **任务详情非真 rail**：io-panel 双栏埋在长单列里、不 sticky；「任务信息/来源/模型调用」是散落 section 而非 Codex 式常驻环境 rail；page-header 7 元素无 flex-wrap | task-axis reader + 亲读 |
| D5 | **语义着色未成系统**：事件行/工具聚合行无 W16 两级语义权重（动词灰/对象黑）；失败态整行同色而非「只染动词 token」 | 亲读 WorkLog |
| D6 | **一致性债**：CTA 渐变四处手调阴影；三套 chip/色条几何不共享；两套 agent-card CSS 叠放（旧版大段 0 消费死 CSS）；登录门是全站投入最少的页面；Portal 图例写「左侧色条」实现却是顶部条（文实不符）；「拒绝」vs「驳回」同动作两措辞 | guide-axis / secondary reader |

## 二、七个工作项

### W0 token 地基收口（App.vue，主控亲写）
- 新增 `--space-1..8`（4/8/12/16/20/24/32/48）与 z-scale token
  （`--z-sidebar/-hamburger/-float/-dock/-switcher`＝现值 30/40/140/150/200 归位）。
- 壳层字面量归位：fs/radius/mono 逐处对表（9/10/11px 游离圆角并入 8/12 阶）。
- hover 语法收口为两态：中性行 hover=`--hover-tint`；选中=`--select-tint-clay`
  （`.nav-link:hover` 的第三套 clay-tint 并入）。
- **全局 `:focus-visible` 语法**：`outline: 2px solid var(--focus-ring-clay);
  outline-offset: 2px`，铺满侧栏/卡片/chip/row 可交互元素——修暗色默认蓝 ring。
- 新增 `.cta-clay` 共享 utility（160deg 渐变+统一阴影+hover 抬升+按压微缩，
  reduced-motion 全静化）；三处真 CTA（发送钮/开工钮/工作台钮主态）模板接线
  真归位，各自只留结构属性；hero 徽记=品牌标识非 CTA，独立保留（施工修订：
  原「四处归位」口径把徽记误计入 CTA）。
- 数字防抖：计数/时间戳类补 `font-variant-numeric: tabular-nums`。

### W1 语义着色系统（WorkLog + 事件行，W16「两级语义权重」）
- 工具聚合行：「调用工具」动词=regular `--ink-soft`；工具名=**bold `--ink` + mono**。
- 时间轴事件：失败类（`*_failed`/error level）**只染动词/状态词 token 玫红**
  （`--trust-fail`），行内其余不动；警示=字重不色块。
- 速览/今日卡 sub 行同语法（对象名略重，动词保持安静）。

### W2 空态纪律（EmptyState 组件 + 全站巡检）
- EmptyState 新增 `tier="line"` 轻量态：无插画，一行 `--ink-faint` 文字。
- 规则钉死：**纯数据空态一律 line 态；每屏至多一张空态插画**；插画只留给
  「值得庆祝/需要引导行动」的空态（收件箱清零、反馈未选任务、空目录）。
- 今日页四处数据空态改 line（description 文案逐字不动——e2e 锚）。

### W3 任务详情环境 rail（TaskDetail，主控亲写；Codex 环境仪表盘范式）
- 页级 grid「主叙事 | rail」：主列=页头/盖章/产物/动作/事件时间轴/反馈；
  rail（sticky）=任务信息折叠（组件原样迁移）/来源四 block/仿真深链。
- DOM 序契约保持：主列先、rail 后（`a[href*='/download']` `.first` 仍指产物）；
  `source-panel` class 与内部结构不改名。
- 断点=容器查询按真实宿主几何（施工实测修订）：/tasks/:id 走任务台三栏，
  1440 视口中栏≈820px——容器 ≥780px 双栏（rail 260px，主列 ≥536 仍宽于旧
  io-panel 给产物的一半≈390）；≥1120px rail 提到 300px；更窄单列。
- page-header 补 `flex-wrap`（7 元素并发溢出的既有 bug）。
- 产物卡 >1 件时提供逐卡收起 affordance（默认全展开不变——纯 additive，
  Batch 3「多产物密度」owner 待裁部分不越权删内容）。

### W4 今日简报密度（TodayPage）
- 空态单行化（依赖 W2）；版块头统一 `.section-label` 语法+`num-token` 计数；
- 统计瓦片数字 mono tabular；版块间 hairline 节奏；文案逐字不动。

### W5 对话轴微工艺（GuidePage / WorkbenchSession，结构不动）
- **助手正文接入 MarkdownLite**（用户气泡保持纯文本忠实显示）。
- CTA 层级结构化：`workbench-btn` 恒次级描边、`open-plan-btn` 唯一满血 clay；
  无 open-plan 时 workbench 升主——由数据显式绑 class，替换 `:has()` 依赖。
- 死 CSS 清理（旧 `.agent-card` 族 0 消费段，先过 e2e grep 再删）。
- `.ap-sub` 补 title 兜底；`.ap-item`/`.chip-peek-btn` 补 `:focus-visible`。
- WB 的 el-button 原生态与 GP 定制态观感对齐（描边/字号对表，不重写组件）。

### W6 登录门仪式感（WelcomeGate）
- ≥900px 左右分屏：左=品牌氛围面（暖纸底+serif 大字标语+平台一句话+现有
  墨线插画复用，零新增资产）；右=登录卡。窄屏回落现状单卡。
- 锚不动：`data-test="login-error"`、「签发永远由你亲手完成」「不提供自助注册」
  两句诚实文案逐字保留。暗色适配同批。

### W7 次级页收口（AgentPortal / MePage / FeedbackPage / TaskCreate / QuickSwitcher）
- Portal：顶部饱和色条改**左侧 3px 类型色条**（修图例文实不符；与 intent-accent/
  member-bar 统一为共享 primitive）；图例块降一行安静小字。
- 治理弹窗趋势柱加 hairline 基线+mono 数字（轻触不重构）。
- 加载语言统一：MePage/FeedbackPage/QuickSwitcher 补 SkeletonBlock。
- TaskCreate 预填提示条 success→amber（未核语义；对齐 owner 2026-07-14 Q3
  已裁决口径，Gate2-T2' 同款修正在未 push 栈上，本批在 main 收敛到同一终点）。
- 「拒绝」vs「驳回」统一为「驳回」（先核 e2e 字面锚，若被断言则同批原子改）。

## 三、红线（不减不越）

- 信任色锁五槽不增不改；类型色（Agent category）是身份轴不是信任轴，只降
  几何重量（3px 条）不升饱和度；completed 恒中性。
- 诚实地板文本全站逐字保留、恒可见：预填提示条/签发权注/诚实缺口条/地板句。
- e2e 锚（class 名/字面文案/DOM 序/颜色断言）改动=契约级，**与实现原子同批**
  并重截图；`worklog-rawline` 折叠态常显保命线不碰。
- 人是唯一签发者；动效遵守 MOTION-SYSTEM（reduced-motion 全覆盖、fresh 门控、
  e2e 零触碰）；零新依赖零新字体；EAR 红线词不入仓。
- Gate2-T2'（未 push 栈 967e3e8）冲突面=TaskDetail/App.vue/TaskCreate/AgentPortal
  ——已知重叠，merge 时向同一设计终点收敛，冲突由 rebase 方按本 spec 裁。

## 四、验收标准

1. `verify_all.sh` 全绿（16 套既有 e2e + 新 `craft_desktop_acceptance.py`，
   `.ps1` 同步加新套——不再扩大两门漂移）。
2. 新 e2e 探针：rail 结构+产物 DOM 序 / focus-visible outline 色 / 今日页空态
   插画数 ≤1 / 助手 markdown 渲染（列表→`<ul>`）/ 双主题 pin 各断一次。
   **tamper 自证**：拆 `--focus-ring-clay` 探针必红；拆 line 空态回插画计数必红。
3. 双主题 × 双宽截图归档 `docs/reviews/craft-shots/`，密度对照可数指标
   （今日页空态插画 3→≤1；CTA 渐变声明 3 按钮→1 utility 真接线（徽记独立）；
   App.vue 游离圆角值 0 残留）。
4. 三镜头对抗审（trust/regression/paradigm）+ Codex 治理审收敛后合并。

---

# 批次二：细粒度还原（Fine-Grain，F1-F6）

> 触发：owner「继续根据 agent-ui-design 里的新分析，进行更细粒度的 UI UX
> 还原、美化」（2026-07-15，承接批次一 ultracode 管线）。
> 设计源（批次一未消化的新拉片真值，均已主控亲读）：
> `workbuddy-desktop.style.md` + `workbuddy-desktop-study.md`（kit11 成果卡
> 语法：完成摘要→成品→做了什么→**校验方式自证段**→工件卡→双 affordance→
> 操作行+绝对时间戳）· `disclosure-grammar.md` §三数字格式表/§四家族轴/§五
> 动效即披露 · `codex-desktop-study.md` R6/R7（产物类型标签「文档 · MD」/
> 「显示另外 N 个」折叠/「已处理 Xm Xs」活跳纯离散替换/完成态解锁三处同变+
> 绝对时间戳）+ W14 §七完成态 typography/§十侧栏状态图标 ·
> `claude-code-desktop-study.md` W15（Show N more 折叠行/mute-pill 正常态
> 零装饰/chart.refilter 两速律）。
> 原则不变：**抄语法不抄元素**，落在 FLAi-OS 暖纸+clay+信任色锁上。

## 五、批次二诊断（2026-07-15 grounded：主控亲读四大件 + e2e 断言面扫描）

| # | 缺口 | 真值出处 | 现状证据 |
|---|---|---|---|
| G1 | **数字格式违反 §三对表**：`formatDuration` ≥60s 秒不补零（`2 分 5 秒`）；token 三处面（TaskDetail rail `toLocaleString`、DeliveryCard 原始数、StatusCenter 速览 `toLocaleString`）均无千位压缩——「判断依据精确 · 量级感受压缩」轴上 token 属量级感受 | disclosure-grammar §三 | format.js:131-133；TaskDetail:263；DeliveryCard:130；StatusCenter:172 |
| G2 | **运行态计时冻结**：WorkLog「已处理 X」由轮询驱动，8s 间隔内数字静止——R7 实证是「活跳递增，纯离散文本替换」 | codex R7 运行态语法表 | WorkLog.vue:107（`Date.now()` 无 ticker） |
| G3 | **「校验方式」自证段整段缺失**：kit11 成果卡的签名段（教用户如何核验工作真伪）在 TaskDetail 无对应物——这是 kit11 语法与 FLAi-OS 假绿哲学的**天然接点**：mock 披露、人签记录、批量结果三条核验线索散落三处（WorkLog 展开态徽标/时间轴内口播/页头 tag），签发前无一眼汇总 | kit11 result card「校验方式」段 | TaskDetail 模板亲读：产物→动作之间无核验层 |
| G4 | **完成态无绝对时间戳**：R7 完成态解锁=操作条浮现含绝对时刻（`13:12`）；CompletionSeal 只报时长，落定时刻埋在 rail 折叠的「任务信息」里 | codex R7 完成态解锁行 + §四家族轴（codex=绝对时间戳） | CompletionSeal.vue:47-53 |
| G5 | **产物列表无尾部折叠**：R6 产物卡列表尾「显示另外 1 个 ⌄」/ W15「Show 3 more」；TaskDetail 全量平铺 | codex R6 §产物与账本装置 | TaskDetail:88（v-for 全渲染） |
| G6 | **产物类型标签只有裸扩展名**：R6 语法是类型词+格式（`文档 · MD`）；现状 `.md` 裸后缀徽章 | codex R6 产物文件卡 | TaskDetail:102 |

**考虑过、本批显式不做**（防 scope 蔓延，回执有据）：
- Portal 类别 pill/成熟度徽章按 mute-pill 降装饰——与任务书 §12.6「分类色标
  是门户视觉重点」冲突，类型轴是既裁决的身份披露，不动。
- gov-trend 图表 refilter 两速律——治理弹窗每开一次拉一次、无 refilter 交互，
  无适用场景。
- 侧栏 lamp 形状语法（环/实心/沙漏）——lamp 已有 is-pulsing 形态区分工作态，
  改形状动 TaskConsole/StatusCenter 双面 + e2e 断言面，收益/风险比不过关，
  挂 retro 观察。
- rail 渐隐 mask 截断——FLAi-OS 无对应「mono 活进程行」面（rawline 刻意
  break-all 换行是 e2e 保命线），无适用锚点。

## 六、批次二工作项

- **F1 数字格式对表（SSOT 层）**：`formatDuration` ≥60s 档秒补零两位
  （`2 分 05 秒`；<60s 纯秒、小时档既有补零口径不变）；新增 `formatTokens`
  （<1000 精确；≥1000 千位压缩 1 位小数 `12.3k`，整值去尾零 `12k`；≥1e6 同
  规则 `M` 档）——接入 TaskDetail rail / DeliveryCard 尾行 / StatusCenter
  速览三处，「部分未报，下界」诚实注保留。
- **F2 活跳计时**：WorkLog 工作态起 1s ticker 驱动 elapsed 重算（纯离散文本
  替换，零动画=R7 语法；终态/卸载即清，reduced-motion 无涉——文本替换非运动）。
- **F3 「核验」自证段（本批核心件）**：新组件 `VerificationCard.vue`，仅
  completed/failed/waiting_review 渲染（cancelled 是中断、不进签发流、无
  成果语义——显式排除），位置=产物之后、动作之前（签发前最后一眼）。
  三行全部真实数据派生，绝不合成：①工具真实性（GET tool_runs：`N 次工具
  调用 · 含 M 次 mock`+amber「未经真实核验」/`均为真实执行` 中性墨——**不给
  绿**，绿解锁是性能盘真结果接入后的项目级决策/`无工具调用记录`/拉取失败
  →`工具核验信息不可用` 诚实降级）；②人工签发（events 派生：teal `✓ 已由
  X 批准放行`/红 `✕ 由 X 驳回`/amber `待人工签发`/中性 `未经人工签发流程`）；
  ③批量结果（有 summary 事件才渲染：`成功 N · 失败 M`，failed>0 计数染红）。
  与 WorkLog 展开态 signoff 同源同谓词（events），report 级与时间轴级双呈现
  不矛盾——kit11 语法点即「核验线索必须在报告层有汇总位」。
- **F4 完成态绝对时间戳**：CompletionSeal 尾部追加落定时刻（同日 `HH:MM`，
  跨日 `MM-DD HH:MM`）；cancelled 保持不报时长（工作量语义），但报中断时刻
  （时刻≠时长）。
- **F5 产物尾部折叠**：>3 件产物默认渲染前 3 + 真 button「显示另外 N 个 ⌄」
  （aria-expanded，单向展开）；m2 e2e 首下载锚不受扰（前 3 恒渲）。
- **F6 产物类型标签**：ext 徽章升级为「类型词 · EXT」（md/txt/pdf/html→文档、
  csv/json/yaml→数据、png/jpg/svg→图像、zip→归档、未知→文件）。

## 七、批次二红线与验收

红线继承批次一 §三全部条款，另加：
- F3 三行内容**只准投影已落库数据**（tool_runs.mock / task_events / summary
  payload），任何一行凑不出数据就整行降级或不渲染，绝不推断。
- 「均为真实执行」是对 tool_runs 记录的忠实投影（runner 如实记 mock 位），
  措辞限定在「记录」层（`无工具调用记录`），不越权声称运行时真相。

验收：
1. craft 套件扩针（fixture 直插 tool_runs/model_calls + 5 产物任务 +
   review_approved 事件）：F1 补零/压缩、F2 活跳（断轮询后 3.3s 窗口 ≥3 个
   不同读数——route abort 把「与轮询解耦」变成可证伪谓词）、F3 三行+amber
   pill+teal 签发、F4 时刻 regex、F5 折叠展开、F6 类型词。
2. tamper 自证 ≥4 处必咬：秒补零回退 / amber pill 拆除 / slice(0,3) 拆除 /
   时刻拼接拆除。
3. `verify_all.sh` 全绿（18 套）；3-lens 对抗审 + Codex 治理审收敛后合并 push。

夹具教训（首跑实测，2026-07-15）：给任务种 tool_runs/model_calls 派生行时
**必须同批种 `data_classification='internal'` 戳**——分级门 fail-closed 兜底
（ADR-0025：NULL 分级+任何派生内容行→封）会遮蔽 events payload/message，
签发行/工具 chip 全部消失。门在正确地咬；夹具必须讲自洽的故事（真实 runner
对 internal 任务必落此戳）。这也是一次免费的门咬合实证：遮蔽路径真的工作。

## 八、批次三来源与审计（2026-07-15，desktop-restudy 深度打磨）

> 触发：owner「参考 agent-ui-design/design-sync/desktop-restudy/ 深度打磨 UI UX」。
> 设计源：desktop-restudy 28 张样张卡（Claude Desktop × Codex Desktop 重研，
> 1948 行，f279b9c），主控亲读 FLAi-OS 相关 17 张（axes-compare + cd-* 12 张 +
> cx-foundations/saturation/done-paused/empty-states/question-card/env-rail/
> composer/shell），跳过 plugins/popover/floating/subagents/review-diff 等无
> 对应面样张。**抄结构不抄元素**红线继承：借语法，色板与人格仍是暖纸 + clay
> + 信任色锁。

对照审计结论（已合规项，零改动）：
- 时间语义=绝对时间戳（家族轴）——批次二 F4 已落，本批只做行级延伸（G4）。
- 工具聚合=纯文字行（cx-env-rail 五图复证）——W13 已落。
- 诚实失败入叙事流/失败只染动词 token——W16 已落。
- 空态不施压（cx-empty-states 站点空态）——全站空态无实心 CTA，已合规。
- 环境 rail 空值=「—」诚实降级——W3 已落。
- 时态双态（cd-collapsed-blocks：进行中现在时+脉动/完成过去式）——WorkLog
  头行已双态，本批补三段式节奏（G2）。

## 九、批次三工作项

- **G1 折叠工作日志贴地形态**（cd-collapsed-blocks「折叠思考块=纯一行灰字，
  无背景无图标」+ cx-env-rail/cx-shell worklog 上下发丝线三明治）：
  `.worklog-head` 去盒化——背景透明、去边框盒/圆角，改上下 `--hairline-soft`
  发丝线；头行文字 ink→ink-soft、600→500（灰字语法）；hover 回墨色保
  可点性 affordance；▸ 旋转展开与既有交互面（class 名/点击锚）零变。
- **G2 头行三段式 + 零值豁口**（cd-workflow-card 思考指示器三段式节奏的
  诚实适配：状态词 · 时间 · 计量——计量轴用真实事件计数，不编 token）：
  工作态头行 `正在处理 · 已 X · N 条事件`（N=0 时该段整段不出现）；完成态
  头行既有 `已处理 X · N 条事件` 补零值豁口——N=0 时不再显示「0 条事件」
  （cd-bg-tasks-panel「空值=em dash，不显示 0」规范）。
- **G3 运行中行实时时长**（cd-bg-tasks-panel Running 卡字段序第二行=
  类型+时长实时）：状态中心收件箱「运行中」行 sub 追加 `· 已 X` 活跳时长
  （started_at 缺失=段不出现，不硬凑）；1s ticker 仅抽屉打开期间存活，
  关闭即清——与 WorkLog F2 同「纯离散文本替换零动画」语法。
- **G4 行级紧凑绝对时钟 SSOT**（家族轴「完成态=绝对时间戳」的行级形态，
  cx-done-paused 操作条 13:12 语法）：utils/format 新增 `formatClockCompact
  (iso, todayKey)`（同日 `HH:MM`、跨日 `MM-DD HH:MM`、非法/缺失=「—」；
  todayKey 由调用方响应式供给——承袭 CompletionSeal 午夜翻页教训 R1-P3，
  纯函数绝不裸读 new Date()）；CompletionSeal 落定时刻改走该 SSOT（输出
  逐字不变，F4 探针=回归网）；状态中心「待你签发/最近落定」行的全量 locale
  串（`2026/7/15 02:02:05`）收敛为紧凑时钟，todayKey 由 G3 ticker 派生。
  **孪生面**（3-lens 孪生点漏改教训）：/me「我发起的任务」行同批收敛同
  SSOT；午夜翻页逻辑抽取为 `useTodayKey` composable（CompletionSeal 原始
  修复的 SSOT 化——只需日界的面用它，已有 1s ticker 的面由 nowTick 派生，
  不重复挂表）。边界说明：任务详情 rail「任务信息」卡与工作日志时间轴保持
  formatTime 全量精度——rail/时间轴是检视面（Codex rail 同哲学），行级
  紧凑时钟只收敛扫读面；今日页 Agent 动态保持既裁决的相对时间语法。

## 十、批次三红线·反采纳·验收

红线继承批次一 §三、批次二 §七全部条款。本批反采纳（样张真理被有意拒绝，
防止「照抄样张」压过项目宪法）：
- **问题卡推荐徽/推荐项行底**（cx-question-card）——签发是人的裁决，平台
  推荐任何方向=施压代签（红线「人是唯一签发者」），签发卡永不采纳。
- **中断报「after Xs」时长**（cx-done-paused Paused 语法）——Codex 的 stop
  是可 continue 的暂停（一等时间线条目+续跑胶囊）；FLAi-OS cancelled 是终态
  无续跑，批次二「时刻不时长」裁决维持，F4' 探针不动。
- **零彩色选中双灰**（cx-saturation）——clay=工作/进行/选中是焊死的信任
  色锁槽位，家族轴已裁决 clay 锚，不迁移。
- **workflow 进度点行**（cd-workflow-card 蓝实心/灰空心）——FLAi-OS 批量
  任务无 per-item 中途真数据，凑点=编造（假绿死罪），summary 落库才有的
  批量行已在核验段。
- **rail 渐隐 mask**——批次二已裁决「无适用锚点」，维持。

验收：
1. craft 套件扩针（⑩ 系列）：G1 贴地样式谓词（背景透明+左右无边+上下发丝
   线+字重 500）；G2 工作态三段 regex + 完成态零事件任务无「条事件」段；
   G3 断轮询后 1s ticker 驱动行内时长仍递增（route-abort 列表端点）；
   G4 状态中心行时间匹配紧凑时钟 regex 且无 locale 斜杠、Seal F4 探针原样
   全绿（回归网）。
2. tamper 自证 ≥4 处必咬：G1 盒化样式回种 / G2 零值豁口拆除（恒拼 0 条
   事件）/ G3 ticker 拆除 / G4 行时间换回 formatTime。
3. node 单测：formatClockCompact 同日补零/跨日/非法/缺失四象限。
4. `verify_all.sh` 全绿；3-lens 对抗审 + Codex 治理审（native Pro sol-ultra，
   cap 3）收敛后合并 push。

# 批次四：新人极简批（Novice-Minimal，Q 系列）

## 十一、批次四来源与诊断（2026-07-16）

触发：owner「以 ChatGPT.app 和 Claude Desktop 的 UI/UX 最大化复刻优化页面；
结合之前的全面审计，现在对新人用户过于困难，所有模块、Agent 都应该最小化、
低噪音」。范本语料 = agent-ui-design `docs/styles/chatgpt.style.md`（稀疏近
单色、一行安静状态代替卡片、工具贴对象不另起面板）+ `claude-desktop.style.md`
（chat-first、折叠思考块默认折、边框语言、拟人低噪文案）+ 批次三已亲读的
desktop-restudy 17 卡 + UI-PARADIGM 的 ChatGPT.app/Claude Desktop 拉片血统。

诊断（fef203d 树最新 e2e 截图逐张过，新人视角）：

| # | 噪音 | 证据 | 范本语法 |
|---|---|---|---|
| Q1 | 裸 `task_xxxxxxx` 当行级主文本（缺名任务 fallback=id 切片） | 状态中心/任务台/今日页行 | ChatGPT/Claude 从不让用户读内部 ID |
| Q2 | 零值照登：「进行中 · 0」空组 + 0 值统计格 + 「0 条反馈」 | 今日页/我的贡献 | cd-bg-tasks-panel 零值不显示（批三 G2 已采，未全站化） |
| Q3 | 方法论脚注轰炸：窗口句同屏两次、/me 三段归因说明、方案卡尾两句 | 任务台+状态中心同屏/MePage/GuidePage | 一行安静状态；说明降披露 |
| Q4 | 门户图例句满行行话（色条=…L0→L3=…）+ 每卡 L0/治理/版本 | AgentPortal 页头+卡 | 卡=名+一句话+动作；分类学进披露 |
| Q5 | 事件类型 mono 计数行（`task_created ×1 · …`）直接可见 | TaskDetail 时间轴脚注 | process 藏折叠里（cd-collapsed-blocks） |

## 十二、批次四工作项（新人低噪五律 → Q1-Q5）

语法总则（本批一切改动的判据）：**①人话优先**（可读名>机器 ID，ID 只活在
检视面/深链）**②零值不显示**（0 不是信息；空组收敛为一行安静空态，绝不渲染
「· 0」）**③一处一行**（同屏方法论脚注去重；诚实口径留一行小字，纯方法论
括注降 title）**④行话进披露**（分类学/事件枚举默认不上首屏；诚实前置语义
不动只降形态）**⑤稀疏即尊重**（每屏一主动作，说明 ≤1 行，其余靠披露）。

- **Q1 任务称呼人话 SSOT**：`taskDisplayName(task, nameMap)`——`t.name` 优先；
  缺名 fallback Agent 显示名（新增模块级 agents 名册缓存，一次拉取懒加载）；
  名册缺失/拉取失败诚实回退 id 切片（绝不编名字）。行 meta 保 `agent_id ·
  时钟`（技术锚+同名区分）。消费面：状态中心行×3+peek 标题、今日页行×2、
  任务台左栏、/me 行。
- **Q2 零值不显示全站化**：今日页组头计数 N=0 不渲染「· N」；团队总量 0 值
  格隐藏、全 0 收敛一行；Agent 动态双空态（无晋升+无活跃）合并单行；/me
  四格 tile 与「我的反馈」同律。空态文案与 batch_b/craft 断言原子同批。
- **Q3 脚注收敛**：「最近任务窗口（100 条）…不虚报」诚实口径保留但同屏只出
  现一次；/me 底部三段说明压一行+披露；方案卡 foot 两句压一行（红线字面
  「亲手」「签发权」保持可见）；「（按仓内固化文件计）」类括注降 title 属性。
- **Q4 门户/选择器最小化**：图例句撤下页头（释义走徽章 title）；卡主体=
  名+状态徽+一句描述+CTA；类型/成熟度/`agent_id vX` 收一行次级 meta；
  「不适用范围」披露保留（诚实前置）；composer popover 的 maturity/
  limitations 字面不动（m11-A1 锚）。
- **Q5 详情页开发者语言收折**：折叠态=人话扫读面（G1/G2 头行/工具聚合行/
  签发口播），原始事件 token 只活在展开态时间轴的逐条 `.event-type-raw`；
  聚合 mono 计数行（rawLine）**退役**——其逐类信息与头行「N 条事件」+
  展开逐条 raw 重复（3-lens 裁决：退役而非移入，档案 §三 留痕）；
  「核验/签发/授权链」信任核心面不动。
- **Q6 池**：六路 grounded 扫描的额外候选，逐条过五律+锚点安全性后择优
  纳入（清单与位点/锚点级明细=评审档案 `NOVICE-MINIMAL-B4-review-record.md`）。

## 十三、批次四红线·反采纳·验收

红线继承批次一 §三、二 §七、三 §十全部条款。本批反采纳：
- **不换皮**——Claude Desktop 三明治深框/ChatGPT 近单色是它们的品牌身份；
  FLAi-OS 暖白+clay 家族轴已裁决，复刻的是语法不是皮肤。
- **不翻双 Surface 案**——「对话｜任务台」双 Surface 为 owner 现行裁决
  （UI-SIMPLIFICATION 两文 N13 状态注），本批绝不重启「删任务台导航」。
- **零值收敛 ≠ 事实隐藏**——0 本身不是待核事实；非零治理事实（未经真实
  核验/mock 标注/已剔除字段/dropped 名）一个不收、一个不折。
- **不重写 TaskDetail 整页**（简化设计 §九 YAGNI 维持）——Q5 只收 mono 行。

验收：craft 套件扩 ⑪ 系列探针（Q1 人话 fallback+诚实回退/Q2 零值豁口/
Q3 同屏唯一性/Q4 卡片最小形态/Q5 折叠态不含事件枚举）；tamper ≥4 处必咬；
`verify_all.sh` 全绿；3-lens 对抗审 + Codex 治理审（native Pro sol-ultra，
cap 3）收敛后按 standing 授权合并 push。

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

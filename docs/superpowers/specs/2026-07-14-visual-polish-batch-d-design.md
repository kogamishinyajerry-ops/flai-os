# 批D「视觉精修」设计 spec

- **状态**：待 owner 审（四批宪章最后一批；本 spec 为批D 独立细化，owner 2026-07-14 两决拍板见下）。
- **依赖**：批A/B/C 全合并 main（token/信任色锁/动效系统/暗色主题已在位）。
- **来源**：批D 视觉审计 workflow（8 维度并行只读审 → 46 findings → 15 簇，零 false positive，全 8 审计员尊重信任色锁豁免清单）。综合建议 INCLUDE 9 簇 / DEFER 零散 P2。

## owner 两决（2026-07-14 AskUserQuestion）

1. **范围 = Core 9 簇**（token 地基 + P0 响应式 + 暗色可读性三簇 + token 绕过 + 标题/section-label 归一 + reduced-motion 补齐 + 失败态不伪装空态）。零散 P2（radius 节奏/页宽/hover 过渡/loading guard/footnote）**DEFER 进 retro**，作 token 迁移第二波。
2. **失败态不伪装空态（state-logic）纳入批D**——2 行 v-if 修复，踩批B/C 诚实红线值得随手修。

## 〇、目标与铁律

一句话：把散落的视觉字面量收成一套 token 地基，并用它修掉审计咬出的可见破损（手机溢出/暗色白光晕/AA 不达标/未定义 token 渲染）与系统性不一致（标题四档/eyebrow 七写法），**精修不重构**。

**铁律**：
1. **精修不重构**：定义 token 地基 + 迁移**本批 9 簇点名的消费者**；**不做**全站魔数扫荡迁移（radius/space 全量迁移 = DEFER 第二波）。改动面控死在审计点名的文件。
2. **信任色锁五槽不动**（批A-C 焊死）：clay 工作/绿 REAL/teal 人签专属/红真失败/amber 未核；completed 不给绿；teal 仅人签。**审计零 FP 已确认无一条建议破锁**——本批同样绝不碰。
3. **诚实文案是内容不是样式**：暗色 AA 修复是**改对比度（提亮 token/加卡面 override）保留诚实文案本身**，绝不因对比度删「草案非结论」「按显示名近似」等诚实地板。
4. **功能零回归**：纯视觉/token/样式改动 + 2 处 state-logic（false-empty guard）；全部 13 套既有 e2e 必须保持绿（选择器/行为不变）。
5. **暗色改动必真验**：ink-faint AA 那条审计标 borderline（~3.95:1 估算）——落地前必做**真实 WCAG 对比度计算**（页内 JS 或工具），不盲改 token 值。
6. **MOTION-SYSTEM 硬约束④**：任何位移/旋转动画必有 reduced-motion 降级——.send-spin 补齐后本约束全站无缺口。

**边界（本批不做）**：不做 radius/space 全量魔数迁移（DEFER）· 不做 card-radius/stat-tile 统一（DEFER）· 不做 --page-max 页宽归一（DEFER）· 不做 hover-transition 补齐/dead-fallback 清理/MePage 骨架/footnote-emoji（DEFER 进 retro）· 不新增页面/功能 · 不碰后端。

---

## 一、Token 地基（cluster 1，P1 最高杠杆——先落，后续簇引用）

`frontend/src/App.vue` 的 `:root`（现 278-364）只有 `--serif`，缺三套地基。补齐（放 --serif 旁，暗色不需额外 override 的除外）：

1. **字体三元组**：
   - `--sans`: 复用现 body 栈（App.vue:587 = `"PingFang SC","Microsoft YaHei",system-ui,-apple-system,sans-serif`）
   - `--serif`: 已有（不动）
   - `--mono`: 归一散落 mono 栈（现 App.vue:779 `ui-monospace,monospace` + 7 文件各写 `"SF Mono"` 字面量）→ `"SF Mono", ui-monospace, Menlo, "Cascadia Code", monospace`
   - `body{font-family}` 指向 `var(--sans)`；migrate 现有 mono 字面量引用改 `var(--mono)`。
   - **修 `--font-mono` 拼写错**：审计报有处引用未定义的 `var(--font-mono)`（plan 定位）→ 改 `var(--mono)`。
2. **字号阶** `--fs-*`（收口散落 ~24 个 9-27px 魔数为阶梯；本批只**定义 + 迁移标题/section-label 消费者**，非全量扫荡）：
   - `--fs-title`（页标题，收口 20/22/25/27 四档 → 单一值，建议 26px）· `--fs-h3`（~16）· `--fs-body`（13.5）· `--fs-sm`（12.5）· `--fs-xs`（11.5）· `--fs-2xs`（9-10，eyebrow/微标）。
3. **radius 阶** `--radius-*`（**只定义**，供本批消费者 + DEFER 第二波引用，不全量迁移）：`--radius-sm`(6) · `--radius-md`(8) · `--radius-lg`(12，卡片主) · `--radius-xl`(16) · `--radius-pill`(999)。

> 迁移纪律：本任务只把**标题/section-label/本批点名的具体元素**切到新 token；其余魔数留存（DEFER）。避免改动面爆炸。

---

## 二、响应式 P0（cluster 2，唯一 P0，真实溢出）

- **AgentPortal**（`views/AgentPortal.vue`）：agent-card 的 `el-col :span="8"` 锁死 → `:xs="24" :sm="12" :md="8"`（手机 1 列/平板 2 列/桌面 3 列），portal-skel-grid 同步 `repeat(auto-fill,minmax(220px,1fr))`。
- **SchemaForm**（`components/SchemaForm.vue`）：固定 px select（260/220）→ `width:100%;max-width:260px`。
- **TaskCreate**（`views/TaskCreate.vue`）：`label-width:100px` 溢出 → <640px `label-position="top"`。
- **WorkbenchSession**（`views/WorkbenchSession.vue`）：`.sess-hero` <640px `flex-direction:column`。
- **TaskConsole**（`views/TaskConsole.vue`）：`.console` 三栏 <900px 改单列（空态得全宽）。

**验收 oracle（机器可检）**：affected 页在 375px 宽度 `document.documentElement.scrollWidth <= clientWidth`（无横向溢出）。

---

## 三、暗色可读性（clusters 3/4/5，P1）

1. **阴影反相**（`views/GuidePage.vue`）：composer focus-within（~1417）与 user bubble（~862）的 `box-shadow` 用 `rgba(var(--ink-rgb),…)`；`--ink-rgb` 暗色翻近白 → 画成白光晕。改用黑基 token（复用 `var(--shadow-composer)`/`var(--shadow-card)`），只保留 additive clay 聚焦环 `rgba(var(--clay-rgb),0.08)`。
2. **ink-faint AA**（`App.vue:387` 暗色 `--ink-faint`）：诚实信号 caption 落卡面（--card-bg/--surface-raised/refuse-card）时对比 ~3.95:1 < AA。**先真实对比度复检**（页内 WCAG 计算 on --surface-raised #2e2823），确认不达标再提亮暗色 `--ink-faint` 一档（候选 #948a7c–#9a9082）至 ≥4.5:1；**保留文案本身**。
3. **硬编码浅色浮层**（`components/QuickSwitcher.vue` + `components/SimMonitorFloat.vue`）：QuickSwitcher ⌘K 面板 `rgba(43,38,34,…)` 阴影/遮罩不随暗色翻 → `var(--shadow-hero)`/`var(--el-mask-color)`；SimMonitorFloat `.sim-frame` 硬 `#f7f4ee`（注释谎称「暗色不闪」实则闪白）→ `var(--paper-rail)`（暗色已定义）或若 hub 视图刻意常亮则订正误导注释。

**验收 oracle**：暗色下 GuidePage composer/bubble 阴影色分量为黑基（非近白）；ink-faint on surface-raised WCAG ≥ 4.5。

---

## 四、Token 绕过消除（cluster 6，P1）

- **WelcomeGate**（`components/WelcomeGate.vue:154`）：错误文本 `color:var(--danger,#c45656)` —— **`--danger` 从未定义** → 恒渲染硬编码 `#c45656`（用户**第一屏**登录门，不随暗色变）。改 `var(--trust-fail)`（亮 #be3a3a/暗 #d4645a 已定义）。
- **AgentPortal**（`views/AgentPortal.vue:757` promote-glow）：硬 `rgba(193,95,60,0.14)`（App.vue 注释点名要消灭的 clay-RGB 字面量反模式，批C 曾修一处又引入）→ `rgba(var(--clay-rgb),0.14)`（随暗色 clay）。

**验收 oracle**：WelcomeGate 错误文本 computed color === `--trust-fail` 值（非 #c45656）；全 `frontend/src` grep 无 `var(--danger` 残留。

---

## 五、标题 + section-label 归一（cluster 7，P1，系统性）

- **页标题**：跨 9 view 有 20/22/25/27px 四档 + 容器混用（`.page-header` vs `.today-head` vs 裸 `<h2>`），MePage 掉了 0.2px letter-spacing，serif weight 分 600/700。收口：`.page-header h2` / 页标题统一走 `--fs-title` + 统一 weight（建议 600）+ letter-spacing 0.2px；**FeedbackPage（裸 h2）/TaskCreate（裸 h2）/TodayPage（.today-head）采用共享 `.page-header` 块**。
- **section-label / eyebrow**：小标题现 7 种写法（`.gov-section-label`/`.me-section-label`/`.today-*` 等 size/weight/color/letter-spacing/margin 各异）+ FeedbackPage 用裸 `<h3>` 承同角色。收口：定义唯一 `.section-label`（建议 11px/700/0.6px letter-spacing/--ink-faint/margin-bottom 8px），迁移 7 处 eyebrow + FeedbackPage h3；**保留刻意的色覆盖**（waiting=trust-pending / working=clay 等语义色不动）。

**验收 oracle**：9 view 页标题 computed font-size 全等 `--fs-title` 值；e2e 既有断言（页标题文本/nav）不破。

---

## 六、reduced-motion 补齐（cluster 8，P1，硬约束合规）

`views/GuidePage.vue` 的 `.send-spin`（旋转，~1472）是全站唯一漏 reduced-motion 降级的位移/旋转动画（其余 5 个 reduced-motion 块都覆盖了各自动画）。在 GuidePage 既有 `@media (prefers-reduced-motion:reduce)` 块内加 `.send-spin{animation:none}`（保留静态环/呼吸做发送指示）。

**验收 oracle**：emulate reduced-motion 下 `.send-spin` computed `animation-name` === `none`。

---

## 七、失败态不伪装空态（cluster 9，P1，state-logic，owner 拍板纳入）

`views/TaskDetail.vue:239` 与 `views/FeedbackPage.vue:55`：catch 分支置 error 标记但没清空仍为 `[]` 的列表 → 「暂无反馈」EmptyState 与 error alert 同屏（失败伪装成空，踩批B/C 焊死红线）。两处同款修：`v-if="list.length===0 && !error"` gate EmptyState（identical fix 防 copy-rot）。

**验收 oracle**：mock 加载失败 → error alert 在屏且 EmptyState **不**在屏（沿用批B/C 三态互斥断言范式）。

---

## 八、测试与验收

**这是视觉批——用机器可检 oracle 兜住主观性，截图供人审。**

1. **build**：`cd frontend && npm run build` 绿。
2. **零功能回归**：全 13 套既有 e2e 保持绿（选择器/行为不变）。
3. **新 e2e** `frontend/e2e/batch_d_visual_acceptance.py`（入 verify_all，含机器 oracle）：
   - **响应式无溢出**：affected 页（AgentPortal/TaskCreate/WorkbenchSession/TaskConsole）在 375px 宽 `scrollWidth <= clientWidth`。
   - **token 定义**：`getComputedStyle(root)` 的 `--sans`/`--mono`/`--fs-title`/`--radius-lg` 均非空。
   - **token 绕过消除**：WelcomeGate 错误文本 computed color === `--trust-fail`；grep 无 `var(--danger`。
   - **暗色可读性**：暗色下 ink-faint on --surface-raised 的 WCAG 对比 ≥4.5（页内计算）；GuidePage composer 阴影分量黑基。
   - **reduced-motion**：emulate 下 `.send-spin` animation-name===none。
   - **标题归一**：9 view 页标题 computed font-size 全等。
   - **失败态互斥**：TaskDetail/FeedbackPage mock 失败 → error 在屏 + EmptyState 不在屏。
4. **视觉存证**：affected 页 亮/暗 × 桌面/375px 全页截图入 `docs/reviews/batch-d-shots/`。
5. **审查**：命中「系统性样式改动 + 暗色 AA + 硬约束合规」→ 完工 Codex 治理审（86gs），逐条 grounded。

## 九、风险与边界

- **最大风险=改动面爆炸**：token 地基诱人做全量迁移——铁律①焊死「只迁本批 9 簇点名消费者」，其余魔数 DEFER。plan 每任务显式列迁移文件清单，reviewer 咬「有无越界扫荡」。
- **暗色 AA borderline**：ink-faint 那条估算 ~3.95:1，落地前真实 WCAG 复检；若复检达标则不改（诚实：审计估算可能偏保守）。
- **信任色锁**：本批碰大量颜色 token——每处改动 reviewer 必核未破五槽（completed 不给绿/teal 仅人签）。
- **DEFER 清单入 retro**（token 迁移第二波候选）：radius/stat-tile 统一 · --page-max 页宽 · hover-transition 补齐 · dead-fallback 清理 · MePage 骨架 + promotions loading guard · footnote divider + ✍ emoji→SVG。

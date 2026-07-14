# 批D「视觉精修」Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把散落的视觉字面量收成一套 token 地基，并用它修掉审计咬出的可见破损（手机溢出/暗色白光晕/AA 不达标/未定义 token）与系统性不一致（标题四档/eyebrow 多写法），精修不重构。

**Architecture:** 先在 `frontend/src/App.vue` 的**全局（非 scoped）** `<style>` 补 token 地基（字体三元组/字号阶/radius 阶），后续任务的消费者引用它。改动面严格控死在审计点名的文件——不做全站魔数扫荡（DEFER）。视觉批用机器可检 oracle（375px 无溢出/WCAG≥4.5/token 定义/computed 值相等）兜主观，亮暗×桌面/375px 截图供人审。

**Tech Stack:** Vue3 + Element Plus + Vite；Playwright 自起后端 e2e（机器 oracle）；无 Vue 单测框架——前端任务机械门=`npm run build` 绿 + grep 断言，行为由 Task 8 e2e 把关。

## Global Constraints

以下为 spec `docs/superpowers/specs/2026-07-14-visual-polish-batch-d-design.md` §〇 的红线，每个 task 隐含包含：

- **精修不重构**：定义 token 地基 + **只迁本批点名的消费者**；绝不全站魔数扫荡（radius/space 全量迁移=DEFER）。每任务只碰其列出的文件。
- **信任色锁五槽不动**：clay 工作/绿 REAL/teal 人签专属/红真失败/amber 未核；completed 不给绿；teal 仅人签。审计零 FP 已确认无破锁建议——本批同样绝不碰。
- **诚实文案是内容不是样式**：暗色 AA 修的是**对比度（提亮 token）保留诚实文案本身**，绝不删「草案非结论」「按显示名近似」等。
- **功能零回归**：纯视觉/token/样式 + 2 处 state-logic（false-empty guard）；全 13 套既有 e2e 保持绿（选择器/行为不变）。
- **暗色改动必真验**：ink-faint AA 那条 borderline（~3.95:1 估算）——落地前真实 WCAG 计算，不盲改 token 值。
- **git 暂存显式路径**：每次 commit 只 `git add` 本 task 明列文件，绝不 `git add -A`。
- **App.vue `<style>` 是全局非 scoped**（line 270 `<style>` 无 scoped）——token 与全局工具类定义于此；各 view 的 `<style scoped>` 内类不跨组件。

## 关键既有锚点（各 task 直接消费，已 grep 核实）

- token 定义处：`App.vue` 全局 `<style>`（line 270），`:root`（278-364），`:root[data-theme="dark"]`（371+）。body font-family = `App.vue:587`。
- 字体现状：`--serif` 已定义（App.vue:316）；`--mono`/`--sans` **未定义**；`var(--mono, "SF Mono"…)` fallback 散落（StatusCenter:814/857、CompletionSeal:97、AgentPortal:667、TaskDetail:864、GuidePage:1132）全落到 "SF Mono" 字面量；两处裸字面量 `AgentPortal:582`、`GuidePage:1507`；**`--font-mono` 拼写错=`GuidePage:1535`**（`var(--font-mono, …)` 未定义）。
- 暗色 `--ink-faint`：`App.vue:387` = `#8a8174`（注释：4.5:1 on page-bg #211d19；未测 surface-raised #2e2823）。
- GuidePage 暗色阴影：`862`（`rgba(var(--ink-rgb),0.06)`）、`1417`（三层 ink-rgb + clay 环）；`.send-spin`=`1468`（`@keyframes spin` at 1474）；GuidePage 既有 reduced-motion 块：834/891/1082/1205/1498。
- token 绕过：`WelcomeGate:154`（`var(--danger,#c45656)`，--danger 未定义）；`AgentPortal:757`（`rgba(193,95,60,0.14)` promote-glow keyframe）。
- 失败态：`TaskDetail:239`（`<EmptyState v-if="feedbackList.length === 0" …>`，页有 `loadError` at line 7）；`FeedbackPage:55`（`v-if="feedbackList.length === 0"`，反馈错误变量 `feedbackError` at line 52）。
- 响应式：`AgentPortal` agent el-col `:span="8"`（≈36）+ `.portal-skel-grid`；`SchemaForm` 内联 `style="width: 180px/260px/160px/220px"`（36/45/84/91）；`TaskCreate` `label-width="100px"`（14）；`WorkbenchSession` `.sess-hero`（344）；`TaskConsole` `.console`（129）/`.console-empty`（257）/既有 media（271）。
- 浮层硬色：`QuickSwitcher`（⌘K 面板阴影/遮罩 rgba(43,38,34,…)）；`SimMonitorFloat` `.sim-frame` 硬 `#f7f4ee`。
- section-label：`.section-label` 已存于 `GuidePage:1000`（scoped）；`.gov-section-label`（AgentPortal）、`.me-section-label`（MePage）各自 scoped；FeedbackPage 承 eyebrow 角色的是裸 `<h3>`。
- 页标题容器：`.page-header`（AgentPortal:3/MePage:3/TaskDetail:25 用）；裸 `<h2>`（FeedbackPage:3、TaskCreate:3）；`.today-head`（TodayPage:7）。

---

## Task 1: Token 地基（App.vue 全局 :root）

**Files:**
- Modify: `frontend/src/App.vue`（:root 278-364 加 token；body 587 指向 --sans；`GuidePage.vue:1535` 的 --font-mono typo 归此任务顺修——见 Step 3）
- Modify: `frontend/src/views/AgentPortal.vue:582`、`frontend/src/views/GuidePage.vue:1507,1535`（裸/拼错 mono → var(--mono)）

**Interfaces:**
- Produces（后续任务消费）：`--sans`/`--mono`（字体，`--serif` 已有）· `--fs-title`(26px)/`--fs-h3`(16px)/`--fs-body`(13.5px)/`--fs-sm`(12.5px)/`--fs-xs`(11.5px)/`--fs-2xs`(10px)（字号阶）· `--radius-sm`(6)/`--radius-md`(8)/`--radius-lg`(12)/`--radius-xl`(16)/`--radius-pill`(999)（radius 阶）。

- [ ] **Step 1: 定义 token 地基**

在 `frontend/src/App.vue` 的 `:root { … }`（278 起）内，`--serif`（316）之后加：

```css
  /* 批D token 地基：字体三元组（--serif 已有）+ 字号阶 + radius 阶 */
  --sans: "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
  --mono: "SF Mono", ui-monospace, Menlo, "Cascadia Code", monospace;
  --fs-title: 26px;   /* 页标题（收口散落 20/22/25/27 四档） */
  --fs-h3: 16px;      /* 版块标题 */
  --fs-body: 13.5px;  /* 正文 */
  --fs-sm: 12.5px;    /* 次要 */
  --fs-xs: 11.5px;    /* faint/caption */
  --fs-2xs: 10px;     /* eyebrow/微标 */
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;  /* 卡片主 */
  --radius-xl: 16px;
  --radius-pill: 999px;
```

> 字体/字号/radius 值不随主题变，**无需**在 `:root[data-theme="dark"]` 加对应项。

- [ ] **Step 2: body font-family 指向 --sans**

把 `App.vue:587` 的
```css
  font-family: "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
```
改为
```css
  font-family: var(--sans);
```

- [ ] **Step 3: 修 mono 裸字面量 + --font-mono 拼写错**

三处改成引用 `var(--mono)`（其余 `var(--mono, "SF Mono"…)` fallback 处**不必动**——`--mono` 定义后 fallback 自然不触发；本批不做全量清 fallback，那属 DEFER 的 dead-fallback 清理）：
- `AgentPortal.vue:582`：`font-family: "SF Mono", ui-monospace, monospace;` → `font-family: var(--mono);`
- `GuidePage.vue:1507`：`font-family: "SF Mono", ui-monospace, monospace;` → `font-family: var(--mono);`
- `GuidePage.vue:1535`（拼写错）：`font-family: var(--font-mono, ui-monospace, monospace);` → `font-family: var(--mono);`

- [ ] **Step 4: 构建 + token 定义断言**

Run:
```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os/frontend && npm run build 2>&1 | tail -3
cd /Users/Zhuanz/projects/aircraft-comac/flai-os && grep -c -- "--fs-title\|--mono\|--radius-lg\|--sans" frontend/src/App.vue
grep -rn "font-mono\|font-family: \"SF Mono\"" frontend/src/ || echo "无裸 mono / font-mono 残留 ✓"
```
Expected: build 成功；grep 计数 ≥4；无 `font-mono`/裸 `"SF Mono"` 残留。

- [ ] **Step 5: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add frontend/src/App.vue frontend/src/views/AgentPortal.vue frontend/src/views/GuidePage.vue
git commit -m "feat(batch-d): token 地基（字体三元组--sans/--mono+字号阶--fs-*+radius阶--radius-*,修--font-mono拼写错）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: P0 响应式（手机端无溢出）

**Files:**
- Modify: `frontend/src/views/AgentPortal.vue`（el-col :span + .portal-skel-grid）
- Modify: `frontend/src/components/SchemaForm.vue`（内联固定 px）
- Modify: `frontend/src/views/TaskCreate.vue`（label-width）
- Modify: `frontend/src/views/WorkbenchSession.vue`（.sess-hero）
- Modify: `frontend/src/views/TaskConsole.vue`（.console 三栏）

**Interfaces:** Consumes: 无（独立）。Produces: 供 Task 8 的「375px 无溢出」oracle。

- [ ] **Step 1: AgentPortal 卡栅格响应**

`AgentPortal.vue` 的 agent 卡 `el-col`（≈36 行 `<el-col v-for="agent in agents" :key="agent.id" :span="8" class="agent-col">`）改：
```html
      <el-col v-for="agent in agents" :key="agent.id" :xs="24" :sm="12" :md="8" class="agent-col">
```
`.portal-skel-grid`（现 `grid-template-columns: repeat(3, 1fr)`）改：
```css
.portal-skel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}
```

- [ ] **Step 2: SchemaForm 固定宽度 → 流式**

`SchemaForm.vue` 的四处内联 `style="width: 180px/260px/160px/220px"`（36/45/84/91）改为不写死、由 CSS 控。最省改法：把 `style="width: Npx"` 换成一个 class（如 `class="sf-control"`），并在 `<style scoped>` 加：
```css
.sf-control { width: 100%; max-width: 260px; }
```
（四处内联样式统一移除，元素加 `class="sf-control"`；若元素已有 class 则追加。）

- [ ] **Step 3: TaskCreate 窄屏标签置顶**

`TaskCreate.vue:14` 的 `<el-form label-width="100px" …>`：加窄屏响应——最省是给 el-form 绑一个基于视口的 `label-position`。在 `<script setup>` 加：
```javascript
import { ref, onMounted, onUnmounted } from "vue";
const narrow = ref(false);
function onResize() { narrow.value = window.innerWidth < 640; }
onMounted(() => { onResize(); window.addEventListener("resize", onResize); });
onUnmounted(() => window.removeEventListener("resize", onResize));
```
（若这些 import/钩子已存在则合并，勿重复声明。）模板改：
```html
    <el-form :label-width="narrow ? '0' : '100px'" :label-position="narrow ? 'top' : 'right'" class="create-form fx-rise">
```

- [ ] **Step 4: WorkbenchSession .sess-hero 窄屏纵向**

`WorkbenchSession.vue` 的 `.sess-hero`（344）在 `<style scoped>` 末尾加窄屏规则：
```css
@media (max-width: 640px) {
  .sess-hero { flex-direction: column; align-items: flex-start; gap: 10px; }
}
```

- [ ] **Step 5: TaskConsole 三栏窄屏单列**

`TaskConsole.vue` 的 `.console`（129）在 `<style scoped>` 加窄屏规则（<900px 单列，空态得全宽）：
```css
@media (max-width: 900px) {
  .console { flex-direction: column; }
}
```
（若 `.console` 用 grid 而非 flex，改为 `grid-template-columns: 1fr;`——implementer 读 129 行确认 display 类型后择一。）

- [ ] **Step 6: 构建验证**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os/frontend && npm run build 2>&1 | tail -3`
Expected: 构建成功。（无溢出的机器 oracle 在 Task 8 e2e。）

- [ ] **Step 7: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add frontend/src/views/AgentPortal.vue frontend/src/components/SchemaForm.vue frontend/src/views/TaskCreate.vue frontend/src/views/WorkbenchSession.vue frontend/src/views/TaskConsole.vue
git commit -m "fix(batch-d): P0 手机端响应式（AgentPortal栅格:xs/:sm/:md+SchemaForm流式+TaskCreate标签置顶+WorkbenchSession/TaskConsole窄屏单列）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 暗色可读性

**Files:**
- Modify: `frontend/src/views/GuidePage.vue`（862、1417 ink-rgb 阴影）
- Modify: `frontend/src/App.vue`（暗色 --ink-faint:387，**仅在 WCAG 复检不达标时**）
- Modify: `frontend/src/components/QuickSwitcher.vue`、`frontend/src/components/SimMonitorFloat.vue`（硬色）

**Interfaces:** Consumes: 无。Produces: 供 Task 8 的暗色对比/阴影分量 oracle。

- [ ] **Step 1: GuidePage 阴影黑基化**

`GuidePage.vue:862`（user bubble）：
```css
  box-shadow: 0 1px 2px rgba(var(--ink-rgb), 0.06);
```
→ 用黑基 token（复用 --shadow-card）：
```css
  box-shadow: var(--shadow-card);
```
`GuidePage.vue:1417`（composer focus-within）：
```css
  box-shadow: 0 2px 6px rgba(var(--ink-rgb), 0.06), 0 16px 40px rgba(var(--ink-rgb), 0.13), 0 0 0 4px rgba(var(--clay-rgb), 0.08);
```
→ 黑基阴影 + 保留 clay 聚焦环：
```css
  box-shadow: var(--shadow-composer), 0 0 0 4px rgba(var(--clay-rgb), 0.08);
```

- [ ] **Step 2: 暗色 ink-faint AA — 先真实 WCAG 复检**

Run（页内 WCAG 计算，判断暗色 `--ink-faint` #8a8174 on `--surface-raised` #2e2823 是否 ≥4.5:1）：
```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os && python3 -c "
def lin(c):
    c/=255
    return c/12.92 if c<=0.03928 else ((c+0.055)/1.055)**2.4
def L(hexs):
    r,g,b=int(hexs[0:2],16),int(hexs[2:4],16),int(hexs[4:6],16)
    return 0.2126*lin(r)+0.7152*lin(g)+0.0722*lin(b)
def ratio(a,b):
    la,lb=L(a),L(b); hi,lo=max(la,lb),min(la,lb); return (hi+0.05)/(lo+0.05)
for surf,name in [('211d19','page-bg'),('2e2823','surface-raised'),('2a2521','card-bg')]:
    print(f'ink-faint #8a8174 on {name} #{surf}: {ratio(\"8a8174\",surf):.2f}:1')
"
```
Expected: 打印三个对比值。**判据**：若 on surface-raised < 4.5 → 执行 Step 3 提亮；若 ≥4.5 → **跳过 Step 3**（审计估算偏保守，诚实不改），在报告里记「WCAG 复检达标，未改」。

- [ ] **Step 3: （条件）提亮暗色 ink-faint**

**仅当 Step 2 判定 < 4.5** 时执行。把 `App.vue:387` 暗色 `--ink-faint: #8a8174;` 提亮到刚过 4.5:1 on surface-raised 的值（用 Step 2 脚本迭代验证候选，如 `#948a7c`/`#9a9082`——选**最小**满足 ≥4.5 的提亮值，避免过亮失去「faint」层级），并更新其行内注释注明 on surface-raised 的实测比值。

- [ ] **Step 4: QuickSwitcher / SimMonitorFloat 硬色 → token**

`QuickSwitcher.vue`：⌘K 面板的硬 `rgba(43,38,34,…)` box-shadow → `var(--shadow-hero)`；遮罩 scrim（硬 rgba）→ `var(--el-mask-color)`。（implementer grep `rgba(43` 与 `overlay`/`mask`/`scrim` 定位。）
`SimMonitorFloat.vue`：`.sim-frame` 的硬 `background: #f7f4ee;` → `background: var(--paper-rail);`（暗色已定义，消装载闪白）。若该 hub 视图刻意常亮，则**改为**订正误导注释而非换色——implementer 读该处注释判断意图；默认按换 token 处理。

- [ ] **Step 5: 构建 + 暗色阴影断言**

Run:
```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os/frontend && npm run build 2>&1 | tail -3
cd /Users/Zhuanz/projects/aircraft-comac/flai-os && grep -n "rgba(var(--ink-rgb)" frontend/src/views/GuidePage.vue || echo "GuidePage ink-rgb 阴影已清 ✓"
```
Expected: build 成功；GuidePage 无 `rgba(var(--ink-rgb)` box-shadow 残留（正文其它 ink-rgb 用途如 tint 不在本 grep 的 box-shadow 语境——implementer 确认清的是两处 box-shadow 而非误伤 tint）。

- [ ] **Step 6: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add frontend/src/views/GuidePage.vue frontend/src/components/QuickSwitcher.vue frontend/src/components/SimMonitorFloat.vue frontend/src/App.vue
git commit -m "fix(batch-d): 暗色可读性（GuidePage阴影黑基化消白光晕+ink-faint AA复检+QuickSwitcher/SimMonitorFloat硬色→token）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Token 绕过消除

**Files:**
- Modify: `frontend/src/components/WelcomeGate.vue:154`
- Modify: `frontend/src/views/AgentPortal.vue:757`

**Interfaces:** Consumes: `--trust-fail`（已定义）、`--clay-rgb`（已定义）。Produces: 供 Task 8 的 `color===--trust-fail` oracle。

- [ ] **Step 1: WelcomeGate 未定义 --danger → --trust-fail**

`WelcomeGate.vue:154`：
```css
  color: var(--danger, #c45656);
```
→
```css
  color: var(--trust-fail);
```

- [ ] **Step 2: AgentPortal promote-glow clay 字面量 → token**

`AgentPortal.vue:757`（promote-glow keyframe，批C 曾去坏 var-fallback 留下字面量）：
```css
  0% { background: rgba(193, 95, 60, 0.14); }
```
→
```css
  0% { background: rgba(var(--clay-rgb), 0.14); }
```

- [ ] **Step 3: 构建 + 断言无 --danger 残留**

Run:
```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os/frontend && npm run build 2>&1 | tail -3
cd /Users/Zhuanz/projects/aircraft-comac/flai-os && grep -rn "var(--danger\|rgba(193, 95, 60" frontend/src/ || echo "无 --danger / clay 字面量残留 ✓"
```
Expected: build 成功；无 `var(--danger` / `rgba(193, 95, 60` 残留。

- [ ] **Step 4: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add frontend/src/components/WelcomeGate.vue frontend/src/views/AgentPortal.vue
git commit -m "fix(batch-d): 消 token 绕过（WelcomeGate未定义--danger→--trust-fail第一屏恒硬编码红/AgentPortal clay字面量→rgba(var(--clay-rgb)))

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: 标题 + section-label 归一

**Files:**
- Modify: `frontend/src/App.vue`（全局 `<style>` 加 canonical `.section-label`）
- Modify: `frontend/src/views/{AgentPortal,MePage,TaskDetail,TodayPage,FeedbackPage,TaskCreate}.vue`（页标题字号 + eyebrow）

**Interfaces:** Consumes: Task 1 的 `--fs-title`/`--fs-2xs`。Produces: 供 Task 8 的「9 view 页标题 font-size 全等」oracle；全局 `.section-label` 类。

- [ ] **Step 1: 全局 canonical .section-label**

在 `App.vue` 全局 `<style>`（非 scoped，line 270 块）内加：
```css
/* 批D：统一 eyebrow 小标题（收口 7 种散写）；语义色由使用处覆盖（waiting=trust-pending/working=clay） */
.section-label {
  font-size: var(--fs-2xs);
  font-weight: 700;
  letter-spacing: 0.6px;
  color: var(--ink-faint);
  margin-bottom: 8px;
}
```

- [ ] **Step 2: 页标题字号统一**

给各 view 的**页标题** h2 统一 `--fs-title` + weight 600 + letter-spacing 0.2px。逐文件（读现有页标题 CSS，改字号/字重/间距三值对齐，不动布局容器结构，除 Step 3 两处）：
- `AgentPortal.vue` `.page-header h2`、`MePage.vue` `.page-header h2`、`TaskDetail.vue` `.page-header h2`、`TodayPage.vue` `.today-head` 的标题：`font-size: var(--fs-title); font-weight: 600; letter-spacing: 0.2px;`
- 若某处已是这些值则不动（幂等）。MePage 此前掉了 letter-spacing——补上。

- [ ] **Step 3: FeedbackPage / TaskCreate 裸 h2 采共享结构**

`FeedbackPage.vue:3` 与 `TaskCreate.vue:3` 的裸 `<h2>提交反馈</h2>`/`<h2>创建任务</h2>`：包进 `.page-header` div（与 AgentPortal/MePage 一致），并确保其 h2 命中 Step 2 的页标题样式。若这两个 view 无 `.page-header` scoped 样式，加最小：
```css
.page-header { margin-bottom: 20px; }
.page-header h2 { font-family: var(--serif); font-size: var(--fs-title); font-weight: 600; letter-spacing: 0.2px; margin: 0; }
```
（FeedbackPage 若原 h2 无 .page-header 包裹，模板改 `<div class="page-header"><h2>提交反馈</h2></div>`；TaskCreate 同。）

- [ ] **Step 4: eyebrow 收口到 .section-label**

把命名的 per-view eyebrow 类迁到全局 `.section-label`：
- `AgentPortal.vue` 的 `.gov-section-label`、`MePage.vue` 的 `.me-section-label`、`GuidePage.vue` 的 scoped `.section-label`（1000）：**保留刻意的语义色覆盖**（若某处 color 是 trust-pending/clay 则留），其余 size/weight/letter-spacing/margin 删掉让全局 `.section-label` 接管——即模板元素加 `class="section-label"`（若已叫 section-label 则天然命中全局，删 scoped 定义即可），named 变体元素改 `class="section-label"` 或追加。
- `FeedbackPage.vue:54` 承 eyebrow 角色的裸 `<h3>该任务已有反馈</h3>`：改为 `<div class="section-label">该任务已有反馈</div>`（去裸 h3）。

> 保守边界：**仅迁 named `*-section-label` + GuidePage scoped .section-label + FeedbackPage h3**；不追猎每一个视觉像 eyebrow 的元素（防 sprawl）。改 class 后确认不破 e2e 选择器（下步 build + Task 8 全量 e2e）。

- [ ] **Step 5: 构建 + e2e 冒烟（防选择器回归）**

Run:
```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os/frontend && npm run build 2>&1 | tail -3
```
Expected: build 成功。（页标题 font-size 全等 + e2e 零回归由 Task 8 全量 verify_all 把关。）

- [ ] **Step 6: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add frontend/src/App.vue frontend/src/views/AgentPortal.vue frontend/src/views/MePage.vue frontend/src/views/TaskDetail.vue frontend/src/views/TodayPage.vue frontend/src/views/FeedbackPage.vue frontend/src/views/TaskCreate.vue frontend/src/views/GuidePage.vue
git commit -m "refactor(batch-d): 标题+section-label归一（--fs-title单值+全局.section-label收口eyebrow七写法+裸h2/h3采共享结构）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: reduced-motion 补齐（.send-spin）

**Files:**
- Modify: `frontend/src/views/GuidePage.vue`（.send-spin 1468 + reduced-motion 块）

**Interfaces:** Consumes: 无。Produces: 供 Task 8 的「reduced-motion 下 .send-spin animation-name===none」oracle。

- [ ] **Step 1: 在既有 reduced-motion 块加 .send-spin 降级**

`GuidePage.vue` 的 `.send-spin`（1468，`animation: spin …` 旋转）。在 GuidePage 里**最靠近 .send-spin 的既有** `@media (prefers-reduced-motion: reduce)` 块（1498 那个覆盖 send 区域的）内加：
```css
  .send-spin { animation: none; }
```
（保留静态环作发送指示——.send-spin 的非动画样式如 border/size 不动，只停旋转。）

- [ ] **Step 2: 构建 + 断言**

Run:
```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os/frontend && npm run build 2>&1 | tail -3
cd /Users/Zhuanz/projects/aircraft-comac/flai-os && awk '/@media \(prefers-reduced-motion: reduce\)/,/^}/' frontend/src/views/GuidePage.vue | grep -q "send-spin" && echo "send-spin reduced-motion 降级已加 ✓"
```
Expected: build 成功；断言打印 ✓。

- [ ] **Step 3: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add frontend/src/views/GuidePage.vue
git commit -m "fix(batch-d): .send-spin 补 reduced-motion 降级（全站唯一漏降级旋转动效,MOTION-SYSTEM硬约束④）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: 失败态不伪装空态

**Files:**
- Modify: `frontend/src/views/TaskDetail.vue:239`
- Modify: `frontend/src/views/FeedbackPage.vue:55`

**Interfaces:** Consumes: 无。Produces: 供 Task 8 的「失败态互斥」oracle。

- [ ] **Step 1: TaskDetail 反馈空态加 error 门**

`TaskDetail.vue:239`：先读 TaskDetail 里反馈加载的错误变量名（页级 `loadError` at line 7，但反馈可能有独立错误——implementer 确认反馈 catch 分支置的是哪个 ref）。设其为 `<ERR>`，改：
```html
        <EmptyState v-if="feedbackList.length === 0" description="暂无反馈" :image-size="84" />
```
→
```html
        <EmptyState v-if="feedbackList.length === 0 && !<ERR>" description="暂无反馈" :image-size="84" />
```
（`<ERR>` = TaskDetail 实际的反馈错误 ref；若反馈与任务共用 loadError 则用 loadError。）

- [ ] **Step 2: FeedbackPage 空态加 error 门**

`FeedbackPage.vue:55`（错误变量确认为 `feedbackError`，line 52）：
```html
      <EmptyState v-if="feedbackList.length === 0" description="暂无反馈" />
```
→
```html
      <EmptyState v-if="feedbackList.length === 0 && !feedbackError" description="暂无反馈" />
```

- [ ] **Step 3: 构建验证**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os/frontend && npm run build 2>&1 | tail -3`
Expected: 构建成功。（失败态互斥的机器断言在 Task 8 e2e。）

- [ ] **Step 4: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add frontend/src/views/TaskDetail.vue frontend/src/views/FeedbackPage.vue
git commit -m "fix(batch-d): 失败态不伪装空态（TaskDetail/FeedbackPage v-if加!error门,踩批B/C诚实红线)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: e2e batch_d_visual_acceptance + verify_all 注册

**Files:**
- Create: `frontend/e2e/batch_d_visual_acceptance.py`
- Modify: `scripts/verify_all.sh`、`scripts/verify_all.ps1`（E2E_SCRIPTS / $E2EScripts 数组注册）

**Interfaces:** Consumes: `_auth` 登录样板 + batch_b/c 自起后端骨架 + Task 1-7 的视觉不变量。Produces: verify_all 内一条新步骤。

- [ ] **Step 1: 写 e2e（照 batch_c 骨架，机器 oracle 兜主观）**

创建 `frontend/e2e/batch_d_visual_acceptance.py`，自起后端骨架**照抄 `batch_c_rewards_acceptance.py`**（tmp WORK、create_app、uvicorn 线程、健康探测、`_auth` 登录、keep-alive `page.evaluate("1")`、SHOTS 目录）。断言体覆盖 7 个机器 oracle：

```python
# —— 机器可检 oracle（spec §八）——
# ① token 定义：root 的 --sans/--mono/--fs-title/--radius-lg 均非空
vals = page.evaluate("""() => {
  const s = getComputedStyle(document.documentElement);
  return ['--sans','--mono','--fs-title','--radius-lg'].map(k => s.getPropertyValue(k).trim());
}""")
check("① token 地基已定义", all(v for v in vals), str(vals))

# ② token 绕过消除：WelcomeGate 未登录错误文本 color===--trust-fail（触发一次登录失败）
#    —— 若难触发错误文本，退化为 grep 断言（见 Step 后注）
grep_danger = subprocess.run(["grep","-rn","var(--danger","frontend/src/"], cwd=REPO, capture_output=True, text=True)
check("② 无 var(--danger 残留", grep_danger.returncode != 0, grep_danger.stdout[:200])

# ③ 375px 无横向溢出：affected 页逐个
for path in ["/portal", "/tasks/new", "/feedback"]:
    page.set_viewport_size({"width": 375, "height": 800})
    page.goto(f"{base}{path}"); page.wait_for_load_state("networkidle")
    poke_wait(page, 1)
    ov = page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    check(f"③ 375px 无横向溢出 {path}", ov, "scrollWidth>clientWidth" )
page.set_viewport_size({"width": 1440, "height": 900})

# ④ 暗色 ink-faint WCAG≥4.5 on surface-raised（页内计算，切暗色主题）
page.evaluate("() => document.documentElement.setAttribute('data-theme','dark')")
wcag = page.evaluate("""() => {
  const s = getComputedStyle(document.documentElement);
  const hexOf = v => v.trim();
  function toRGB(str){ const m=str.match(/\\d+/g).map(Number); return m; }
  const faint = toRGB(s.getPropertyValue('--ink-faint'));
  const surf = toRGB(s.getPropertyValue('--surface-raised'));
  const lin=c=>{c/=255;return c<=0.03928?c/12.92:Math.pow((c+0.055)/1.055,2.4);};
  const L=([r,g,b])=>0.2126*lin(r)+0.7152*lin(g)+0.0722*lin(b);
  const la=L(faint),lb=L(surf),hi=Math.max(la,lb),lo=Math.min(la,lb);
  return (hi+0.05)/(lo+0.05);
}""")
check("④ 暗色 ink-faint on surface-raised WCAG≥4.5", wcag >= 4.5, f"ratio={wcag:.2f}")

# ⑤ reduced-motion 下 .send-spin animation:none（emulate reduced-motion 新 context）
# —— 见下：用 context = browser.new_context(reduced_motion="reduce") 打开 / 再查
# ⑥ 9 view 页标题 font-size 全等（逐页取 .page-header h2 / 页标题 computed）
# ⑦ 失败态互斥：mock 反馈加载失败 → error alert 在屏 + EmptyState 不在屏
#    （FeedbackPage：选任务后令反馈请求 500，断言 .el-alert 在屏且无 EmptyState）
```

> 说明：computed 色比对 `--trust-fail` 依赖能渲染出 WelcomeGate 错误文本；难稳定触发时，② 用 grep 断言（已给）即足够——「无 var(--danger 残留」直接证 token 绕过消除。⑤ reduced-motion 用 `browser.new_context(reduced_motion="reduce")` 打开 GuidePage 后 `getComputedStyle(sendSpinEl).animationName === 'none'`。⑥ 逐个 goto 9 个 view 取页标题 computed font-size，断言集合 size==1。⑦ 用 `page.route` 拦截 `**/api/**feedback**` 返 500 后再进 FeedbackPage 选任务。截图落 `docs/reviews/batch-d-shots/`：亮/暗 × 桌面/375px 各 affected 页。implementer 按 batch_c 的 `check(...)`/`poke_wait(...)`/honest-exit 样板落地这些断言。

- [ ] **Step 2: 构建前端 + 跑 e2e（真退出码）**

Run:
```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os/frontend && npm run build > /tmp/bd_build.log 2>&1; echo "build=$?"
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
uv run --no-project --with playwright --with uvicorn --with fastapi \
  --with jsonschema --with pyyaml --with httpx --with python-multipart \
  --with "pydantic>2" --with jieba python frontend/e2e/batch_d_visual_acceptance.py > /tmp/bd_e2e.log 2>&1; echo "exit=$?"
tail -40 /tmp/bd_e2e.log
```
Expected: `build=0`、`exit=0`，全部 oracle green + 截图落 `docs/reviews/batch-d-shots/`。

- [ ] **Step 3: 注册进 verify_all（.sh + .ps1 双门）**

`scripts/verify_all.sh` 的 `E2E_SCRIPTS=(` 数组，`batch_c_rewards_acceptance.py` 之后加：
```bash
  "frontend/e2e/batch_d_visual_acceptance.py"
```
`scripts/verify_all.ps1` 的 `$E2EScripts = @(` 数组，末元素补逗号后加（.ps1 现缺 m9-m11/cfd/batch_a-c 是 pre-existing drift，本任务只加 batch_d，drift 入 retro）：
```powershell
    "frontend/e2e/batch_d_visual_acceptance.py"
```

- [ ] **Step 4: 全量 verify_all 真跑**

Run:
```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
bash scripts/verify_all.sh > /tmp/verify_all_d.log 2>&1; echo "exit=$?"
tail -25 /tmp/verify_all_d.log
```
Expected: `exit=0`，全部后端 + 全部 e2e（含新 batch_d）绿，`[失败]（无）`。m10 若偶发 flake（retro 已知）单独复跑确认非本批回归。

- [ ] **Step 5: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add frontend/e2e/batch_d_visual_acceptance.py scripts/verify_all.sh scripts/verify_all.ps1 docs/reviews/batch-d-shots/
git commit -m "test(batch-d): e2e 视觉验收（token定义/375无溢出/无--danger/暗色WCAG≥4.5/reduced-motion/标题字号全等/失败态互斥）入verify_all双门

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: 收口——Codex 治理审 + 并行对抗视觉复审

**Files:** 无代码（审查与修复轮）。

**说明**：命中「系统性样式改动 + 暗色 AA + MOTION-SYSTEM 硬约束合规」→ 治理审同步阻塞。视觉批额外加**并行对抗视觉复审**（主控编排 Workflow：多 agent 各审一维——信任色锁未破/暗色真达标/token 无绕过残留/e2e oracle 非 vacuous）。

- [ ] **Step 1: Codex 治理审（86gs gpt-5.6-sol ultra）**

Run:
```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
codex-review-relay --base main
```
重点盯：信任色锁是否被某处 token 迁移误破（completed 上绿/teal 扩用）· 暗色 AA 是否真达标（非估算）· token 绕过是否清干净 · 页标题/section-label 迁移有无破 e2e 选择器 · 改动面是否越界扫荡（超出审计点名文件=范围膨胀）。

- [ ] **Step 2: 逐条 grounded 复核 + 修复**

每条 finding 先 grounded 复核（审查方也会 over-claim）→ 确认为真 → 新 commit 修复再审。round cap=3。verbatim 例外落地 Codex Suggested fix，commit 标 confidence。

- [ ] **Step 3: 并行对抗视觉复审 + 收口**

主控编排一个只读 Workflow（多 agent 各审一维 + 综合），或抽检 batch-d-shots 亮暗×桌面/375 截图人审。全绿 + Codex APPROVE 后交 owner 裁合并（feedback_review_pass_auto_merge_push：过审即自主合并 push，多批次工程台合并前向 owner 报一句收尾）。

---

## Self-Review

**1. Spec coverage**（逐簇对照 spec §一-§七）：
- §一 token 地基 → Task 1 ✅（字体三元组/字号阶/radius 阶/--font-mono 修）
- §二 P0 响应式 → Task 2 ✅（AgentPortal/SchemaForm/TaskCreate/WorkbenchSession/TaskConsole）
- §三 暗色可读性三簇 → Task 3 ✅（ink-rgb 阴影/ink-faint AA 真验/QuickSwitcher+SimMonitorFloat）
- §四 token 绕过 → Task 4 ✅（WelcomeGate --danger/AgentPortal clay 字面量）
- §五 标题+section-label 归一 → Task 5 ✅（--fs-title + 全局 .section-label + 裸 h2/h3）
- §六 reduced-motion → Task 6 ✅（.send-spin）
- §七 失败态不伪装空态 → Task 7 ✅（TaskDetail/FeedbackPage）
- §八 验证（机器 oracle + 截图 + 双门注册）→ Task 8 ✅；§八 审查 → Task 9 ✅
- DEFER 清单 → 未建 task（spec §九 明列进 retro）✅

**2. Placeholder scan**：无 TBD；每步给完整代码/anchor 行号；Task 3 Step 2 的 WCAG 复检是可跑脚本（条件分支明确）；Task 5/7 中 `<ERR>`/eyebrow 迁移标注了「implementer 确认实际变量/类名」——这是真实的按现状确认点，非占位（给了确认方法）。

**3. Type/命名一致性**：`--fs-title`/`--fs-2xs`/`--mono`/`--sans`/`--radius-lg` 跨 Task 1（定义）/5（消费）/8（断言）一致；`.section-label` 全局类在 Task 5 定义、Task 8 不直接断言（页标题字号断言即可）；信任色锁术语一致。

**已知残差（诚实标注）**：Task 3 ink-faint 提亮是条件性（WCAG 复检 <4.5 才改）；Task 5 eyebrow 迁移保守边界（只迁 named 变体，不追猎）；.ps1 pre-existing drift 只补 batch_d（其余 retro）。

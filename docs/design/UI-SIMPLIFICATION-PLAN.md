# 「对话即家」UI 简化 实现计划（UI-PARADIGM Phase 3）

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:subagent-driven-development 或
> superpowers:executing-plans 逐任务实现。步骤用 `- [ ]` 复选框跟踪。
> 设计 SSOT：`docs/design/UI-SIMPLIFICATION-CONVERSATION-HOME.md`。

**Goal:** 把 FLAi-OS 前端削到克制——对话主轴方案卡去装饰性重量、任务台并入状态中心抽屉、
任务详情速览优先——同一时刻只让用户看见此刻要做的那件事。

**Architecture:** 纯前端密度 + IA 层，零后端契约/依赖变更。四批小步可逆，每批 e2e 契约与实现
原子同批，`verify_all.sh` 八步门全绿。基于 Vue3 + Element Plus，改动集中在
`frontend/src/views/GuidePage.vue`、`App.vue`、`components/StatusCenter.vue`、`views/TaskConsole.vue`。

**Tech Stack:** Vue3 SFC · Element Plus · Playwright e2e（`frontend/e2e/*.py`）· `scripts/verify_all.sh`。

## Global Constraints（每个任务隐含继承）

- **验证 = 回归保护，不是 TDD 造新**：本工作是「减法不破坏既有真值」。每批的「测试」= 既有 e2e 套件
  （Playwright `inner_text()` **只见可见文本**——`v-show`/`display:none` 内容不计入 body 断言）+
  视觉密度对照。绝不为凑绿改断言语义；断言随设计变时**与实现原子同批**且重截图留证。
- **可见文本红线（`inner_text` 必含，故绝不可藏进折叠）**：`协作方案` · 每 Agent 的 `分工`(role) ·
  预填 **键+值**(`top_event`/`供电完全丧失`) · `已剔除不合法字段`+字段名(`bogus`) · dropped 名(`ghost_agent`) ·
  诚实地板 `签发权`+`亲手提交` · refuse 卡 `平台暂时接不住`/reason/residual/reframe。**这些是诚实地板
  （设计 §六焊死），减法只去装饰重量、绝不隐藏这些事实。**
- **e2e 选择器红线（保留 class 名与语义，减重在其内部）**：`.plan-card` · `.agent-status`(+`排队中`) ·
  `.status-artifact`(+`N 件产物`) · `.bubble-row.user` · `.hero-title` · `.composer textarea` ·
  按钮可及名 `去创建此任务` / `进入协作工作台`。
- **信任色锁**：clay 工作 / amber 待签 / teal 人签 / 绿 仅真实 / 中性 完成——五槽不增不改；注意力信号
  用形状+字重零新色。
- **人是唯一发起者**：意图卡/Agent 选择器/reframe 只填草稿绝不代发；签发只走人具名 `POST /tasks/{id}/review`。
- **路由全保留**（祈使句 5，批 2）：`/tasks`·`/tasks/:id`·`/workbench/*` 可刷新/分享/回退。
- **分支**：`feat/ui-simplify-conversation-home`。commit 尾 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。
  只 `git add` 本次亲改文件（**绝不 `-A`**；`uv.lock`/`CFDB-TOOL-ADAPTER-BOUNDARY.md`/未署名 PNG 非我文件不碰）。
- 每 commit 前 key/EAR scan：`git diff --cached` 过滤 EAR 红线词（清单见 `~/CLAUDE.md`/memory，本文不复述）+ `sk-`/`api_key`/`secret` 应空。

## 设计修正（规划期发现，须 owner 确认后执行）

摸图「after」把 预填值/剔除项 藏进「展开」——与上「可见文本红线」+ 设计 §六诚实地板**冲突**
（Playwright `inner_text` 见不到折叠内容，且这些是焊死的诚实事实）。**修正**：Batch 1 = **去装饰
性重量（accent 条/step 圆/分类 pill/maturity 徽章/JSON `<pre>` 块/重复 CTA/冗余 section label）+
版式放松，同时所有诚实事实保持可见**（预填改紧凑 `键: 值` 行、剔除/dropped 收成安静单行但可见）。
这是「同信息、更轻」，非「隐藏信息」。视觉更克制的同时诚实地板不破。**per-Agent「去创建此任务」
按钮保留**（m6 e2e 点它 + 它是人发起创建的核心动作，非装饰）。

---

## Batch 1 — 方案卡去装饰重量（低风险 · 纯 GuidePage · 保诚实地板与全 e2e 锚）

**Files:**
- Modify: `frontend/src/views/GuidePage.vue`（template plan-card 块 :99-231 + 相关 CSS :975-1370）
- Test（回归，不改语义）：`frontend/e2e/m6_guide_acceptance.py` · `m8_guide_orchestrator_acceptance.py` · `m9_guide_loop_acceptance.py`

**Interfaces:**
- Consumes：既有 script 函数不变签名——`agentTaskInfo(a)` · `openTaskPeek(id)` · `createOneTask(a,reco)` ·
  `openWorkbench()` · `focusComposer()` · `statusLabel/taskLampColor/isWorkState` · `inputCount/prettyInputs` ·
  `isDraftOpen/toggleDraft/draftKey`。
- Produces：更轻的 plan-card 视觉；后续批不依赖本批产出新符号（纯视觉层）。

- [ ] **Step 1：确认绿基线 + 记录密度基线**

Run:
```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os && bash scripts/verify_all.sh 2>&1 | tail -30
```
Expected：exit 0，8 步全绿（含 m6/m8_guide_orchestrator/m9）。若非绿，**先停**——基线不绿不动手（无法区分「减法引入的回归」与「本就红」）。
记录当前 plan-card 控件数（accent/step/pill/maturity/JSON-pre/双 CTA…）作 before 对照，截 `docs/reviews/ui-simplify-shots/b1_before.png`（手动或复用 m6 `2_recommendation.png`）。

- [ ] **Step 2：去 Agent 卡装饰件（accent 条 / step 圆 / 分类 pill / maturity 徽章）**

改 `GuidePage.vue` template agent-card 块（:117-202）：删除 `.agent-accent`(:124)、`.agent-step`(:127)、
`.agent-pill`(:129-132)、`.agent-maturity`(:133) 四个纯装饰 span；`.agent-name`(:128) 保留。
`.agent-status`(:138-159 督战块，含 status-lamp/status-word/peek/is-review) **整块不动**（imperative 1 + m9 锚）。
`.status-artifact`(:164-175) **整块不动**（m9 锚）。`a.rationale`(:177) 保留为安静一行，`a.role`(:178 `分工`) **保留可见**（m6/m8 锚）。
同步删对应 CSS：`.agent-accent`/`.agent-step`/`.agent-pill`/`.agent-maturity`（若定义在 :1120-1200 区，grep 定位精确行删）。

- [ ] **Step 3：验证 m6/m8_orchestrator 仍绿（role/名/督战仍可见）**

Run:
```bash
cd frontend && python -m pytest e2e/m6_guide_acceptance.py e2e/m8_guide_orchestrator_acceptance.py -x -q 2>&1 | tail -20
```
Expected：PASS。关键断言仍中——`故障树`/`分工`/`协作方案`/`2 个 Agent 协作`/role 文本/`ghost_agent`/`.agent-status`+`排队中` 在 body。若 `分工`/role 丢失=删过头，回退 Step 2 只删装饰 span。

- [ ] **Step 4：预填 JSON `<pre>` 块 → 紧凑可见 `键: 值` 行**

改 `.agent-draft`(:179-190)：把 `<pre class="plan-json">{{ prettyInputs(a.prefilled_inputs) }}</pre>`（默认展开的 monospace 大块）替换为紧凑内联渲染——遍历 `a.prefilled_inputs` 出 `键: 值 · 键: 值` 安静行（值仍是可见文本）。
保留 `draft-toggle` 语义可选（折叠只切「紧凑行 ↔ 原始 JSON」，**默认显示紧凑行**，值恒可见）。
代表性目标（精确 class/样式随视觉微调，但 `top_event`+`供电完全丧失` 必在可见 DOM 文本）：
```html
<div class="agent-draft" v-if="inputCount(a)">
  <div class="draft-fields">
    <span v-for="(v,k) in a.prefilled_inputs" :key="k" class="draft-field">
      <span class="df-key">{{ k }}</span><span class="df-val">{{ v }}</span>
    </span>
  </div>
</div>
```
CSS：`.draft-fields` 换行 flex，`.df-key` 弱色小字，`.df-val` 常规——去掉 monospace 大块的视觉重量。删 `.plan-json`/`.draft-toggle`/`.draft-chevron` 相关 CSS（若不再用）。

- [ ] **Step 5：验证 m6 预填值仍可见**

Run:
```bash
cd frontend && python -m pytest e2e/m6_guide_acceptance.py -x -q 2>&1 | tail -15
```
Expected：PASS，③断言 `top_event`+`供电完全丧失`+`已剔除不合法字段`+`bogus` 全在 body。若失败=紧凑行没渲染值或被折叠，修 Step 4。

- [ ] **Step 6：plan-level 冗余收敛（保诚实地板可见 + 单主 CTA）**

改 plan-card plan-level（:105-231）：
- `.plan-topline`(kicker+count)、`.plan-goal-title`、`.plan-reason`(analysis) 保留但版式放松（去多余 section label 重复）。
- `.plan-section`「分工如何衔接」workflow 段（:111-114）——**m8_orchestrator 不断言 workflow 文本**，可收成安静一行或移入 rationale 同级弱化（非红线，可减）。
- `dropped_agents` alert(:206-213) 与 `capped` alert(:214-221)：**保留可见**（`ghost_agent` 必在 body），但从 el-alert 大块换成安静单行文案（去 el-alert 的图标+边框重量）。
- `.plan-foot`(:223-230)：`进入协作工作台 →`(主 CTA 保留) + `想调整？直接告诉导引`(逃逸保留) + `.plan-note`(:226-229 `签发权`/`亲手提交` **保留可见**——诚实地板 + m6 line200 锚)。

- [ ] **Step 7：全量 e2e + 视觉 after 对照 + 密度计数**

Run:
```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os && bash scripts/verify_all.sh 2>&1 | tail -30
```
Expected：exit 0 八步全绿。截 after 图 `docs/reviews/ui-simplify-shots/b1_after.png`；记录 plan-card 控件数（目标：装饰件 -5～6，视觉重量显著下降，诚实文本 0 丢失）。before/after 并置自检：更克制？诚实事实全在？信任色锁未动？

- [ ] **Step 8：Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git diff --cached --name-only  # 先确认暂存区
git add frontend/src/views/GuidePage.vue docs/reviews/ui-simplify-shots/b1_before.png docs/reviews/ui-simplify-shots/b1_after.png
git diff --cached | grep -niE "$EAR_SCAN_PATTERN" || echo "key/EAR clean"   # EAR 词清单见 ~/CLAUDE.md，勿把红线词写进仓
git commit -m "$(printf 'feat(ui): 方案卡去装饰重量（Batch1 · 保诚实地板与全 e2e 锚）\n\n删 accent/step/分类pill/maturity 徽章 + JSON<pre>→紧凑键值行 + alert 大块→安静单行；\n督战/产物锚/预填值/剔除告警/dropped名/签发权全保持可见。verify_all 八步绿。\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Batch 2 — 任务台并入状态中心抽屉（中风险 · IA · 重立导航 e2e 契约）

> 依赖 Batch 1 落地（对话主轴清爽后再收敛入口）。此批改导航契约=祈使句级 IA 动作，动手前过
> skill `safe-refactor` 穷举全部 `.sidebar-nav`/`nav-link`/`任务台` 消费者。**step 级细化在 Batch 1
> 落地后 JIT 补**（e2e 重写方案依赖 Batch 1 后的实际 DOM + 需独立 grounding 一遍），此处锁任务边界与验收。

**Files:** `App.vue`(NAV :215-218 + activeMenu :222-228) · `components/StatusCenter.vue`(inbox 视图底部加「查看全部任务 →」深链) · e2e：`m8_workbench_acceptance.py`①②④ · `m8_collab_chain_acceptance.py`⑦ · `m6_guide_acceptance.py`(nav 注释校对)。

**任务：**
- [ ] App.vue `NAV` `["对话","任务台"]` → `["对话"]`；`activeMenu` 移除 `/tasks`→任务台 高亮分支（改「对话」为唯一高亮或按路由无 nav 高亮）。
- [ ] StatusCenter inbox 底部加「查看全部任务 →」→ `router.push('/tasks')`（治理全量总览深链可达）。
- [ ] `/tasks`·`/tasks/:id`·`/workbench/*` 路由保留验证（headless 刷新/回退实测）。
- [ ] **原子重立 e2e**：`m8_workbench`① `nav_texts==["对话"]`+重截图；②④ `.nav-link.is-active` 断言改（无任务台项后断言对话高亮或改走「状态坞可达+深链渲染」新契约）；②`/workbench→/tasks` 重定向保留；`m8_collab_chain`⑦ 侧栏断言同步；`m6` nav 注释校对。
- [ ] verify_all 八步绿 + 双 Surface→单入口走查图归档。

**验收：** 一级导航仅「对话」；三类深链全兼容；总览/待签从状态坞可达；八步门绿。

---

## Batch 3 — 任务详情速览优先（中风险 · 默认路径改道 + 整页深链态清理）

> **规划期审计结论（Batch 1-2 落地后，2026-07-12）**：**「速览优先」核心目标已满足**——
> 全部随手「看任务」入口默认走速览 `openTaskPeek`（对话 plan-card 督战点/产物锚 · StatusDock/
> StatusCenter inbox · WorkbenchSession chips）；每个 `router.push('/tasks/:id')` 整页跳转均为
> ①速览内「打开完整页 ↗」显式 opt-in / ②已在深链上下文内（TaskConsole 行/WorkbenchSession）/
> ③创建后或 ⌘K 搜索——**无一随手一瞥被甩去 87 控件整页**。故 Batch 3 只剩**可选**的「整页深链态
> 二次密度清理」（TaskDetail 918 LOC/87 控件），属 §九「只深链态二次清理不重写」的低边际、
> 主观、opt-in-page 工作 → **交 owner 定优先级**（是否值得做、削到多克制），不擅自重塑复杂页。
> 次要可选增强：⌘K 选任务 → 速览（当前跳整页，可议）。

> 依赖 Batch 2。step 级细化 JIT 补。

**Files:** `components/StatusCenter.vue`(peek 已含内联签发，确认所有默认点击落 peek) · `views/TaskConsole.vue`/`views/TaskDetail.vue`(整页深链态二次密度清理) · e2e：`m8_workbench`·`m9_guide_loop`·`m2_acceptance`。

**任务：**
- [ ] 审计所有「看任务」入口（方案卡督战点/产物锚/状态坞条目/任务台列表）→ 确认默认落速览 peek，无一甩整页（现状多数已如此，补齐缺口）。
- [ ] peek 内联签发就地闭环确认（同 `POST /tasks/{id}/review` 人具名 fail-closed）。
- [ ] 「查看完整页 →」深链保留；整页深链态次要区块折叠（87 控件二次清理，不破 TaskConsole 三栏/TaskDetail 自身 e2e）。
- [ ] `m8_workbench`(三栏+到席灯中性墨色级断言)·`m9`(速览直达)·`m2`(详情事件/签发) 逐一不回归。

**验收：** 默认点击无一甩整页；速览签发闭环；整页留深链；八步门绿。

---

## Batch 4 — 全局密度纪律收尾（低风险）

**Files:** `GuidePage.vue`(composer :246-334 + hint :329-332) · 跨屏巡检。

**任务：**
- [ ] composer Agent 选择器 popover 瘦身（保诚实前置 maturity/limitations，m11-A1 锚）；hint 收一行，`导引不会替你创建或签发` 字面保留（m6 锚）。
- [ ] 逐屏「一屏一主动作」巡检；冗余文案/次要控件/留白清理，无 e2e 锚字面改动。
- [ ] verify_all 八步绿。

**验收：** 每屏一主动作；无锚字面改动；八步门绿。

---

## Self-Review（对照 spec）

- **Spec 覆盖**：动作 1→Batch1；动作 2→Batch2；动作 3→Batch3；动作 4→Batch4；动作 5(红线)→Global Constraints + 每批诚实地板保留。✅
- **规划期修正**：spec §四动作1「JSON/剔除进展开」与 §六诚实地板 + e2e 冲突 → 已修正为「去装饰不藏事实」，记「设计修正」节，**待 owner 确认**。
- **Placeholder**：Batch 1 步级完整；Batch 2-4 任务级（step 级 JIT 补——因其 e2e 重写依赖前批落地 DOM + 需独立 grounding，此刻写死=盲写）。已显式标注，非偷懒占位。
- **类型一致**：复用既有函数签名，无新符号跨任务。✅

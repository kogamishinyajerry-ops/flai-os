# 桌面工艺批（UI-DESKTOP-CRAFT）评审记录

- 批次规格 SSOT：`docs/design/UI-DESKTOP-CRAFT.md`
- 分支：`feat/uiux-desktop-language`（base = origin/main @ f124ffd）
- 日期：2026-07-15

## 改动面

| 工作项 | 文件 | 施工 |
|--------|------|------|
| W0 token 地基（fs-display 双档/space 阶/z 阶/radius-xs/.cta-clay/.num-token/焦点环/hover 收口） | App.vue | 主控 |
| W1 工作日志语义着色（chip 动宾分踢/失败行染色集合） | WorkLog.vue | 主控 |
| W2 空态三级纪律（tier="line" 轻量态 + 今日页 4 处收敛） | EmptyState.vue / TodayPage.vue | builder A |
| W3 任务详情环境 rail（td-grid 容器查询双档/产物折叠/驳回术语） | TaskDetail.vue | 主控 |
| W4 今日简报（num-token 计数/token 归位） | TodayPage.vue | builder A |
| W5 对话轴微工艺（MarkdownLite 助手正文/CTA 层级 is-secondary/字阶归位/死 CSS 清理） | GuidePage.vue / WorkbenchSession.vue | 主控 |
| W6 登录门仪式感（≥900px 分屏品牌氛围面） | WelcomeGate.vue | builder B |
| W7 次级页收口（左色条文实相符/图例降噪/趋势柱值/预填条 amber/骨架语言） | AgentPortal / MePage / FeedbackPage / TaskCreate / QuickSwitcher | builder C |
| W8 验收（新 e2e 28 探针 + 双平台注册） | frontend/e2e/craft_desktop_acceptance.py + scripts/verify_all.sh/.ps1 | 主控 |
| 设计系统 specimen（9 卡，DesignSync 已推送 claude.ai/design） | docs/design/design-system/*.html | 主控 |

## 验证证据

- **verify_all 17/17 全绿**（build + pytest -n auto + node --test + 16 既有 e2e + 新套件）。
- **新套件 28/28**：`uv run … python frontend/e2e/craft_desktop_acceptance.py`。
- **tamper 咬合自证 ×2**（针对 dist 编译产物直改，改后必红、rebuild 复绿）：
  - T-A：`--focus-ring-clay:` 声明改名 → 探针①亮/暗双双 FAIL（outline-style 落 none）✔ 咬合；
  - T-B：`empty-line` class 发射名改名 → 探针③「纯数据空态 4 处全为轻量行」FAIL ✔ 咬合。
- **施工期真 bug 由探针捕获并修复**（oracle 先于人眼工作的实证）：
  - 焦点环从 currentColor 淡入（`.sb-new` 基态 `transition:all` 卷入 outline，Tab 瞬间采样到 clay 中间帧）→ 修复=focus-visible 块 `transition:none`（焦点环瞬时出现，可达性工艺）；
  - rail 980px 断点在主力 1440 桌面永不触发（/tasks/:id 走任务台三栏，中栏≈820px）→ 修复=容器查询双档 ≥780px/260px + ≥1120px/300px，几何依据写入规格 §W3。
- 截图证据：`docs/reviews/craft-shots/`（登录门宽/窄、今日页空态、rail 宽亮/宽暗/窄、worklog 语义、导引 markdown）——均为套件运行时真实产物非摆拍。
- 密度指标：今日页空态插画 3→1；主 CTA 渐变/投影手调 4 处→单一 `.cta-clay`；焦点环 0→全局键盘语法；App.vue 游离 px 字面量批量归 token。

## 3-lens 对抗审（sonnet ×3，默认反驳）

三镜头（信任红线 / 回归面 / 范式契合）confirmed 7 条、refute 41 条候选；全部 grounded 复核后**7/7 落地**，
每条修复带回归探针或注释级对齐：

| # | 级 | 镜头 | Finding | 处置 |
|---|----|------|---------|------|
| 1 | P1 | trust | WorkLog `isFailureEvent` 的 `\|\| level==="error"` 兜底把毒丸隔离（runner `_quarantine_poison_candidate` 写 `task_cancelled+level=error`，可达路径）误染红，违反「取消绝不染红」 | `task_cancelled` 先于兜底显式豁免；新探针⑥'（task C 夹具=毒丸同款事件）+ tamper 实证咬合 |
| 2 | P2 | trust+paradigm | `.cta-clay` 零模板消费——四处 CTA 只是数值同步并未归位，「4→1」指标未达成；且探针用合成元素恒绿 | **真归位**：send-btn/open-plan-btn/workbench-btn 主态模板接线、各自删渐变/投影/hover 重复声明只留结构；utility 升级为完整主 CTA 语法（hover 抬升+按压缩+reduced-motion 全静化）；hero 徽记=品牌标识非 CTA 独立保留，规格 §W0/验收口径同步修订；探针改真实 `.send-btn`（类名+渐变+投影三重断言）+ tamper 实证 |
| 3 | P2 | regression+paradigm | 产物折叠头嵌套下载 `<a>` 只 `@click.stop`——键盘 Enter 冒泡触发折叠且 `.prevent` 连原生下载一并吞掉 | `@keydown.stop` 与 `@click.stop` 对称；新键盘探针 + tamper 实证 |
| 4 | P2 | paradigm | StatusCenter 按钮「驳回」但确认弹窗仍「确认拒绝」（W7 术语统一遗漏面） | `StatusCenter.vue` doReview label 拒绝→驳回（e2e 零锚点引用，安全） |
| 5 | P3 | paradigm | `.workbench-btn.is-secondary:hover` 用 `--select-tint-clay` 与 W0 批注「clay 只留给选中态」自相矛盾 | 视觉判定为刻意（tint 跟随控件色相），批注改为如实三分口径（中性 hover / 选中 / clay 描边控件自身 hover） |
| 6 | P3 | regression | TaskDetail 模板注释断点写 980 与代码/规格/套件三方 780 不符 | 注释修正 780/260 + 1120/300 |
| 7 | P3 | regression | batch_d docstring「22px .sess-goal」数值过期（本批 22→var(--fs-display)=24） | docstring 同步（值由本批改动，原子性属本批） |

修复后套件扩至 **30 探针全绿**；三处修复各做 tamper（拆修复必红：⑤键盘/⑥'/② 恰好三红），oracle 咬合实证。

## Codex 治理审（86gs · gpt-5.6-sol ultra，`codex review --uncommitted`）

**R0：4×P2（无 P1），grounded 复核 4/4 全部成立并落地：**

| # | Finding | 处置 |
|---|---------|------|
| C1 | rail sticky `top:20px` 与固定态 StatusDock（top16+高32）叠压，坞盖住元信息卡（截图可证） | 容器查询块内 `top:64px + margin-top:var(--space-12)`（坞几何推导值，注释声明）；新探针「rail 让位状态坞（bounding box 无叠压）」 |
| C2 | `.artifact-head[role=button]` 内嵌可聚焦下载 `<a>`=非法嵌套可交互控件（AT 会拍扁 button 后代） | 结构手术：披露触发器降为真 `<button.artifact-toggle>`（原生 Enter/Space，删 tabindex/keydown 手写），下载 `<a>` 升为兄弟节点；新探针「下载链接是触发器兄弟（不嵌套）」+ 键盘探针改由原生语义保证 |
| C3 | QuickSwitcher 骨架根 aria-hidden 顶掉了可读的「加载中…」——读屏用户无加载指示 | `.qs-loading` 加 `role="status"` + 视觉裁剪的 `.qs-loading-sr`「加载中…」（repo 无全局 sr-only，本地最小实现） |
| C4 | `frontend/node_modules` 是指向兄弟检出的 symlink，`.gitignore` 的 `node_modules/`（dir-only）不匹配 symlink 形态 | `.gitignore` 增补无尾斜杠 `node_modules` 规则（目录+symlink 双匹配）；本批提交本就走显式路径 staging |

修复后套件 **32/32 全绿**；受影响面定向重跑（m2 产物下载流 / m8_collab 详情页 / batch_d 视觉契约）+ 全量 verify_all 终局门。

**R1：2×P1 + 2×P2，grounded 复核 4/4 成立并落地：**

| # | Finding | 处置 |
|---|---------|------|
| R1-1 (P1) | 取消豁免只摘了文字 class，时间轴 dot 仍由 `LEVEL_COLOR[level]` 驱动——毒丸隔离路径残留红点 | `markerColor(e)` 与文字同一谓词：非真失败的 error 级降中性蓝；新探针「毒丸隔离 dot 降中性（无 #F56C6C 红点）」 |
| R1-2 (P1) | `MarkdownLite.clean()` 无差别删 `**`/反引号——`def f(**kwargs)`、`2 ** 3` 等字面量被静默改写（助手回复是任意字符串） | 重写为行内分段渲染：成对 `` `code` ``/`**strong**` 落成真实元素（零 v-html，函数式 h() 文本节点），不成对标记逐字保留；strong 按 CommonMark 侧翼规则配对（首版探针实测咬出跨内容误配对后收紧）；新探针×2（成对渲染成真元素 / 不成对逐字保留） |
| R1-3 (P2) | 全局焦点环令牌亮 #dcb6a4 仅 ~1.6:1、暗 #8a5a42 ~2.7:1，低于 3:1 焦点指示阈 | `--focus-ring-clay` 双主题改指 `var(--clay)`（亮 ≈3.9:1 / 暗 ≈4.0:1），WCAG 论证注释入 token 定义处 |
| R1-4 (P2) | line 空态 `--ink-faint` 亮色 ~2.5:1 低于 12.5px 正文 4.5:1 阈，且去插画后是版块唯一空态指示 | `.empty-line` 改 `--ink-soft`（≈5.4:1）；新探针「line 空态走 ink-soft」；DesignSync specimen 卡同步重推 |

修复后套件 **36/36 全绿**（探针从 28→36 随两轮审查逐步增网）；全量 verify_all 复跑。

**R2（终轮，round cap=R0+2）：1×P1 + 1×P2 + 1×P3**

| # | Finding | 处置 |
|---|---------|------|
| R2-1 (P1) | 侧翼规则 v2 仍可跨内容误配：`def f(**kwargs)：**重要**` 中 '：**' 既是合法开标记又满足闭标记条件，被当闭标记吃掉函数语法（此例连 CommonMark 参考实现同样会加粗 `kwargs)：`） | **verbatim-suggested-fix 例外落地**（Codex 建议=delimiter-flank scanner，照做）：opener 增加 ASCII 代码上下文负向卫（前禁字母/数字/_/([{/\）——f(** 永不为开标记，'：**重要**' 正常配对。刻意收窄于 CommonMark（ASCII 词内加粗不解析）换代码字面量零误伤，契约注释入组件；Codex 原例进探针 |
| R2-2 (P2) | FeedbackPage/MePage 首载骨架同 QuickSwitcher 缺口：aria-hidden 骨架顶掉可读控件，读屏无加载指示 | 同款 `role="status"` + 视觉裁剪「任务列表加载中…」补齐两处（verbatim：per Codex "as done in QuickSwitcher"） |
| R2-3 (P3) | 驳回流深层文案：backend `人工拒绝（reviewer=…）` error_message / 事件 message 与前端「驳回」混用 | **retro 队列**（cap 纪律）：backend 字符串被 `backend/tests/test_api.py:515` 锚定，跨层原子改超本 UI 批爆炸半径——应由带后端测试更新的专项小批处理 |

R2 后套件 **36/36 全绿**（含 Codex R2 原例探针）；定向回归 m6/m9/m8_orch/batch_b/batch_c/batch_d + 终局 verify_all。
**收敛判定：round cap 用尽，P1/P2 均以 verbatim-suggested-fix 例外落地并有探针回归网；唯一残余=P3 术语深层统一，进 retro 队列交 owner。**

## 剩余风险

- Gate2-T2'（967e3e8，未 push 本地栈）与本批在 SignPanel/StatusCenter/TaskDetail 等面的合并收敛按规格 §三处置（同一设计终点，rebase 方按规格裁）。
- m10_governance ④' 「maturity 行真实变 L1」历史 flake（前两轮各出现一次）：本批两次全量跑均绿，未复现；retro 队列继续挂账。
- builder A 报告的 ±2px token 归位视觉近似（12→12.5px 等）：batch_d 逐像素回归门未咬（全绿），确认在许可幅度内。

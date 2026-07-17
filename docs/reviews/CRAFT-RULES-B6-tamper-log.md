# 批次六 tamper 咬合逐字存档

> 诚实边界：以下为执行会话逐字输出摘录（FAIL 行+套件计数）。与批五不同，本批
> 起 `scripts/tamper_replay.sh`（B6-6，批五 §八 retro 兑现）提供隔离 worktree
> 独立重放——脚本重放基 HEAD，本文档存档的是工作区实跑。每处流程 =
> patch → `npm run build` → 跑套件 → 恢复（未提交文件 cp 备份 + `cmp` 一致；
> 已提交文件 `git checkout`）→ 下一处 patch 前重建。
>
> 基线：craft 108/108 · m10 14/14（批六首过全绿）。B6-5 elapsed 端锚为
> oracle 先行红→绿（format_elapsed.test.mjs waiting_review 例 pre-fix 红），
> 不另设 tamper。

## 总账

| tamper | 预期红 | 结果 |
|---|---|---|
| TB1 roving 撤除 | ⑭C6″+⑭C6‴ | 咬合 106/108 |
| TB2 Fitts 缩穿 | ⑮ | 咬合 107/108 |
| TB3a dock 全页铺满 | ⑯ | 上游兜死（⑤rail 红+点击拦截崩，fail-closed 未达 ⑯） |
| TB3b dock 顶部通栏 | ⑯ | 咬合 107/108 |
| TB4 uploadPhase 置空 | ⑮′ | 咬合 107/108 |
| TB5 :disabled 撤除 | m10 ⑩ | 咬合 13/14 |
| TB6 dialog-reduce 撤除 | ⑭C4′ | **首跑假绿→探针重设计（强加 enter-active 类）→咬合 107/108** |

复位后绿位确认：craft 108/108（重设计 ⑭C4′ 在完好代码上 PASS）。

> 注：tamper 轮跑在 108 探针基线上；随后 3-lens 采纳新增 ⑭C6⁗（aria-live
> 播报，oracle 先行红 108/109 `ann=''` → 落码绿 109/109），并落 oracle 审
> 三 P2 修复（replay grep 长前缀锚死 / ⑭C4′ try-finally 摘类 / ⑯ 夹具回滚）。
> 上表计数按当时基线如实保留。

## TB1 roving 撤除（router afterEach 焦点选择器打歪 `.app-main`→`.app-main-x`）

→ 106/108：
```
FAIL ⑭C6″ 导航离场不回还（焦点=app-main roving 落点，绝不拽回搜索钮） | active=(body)
FAIL ⑭C6‴ SC「查看全部任务」导航离场不回还（焦点=app-main roving 落点，不被拽回 dock） | active=(body)
```
（B6-2 有意识更新后的断言（`"app-main" in nav_focus`）对 roving 缺失双点必咬；
批五旧断言只验「不回还」，此 tamper 下会假绿——正是本批收紧的动机实证。）

## TB2 Fitts 目标缩穿（.sb-foot-btn 10×10，gap 6 → 圆心距 16 拥挤）

→ 107/108：
```
FAIL ⑮ 触达目标 census：/today /me /portal 全部 ≥24×24 或豁免（违规=0） | {'/today': ['button.sb-foot-btn(10x10)', 'button.sb-foot-btn.sb-theme(10x10)'], '/me': [...], '/portal': [...]}
```
（违规元素逐个点名带实测尺寸；⑮ 首过零违规为「现状达标」而非 vacuous——
此 tamper 证明 census 对缩穿+拥挤组合必咬。注：spacing 豁免的反向面
（孤立缩穿目标不误报）是判定式设计属性，本批未单设 tamper 实证。）

## TB3 dock 合成遮挡（两级）

**TB3a inset:0 全页铺满** → 套件在 ⑯ 之前即崩（fail-closed 但未达 ⑯）：
```
FAIL ⑤rail 让位状态坞（无叠压） | dock={'x': 0, 'y': 0, 'width': 1440, 'height': 900} rail={...}
playwright TimeoutError: <div class="status-dock" ...> intercepts pointer events   ← 后续点击被拦
```
（粗暴遮挡被上游探针+playwright actionability 兜死，⑯ 自身咬合待 TB3b 证。）

**TB3b 顶部通栏（left:0/right:0，高度不变）**——温和遮挡专测 ⑯ → 107/108：
```
FAIL ⑯ dock 带全页遮挡审计（waiting+running pill 在场，六页可点元素零被拦） | {'/tasks': ['button.el-button.el-button--primary']}
```
（六页枚举里唯 /tasks 顶栏主按钮圆心落入通栏带——审计对「静默叠压可点元素」
必咬，且与 TB3a 互补：粗暴遮挡由上游兜死，细微遮挡由 ⑯ 点名。）

## TB4 上传分阶段撤除（uploadPhase 置空 → 网络耗时冒充「导引思考中」）

→ 107/108：
```
FAIL ⑮′ 上传期 thinking 区显「正在上传附件 1/1」不冒充「导引思考中」 | tlabel=导引思考中…
```
（B5 Codex R0 P2 的代码级修复至此升为活体锁：upload 路由挂起下 thinking 区
一旦回退到冒充文案立刻点名。）

## TB5 portal 防重复入队撤除（删 `:disabled="latestRunInFlight"`）

→ m10 13/14：
```
FAIL ⑩入队后首轮询失败→错误行+行内重试在场+「跑评测」压住（绝不诱导重复入队） | err=评测状态刷新失败（…）——所示结果可能已过期 重试 disabled=False retry=True
PASS ⑩'行内重试恢复轮询到终态（错误行清除+「跑评测」解锁）
```
（⑩ 单点红、⑩' 照常绿——探针分辨率到「压钮」这一件事，不连坐。）

## TB6 dialog-reduce 撤除（reduce 块删 .el-overlay-dialog/.el-dialog）

**首跑未咬——⑭C4′ 假绿实锤**：保护规则删除后 108/108 全绿。根因：dialog-fade
动画只在 enter/leave 瞬挂 `.dialog-fade-enter-active`（Vue 动画毕即摘类），原探
针在弹窗**稳态**读 computed → animationName 恒 none，量错了时刻、天生 vacuous。

**探针重设计（oracle 先行，tamper 仍在位）**：运行时把 enter-active 类强加回
`.el-overlay` 再读级联（reduce 规则在位 → `!important` 压成 none；被撤 →
`dialog-fade-in` 现形）。篡改态重跑 → 107/108：
```
FAIL ⑭C4′ reduce 下治理 el-dialog 位移动画归零（dialog+overlay-dialog 双节点） | dlg=0s|none|dialog-fade-in
```
（教训：computed-style oracle 必须在动画**真实挂类的时刻**取样——稳态读数对
transition-class 型动画恒真。tamper 轮的价值本批第二次自证：抓的不是产品回归，
是探针自己的假绿。）

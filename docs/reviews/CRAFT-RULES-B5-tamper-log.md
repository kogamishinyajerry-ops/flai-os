# 批次五 tamper 咬合逐字存档

> 诚实边界：以下为执行会话的逐字输出摘录（FAIL 行+套件计数），非独立重放产物；
> 隔离 worktree replay 脚本在 retro 队列（评审记录 §八）。每处 tamper 流程 =
> patch → `npm run build`（亲证破坏进入被测制品 dist）→ 跑套件 → 恢复核验
> （已提交文件 `git checkout` + status 空；未提交文件 cp 备份 + `cmp` 一致）。

## 实现批（基线 e39ba1b，实现 df2cba7）

**T1 census 回染**（nav-link+section-head 染 clay !important）→ 97/99：
```
FAIL ⑭C3 /today clay census ≤2（非豁免·own-属性归因） | ['span.brand-mark', 'button.sb-new', 'a.nav-link', 'div.today-section-head.waiting', 'div.today-section-head.working', 'div.today-section-head', 'div.today-section-head', 'div.today-section-head']
FAIL ⑭C3 /me clay census ≤2 | ['span.brand-mark', 'button.sb-new', 'a.nav-link', 'a.nav-link']
```
（副产物：基线=2，brand-mark+sb-new 恰满预算）

**T2 超时机制撤除**（删 setTimeout→abort 触发线，signal 管线保留）：
```
FAIL ⑭C1 后端挂起→20s 硬超时落地（「请求超时」分型+行内重试钮+role=alert） | (无错误行)
playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.   ← 后续 ⑭C2 重试点击崩（fail-closed）
node: ✖ tests/api_client_timeout.test.mjs (59962ms) 'Promise resolution is still pending but the event loop has already resolved'
```

**T3 降级条阉割**（fetchDegraded 永 false）→ 98/99：`FAIL ⑭C2 ⌘K 三源失败→诚实降级条+空态文案切换`

**T4 ring 回退**（me-stat 实线边框+去环）→ 98/99：
```
FAIL ⑭C5 ring 试点（me-stat/sc-item：边框透明+box-shadow 1px 环） | me=rgb(236, 229, 219)|none sc=rgba(0, 0, 0, 0)|rgb(240, 236, 226) 0px 0px 0px 1px
```

**T5 worklog button 回退**（→div+撤 aria）→ 98/99：`FAIL ⑭C6 ... | tag=DIV None→None`

**T6 reduce 补洞撤除**（删 .sidebar !important 行）→ 98/99：
```
FAIL ⑭C4 reduce 下补洞归零（窄屏侧栏 transition=0s；el-drawer 过渡/动画禁用） | sidebar=0.22s drawer=0s|none
```

## 3-lens 修复批（03d6f0c）——oracle 先行 pre-fix 红

首跑 99/102（修复前代码即「篡改态」，三红逐字命中预测）：
```
FAIL ⑭C6′ 跨模态互斥：SC 开着按⌘K→焦点归 qs-input（不被 dock 回还抢走） | active=status-dock
FAIL ⑭C6″ 导航离场不回还（选中结果后焦点不被拽回搜索钮） | active=sb-foot-btn
FAIL ⑭C2′ feed 超时→「自动重试中」真声明（在场+无自相矛盾拼接+轮询真二次开火） | err=请求超时（20 秒无响应）——后端可能繁忙或已停止，请稍后重试（自动重试中） hits=2
```
修复后 102/102。

**T1′ 动态 census 回染重咬**（oracle 改运行时解析后同 T1 patch）→ 100/102：FAIL 明细同 T1（咬合力不减）。

**T7 出错停轮**（schedule 入口 `if (ch.state.error.value) return`）→ 101/102：
```
FAIL ⑭C2′ ... | err=请求超时（20 秒无响应）——后端可能繁忙或已停止（自动重试中） hits=1
```
（err 文本同时证实反矛盾修复已生效）

## Codex R0 修复批——oracle 先行 + 补咬

**node body-hang**（P2：响应头到 body 挂）：pre-fix `✖ tests/api_client_timeout.test.mjs`（文件级永不绿）→ 修复后 4/4，80ms 落地。

**m8 ⑤b0 去 sentinel**：当场暴露 chip-action 从未渲染（人签流程恒 waiting_review）——wait 超时崩=fail-closed 咬合实录；running 翻转夹具后 9/9。

**T11 分级口径回退** → 102/104：
```
FAIL ⑭C2 ⌘K 三源失败→诚实降级条+空态文案切换（后端故障绝不伪装成无结果）
FAIL ⑭C2″ 单源失败+真无匹配→部分口径（不夸大成整个服务不可用） | bar=部分结果不可用（后端搜索请求失败）——以下显示可能不完整 empty=搜索服务不可用（后端请求失败）——请稍后重试
```

**T12 openAllTasks 出口回退** → 103/104：
```
FAIL ⑭C6‴ SC「查看全部任务」导航离场不回还（焦点=body，不被拽回 dock） | active=status-dock
```

## 全量 verify_all

三轮均 EXIT=0（tamper 恢复后 / 3-lens 修复后 / Codex R1 修复后），`[失败]（无）`，17/17 e2e。

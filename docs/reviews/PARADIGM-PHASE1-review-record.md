# 范式 Phase 1 对抗审记录（状态坞 + 状态中心 + 内联签发）

> 批次：UI-PARADIGM.md Phase 1（状态来找人 + 渐进披露四级）。
> 审查结构：**谁写另一方审**——主控亲写宪法路径组件（StatusCenter/StatusDock/store），
> Codex（GPT-5.6, read-only）异源敌意审；builder（B1 导引督战 / B2 工作台速览）由
> workflow 信任/回归双镜头审 + 主控亲核 diff。三源合并去重后统一裁决落修。

## 审查三源与 findings

### Codex 异源审（主控亲写组件）——1P1 + 4P2 + 2P3，全采纳

| 级 | Finding | 修法 |
|----|---------|------|
| P1 | 产物预览挂靠轮询 epoch：轮询每 3s 换代，加载 >3s 被永久丢弃且 file_ids 未变不重试→「有产物、无显示、无报错、仍可签发」 | 产物改持独立指纹世代（taskId+file_ids）；有产物声明必渲染区块（loading/error 可见）；首次预览尝试完成前禁「批准放行」（驳回不设门——安全方向） |
| P2 | doReview 用 await 后的 statusCenter.taskId 刷新（任务可能已切） | 调用前捕获 taskId；成功后校验抽屉仍开且同任务才迸发+刷新 |
| P2 | reviewComment 常驻 setup 跨任务残留 | 切任务/签发成功/关闭抽屉三处清空（签发人姓名保留） |
| P2 | StatusDock 轮询 in-flight finally 可越过 onUnmounted 续排 | disposed 标志；初载 await 落地后再排轮询 |
| P3 | watch 与 @open 双触发初载 | peekLoadedFor 去重，onOpen 走同一幂等入口 |
| P3 | role=button 只响应 Enter 缺 Space | 补 @keydown.space.prevent |

### Workflow 双镜头（信任+回归）——共识 P1 ×1 + P2 ×4 + P3 ×4

| 级 | Finding | 修法 |
|----|---------|------|
| P1（双镜头共识） | `.sc-shell` 无条件 `@keydown.esc.stop` 吞掉冒泡，el-drawer 的 document 级 close-on-press-escape 永远收不到→inbox 态 Esc 连整体关闭都做不到 | 去掉模板级 .stop，只在 peek 态 handler 内 stopPropagation + backToInbox；inbox 态放行给 drawer |
| P2（信任） | goFullPage 不等 destroy-on-close 的 0.3s 过渡即 push 路由，「批准放行」与 TaskDetail 同名按钮瞬时选择器重影（红线§e2e） | 先 backToInbox() 同步卸载 peek 子树再关抽屉+跳转 |
| P2（信任） | 内联签发比 TaskDetail 少一道二次确认，宪法路径操作摩擦被静默降低 | 补同款 ElMessageBox.confirm，两条签发路径摩擦对等 |
| P2（信任） | 产物静默截断 3 件无披露，可能没看全就背书 | 截断必披露：「仅预览前 N 件，另有 M 件——请打开完整页审阅后再签发」 |
| P2（回归） | ⌘K 面板 z-index 200 被 el-drawer(2000+) 遮罩盖住，焦点被偷进不可见输入框 | QuickSwitcher.open() 先 closeCenter()——任意时刻只留一个顶层模态 |
| P3 | .sc-item 无键盘路径；burstSigned 一次性 rAF 与 ambient rAF 短暂并发；StatusDock 与页面轮询冗余 | .sc-item 补 role/tabindex/Enter/Space；MOTION-SYSTEM.md 增「瞬时迸发例外」口径；轮询共享缓存递延 Phase 2 |

### 主控亲核 builder diff——追加 2 处统一纪律

- B1 GuidePage 轮询 finally 无 disposed 守卫（与 StatusDock 同款竞态）→ 补 taskPollDisposed；督战 chip 补键盘路径。
- B2 WorkbenchHome/Session diff 核过：第 8 轨道显式 grid-column、@click.stop、既有导航零改动、无表头行共享模板——放行。

## 实机探针（修复真咬验证，常驻 8620 真数据）

首轮探针 **咬出修复不完整**：点击收件箱条目进速览后被点元素卸载、焦点跌落 body，
keydown 不再冒泡经过 .sc-shell——Esc 修复形同虚设（④⑤ FAIL）。补「焦点跟随视图」
watch 后复测：

```
PASS ①状态坞常驻右上          PASS ④Esc 第一跳：速览→收件箱（抽屉仍开）
PASS ②状态中心抽屉打开        PASS ⑤Esc 第二跳：收件箱→整体关闭（P1 真咬）
PASS ②收件箱三分组+诚实脚注   PASS ⑥关闭后签发按钮零 DOM（红线§e2e）
PASS ③速览视图+WorkLog+消耗   PASS ⑦导引页正常
PROBE ALL GREEN
```

截图证据：`paradigm-phase1-shots/`（01 状态坞 / 02 收件箱+归位图章空态 /
03 GLM 真任务速览：产物内联+人签记录+2,533 tokens / 04-05 Esc 两跳）。

## 收口验证

- `bash scripts/verify_all.sh` 七步全绿（build + 全量 pytest + 5 套 e2e 35 断言），失败（无）。
- 既有 e2e 零改动零触碰（Phase 1 承诺）；导航塌缩与 e2e 契约重立递延 Phase 2。

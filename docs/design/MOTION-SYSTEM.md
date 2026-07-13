# FLAi-OS 动效系统 v1 ——「绘图桌上的活平台」（SSOT）

> 定位：效果层是**独立可整体拆除的模块**（`frontend/src/effects/` + motion tokens），
> 不是散落各页的 hack。平台主线仍是架构；本系统的存在理由是采纳推广——
> 震撼来自工艺一致性与材质真实感，好玩来自与**真实状态**挂钩的生命感，
> 细腻来自 micro-interaction 打磨。**绝不赛博霓虹。**

## 北极星与材质隐喻

工程师的绘图桌：石墨粉尘（粒子）、蓝图连线（粒子近距连线）、墨迹晕开（入场）、
纸张滑动（路由过渡）、制图笔画线（hero 插画）。全部延续既有暖纸+漫画墨线语言
（空态三插画同源）。

## 硬约束（violating any = 审查 BLOCK）

1. **信任色锁**：动效用色只允许中性暖阶（--ink*/--paper*/--hairline）+ clay
   （工作/行动语义）。teal **仅**人签时刻（放行成功迸发）。绿/红/amber 三槽
   动效一律不碰（驳回/失败不做庆祝动效——失败不是烟花时刻）。
2. **诚实地板**：动效强度不得暗示不存在的活动。常驻 ambient 必须低速低密度、
   无随机爆发（装饰性明示）；「增强档」只绑真实信号（work-state 任务数、
   请求真实在途）；信号消失动效必须回落。**入场动效（fx-ink-in/fx-rise）只给
   「本次会话刚落地」的内容**——历史批量加载/折叠展开重挂载/用户手动切换视图
   形态（如表单↔JSON 模式）都不得重播「刚发生」视觉（GuidePage 用 m.fresh、
   WorkLog 用 isWorking、TaskCreate 用 modeToggled 门控——三案例均为双镜头审
   实证后落修）。
3. **e2e 契约零触碰**：选择器/DOM 序/文案锚点不改；所有效果 additive。
   canvas/装饰元素一律 `pointer-events: none` + `aria-hidden="true"`，
   绝不遮挡交互与文本。
4. **reduced-motion 全覆盖**：每个**位移/缩放类**动效必须有
   `prefers-reduced-motion: reduce` 降级（rAF 引擎直接不启动，CSS 动画
   `animation: none`；优先用全局 fx-* 类天然继承降级，本地 @keyframes 必须
   自带降级块）。裁决口径：纯颜色过渡（background-color/border-color fade）
   不属于前庭运动，不强制降级（v1.1 审定）。
5. **性能**：单页 ≤1 个 rAF 循环；`document.hidden` 暂停；DPR 上限 2；
   粒子上限 120；**零第三方依赖**（禁 three.js/GSAP——内网低配 Windows +
   bundle 纪律）；CSS 动画只用 transform/opacity（不触发 layout）。
   **瞬时迸发例外**（范式 Phase 1 审定）：burstSigned/burstNeutral 的一次性
   rAF（<1s 自清理、reduced-motion no-op）允许与页面 ambient rAF 短暂并发
   ——签发迸发自全局状态中心触发，无法预知宿主页面；常驻循环仍严格 ≤1。
6. **可整体拆除**：`src/effects/` 删目录 + 移除调用点即回到纯静态平台；
   tokens 留在 :root 无副作用。

## Motion tokens（:root）

```
--motion-fast: .14s      微交互（按压/hover）
--motion-med:  .22s      入场/过渡
--motion-slow: .6s       墨迹晕开/大时刻
--ease-out-soft: cubic-bezier(.25,.8,.35,1)
--ease-spring:   cubic-bezier(.34,1.4,.64,1)   仅小位移元素（防溢出裁切）
```

### 已废除：--ease-lift（批A T8，2026-07-13，实测证据）

`--ease-lift: 0.18s cubic-bezier(0.22, 0.61, 0.36, 1)` 是复合 token（自带时长）。全站
~20 处以 `transition: <prop> 0.14~0.22s var(--ease-lift)` 写法使用——显式时长 + 复合
token 展开后，CSS transition 简写按位置解析两个 `<time>`：第一个记为
`transition-duration`，第二个（来自 token 内的 0.18s）记为 `transition-delay`。

**实机验证**（Playwright，`.sb-new` 真实渲染元素，chromium `getComputedStyle`）：
```
transition: 0.16s cubic-bezier(0.22, 0.61, 0.36, 1) 0.18s
transitionDuration: 0.16s
transitionDelay: 0.18s   ← 确证 bug：每次 hover/press 微交互多出 180ms 死等
```
即按压/hover 反馈实际比设计意图晚 180ms 才开始过渡，与「细腻」北极星相悖。

**处置**：全站引用改为 `var(--motion-fast) var(--ease-out-soft)`（hover/press 微交互，
唯一例外 `App.vue` 移动端侧栏抽屉开合过渡——非 hover 而是状态切换/入场语义，改用
`var(--motion-med) var(--ease-out-soft)`，原时长 0.22s 与 --motion-med 精确重合）；
`WorkbenchSession.vue` 一处裸用法（`transition: box-shadow var(--ease-lift)`，无
显式时长，实测无 delay bug）为与站内同类卡片 hover 抬升写法一致，同样归一到
`--motion-fast` + `--ease-out-soft`。`--ease-lift` 定义已从 `App.vue :root` 删除。

## 模块清单

| 件 | 文件 | 说明 |
|---|---|---|
| E1 粒子场引擎 | ~~`src/effects/particleField.js`~~ | 已按「可整体拆除」条款清理（批A T8，2026-07-13）——零调用方死代码（`BEAUTIFY-review-record.md` 已标注），`git rm` 删除 |
| E2 迸发引擎 | `src/effects/burst.js` | 一次性粒子迸发 `burstAtElement(el, {color})`；**teal 仅人签放行**；completed 用中性 ink 尘埃沉降；reduced-motion → no-op |
| E3 tokens+全局 | `App.vue` | tokens、路由过渡（`:key="route.path"`，**纯 opacity**——容器动画带 transform 会劫持后代 position:fixed 的定位基准，「升起」由各页内部 fx-* 承担）、按压 micro（不覆盖 .el-button 自带 transition）、stagger-in 工具类 |
| A1 hero 动态插画 | ~~`src/components/artwork/DraftingScene.vue`~~ | 已按「可整体拆除」条款清理（批A T8，2026-07-13）——宿主 `WorkbenchHome.vue` 已删,零调用方,`git rm` 删除 |
| A2 思考墨滴 | `src/components/artwork/ThinkingInk.vue` | 导引等待回复的墨滴扩散动画（替换纯打字点），仅真实请求在途时渲染 |
| P1 工作台首页 | ~~`WorkbenchHome.vue`~~ | 宿主已删，其 hero ambient 粒子场用法随 E1（particleField.js）一并清理（批A T8，2026-07-13） |
| P2 智能导引 | `GuidePage.vue` | ThinkingInk + 消息气泡 stagger 入场 + 推荐卡片展开动效 |
| P3 任务详情 | `TaskDetail.vue` | 真实 work-state 时页头细流光带（clay 流动渐变，状态回落即停）+ 新事件墨迹晕开入场 + 放行成功 teal burst |
| P4 门户/会话/⌘K | `AgentPortal.vue` / `WorkbenchSession.vue` / `QuickSwitcher.vue` | 卡片 stagger + hover 微动 + 面板 spring 微弹（CSS-only） |

## 验证口径

- `verify_all.sh` 七步全绿（动效 additive，5 套 e2e 锚点不动）；
- headless 截图目检 + reduced-motion 模拟对照（动效关停仍完整可用）；
- 双镜头对抗审：信任/诚实镜头（色锁+假活动）+ 回归/性能镜头（e2e 面+rAF 泄漏+遮挡）。
- 已知残余：动效本身 e2e 零断言（与空态插画同判例——装饰性资产，
  若日后升格为契约再补）。

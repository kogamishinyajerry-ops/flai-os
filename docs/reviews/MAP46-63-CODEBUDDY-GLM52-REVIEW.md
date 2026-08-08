# Map #46 / Task #63 CodeBuddy 互审

- 工具：本机 CodeBuddy CLI `2.133.0`
- 模型：`glm-5.2`（CLI 回报实际模型 `GLM-5.2`）
- 模式：`--permission-mode plan`、`--no-session-persistence`
- 范围：`origin/main` 到 #63 最终 worktree；包含 PR 自动审查 P2 处置、性能测试和证据包
- 写权限：无。CLI 明确回报没有 Write 工具，未修改、暂存、提交或外部回写
- 裁决：**PASS**

## 审查时间线

1. 初审对原始 #63 变更给出 PASS，但随后 GitHub 自动 Codex Review 发现一个成立的 P2：
   候选卡与地图 disclosure 虽是异步定义，父模板却无条件实例化，首屏仍会请求 chunk。
2. #63 随即重新打开，地图改为同步轻壳 + 首次展开异步正文，候选卡增加真实父级状态门；
   浏览器再补“请求前/后”断言和证据。
3. 最终复审继续显式使用 `glm-5.2`。首次调用读满 12-turn 上限而没有裁决，故不计通过；
   第二次提高只读 turn 上限后完整输出 P0/P1/P2 均无，并给出 `VERDICT: PASS`。

## Findings

没有 P0、P1、P2 可行动问题。

### P3-1 异步条件组件没有专用 loading/error component

- 位置：`frontend/src/views/GuidePage.vue`、`frontend/src/views/TodayPage.vue`
- 观察：`defineAsyncComponent` 使用 loader 简写；chunk 真失败时该条件区域不会提供专用错误面。
- 互审判断：这些组件不是首条纯文本主路径，UI Lab 已等待真实异步锚点；当前不阻断。
- 本票处理：不顺手增加新错误 UI，避免扩大范围。后续如统一异步失败语法，再单独施工。

### P3-2 JS 前品牌骨架固定浅色

- 位置：`frontend/index.html`
- 观察：暗色偏好用户在 JS 应用主题前可能短暂看到浅色骨架。
- 互审判断：当前产品主题由 JS 中的应用偏好决定，并不等同 OS 偏好；固定中性浅色避免
  预判错误主题，收益/风险不足以阻断本票。
- 本票处理：保持静态、零脚本、零动画，不新增第二套主题判断。

### P3-3 异步组件 CSS 没有单列预算

- 位置：`docs/reviews/map46-63-performance-shots/chunk-budget-after.json`
- 观察：`subchunks` 当前单列异步组件自身 JS，scoped CSS 仍可从 manifest/构建日志核对，
  但没有在子 chunk 表逐项展开。
- 本票处理：路由闭包的 JS/CSS 均已递归计量，且异步 CSS 会随组件按需加载；不阻断本票。

### P3-4 地图 loading 期间摘要仍显示“只读披露”

- 位置：`frontend/src/components/FeatureAssetMapDisclosure.vue`
- 观察：`phase !== 'ready'` 都显示“只读披露”，没有专用“正在冷读”摘要。
- 本票处理：正文已有 `role=status` 的明确加载态，“只读披露”仍属实；不扩大文案改动。

## PR 自动审查 P2 最终闭合

| 原问题 | 最终机制 | 运行时证据 |
| --- | --- | --- |
| idle 候选卡仍下载 | 父级 `assetCandidatePhase !== 'idle'` 后才实例化 | 起手页 Candidate `0`；候选态 `1` |
| 折叠地图仍下载全文 | 同步 `<details>` 轻壳，`openedOnce` 后异步加载正文 | 折叠 MapBody `0`；首次展开 `1` |
| 折叠后可能丢状态 | `openedOnce` 只从 false 变 true，原生 details 仅隐藏子树 | V1 纵向 + UI Lab ready/refresh/mobile 全绿 |
| manifest 收益可能误导 | view 路由与组件子 chunk 分口径，浏览器 request 事件交叉验证 | Guide 180,585 B gzip；8 routes / 5 subchunks |

## 红线复核

| 边界 | 互审结论 |
| --- | --- |
| 人是唯一签发者 | 无签发逻辑改动 |
| API/schema/状态机/持久化格式 | 无改动 |
| 假绿 | bundle 脚本只统计 `src/views/` 路由，异步子 chunk 不顶路由数 |
| 预算纪律 | 原阈值与动态路由下限均未放宽 |
| UI Lab 只读 | acceptance fixture 和 `/ui-lab.html` 双重禁止 prefetch |
| 路由目的地 | `/workbench`、`/tasks/new` 等 redirect 保持原样 |

## 互审确认的关键机制

- 路由和 prefetch 复用同一 loader；Map 对并发/完成态去重，失败删缓存以便真实导航重试。
- idle 用 `Promise.allSettled`，hover/focus 吞掉 speculative 失败，不形成未处理拒绝。
- idle 调度在 App 卸载时取消；UI Lab 在任何 speculative import 前短路。
- 静态骨架有 `role="status"`、品牌文本与 SVG 无障碍边界，且无动画或外部请求。
- 同步入口增加 1,441 B 已如实披露；Guide/Today 闭包净下降，8 路由/5 子 chunk 对表一致。

## 残余风险

1. 无 `requestIdleCallback` 的浏览器在 1,200 ms 后执行 fallback，预取可能略迟；它是
   best-effort，不影响导航正确性。
2. JS 前骨架固定浅色，见 P3-2。
3. 一部分回归锚是源码 regex，纯格式化可能触发误报；运行态行为另有真实浏览器 E2E 覆盖。
4. 异步组件 CSS 尚未在子 chunk JSON 中逐项列示，见 P3-3。
5. 地图加载期间 summary 使用宽泛的“只读披露”，见 P3-4。

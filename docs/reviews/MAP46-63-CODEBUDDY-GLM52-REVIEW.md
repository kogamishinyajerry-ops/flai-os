# Map #46 / Task #63 CodeBuddy 互审

- 工具：本机 CodeBuddy CLI `2.133.0`
- 模型：`glm-5.2`（CLI 回报实际模型 `GLM-5.2`）
- 模式：`--permission-mode plan`、`--no-session-persistence`
- 范围：`origin/main` 到 #63 worktree；包含新 route loader、性能测试和证据包
- 写权限：无。CLI 明确回报没有 Write 工具，未修改、暂存、提交或外部回写
- 裁决：**PASS**

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
- 同步入口增加 1,432 B 已如实披露；Guide/Today 闭包净下降，8 路由/5 子 chunk 对表一致。

## 残余风险

1. 无 `requestIdleCallback` 的浏览器在 1,200 ms 后执行 fallback，预取可能略迟；它是
   best-effort，不影响导航正确性。
2. JS 前骨架固定浅色，见 P3-2。
3. 一部分回归锚是源码 regex，纯格式化可能触发误报；运行态行为另有真实浏览器 E2E 覆盖。

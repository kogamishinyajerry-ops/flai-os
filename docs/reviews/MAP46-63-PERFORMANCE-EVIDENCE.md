# Map #46 / Task #63 性能低悬果证据

基线：`origin/main@c5df9f3c7d407f0b5237cce58ba03900a93dff86`。施工分支：
`kimi/map46-63-perf-low-fruit`。本记录只覆盖 GuidePage 拆包、JS 前静态首屏和
现有路由的 speculative prefetch；不改 API、持久化格式、路由目的地或人工签发边界。

## 1. Bundle 前后对表

同一台机器、同一份依赖，用 Vite manifest 递归计算入口/路由闭包 gzip：

| 指标 | before | after | 变化 |
| --- | ---: | ---: | ---: |
| 同步入口 JS | 136,490 B | 137,922 B | +1,432 B（+1.0%） |
| 同步入口 CSS | 20,674 B | 20,674 B | 0 |
| Guide 路由闭包 JS | 206,266 B | 180,009 B | -26,257 B（-12.7%） |
| Guide 路由闭包 CSS | 34,228 B | 28,070 B | -6,158 B（-18.0%） |
| Today 路由闭包 JS | 144,178 B | 142,087 B | -2,091 B（-1.5%） |
| Today 路由闭包 CSS | 22,301 B | 22,050 B | -251 B（-1.1%） |
| 真实动态 view 路由 | 8 | 8 | 不变 |
| 异步组件子 chunk | 0 | 5 | +5 |

同步入口增加 1,432 B 是共享路由 loader、去重和 idle/hover 控制的真实成本，未隐藏；
目标 Guide/Today 路由闭包均净下降。既有预算阈值完全不放宽。预算脚本现在只把
`src/views/` 计入动态路由数，异步组件不能把路由退化顶成假绿。

- [before 原始 manifest 计算结果](map46-63-performance-shots/chunk-budget-before-c5df9f3.json)
- [after 原始 manifest 计算结果](map46-63-performance-shots/chunk-budget-after.json)
- [前后 chunk 对比图](map46-63-performance-shots/06_chunk_comparison.png)

## 2. JS 前静态首屏

`index.html` 内只放内联 HTML/CSS/SVG：六瓣品牌标、`FLAi-OS`、
`二所工程智能体运行底座` 和两条静态骨架。无外链资源、无脚本进度、无动画；
Vue mount 后原子替换同一个 `#app`。

- [before：阻断 main.js 后为空白](map46-63-performance-shots/01_before_blank_boot.png)
- [after：阻断 main.js 后仍有品牌骨架](map46-63-performance-shots/02_after_branded_boot.png)
- [after：Vue 挂载后骨架已被产品登录门替换](map46-63-performance-shots/03_after_app_mounted.png)

## 3. Prefetch 只预取模块，不改变产品状态

生产壳层复用 router 的同一组 loader：空闲时预取 `/today`，主导航和“我的贡献”
在 hover/focus 时预取。缓存对并发和完成态去重，失败会清缓存，让真实导航重试。
预取只触发动态 import，不调用业务 API，也不改变 URL。

UI Lab/DEV fixture 在任何 import 调度前 fail-closed：实测没有 Today/Me view 请求。
真实 FastAPI 登录栈中，Today 模块在点击前请求 1 次、点击后仍为 1 次；hover Me
请求 1 次且 URL 不变，随后 `/today` 正常可达，浏览器 `page_errors=[]`。

- [UI Lab 无预取截图](map46-63-performance-shots/04_ui_lab_no_prefetch.png)
- [真实 Performance API 网络瀑布](map46-63-performance-shots/05_prefetch_network_waterfall.png)
- [开发态原始 resource timing](map46-63-performance-shots/prefetch-network-dev.json)
- [真实认证栈断言](map46-63-performance-shots/prefetch-real-stack.json)
- [真实栈点击后 Today 页面](map46-63-performance-shots/07_real_stack_today_after_prefetch.png)

## 4. 验收状态

- `frontend/node --test`：306 passed / 0 failed。
- `npm run build`：通过。
- `npm run check:bundle`：通过；8 个动态 view 路由、5 个异步组件子 chunk。
- `frontend/e2e/ui_lab_acceptance.py`：通过；拆包后的 DOM 锚点改为等待真实异步组件。
- `frontend/e2e/m6_guide_acceptance.py`：21/21 通过。
- `frontend/e2e/batch_b_today_acceptance.py`：12/12 通过。
- 全量 `scripts/verify_all.sh`：`EXIT=0`。第二个全新隔离副本
  `/tmp/flai-os-63-verify2.frCDyo` 只排除 `.git`、`node_modules`、`dist`，保留
  `data/`、`logs/`；构建、预算、1800 passed / 2 skipped pytest、306/306 Node
  和 21 个浏览器验收脚本全部完成，汇总为“失败（无）”。

第一次隔离全量在冷 Vite 首次优化 Asset Builder 依赖时暴露 frame detach：旧 helper
已拿到可见锚点，但优化重载随后替换 iframe。该失败没有以复跑掩盖；先在第三个全新
冷依赖副本复现并修改 helper，使其在异步锚点连续稳定且 frame 未替换后才返回；独立
冷启动 UI Lab 随后通过，第二次全量隔离再覆盖并通过同一场景。

# open_design_candidate_agent

第一条 Open Design 可信接缝：以仓内锁定、`mock=true` 的 HTML/SVG fixture 验证
FLAi-OS 能把自身设计 SSOT 投影为稳定的 `flai-design-reference-package/v1`，并按
Open Design 的生产形状 `create_project → start_run → get_run → get_artifact` 获取候选。

这里的 HTML/SVG 是本次实现**手工编写的 machine-only protocol contract fixture**，
只给自动化测试咬合协议与哈希。它们不是 Open Design 生产 daemon 的真实生成结果，
不是产品 UI 资产，也不是本轮视觉 QA 结论；不得在产品界面渲染、采纳或发布。人工
放行本任务只表示协议证据已复核，不表示这些手工图形获得视觉采纳。

它只产生候选与 provenance，不发布、不改前端源码、不替代人签。正常执行结果由
Runtime 停在 `waiting_review`；只有工程师通过既有审核动作才能转出。

## 产物

- `flai_design_reference_package.json`：App.vue token allowlist + 三份设计 SSOT 源哈希；
- `flai-task-review-candidate.html` / `.svg`：手工 machine-only 协议夹具，无 script/iframe/外链，禁止产品渲染/发布；
- `open_design_candidates.json`：候选索引；
- `open_design_provenance.json`：fixture/request/response/package 哈希与协议轨迹；
- `OPEN_DESIGN_REVIEW.md`：mock 水印与人工审核清单。

生产 daemon 接入不在本包范围内，必须新建单独 tool id，不能把 fixture 的 `mock`
原地改成 false。

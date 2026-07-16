# 批次三（desktop-restudy 深度打磨）审查记录

> 契约：docs/design/UI-DESKTOP-CRAFT.md §八-§十。触发：owner「参考
> agent-ui-design/design-sync/desktop-restudy/ 深度打磨 UI UX」（2026-07-15）。
> 设计源：desktop-restudy 28 张样张卡（f279b9c），主控亲读 FLAi-OS 相关 17 张。

## 一、改动面

| 文件 | 改动 | G 项 |
|---|---|---|
| `frontend/src/utils/format.js` | 新增 `formatClockCompact(iso, todayKey)`（同日 HH:MM/跨日 MM-DD HH:MM/非法「—」） | G4 |
| `frontend/src/composables/useTodayKey.js` | **新文件**：响应式本地日界 composable（CompletionSeal 午夜翻页修复 R1-P3 的 SSOT 化） | G4 |
| `frontend/src/components/WorkLog.vue` | 头行贴地形态（去盒化→上下发丝线+灰字 500）；头行三段式 + 零值豁口（N=0 无「条事件」段） | G1 G2 |
| `frontend/src/components/StatusCenter.vue` | 收件箱 1s ticker（抽屉开存活/关即清）；运行中行活跳时长「· 已 X」；待签/最近落定行紧凑时钟（todayKey 由 ticker 派生） | G3 G4 |
| `frontend/src/components/CompletionSeal.vue` | 落定时刻改走 formatClockCompact + useTodayKey（输出逐字不变，F4 探针=回归网） | G4 |
| `frontend/src/views/MePage.vue` | 任务行 locale 全量串→紧凑时钟（孪生面，3-lens 命中修复） | G4 |
| `frontend/e2e/craft_desktop_acceptance.py` | ⑩ 系列 9 探针（G1×2/G2×2/G3×2/G4×3）+ 夹具（task_d 事件、task_g 零事件完成态） | 验收 |
| `frontend/tests/format_display.test.mjs` | formatClockCompact 四象限 2 测试块 | 验收 |

反采纳（样张真理有意拒绝，见设计文档 §十）：问题卡推荐徽 / 中断 after-Xs
时长 / 零彩色选中双灰 / workflow 进度点行 / rail 渐隐 mask（批次二裁决维持）。

## 二、验证证据（2026-07-15 本机实测）

- **构建**：`npm run build` exit 0。
- **node 纯函数核**：`node --test` 18 pass 0 fail（含 formatClockCompact 同日
  补零/跨日/非法/缺失新块）。
- **craft 套件**：65/65 ALL GREEN（批次二 56 + ⑩ 系列 9）。
- **verify_all.sh 全量**：预孪生树 20 步全完成、聚合 226 PASS / 0 FAIL、
  exit 0（m10 本轮未复现历史 flake）；孪生面落地后终树全量重跑见下方
  收敛判定补记。
- **tamper 自证（5 处 6 咬，全部 cmp 校验还原）**：

| # | 篡改 | 期望咬合 | 实测 |
|---|---|---|---|
| T1 | `.worklog-head` 盒装样式回种（bg+border+radius） | ⑩G1 贴地谓词 | ✅ 咬（bg=rgb(247,244,236)/radius=10px 全暴露） |
| T2 | 零值豁口拆除（恒拼 `· ${n} 条事件`） | ⑩G2 零事件头行 | ✅ 咬（「已处理 42 秒 · 0 条事件」现形） |
| T3 | StatusCenter ticker 冻结（interval 空转） | ⑩G3 断轮询递增 | ✅ 咬（3.3s 窗口仅 1 个读数） |
| T4 | rowClock 换回 locale 全量串 | ⑩G4 待签行+落定行 | ✅ 双咬（`2026/7/15 22:33:24` 斜杠现形） |
| T5 | MePage 行时间换回 locale 串 | ⑩G4 /me 孪生行 | ✅ 咬（`2026/7/15 22:43:40`） |

- 篡改运行均无旁伤（其余探针全绿），咬合=探针与实现真耦合的实证，非全绿装饰。
- 时区注记：本机 TZ=UTC-7，固定 UTC 夹具跨日渲染（如 `07-14 23:00`）由
  regex 可选 MM-DD 前缀吸收——探针对运行时区不敏感（同批次二 F4 口径）。

## 三、3-lens 对抗审处置

| # | 镜头 | 发现 | 处置 |
|---|---|---|---|
| 1 | paradigm | **MePage 任务行残留 locale 全量串**——与状态中心行同为扫读面，同一行级语法漏孪生点（批次二 F6 同款教训） | **修**：本批收敛同 SSOT + ⑩d 探针 + T5 tamper |
| 2 | paradigm | 任务详情 rail「任务信息」卡/工作日志时间轴仍 formatTime 全量精度 | **有意保留**：rail/时间轴=检视面（Codex rail 同哲学），紧凑时钟只收敛扫读面——写入设计文档 §九 G4 边界说明 |
| 3 | trust | G2 零值豁口把「0 条事件」信息藏掉是否失诚 | **判合规**：展开态 EmptyState「暂无事件」按需可见，折叠行零值=噪音非信息（cd-bg-tasks-panel 规范）|
| 4 | craft | StatusCenter ticker 按「抽屉开」而非「有运行行」存活 | **有意**：todayKey 日界在 peek/空收件箱下同样需要跨午夜反应性；1s 空转成本可忽略，关闭即清 |
| 5 | trust | 今日页待签行「运行 X」以 now 锚定，任务停跑等签期间数字仍缓涨（B-T3 审 P3 既有措辞裁决） | **不动，登记 retro**：终点锚应为停跑时刻（review_requested），属既审面语义翻案，交回顾队列 |

## 四、Codex 治理审（native Pro gpt-5.6-sol ultra，cap=3）

| 轮 | 通道 | 结论 | Finding | 处置 |
|---|---|---|---|---|
| R0 | `codex review --uncommitted`（`~/.codex` 默认=gpt-5.6-sol ultra，用户 20x Pro） | **无可行动正确性问题** | 0 | — |

- R0 审查方自跑验证：production build + 前端 18 单测 + Python 语法检查 +
  **65 项浏览器验收全量重跑**全部通过（异源独立执行，非采信我方自报）。
- R0 即收敛，round cap 3 未动用。

## 四'、集成事件（rebase onto 新手首跑批）

推送时发现 origin/main 已被「新手首跑批」（N 系列 15 commit，自带 Codex
R0-R2 治理审）推进——本批 rebase 到 a75d4b9。冲突与集成修复：
- `m8-workbench-shots/2_console.png` 双方重生成的二进制证据冲突——取上游，
  联合树 verify_all 重生成为最终真相。
- **集成破绽（主动 grep 咬出）**：上游 N8 授权链行在 peek 签发卡模板使用
  `formatTime`，本批曾将其从 StatusCenter import 移除（行级时钟收敛后原以为
  零消费）——Vite 不校验模板绑定，运行时渲染待签速览必崩。修复=恢复 import
  并注明分工（授权链=检视级全量时间戳，行级=紧凑时钟——恰好印证 G4 边界）。
  m10 套件在 peek 签发卡上有真断言（.peek-approve 可见+文本+点击），联合树
  verify_all 亦必咬中；主动扫描提前一轮发现。
- 该集成修复为 1 行 import 恢复（回到上游既有行为），不改本批任何语义——
  不触发新一轮治理审；联合树全量 verify_all 为集成正确性证据。

## 五、收敛判定

- 终树 `verify_all.sh`：20 步全完成、聚合 227 PASS / 0 FAIL、exit 0
  （含 craft 65/65；m10 历史 flake 本轮未复现）。
- tamper 5 处 6 咬全部命中且无旁伤，还原经 cmp 校验。
- 3-lens 5 发现：1 修（MePage 孪生面）、3 有意保留（写入契约）、1 登记
  retro（今日页待签行 elapsed 终点锚语义）。
- Codex R0 零 finding 收敛。EAR/key 扫描干净。**判定：批次三收敛，可合并。**

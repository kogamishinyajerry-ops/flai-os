# 美化大批次「夜航图纸」对抗审记录（ultracode，Claude × Codex 5.6 Sol 联合开发）

> 触发：owner「继续推进优化，配合 5.6 sol 进行大幅提升美化 ultracode」。
> 证据 SSOT=四份拉片 memory（Claude Desktop/Codex 桌面实机 74 张 + 官方视频综合）。
> 三主件：暗色主题「夜航图纸」/ 对话空态四意图卡 / 全站 token 化收口。

## 编排与分工（谁写另一方审）

- **前置审计**：Workflow 三镜头（对话轴 / 任务台 / 暗色工程侦察）——产出 27 findings
  + 94 条暗色风险点。关键发现：①`var(--surface)` 全仓未定义既有 bug（plan-card
  实际透明）②theme.js 默认跟随系统 → **e2e 必须 pin color_scheme=light**（否则
  CI 环境 prefers-color-scheme 漂移让颜色断言集体静默失败——canon 级）③EP 暗色
  变量面缺口横跨每个 el-* 组件④JS 直出 hex（categoryColor/LEVEL_COLOR）CSS 层
  覆盖不到（既有类型色标体系，判保留+暗色截图复核）。
- **主控亲写**（共享热点）：App.vue 全 token 手术（亮色新 token 20+ 与
  `:root[data-theme="dark"]` 暗色块 ~130 行）、stores/theme.js、
  stores/quickSwitcher.js、侧栏脚部（⌘K 入口+主题三段切换）、会话行 hover
  时间戳、6 套 e2e pin、意图卡图标接线。
- **Codex 5.6 Sol lane（写，主控亲核）**：IntentGlyph.vue 五枚手绘墨线图标
  （disk 性能包线/fta 故障树/knowledge 书+放大镜/collab 协作网/logic 状态机），
  currentColor+var(--clay) 唯一点缀——亲核 APPROVE。
- **Workflow 三 builders（写，双镜头+Codex 审）**：guide（GuidePage 意图卡/
  气泡 token 化/placeholder 分化/hover 时间戳/hint 门控/夜航问候）、detail
  （TaskDetail 产物行数 num-token/待你签发 pill/tag 过渡/meta 卡片化 +
  TaskCreate/WorkbenchSession 收口）、chrome（StatusDock/StatusCenter/
  QuickSwitcher store 化/burst.js 运行时读 token/artwork 漏网 fill）。

## 对抗审三路裁决

| 审 | 裁决 | Findings 与处置 |
|----|------|----------------|
| trust/色锁镜头 | APPROVE | 五槽暗色值程序化实测：色相漂移 0.44°–4.92°（全 <15°）、明度统一提亮、对比度 4.60–6.52 全过 AA-text——「只做明度适配」声明与测量吻合。P2=--ink-faint 暗值 3.49:1 差 AA-text → **已修 #8a8174**（亮色 2.52:1 为既有债，另记 ticket 不混入本批）。P3=trust-fail 暗值余量最薄（4.60）备案。四意图卡 categoryColor 判定=既有类型色标体系（0577196 起）非新开槽 |
| regression 镜头 | APPROVE | QuickSwitcher store 化副作用链逐行等价、createdAt 空值路径安全、e2e 引用独立 grep 复核零命中（不轻信 builder 报告）、burst fallback 兜住空串。P3=field-error 用 --trust-fail 是否语义拉伸——与前轮审计镜头「两红并存是漂移」**相左，主控终裁保持**：表单错误红与任务失败红上下文无误判空间，一套红可维护 |
| Codex 5.6 Sol 异源 | CHANGES_REQUIRED | P2=EP 语境四族暗色只覆盖 base+light-8/9，danger 按钮 hover/plain tag 边框（light-3/5/dark-2）继承亮色奶油值 → **verbatim 落修**：四族全梯度 color-mix 朝暗底混 |

## 验证

- verify_all 八步门全绿 ×2（落修前后各一轮，6 套 e2e 44+ 断言含 pin light 后全存活）；
- 双主题实机截图目检（对话 hero+意图卡 / 任务台三栏，亮暗各一套）：暖炭画布成立、
  clay 锚保持、到席灯语义色暗底可辨、空态插画浅线稿暗底可读（无需重画）；
- IntentGlyph 构建独立验证 ×2（Codex 自跑 vite build）。

## 遗留

- 亮色 --ink-faint 2.52:1 既有对比度债（本批只修了暗色）；
- categoryColor/LEVEL_COLOR JS hex 暗色截图复核通过，token 化递延；
- particleField.js 零调用方（死代码），未投资暗色适配；
- Codex MCP server 仍超时（本批全程走 codex exec CLI，通路稳定）。

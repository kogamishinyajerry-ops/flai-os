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

## 追批：W13/W14 新拉片经验注入（同日）

agent-ui-design W13 桌面证伪轮 + W14 CLI 轮（memory 2026-07-11 更新）逐条裁决：

| 经验 | 裁决 | 落地 |
|------|------|------|
| W13 证伪「工具聚合 chips」——Codex 真实=灰色纯文字聚合行 | **采纳** | WorkLog 徽章 chip → .worklog-toolline 纯文字行（聚合逻辑零动；mock amber 徽=诚实标注保留贴对应工具旁） |
| W13 盲区方法学：保亮度换色相钻过快照，色相轴必须探针 | **采纳** | m8_workbench 增⑥暗色探针：画布 --page-bg 暗值 + completed 到席灯 --ink-soft 暗值颜色级断言——暗色块从零断言补到有咬合 |
| W13 时态双态（过去式纯灰零图标 vs 现在时+星标） | 已对齐 | WorkLog 现状核对通过（work-pulse-dot 进行时 / 纯文字过去式摘要），零改动 |
| CLI ⏺/⎿ 悬挂缩进、✻ 俏皮盖章、模式循环色 | **不搬** | TUI 单画布语法不跨 shell 搬进 GUI（kit9 教训「GUI 分层 vs TUI 单画布=范式差」）；盖章已用 Codex 桌面式横线 |
| kit9 defer：Claude 暗色气泡实测比画布暗（与三档暗阶反向，两源未裁决） | **持有** | 本仓暗色气泡亮于画布（常规做法）；等 kit 裁决后再议，不跟未决证据摇摆 |

## 追批 2：身份门 + 文本减重（同日，owner「首页文字太多/要登录鉴权/文本太重」）

- **WelcomeGate 身份门**：本地工作身份（非认证——真鉴权需后端 session/内网
  SSO，递延 owner 批）。gpt-image-1 工牌插画（白底生成+PIL 去底）+Codex 写
  组件（主控亲核 APPROVE）。一次具名全站免问；侧栏身份行可改名。
- **文本减重**（Claude 精髓=留白克制，信任靠交互不靠说教）：hero 删三行
  价值主张/名字框/starter-hint，只剩问候+一句主标题；composer 政策句+诚实
  地板两行合一（m6 锚「导引不会替你创建」字面保留）；意图卡 tip 收进悬浮。
- **e2e 契约重立**：6 套注入身份（add_init_script / orchestrator 双名走
  evaluate+reload）；m6 新增 ⑧/⑧'/⑧'' 三断言（13 断言）。
- **主控自审出真 P1**（送审 prompt 中即点出并先行修复）：门是 overlay、
  GuidePage 门下已挂载捕获空身份，门过不重挂 → 第一条消息即撞兜底。
  修=identityReady 参与 page-turn key（门过整页重挂）；⑧' 咬合+tamper
  实证（拆 key 修复 → e2e 死在 waiting for .user-bubble → 复绿）。
- **Codex 异源审 CHANGES_REQUIRED 三条全处置**：P1 存储失败死循环（隐私
  模式 saveName 静默失败仍 emit done）→ identity.js 内存态兜底+saveName
  返回持久化布尔+门内如实提示「本次会话有效」+⑧'' 回归咬合；P2 StatusCenter
  根级不重挂、reviewer 门前空快照 → onOpen 懒补；P2 overlay 非真模态 →
  :inert 隔离主 shell 与状态坞。**跨 tab 身份漂移判设计选择**（会话身份
  延续，不做 storage 事件重开门——打断工作比边缘不一致代价高），注释+
  此处双记录；QuickSwitcher 热键面板 z 序低于门，残余无害记录。
- 验证：verify_all 八步门全绿（m6 13/13 逐断言实证）。

## 遗留

- 亮色 --ink-faint 2.52:1 既有对比度债（本批只修了暗色）；
- categoryColor/LEVEL_COLOR JS hex 暗色截图复核通过，token 化递延；
- particleField.js 零调用方（死代码），未投资暗色适配；
- Codex MCP server 仍超时（本批全程走 codex exec CLI，通路稳定；
  后台 dispatch 必须 `< /dev/null`——开放 stdin 会挂住等输入）；
- 暗色气泡明度方向：持有亮于画布，挂 kit9 defer 裁决。

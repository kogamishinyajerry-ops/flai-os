# Fable UI 批八可信迁移契约

> 状态：CONTROLLED MIGRATION COMPLETE
> 可信基线：`5c086338b998971aa92299d085873de900b39bb3`
> 候选只作需求与反例来源；本文件不把候选工作树认定为已验收实现。

## 1. 来源与边界

最高执行依据是仓外文件：

- 路径：`/Users/Zhuanz/Downloads/FLAi-OS_Fable5_执行任务书.md`
- SHA-256：`442bc141dbc8c79265b7963f437df5009d52a419b175cd3ed733cd146ba8baeb`
- 实测行数：1662
- 本次直接相关条款：§0、§4.2～4.5、§6、§7、§12、§13、§15、§18～19。

Fable 批八候选来自：

- 工作树：`/Users/Zhuanz/projects/aircraft-comac/flai-os-telemetry-wt`
- 分支：`feat/uiux-gap-batch8`
- 候选 HEAD：`c3767fc0891195d3d92a4794d512789360021ffb`
- 与可信基线的 merge-base：`c3767fc0891195d3d92a4794d512789360021ffb`
- 候选相对可信基线落后 10 个提交，且存在未提交实现；不能 merge、cherry-pick 或整文件覆盖。
- Claude 会话在批八 E 中途因 API 错误停止；任务 E 仍为 `in_progress`，收口任务仍为
  `pending`，没有完成 `verify_all`、最终审查、提交或推送。

可信树已经包含另一个经 DESIGN-FINAL 与 tamper 验收的“批八”——专家团队模板、
召集 gate 与 withheld 三面投影。该实现及其 `_artifacts.py` 证据隔离是不可回退前置项。

## 2. 候选 A～E 冲突矩阵

| 片段 | 产品意图 | 候选主要问题 | 迁移裁决 |
|---|---|---|---|
| A 对话呼吸 | 真 SSE、停止、首轮起题 | 无 180 秒/心跳期限；停止按钮有无效窗口；真实断连未测；会修改 gateway、Runtime、DB | 先重写协议与无效输入测试，再实现；禁止直接搬运 |
| B 寻址 | 服务端消息搜索、窗口外补齐、任务状态 chips | 在途先闪“无结果”；消息不能定位；`cancelled` 被归为“失败”；无新增浏览器验收 | 仅 B1 状态筛选进入本轮；取消独立中性。B2 搜索延期，不能把候选 LIKE 方案当完成 |
| C 产物一等公民 | 文本/xlsx 有界预览、真实 403/409 文案 | 前端先完整下载二进制再请求预览；预览失败静默；会与可信 withheld 面冲突 | 本轮按 metadata/preview-first 重做；保留 withheld，并证明显式下载前 `/download` 请求数为 0 |
| D 请签路由 | 可选点名、收件箱置顶 | 新持久字段与 task schema；触及人签路由；名册失败伪装为空；文案过诺“专属分组” | 本 Goal 不迁移；另开安全/契约变更切片 |
| E 整理小件 | 可测 Markdown、标题/归档整理 | Markdown 提取可独立验收；重命名无 UI 入口；标题需 DB/API；候选未收口 | 先迁移纯解析 SSOT；标题另随 A 的会话协议验收 |

## 3. 迁移顺序

本轮实际执行顺序以风险和依赖为准，不按候选 A～E 字母顺序整包前移：

1. **E1 Markdown 解析 SSOT**：复制 witness，红后提取实现；DOM 与视觉契约不变。
2. **C 有界预览**：先证明 sensitive、篡改、未知类型、缺失文件和超限路径；前端只调用
   `/preview`，显式用户下载之前不允许请求 `/download`。
3. **B1 任务筛选**：只在可信 `TaskConsole` 上增量实现；工作、待签、完成、失败、取消
   六组严格分离，取消保持中性。
4. **可信设计清理**：只修复已存在的未定义 token 与 QuickSwitcher focus ring，不扩张
   Fable 候选视觉。
5. **JerryAgent 合同映射**：冻结认证 username、真实 conversation、新会话目标 Agent
   三轴隔离与 accepted-only 清理要求；sessionStorage 原型因全存储故障窗中的连续 accepted
   单槽覆盖风险已撤出，本轮不宣称运行时草稿持久化。
6. **Open Design fixture 接缝**：输出确定性设计引用包和显式 mock 候选，运行成功只到
   `waiting_review`。

以下工作不在本轮伪装成已交付：B2 服务端搜索、A SSE/停止/标题、D 定向审核、会话
重命名/归档、composer 持久化，以及 Open Design 生产 daemon。它们必须各自先补公开契约与
invalid-input witness，再进入实现。

## 4. 不变量

- 人是唯一签发者；LLM、Open Design 和任何 Agent 都只生成候选，不进入判决链。
- `completed` 与 `cancelled` 保持中性；绿只给 REAL；teal 只给人签；amber 只给未核；
  红只给真失败/驳回。
- 可信 teams/withheld UI、任务状态机、签发语义和证据隔离不可回退。
- 新样式只用 App.vue 已定义 token；新增 token 必须同时有 light/dark 值与用途说明。
- 截图默认写临时工件目录；没有 `UPDATE_GOLDENS=1` 不得覆盖 `docs/reviews`。
- 每片先跑 invalid-input witness，再跑定向测试、构建与相关浏览器验收；最终跑
  `UV_OFFLINE=1 bash scripts/verify_all.sh`。

## 5. 新鲜基线审计（2026-07-19）

使用隔离数据库与 Codex 应用内浏览器检查 `5c08633` 当前真实页面：

- desktop light/dark、390×844 light/dark、登录门、composer focus ring 均已实拍；
- 核心视觉语言、纸墨层级、clay 主操作与焦点环成立；
- 390px 首屏因 onboarding 卡过长，核心 composer 被压到折页以下；
- QuickSwitcher 输入框源码移除 outline 且无替代 focus-visible；
- teams/EvidenceList 存在未定义 token（`--surface`、`--font-mono`、
  `--surface-sunken`）；
- reduced-motion 有既有全局与 E2E，但若干 hover 位移未被真正清零；
- 系统没有统一 disconnected 投影，主要页面各自显示请求失败/自动重试。

审计截图只保存在本次 Codex visualization 工件目录，不写入金图目录，也不作为通过证明。

## 6. 下一开发方案：可信 UX 与设计生成主线

后续不继续按候选 A～E 整包搬运，而按公开合同、风险和可机械验收性切成九个窄阶段：

| 阶段 | 目标 | 先决条件与机械退出门 |
|---|---|---|
| P2.1 断连诚实度（已实现，待全量门） | 借鉴 JerryAgent，把 `connection`、`lastSuccessAt`、旧快照提示与 task exact cursor 投影到现有阅读轴 | 旧 task/event 响应不改；additive live-snapshot 提供 gap 检测；冷断连零假数据、暖断连标旧、重连 sequence-zero 覆盖，并有 Node + contract + E2E witness |
| P2.2 视觉信任债 | 收口 Element Plus 旁路语义色、Agent 类别色暗色对比和残留 reduced-motion 位移 | 不新增信任色；light/dark 对比可测；desktop/narrow/focus/reduced-motion 四态通过应用内浏览器复核 |
| P2.3 结构化问题 | 为普通澄清建立 Question/Answer 合同 | Question 与 task review API、状态机、权限完全分离；过期/重复回答 fail-closed |
| P2.4 服务端寻址 | 在 B2 中实现会话/任务/产物可定位搜索 | 先以唯一 `username` 建 owner 合同与迁移 ADR；再决定 FTS5、分页、权限过滤和 inputs/output filename 范围 |
| P2.5 具名审核收件箱 | 把“点名请签”做成真正的收件箱而非全量排序 | 所有 task 创建入口同一契约；候选审核、人签与发布批准仍是三个状态；同名 display name 反例必须拒绝 |
| P2.6 会话生命周期 | 标题、重命名、归档和历史分组 | owner 轴完成迁移；API/UI/审计事件和并发更新契约均有无效输入测试 |
| P2.7 Open Design 生产 adapter | 新增独立 `mock=false` daemon tool，真实生成统一候选 | loopback、有界轮询、路径/内容清洗、exact provenance；成功只到 `waiting_review`，不写源码、不自动晋升 |
| P2.8 候选比较与 promotion | 同 viewport/state 比较现状与真实候选，显式晋升资产 | 不执行不可信 HTML；人工选择与发布批准分开；exact hash、明确目标、可回退、普通 E2E 零金图覆盖 |
| P2.9 Windows/离线运维 | 让 Open Design sidecar 达到内网交付标准 | `.sh/.ps1` 成对、固定版本、离线包、health/status/stop、端口冲突和异常退出演练全部通过 |

推荐严格按 P2.1→P2.9 推进；只有 P2.1 与 P2.2 可在互不重叠文件上并行。每阶段单独提交、
单独验收，上一阶段未绿不得借下一阶段扩大范围掩盖失败。

## 7. 本轮收口

已受控迁入并验收的只有以下窄片：

- Markdown inline 解析 SSOT 与中文 strong-marker 回归；
- text/markdown/json/xlsx 有界 preview-first，密级、完整性、未知类型与超限均显式失败或截断；
- TaskConsole 六组状态筛选，`cancelled` 独立中性，冷失败不伪造零结果；
- 三个证据消费面的 unavailable/truncated/withheld 事实并显；
- 未定义 surface/mono token、QuickSwitcher focus ring 与本次触及 hover 的 reduced-motion 清理；
- Open Design candidate-only machine fixture 接缝。

候选中的 SSE/停止、LIKE 搜索、display-name 判权、点名请签、标题/归档与五张被覆写截图均
未迁入。JerryAgent composer persistence 原型也在终审故障注入后撤出。最新稳定 cut 快照的
定向证据为：后端 137/137、前端 Node 49/49、M6 14/14、frontend build 通过、双轴终审无
P0–P2；最终发布门仍以 `bash scripts/verify_all.sh` 的当次退出码为准。

# FLAi-OS 交互范式宪法 ——「状态来找人」（SSOT）

> 触发：owner 判定「即使我作为设计者，都要看导航指引才知道去哪里发起请求、
> 看工单、监控进度——这本质上是设计上的失败」。本文档把 Claude Desktop /
> ChatGPT.app 实机拉片（[[reference_agentic_ui_live_traces]] 74 张证据）与
> /team conversation-spine 已验证哲学落成 FLAi-OS 的 IA 宪法。
> 与 MOTION-SYSTEM.md（动效层）、信任色锁、诚实地板并列为前端三宪法。

## 七条祈使句（违反=废）

1. **对话是主轴**：一切工程活从导引对话发起；对话线程即督战台——召集的成员
   任务状态直接内联在方案卡里活着，不逼人换页面看进度。
2. **状态来找人**：全局状态坞（StatusDock）常驻每个页面右上——「运行中 N /
   待你签发 N」自己浮到眼前；点开即状态中心。用户永远不需要记住「去哪看」。
3. **渐进披露四级**：pill（一眼计数）→ 状态中心（分组清单）→ 任务速览
   （产物+签发+折叠日志）→ 完整页（深链全貌）。每级默认最小，点一下多一层。
4. **签发内联**：人签动作（批准/驳回）在任务速览里滑出完成，任何上下文
   不跳页闭环；速览里同样「先看产物再见动作」（信任核心 P0-2 顺序不变）。
5. **页面降级为深链**：路由全部保留（可分享/可刷新/可回退），但导航不再是
   找到功能的前提——当前一级导航只保留「对话｜今日」，任务、门户与工作台
   继续作为可分享深链存在。
6. **真流非表演**：状态坞计数/收件箱条目/速览动态全部来自真实轮询数据；
   信任色锁（clay 工作/amber 待签/teal 人签/绿仅真实/completed 中性）与
   诚实地板全承袭，pill 数字绝不估算。
7. **键盘与退出**：⌘K 检索直达一切；Esc 层层退出（速览→中心→关闭）。

## Phase 1（本批交付）

| 件 | 文件 | 说明 |
|---|---|---|
| 状态源 | `src/stores/statusCenter.js` | 模块级 reactive 单例（零新依赖）：open/view/taskId + openInbox/openTaskPeek/backToInbox/close |
| 状态坞 | `src/components/StatusDock.vue` | fixed 右上：运行中（clay 脉动）/待你签发（amber）计数 pill + 常驻入口钮；5s 链式轮询 listTasks 一次派生两数 |
| 状态中心 | `src/components/StatusCenter.vue` | el-drawer 双视图。inbox=待你签发/进行中/最近完成三分组；peek=速览（状态带→产物预览→内联签发卡→折叠 WorkLog→模型消耗→打开完整页）；打开期间 3s 链式轮询，destroy-on-close 保证关闭时零 DOM（不污染 e2e 选择器） |
| 对话轴督战 | `GuidePage.vue` | orchestrate 方案卡的 agent 卡内联真实任务状态 chip（该会话已召集时），点击开速览 |
| 工作台接入 | `WorkbenchHome/Session.vue` | 既有导航点击零改动（e2e 锚点），additive 增「速览」次级入口 |
| 空态插画 | `artwork/InboxZero.vue` | Codex 绘制：清空的收件盘（漫画墨线） |

## Phase 2a（已交付）——对话轴内闭环（owner 拍板双 Surface 方向后第一刀）

> 2026-08 SSOT 校正：本节“双 Surface”记录的是当时演进阶段；当前真实 App
> 已收敛为「对话｜今日」一级导航，任务台退为深链。后续实现不得据历史描述
> 把任务台重新放回一级导航。

Owner 判定 Phase 1 装饰层不改变骨架认知，拍板重构方向：**双 Surface**
（对话轴=Claude Desktop 式零跳页 / 任务台=Codex 式三栏），分批推进。
方案示意图=`paradigm-phase2-sketches/`（骨架对比/对话轴/任务台三栏）。

- **召集回流（零跳页核心）**：GuidePage 召集带 `back=chat`，创建页提交成功
  回流 `/?c=<conv>`——任务卡在对话流里原地亮起，不再甩去详情页。
  WorkbenchSession 召集不带此参数（m8_collab_chain 详情页契约不动）；
  conclude_after（单 Agent 归档）仍走详情页。
- **督战条升格活任务条**：waiting_review 露 amber「审阅签发 →」强 CTA；
  completed 且真有产物长「N 件产物 · 查看 ↗」锚点行（Claude Artifact
  卡片锚点哲学）——点击直开速览（产物+签发同面板）。
- **restoring 门控**：?c 深链落地时 getConversation 在途窗口不渲染可交互
  空态 hero、send 早退（防「假起手」误建新会话——双镜头 P2 咬出）。
- **回归网**：新增 e2e `m9_guide_loop_acceptance.py`（9 断言：回流 URL/
  hero 不闪/督战条/锚点行/速览直达/back=chat 不越界），入 verify_all。

## Phase 2b（已交付）——骨架手术

- **导航塌缩**：三入口最终收敛为「对话 | 今日」（App.vue NAV）；
  /workbench 重定向 /tasks 保深链；WorkbenchHome/TaskHistory 退役删除。
- **任务台三栏**（views/TaskConsole.vue）：左=任务列表（待签发 amber 组
  置顶 + 状态徽章随 5s 轮询原地切换 + 诚实脚注）；中+右=TaskDetail 完整
  复用（它自身的「主列+来源栏」嵌入后合成 Codex 三栏）。/tasks/:taskId
  旧深链全兼容；page-turn 靠 meta.pageKey 免整页重挂，中栏 :key=taskId
  重建（TaskDetail 补 disposed 守卫防 :key 重建竞态下的僵尸轮询）。
- **门户降级**：Agent 门户退出一级导航，降为 composer 内选择器 popover
  （点选只填草稿绝不代发；错误/零态语义分离；/portal 深链保留，hero
  提示行给出可发现性线索）。
- **e2e 契约重立**（与骨架同批原子交付）：m8_workbench 重写为双 Surface
  契约（含 completed 到席灯=中性墨的信任色锁**颜色级**真咬合断言——旧断言
  只查可见性=声明超出证据）；m8_collab_chain ⑦ 改 redirect+侧栏断言；
  m6 ①锚改 hero 主标题。八步门（6 套 e2e）全绿。

## Phase 2c（已裁决）——活性细节：交付三 / 撤一 / 递延一

**已交付**：

- **完成未读**（R3 落点②，WorkbenchHome 退役后的能力回归）：任务台左栏
  终态任务（completed/failed）未读标记=**墨色空心环+名字加粗**双通道。
  原案「蓝点」与初版实现「clay 点」均否：蓝不在色板（开新槽须 owner 拍板），
  clay 的锁定许可仅「工作/进行/选中」——未读是注意力信号非信任信号，不占
  五槽，用形状+字重承载、零新色（异源镜头 P1 咬回）。锚=baseline（首次进
  任务台锚定，此前存量不标——「不标 ≠ 没有新进展，是无证据不标」）；打开
  详情/速览、亲手签发、以及打开期间状态翻面均记 seen（绝不对「刚亲手签发/
  正盯着看」的任务回头亮未读——宁可少标不虚标）。`utils/lastSeen.js` 任务级
  API + 200 条容量淘汰。waiting_review 不进未读——amber 置顶组已是强 CTA，
  双信号即噪声。e2e 真咬合（亮/灭两断言）；waiting_review→签发→completed
  不复亮链无 e2e（hello_agent 直落 completed，人工推演+四挂接点覆盖，缺口
  记录在 review record）。
- **轮询共享缓存**（`stores/taskFeed.js`）：StatusDock 与任务台左栏原本各拉
  各的 listTasks(limit=100) 5s 链 → 模块级单例引用计数订阅，一条链一份数据。
  诚实口径/失败自愈/无数据不装有数据全承袭。StatusCenter 打开期间的 3s 短时
  链**不并入**（打开才存在、节奏不同，强行合并搅乱两边语义）。
- **徽章切换微动效**：到席灯颜色随轮询翻面时 --motion-med 渐变（reduced-motion
  关闭）。

**撤项（不做的决定）**：

- 任务 MRU 切换 ^Tab——Ctrl+Tab 是浏览器保留快捷键（网页拦截不到），且
  ⌘K QuickSwitcher 已含任务检索直达，需求实质已覆盖。

**递延（需后端契约批）**：

- 中断-恢复=时间线一等条目+常驻 continue（R4 落点②）——后端无 retry/resume
  端点；「重跑」语义（新任务复制 inputs vs 原任务复位）牵动审计链完整性，
  必须先立后端契约再做前端，不在纯前端范式批内拍板。

## Phase 2d（本批）——本体驱动的 Agent Shell

- **唯一语义源**：`AgentShellCatalog.snapshot()` 从 Agent / Tool / Knowledge
  Registry 的当前快照生成只读、版本化 `agent_shell.v1` 投影。前端不再分别
  猜测分类、启动方式、密级缺省、工具与知识引用状态。
- **任务上下文轨道**：1440px 及以上在对话主线右侧保留 296px 轨道；375px
  继续复用 composer 内 Agent 入口和左右 12px 安全区弹层。它呈现工程对象、
  工作类型、候选 Agent、引用与人工/依据门，选择只加入草稿，绝不自动发送、
  建任务或签发。
- **Portal 同源**：能力地图只渲染服务端 facet 和诊断摘要；治理、评测、团队
  召集仍留在 `/portal` 深链，不把门户重新升为一级导航。
- **领域后置**：CFD、CAD、系统计算等不再各开壳层入口；后续 Agent Package
  通过 `classification.domain`、工具白名单、知识范围和输入输出契约批量挂接。
- **未知不归零**：未知启动方式为 `unknown`，悬空引用为 `unresolved`，密级
  缺省按 ADR-0030 显式 `internal/defaulted`；任何 malformed 投影都显示不可用，
  不伪装成“0 个 Agent”。

## 红线继承

- e2e Phase 1 零触碰（全部 additive；drawer destroy-on-close 关闭时零 DOM，
  不与 TaskDetail 的「批准放行」按钮产生选择器重影）；
- 状态中心内签发走同一 `POST /tasks/{id}/review`（人具名，fail-closed 全承袭）；
- 速览产物预览失败诚实显示错误行，绝不空白假装没有产物。

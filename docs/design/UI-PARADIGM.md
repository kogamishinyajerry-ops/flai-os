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
   找到功能的前提——Phase 2 三入口导航塌缩前，两套并存且互不依赖。
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

## Phase 2b（待批）——骨架手术

- 三入口导航塌缩为「对话 + 任务台」双 Surface；工作台/任务历史/任务详情
  三页合并为任务台三栏（任务列表 | 任务叙事流 | 输出/来源面板坞）；
- Agent 门户降级为 composer 选择器（owner 已拍板），门户页退为深链；
- **涉及 e2e 契约重立**（m8 断言「点任务行→落详情页」等），必须与 e2e
  更新同批原子交付；
- 任务 MRU 切换（^Tab）、完成未读蓝点入侧栏（R3 落点②）。

## 红线继承

- e2e Phase 1 零触碰（全部 additive；drawer destroy-on-close 关闭时零 DOM，
  不与 TaskDetail 的「批准放行」按钮产生选择器重影）；
- 状态中心内签发走同一 `POST /tasks/{id}/review`（人具名，fail-closed 全承袭）；
- 速览产物预览失败诚实显示错误行，绝不空白假装没有产物。

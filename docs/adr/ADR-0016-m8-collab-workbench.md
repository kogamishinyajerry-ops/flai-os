# ADR-0016: M8 协作工作台——导引升级为编排官 + 会话级多 Agent 协作

- 状态：已采纳（2026-07-09，owner 长愿景 + 「go」拍板立项）
- 关联：ADR-0012（interactive 运行时 / 导引）/ ADR-0013（会话事务/迁移模式）/
  ADR-0014（会话附件）

## 背景

任务书对导引的原始定位是「统一入口」。M6-M7 交付的导引只做「推荐一个 Agent +
预填草案」，而 create-task / task-history / feedback 各占一个独立顶导航入口——对
**不学「什么是 Agent」的领导/同事**（M8 目标用户：丢一个繁琐任务 + 附件，问「这活儿
怎么弄」）过度暴露了平台内部结构。owner 拍板把导引做成**真正的门面/编排官**，并把
任务相关页收编进一个「协作工作台」。

## 决策

分五阶段（P1-P5）落地，每阶段纯增量 + 全绿 + tamper 实证 + 复跑既有 e2e：

### P1 视觉地基 + IA 骨架
- 顶导航 5 → **3 个真入口**：智能导引 / Agent 门户 / 协作工作台。旧的创建任务/
  任务历史/反馈从导航撤出（路由仍在、上下文内可达）：创建从门户+导引进、反馈在
  任务详情内、历史折进工作台。
- **信任色锁**（收编自 COMACAgentPlatform，焊死纪律）并入 :root：语义色只表状态、
  绝不被装饰借用——clay=工作/进行/选中 · 绿=仅真实(REAL)结果 · teal=仅人签 ·
  红=仅真失败 · amber=仅未核/降级；装饰用色走中性暖纸阶。**关键：到席灯的
  completed 不给绿**——当前跑 mock，给绿即假 REAL（色锁纪律的活标本，抽到
  utils/format.js `taskLampColor` 单处守）。

### P2 导引升级为编排官
- 输出契约从「单 Agent 推荐」升为**计划裁决**（`<<PLAN>>` 块，取代 `<<RECOMMEND>>`）：
  - **orchestrate**：平台接得住 → 召集一个或多个真实 Agent 协作，含最终分析、待
    用户确认目标、各 Agent 分工（role）+ 预填草案、协作方式。
  - **refuse**：平台接不住（甚至不值得为此建专用 Agent）→ **显式拒绝**，给拒绝
    理由 + 残留问题 + 如何重述才可接——不硬凑。
- **确定性校验扩到每个 Agent**（LLM 边界的咬合点，宪法铁律六）：orchestrate 里逐个
  Agent 对账 Registry（真实/非 disabled/interactive/自身）+ 目标 input_schema（逐
  字段剥离）；幻觉/重复记 dropped_agents；**无任何合法 Agent 存活 → 整份计划作废
  （fail-closed）**。召集上限 5、自由文本长度/类型强制。output_schema.json 改 oneOf
  仍作返回结构 oracle。
- 传输/存储**沿用 conversations.recommendation_json 列**（opaque JSON，形状变、
  免 DB 迁移）；前端 GuidePage 按 decision 分支渲染 refuse/orchestrate 卡片。

### P3 协作会话数据模型
- **复用 conversations 表作协作会话锚点**（其 recommendation_json 已存计划快照），
  免建新表：tasks 加 `conversation_id`（迁移 #3，与 #1/#2 同 BEGIN IMMEDIATE 写锁
  块内探测补列，并发启动安全；base DDL 同步带列）。
- 导引编排官把一次会话的计划分流成 **N 个人签发任务**，各任务记 conversation_id 归
  到同一会话下。创建前校验会话真实存在（防悬空引用，先于副作用 404）**且仍 active**
  （会话 concluded 后拒新任务 409）。**注（异源 Codex R2-#3 修订，超越初版）**：初版
  为"不要求 active，concluded 仍分组"，与后续「结束协作=真只读」增补自相矛盾——已
  统一为**归档即真只读**：conclude 后不再接受新成员任务，单 Agent 流程相应改为「先建
  任务成功、后归档会话」（原先 fire-and-forget 先归档会与本校验死锁）。GET
  /conversations/{id}/tasks 会话成员视图（对 concluded 会话只读展示既有成员，不再新增）。
- contracts/task.schema.json 补 conversation_id（契约 parity gate 要求）。

### P4 协作工作台 UI
- `/workbench/:sessionId` 协作会议室：取会话（含计划快照）+ 成员任务，**三态降级**
  （loading/error/ready）。orchestrate 会话渲染目标 + 分工架构（蓝图）+ roster——每个
  被召集 Agent 显示分工，已召集则列成员任务（到席灯 + waiting_review 醒目提示，
  **复用既有 TaskDetail review 流做放行，不另造放行面**），未召集则「去创建此任务」
  从蓝图预填草案召集；进度 X/N。refuse/无方案会话诚实降级。
- WorkbenchHome 加协作会话卡片区；GuidePage「进入协作工作台」；TaskDetail「返回
  协作会话」；三态与色锁贯穿。

## 红线守恒（本 ADR 全程不破）

- **人是唯一签发者**：导引/工作台**绝不创建/召集/签发任务**——计划里每个 Agent 都要
  人在创建页补全 + 亲手提交。工作台的「召集」按钮只是把预填草案带到创建页，签发权
  始终在人。tamper 实证：移除 agent_id 白名单校验 → 幻觉召集/注入剥离/fail-closed
  三测齐红。
- **LLM 不进判决链**：LLM 只提议计划，agent_id 与预填字段一律 workflow 确定性对账后
  才算数；无合法 Agent 存活整份作废。
- **假绿=死罪**：completed 到席灯不给绿（跑 mock）；每阶段全绿都配 tamper 咬合实证。

## 影响与风险（诚实清单）

- **不是「一键召集」**：计划的 prefilled_inputs 是**部分**输入（导引只填已知字段），
  每个任务仍需人在创建页补全 required 字段——故工作台是「逐个召集」不是「一键起
  N 个任务」。这是「人是唯一签发者 + 不替用户编工程数据」的必然，非缺陷。
- **会话生命周期**：单 Agent 计划确认沿用 M6 归档（conclude）；多 Agent 会话保持
  active 作协作锚点，工作台已有**显式「结束协作」按钮**归档会话（归档后只读、不再
  召集，已建任务不受影响，复用既有 conclude 端点）；无主会话与孤儿附件 GC 仍留 V0.2。
- **echo/引用注入残余风险**（继承 ADR-0014 修订二 P1）：真实 agent_id + schema-valid
  的计划块无论来源都会产出卡片——已知残余，最终签发防线（人工创建页复核+提交）
  守住，不造任务、不造幻觉 agent_id。
- **偏离 COMAC 原设计的取舍**：flai-os IA 是 3 入口非 rail+5，故未照搬 COMAC「三窗
  +rail 五入口」，而是按 flai-os 既有卡片/暖纸/色锁范式建会话视图——照搬结构非照搬
  元素（宪法「优先复用项目现有模式」）。AgentTraceTheater 剧场/three.js/surface-
  manifest 构建门/双层镜像变量均未 port（over-engineering 之于本平台）。

## 验证

pytest 398/398（guide 编排官 +10 / 协作会话 +8，含迁移补列·幂等·往返·过滤·API
归属·悬空 404·多任务同会话）· 5 套真浏览器 e2e 全绿（M2 8/8 · M6 10/10 · M8 工作台
6/6 · M8 编排官 4/4 · **M8 全链 6/6**：导引方案→进工作台→蓝图 roster→召集→人签发→
任务归会话→首页列会话）· 三处 tamper 咬合（agent_id 白名单 / 迁移 ALTER / 悬空
引用校验）。异源 Codex 治理审见 docs/reviews/M8-review-record.md。

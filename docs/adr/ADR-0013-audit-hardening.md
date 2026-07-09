# ADR-0013: 全仓深度审计后的诚实修复与硬化

- 状态：已接受（2026-07-09）
- 背景：M6 收口后做了一轮全仓深度审计（三路独立：宪法保真度 / 任务书需求覆盖 /
  实现正确性，均证据到行）。结论：哲学保真 9/10、无可利用 P1，但存在①**文档
  说得比代码多**的诚实性漂移（导引附件虚假声明、docs/01 假目录、「原子」注释）、
  ②§18 终验 Q5（追溯数据存而不可达）/Q7（失败不沉淀）缺口、③会话路径并发/资源
  无上限、④若干「今天被 schema 掩盖、未来必咬」的 fail-open 潜伏。本 ADR 记录
  一次性修复的口径与取舍。

- 决策：
  1. **能力声明对齐实现（假绿修复）**：guide_agent 删除「接住上传附件」声明
     （V0.1 全链路不支持），改为显式 limitation + V0.2 规划；`backend/app/`
     补建 `knowledge/`、`memory/` 空槽位目录（与 `governance/` 同待遇，.gitkeep
     占位），使 docs/01 的结构声明恢复为真、且符合任务书 §3「槽位不得从架构
     删除」；conversation 落库注释的「原子」改为真原子（见 3）。
  2. **追溯读 API（§18-Q5 收口）**：`GET /api/tasks/{id}/tool_runs|model_calls|
     samples` 三只读端点——tool_version/model_name/样本自 M1 起就成败全量落库，
     此前无任何读端点，「可追溯」的数据存而不可达。会话侧：`model_calls` 新增
     可空 `conversation_id` 列（init_db 幂等 ALTER 迁移，V0.1 无迁移框架的最小
     替代）+ `GET /api/conversations/{id}/model_calls`；归因由运行时
     `_ConversationGatewayContext` 自动注入（与 job 路径 `_ModelGatewayContext`
     对称），workflow 不手工传身份。
  3. **会话单轮事务化 + 乐观并发**：workflow（含 LLM 调用）刻意留在事务外（绝
     不持锁等模型）；成功后 `BEGIN IMMEDIATE` 内复查「仍 active 且消息数未变」，
     被并发轮抢先则整轮回滚抛 409（ConversationConflictError），绝不把基于过期
     历史的回复交错写进历史；user+assistant+推荐快照原子提交，失败轮零落库
     （幂等重试语义不变）。
  4. **会话资源上限 + 终态**：发给模型的历史截窗（40 条 / 60K 字符双限，全量
     历史仍完整落库）；`content` ≤16000 字符、任务 `inputs` ≤256KB（大数据走
     附件通道）；新增 `POST /conversations/{id}/conclude`（active→concluded，
     BEGIN IMMEDIATE 防双转），前端「确认草案去创建任务」时调用——ADR-0012
     「V0.1 会话不落终态」的债就此还清。
  5. **fail-closed 硬化（今天被 schema 掩盖、未来必咬的三处）**：
     - 人工审核 gate（runtime）：truthiness → **仅显式 False 才跳过审核**
       （`is not False`）。错误方向必须是「多审」而非「漏审」——此前字段缺失
       默认跳审（fail-open），安全依赖 agent.schema.json 的 required 耦合而非
       gate 自证（宪法「安全 gate 判定一律 is True/is False」）。
     - 工具输出缺 status：`get("status","success")` 默认成功 → 契约层
       （tool.schema.json 强制 output_schema.required 含 status，注册期拒）+
       运行时（缺/非法 status 记 failed 并抛）双层 fail-closed。
     - Gateway chat 空内容 200：此前记 success（把「无回答」伪装成成功调用）
       → 折叠为 ModelUpstreamError 走统一 failed 留痕；上层空内容防线保留作纵深。
  6. **M4 红线冻结测试**：performance_disk_agent 的工具白名单一旦偏离已知
     mock 集合（即 M4 换入真实计算工具），`requires_human_review` 必须已显式
     为 True，否则测试红——「真实工程数值必须人工签发」不能只活在注释里。
  7. **失败样本沉淀（§18-Q7 最小落点）**：collect_samples 型 Agent 的失败任务
     （输入校验失败/workflow 异常/失败态）也落 samples 行（validation_status=
     'failed'，accepted_by_engineer 留 NULL）——失败输入是未来评测集反例的直接
     素材，此前只有成功路径沉淀、失败即蒸发。**完整 Memory 子系统仍是 V0.2
     槽位，本项不冒充**（docs/06 的三类记忆无运行时实现）。
  8. **其余硬化**：`_split_recommendation` 保留推荐块后文本（此前静默丢弃）；
     上传入库失败清理已落盘 blob（孤儿文件）；`busy_timeout=5000` 显式化（并发
     可用性此前隐式依赖 Python 默认）；前端事件时间轴分页拉取到取尽（批量任务
     >5000 事件时尾部 task_completed 不再静默截断）；顶层 `evals/` 补三业务子目录
     骨架（用例单一事实源仍在 agents/*/eval_cases，README 注明）。

- 影响与风险：
  - `model_calls` 列迁移采用「DDL 含列 + init_db 探测 ALTER」，无迁移框架前提下
    幂等安全；后续再加列沿用此式，列多了再引迁移工具。
  - 会话乐观并发在「并发轮」场景会牺牲后完成方的一次 LLM 调用（409 重试）——
    这是刻意取舍：正确性（历史不交错）优先于那次调用的成本。
  - 历史截窗是「截断」不是「摘要」：超窗信息对模型不可见（limitation 已声明），
    「超窗摘要」等 V0.2 按需演进。
  - 导引「接附件 + 深度分析（知识/工具接入）」是用户原始愿景的未竟部分，
    **本 ADR 只做诚实降级不做补实**——补实为里程碑级工作，待 owner 排期。

## 修订：异源 Codex R1 findings 处置（2026-07-09）

对本 ADR 落地 commit（1d34906）的 86gs Codex 治理审返回 1 P1 + 2 P2，全部
grounded 复核坐实后修复：

1. **[P1] 迁移并发启动竞态**：API 进程与 Job Runner 进程都在启动时调
   `init_db()`，对 pre-ADR-0013 存量库，无锁的 check-then-ALTER 会让双方同时
   观察到「列缺失」，输家撞 `duplicate column name` 直接启动失败。修复：迁移
   块置于 `BEGIN IMMEDIATE` 写锁内、锁内复查列集。回归：一条 trace 卡点确定性
   时序测（严格 happens-before，两种实现下均确定性终止、仅旧实现红）+ 一条
   8 轮×3 线程黑盒并发扫；tamper（拆锁）双测齐红实证。
2. **[P2] 失败轮前端幽灵气泡**：后端已改「失败零落库幂等重试」，但 GuidePage
   乐观追加的 user 气泡在失败时不回滚——界面显示一条服务端不存在的消息，重试
   本地堆重复气泡。修复：catch 内回滚乐观气泡并把原文还原进输入框，与后端
   契约对齐。回归：m6 e2e 新增失败轮检查（stub 注入 ModelUpstreamError→气泡
   回滚+草稿还原+重试无重复气泡）；tamper（拆回滚）e2e 必红实证。
3. **[P2] 详情页轮询全量重拉**：事件分页取尽修复（本 ADR 第 8 条）引入退化——
   2s 轮询每次从 offset 0 翻到尽，事件越多轮询越重。修复：`listTaskEvents`
   支持 offset 起点（事件表 append-only + id ASC，偏移稳定），轮询只拉尾段增量
   追加；手动刷新/首载仍全量，兼作自愈；baseline 身份守卫防在途轮询与手动刷新
   交错重复追加。M2 e2e ④（轮询驱动的事件时间轴）即此路径的行为验收。

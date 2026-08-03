# ADR-0034：任务证据绑定的资产候选账本

- 状态：Accepted（2026-08-02）
- 关联：ADR-0019（签发者来源）· ADR-0025（不可变任务分级）· ADR-0032（资产草稿预览）· ADR-0033（会话优先工程师壳）

## 背景

ADR-0032 已建立无状态的 `Work Case -> Task Pattern Draft -> Skill Draft` 纯投影，
但它只证明会话来源存在，尚不能证明方法来自一项真实完成、版本与产物可核对的工程
任务。若让工程师再次填写 Generalization、选择 Skill/Workflow/Agent 类型，闭环会
退化成资产表单；若 Builder 直接写 Agent 包或 Registry，又会把“提出候选”混同为
“注册并运行”，绕过人签、评测和晋级门。

## 决策

在既有无状态 Draft Bundle 之外新增 `asset_candidate.v1`。Asset Candidate 不是新的
资产类型，而是一个内容寻址的治理包络，包含：

- 原样保存的 `asset_draft_bundle.v1`；
- 已完成单 Agent 用户任务的精确血缘；
- 自动 Generalization Proposal 的确定性来源说明；
- 候选内容摘要、状态和追加式审核事件指针；
- Task Pattern、Skill、Workflow、Agent 四层资格地图。

Guide 在权威任务快照严格为 `completed` 后，幂等请求系统形成候选。工程师不填写
Generalization、不选择模型、Agent、Workflow 或资产类型。系统从同一工作段、任务、
不可变 Agent Package Snapshot、输入输出文件摘要和签发事件自动归纳；无法建立精确
血缘时 fail-closed，并回到主对话解释缺口。

首版只接受同时满足以下条件的任务：

- `origin == "user"`、`data_classification == "internal"`；
- 当前登录 username 与不可变 `created_by_username` 精确一致；存量 NULL 不猜测；
- 有真实 conversation，且任务创建前的工作段中至少有一条已保存用户消息；
- 任务元数据中的 Package Snapshot digest、`validation_started` 事件记录的实际执行摘要，
  与当前一次性钉扎的同版本 Snapshot 三者精确一致；缺任一锚点即 fail-closed；
- `validation_started` 同时钉扎执行时任务参数摘要、输入文件 ID 集合、文件内容证据摘要
  及其统一 `execution_evidence_digest`；`task_completed` 或 `review_approved` 必须携带同一
  摘要，候选形成时再按当前任务与文件账本重算，不能把完成后替换的参数或附件冒充执行输入；
- 直接输入附件必须来自与 Guide 相同边界规则解析出的当前用户工作段，且其不可变上传
  `owner_username` 与任务责任人逐字一致；旧行 NULL 或他人附件不得用 display name 兜底；
  上游任务输出只有在 `depends_on`、`input_binding`、同会话同责任人、已签发完成状态以及
  `dependency_resolved.piped_file_ids` 全部精确咬合时才可作为输入；当前产物必须归属本任务；
- 只有同一责任人、同一 `operation_id`、同一请求指纹与同一 `count`，且完整覆盖无重复
  合法 `index` 的原子 Guide 批次成员，才共享批次开工前的工作段；单独复用 operation id
  不得吞掉前序任务边界；
- 需要人工审核的任务存在带稳定 username 的 `review_approved` 事件，不能用显示名猜测
  签发者；无需审核的任务必须同时显式声明 `model.profile == "none"` 与
  `requires_human_review is False`，并以唯一 `task_completed` 事件作为完成证据。

同一任务与同一内容的创建请求幂等返回原 Candidate，不新增第二条 created 事件。若
工作段、文件、执行或签发证据变化，系统新增递增 `revision`，通过
`supersedes_candidate_digest` 指向上一版；仍待审的上一版先以追加
`candidate_superseded` 事件进入 superseded 审计态，已接受或拒绝的历史决定不被改写。
冷读必须实证同任务连续 `N-1 -> N` 前驱、每版唯一且精确绑定的 `candidate_created`
事件，以及待审前驱的唯一 `candidate_superseded` 事件；不能只相信修订号和摘要外形。
候选内容只插入一次；状态变化由独立 `asset_candidate_events` 追加记录。接受或拒绝
必须携带预期 Candidate digest 与 Bundle digest，并在同一个 `BEGIN IMMEDIATE` 事务中：

1. 重新验证提交时仍有效的精确认证会话；
2. 从任务、工作段、实际执行摘要、输入输出文件和签发事件重建 Bundle 与 Lineage，
   并与待决定 Candidate 的三层摘要逐字比对；
3. 插入具名签发事件；
4. 以 `state='awaiting_human_review' AND decision_event_id IS NULL` 做 CAS 更新。

任一检查失败、摘要漂移、会话过期或并发第二次决定都整体回滚。HTTP 响应不返回
session hash，只给出已绑定有效会话的布尔证明。

## 资产层级

- **Task Pattern Revision**：描述会重复出现的问题与完成条件，不可执行。
- **Skill Revision**：操作化已批准 Task Pattern，说明如何工作、验证及何时停给人判断。
- **Workflow Revision**：只引用已批准 Skill Revision，并补充组合、依赖和 I/O 绑定。
- **Agent Package Revision**：承载责任、模型、工具、知识、权限与部署边界，继续经过
  既有 Package Schema、Registry、Eval 与人工晋级门。

一次完成任务可以形成 Task Pattern 与 Skill Candidate，但不能据此声称 Workflow 或
Agent 已形成。不是所有 Skill 都需要 Workflow，也不是所有 Workflow 都应成为 Agent。

## 不变量

- Candidate digest 只覆盖版本、修订号、上一版 Candidate digest、Bundle digest、工程血缘
  digest、Generalization Proposal provenance digest 与校验策略；时间、状态、数据库 ID、
  候选审核签发者和 session 不进入内容摘要。任务责任 username 同时进入 task lineage，
  因而由 lineage digest 咬合；公共 source 必须与账本责任人一致，终态 signer username
  必须再与该责任人逐字一致。
  任务完成/签发事件属于来源 Lineage，因此其精确摘要会通过 Lineage digest 间接绑定
  Candidate digest。把证据恢复成旧内容仍会形成链上的新修订，不能复用旧地址绕过历史。
- Draft Bundle 保持 ADR-0032 的纯投影语义，其 `writes_database=false` 与
  `decision_state=not_recorded` 不被改写。
- Candidate 响应必须如实声明 `writes_candidate_store=true`，同时锁定
  `executes_work=false`、`writes_package_files=false`、`registers_asset=false`、
  `promotes_asset=false`。
- `accepted` 只表示“精确候选修订已被人接受”，不得显示为已安装、已注册、已发布、
  可执行、completed 或 promoted。
- 候选审核 UI 是对话轴上的按需只读披露，只有按钮；不得新增表单、选择器、第二个
  文本输入或常驻资产面板。

## 后果

FLAi-OS 得到第一条“真实工程任务 -> 可追溯方法候选 -> 人工接受”的通用资产闭环，
并让功能地图能由本体关系自然生长，而不是靠 CFD/CAD 字段数量增长。代价是新增两张
SQLite 表、三份严格合同与一组失败关闭门。Matt 风格 `SKILL.md` Materializer、
Workflow 组合与 Agent Package 生成仍是后续独立、摘要绑定的切片，本 ADR 不授权它们
写包、注册或执行。

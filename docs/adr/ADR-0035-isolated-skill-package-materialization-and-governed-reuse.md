# ADR-0035：隔离 Skill Package 材化与受控自动复用

- 状态：Accepted（2026-08-02）
- 关联：ADR-0019（签发者来源）· ADR-0025（不可变任务分级）· ADR-0033（会话优先自动路由）· ADR-0034（任务证据绑定的资产候选账本）
- 授权边界：本 ADR 只授权 Approved Candidate 的确定性 Skill Package 材化、包级人工审核、已批准包的确定性匹配与任务级运行时绑定；不授权 Registry 注册、Agent 包写入、自动执行、自动晋级或 Workflow/Agent Candidate 生成。

## 背景

ADR-0034 把一项真实已完成任务变成可审计的 Task Pattern 与 Skill Candidate，
但明确不授权写入 Skill Package。若接受 Candidate 后仍要工程师填写名称、版本、
模型、Agent 或 Workflow 表单，资产闭环会重新把系统应负责的抽象与编排转嫁给人。
若接受决定直接将包写入 `agents/`、Registry 或可执行搜索路径，又会把“方法候选
被接受”误当成“运行资产已批准”，绕过包字节、执行边界与人工签发。

同时，主对话中仅展示“已匹配 Skill”不能证明真实复用。包必须在任务创建时被
重新验证，并在运行时将精确方法与实际执行证据咬合；否则既无法审计是否真用了
该方法，也会把模型建议次数误当成 Workflow 或 Agent 的重复证据。

## 决策

### 从 Candidate 到隔离 Package

系统在某个精确 Candidate Revision 已经通过 ADR-0034 的人工 `accepted` 决定后，
自动运行确定性 Materializer。材化前必须重建并逐字比对 Candidate digest、Bundle digest、
工程证据血缘与接受事件；非 `accepted`、摘要漂移或历史修订不得写包。

材化是纯确定性转换，名称、版本、目录与文件内容都由已接受内容自动派生；
不调用 LLM 补写，不要求工程师填字段或选类型。每个 Skill Package Revision 至少包含：

- `SKILL.md`，frontmatter 只有 `name` 与 `description`，正文保留使用时机、步骤、验证与人工边界；
- `references/provenance.json`，精确引用来源 Candidate、Bundle、任务和签发摘要；
- `references/task-pattern-revision.json` 与 `references/skill-revision.json`，原样保留被材化的修订。

包具有自动派生的语义版本与覆盖完整文件清单的内容摘要。同一精确 Candidate
Revision 只能对应同一个 Package Revision；重试幂等返回原包，不通过时间、随机数或调用顺序
改变字节。Materializer 使用专用数据根目录下的隔离区，先在同根 staging 目录完整写入与验证，
再原子重命名到内容寻址目录。该路径必须位于 `agents/`、Registry、用户或全局 Skill 目录、
Python 导入路径之外；路径逃逸、符号链接、文件缺失或字节不符均 fail-closed。

新包一律进入 `pending_review`。Candidate 审核与 Package 审核是两个独立决定：包决定
必须由当前有效会话绑定的具名人作出。请求路径携带 Package id，请求体只携带动作与
预期 Package digest；版本、Candidate digest 与所有来源摘要均由服务端冷读并重验，绝不让
客户端自报权威字段。系统在一个 `BEGIN IMMEDIATE` 事务内追加审核事件、以
`state='pending_review' AND decision_event_id IS NULL` 做 CAS。并发第二次决定、会话失效或
字节漂移必须整体回滚。`approved` 只表示该精确 Package Revision 可进入匹配与任务级复用，
不表示已注册、已发布、已晋级或可绕过开工与签发门。

### 主对话内自动复用

新工作段进入 Guide 时，服务端在 LLM 编排之前对当前用户可见的 Package 做确定性匹配。
候选集只包含 `approved` 且每个存储字节都已按 manifest 重算通过的 Skill Package Revision。
匹配依据只取当前工作段的用户文本、附件名册与已批准包的明示使用边界，并产生策略
版本与依据摘要。只有唯一高置信结果才可复用；并列、低置信、未审、已拒、越权、
文件缺失或摘要漂移都不建立匹配。匹配失败不得伪造方法复用，但也不应阻断 Guide
继续用既有路由理解新任务。

唯一匹配方法以受信系统上下文提供给 Guide，模型只能在该方法的明示边界内产生方案。
LLM 输出中自行伪造的 Package 引用必须被丢弃；仅当经过确定性校验的方案确实包含匹配
Agent 时，服务端才附加精确 Skill Reuse Match 引用。

工程师仍然只看到一个主任务、一个文本输入、附件上传和既有的“按方案开工”主确认。
复用信息只能作为当前方案卡片中的一行摘要，细节放进已有的按需披露；不新增资产面板、
输入框、选择器、复用按钮或第二个主 CTA。

点击“按方案开工”时，原子 batch 在任何任务写入前重新验证 Package 所有者、状态、
版本、Package digest、Candidate digest、文件 manifest 与匹配 Agent，并将精确引用写入任务
不可变元数据。任一不符使整个 batch 零写入。运行时在工具或 Workflow 执行前再次验证包
字节，把精确 `SKILL.md` 与结构化修订放入有界、确定性的系统数据包，并将复用绑定摘要写入
`validation_started` 及追加审计证据。注入本身不等于实际使用：模型型 Agent 必须有携带同一
Application digest 的成功 `chat` 或 `vision` 调用；无模型的确定性 Workflow 必须逐字段返回
运行时提供的 exact receipt，且其不可变 Agent Package 快照必须先声明
`workflow.skill_reuse_application: deterministic_receipt_v1`。未声明的 `profile:none` Agent
不会进入自动复用任务。只有 `validation_started < skill_reuse_bound < skill_reuse_applied
< terminal` 的单一完整链才可计数，终态也必须携带同一 Application digest。`embed`、空
Workflow、失败调用、Workflow 自报事件、方案标签、匹配建议或任务元数据都不得声称已真实复用。
确定性 receipt 证明的是：经代码审查并显式声明能力的 Workflow 接收了这份精确方法契约、
完成运行并对同一回执负责；它不是对 Workflow 内部计算过程的数学因果证明，不能据此宣称
方法内容必然改变了某个中间变量或工程结论。

### 重复证据与高阶资产门

只有真实运行时建立 Skill Reuse Binding，且任务已有同一执行证据摘要的完成或人工
签发证据，才能进入重复证据计数。匹配建议、展示标签、未开工方案、失败执行、未审包或
后来被改写的字节都不计数。

“多个独立任务”的最低门槛为两份 Independent Work Case Evidence。每份证据必须有不同的
源任务、来源工作段修订、实际执行摘要与完成/签发事件摘要。同一任务的 Candidate 修订、
失败重试、幂等重放，以及同一原子 Guide 批次或同一工作段派生的多个任务，都只能计一份。
系统用排除任务 id、上传 id、文件名与顺序的内容稳定 fingerprint 保守折叠同内容重传；该
fingerprint 只是去重依据，不是语义独立性的充分证明。

两份证据是 Workflow/Agent 更高层抽象的必要条件，不是充分条件：

- 单个 Skill 被多次成功复用，只证明该 Skill 的复用性，不自动形成 Workflow Candidate。
- Workflow Candidate 还必须在独立 Work Case 中呈现稳定的多 Skill 组合，以及真实的顺序、
  依赖、输入输出绑定、交接或人工停止点之一；空组合或仅复制 Skill 内的线性步骤不合格。
- Agent Candidate 只能晚于某个精确 Approved Workflow Revision，并在多个独立执行中再次证明
  稳定的责任、工具、知识、权限与人工边界组合；不得从 Skill Package 跨级生成 Agent。

当前切片只可输出只读 Composition Eligibility 与证据缺口，不得动态改写既有 Candidate
digest 所咬合的资格地图，也不得以达到数量阈值为由自动写入 Workflow 或 Agent Candidate。

## 不可变量

- Candidate `accepted` 与 Package `approved` 是两个独立、摘要绑定、具名人触发的 CAS 状态迁移；
  前者不能被解释为后者。
- 已存在包的任何文件不原地改写；方法内容变更必须形成新 Candidate Revision、新版本和新内容摘要。
- 只有 `approved` 且存储字节实证通过的包才能被匹配、绑定或注入；状态字段不能代替字节完整性。
- 复用不改变人是唯一签发者的边界，也不改变 Agent Package Snapshot、工具白名单、权限、密级、
  输入 schema、原子 batch 和结果审核门。Skill Package 不得通过正文扩大 Agent 原有权限。
- 工程师交互面继续只有自然语言、附件与治理按钮；匹配、版本、模型、Agent、Workflow、
  工具和包参数都是系统内部对象，不变成新表单或常驻面板。
- 系统可以自动匹配方法，但不能自动点击开工、自动替人通过 Package 审核、自动签发结果或
  自动将方法注册为全局资产。

## 后果

FLAi-OS 得到了“真实完成任务 -> 可审 Candidate -> 隔离待审 Skill Package -> 新任务自动复用
-> 可验证重复证据”的最小闭环。工程师不学习资产管理表单，只在原对话中描述问题、上传附件、
确认开工并作出必要的审核或签发。

代价是平台必须同时维护文件完整性、包审核账本、匹配策略版本、任务与运行时复用绑定，
并对独立 Work Case 去重。这些成本换来的是可信的方法复用证据，而不是一个无法证明真实执行过的
“资产已生成”标签。无模型 Workflow 只有在其受 Package snapshot digest 约束的 manifest
显式声明 `deterministic_receipt_v1` 后，才可通过 batch 能力门；其返回值仍须由运行时逐字段
核对，不得从 `profile:none`、源码扫描或上下文参数猜测兼容。
Workflow 材化、Agent Package 生成、Registry 晋级与发布仍需后续独立 ADR 授权。

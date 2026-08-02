# FLAi-OS Domain Context

## Work Case

一次已经真实发生、由工程师负责的具体工作实例。Work Case 是资产抽象的来源，
不是可复用资产本身，也不等于一段脱离平台来源的提示词。

## Generalization

工程师对某个 Work Case 所做的可复用抽象，说明何时需要、要交付什么、需要
哪些输入、遵循哪些步骤，以及必须保留的人工判断、证据和不适用边界。
Generalization 是待核输入，不代表平台已经理解或认可该工作。

## Generalization Proposal

系统从一个有完成证据的 Work Case 自动归纳出的 Generalization 提案。提案只能引用
平台内已经存在的任务、Agent Package、产物摘要与签发证据；它可以减少工程师整理
成本，但不具有审核或签发权。语义缺口必须回到同一主对话补充，不能退化成字段表单。

## Task Pattern Draft

从一个 Work Case 的 Generalization 派生出的任务模式草稿，描述一类问题的触发
条件、目标、输入、输出、步骤、证据和边界。它与某个具体 Agent 或工具实现解耦。

## Skill Draft

对 Task Pattern Draft 的操作化表达，说明 Agent 在何时使用、按什么步骤工作、
如何验证，以及在哪里必须停下来等待工程师判断。Skill Draft 不是已安装或已注册
的 Skill。

## Asset Draft Bundle

把 Work Case 血缘、Task Pattern Draft、Skill Draft、确定性校验结果和人工审核
要求封装在一起的原子草稿。草稿包可以交给人审，但不能直接执行、注册或晋级。

## Asset Candidate

一个精确 Asset Draft Bundle 与一个精确工程证据血缘组成的持久治理包络。它证明
“这份草稿来自哪次已完成任务、哪版 Agent Package 和哪些产物摘要”，不证明内容
正确，也不是已安装 Skill、Workflow 或 Agent。Candidate 的唯一允许副作用是写入
候选账本与追加审计事件；不得执行工作、写 Agent 包、注册或晋级资产。

## Candidate Revision

以内容摘要标识的一次不可变 Asset Candidate 内容。草稿或证据发生变化时必须形成
新的摘要与递增修订号，不能原地改写旧内容；新修订以
`supersedes_candidate_digest` 精确引用上一版，上一版待审内容进入 superseded 审计态。
审核状态和签发事件不进入内容摘要，人工决定必须同时绑定 Candidate digest 与
Bundle digest。

## Approved Revision

具名工程师对某个精确 Candidate Revision 作出接受决定后的修订。Approved 只表示
接受该修订会自动触发确定性 Materializer，生成隔离、版本化、`pending_review` 的
`SKILL.md` 文件包；这仍不等于 Package 已批准、已注册、可执行、已发布或已晋级。

## Skill Package Revision

确定性 Materializer 从一个精确 Approved Revision 生成的不可变文件包，包含
Matt 风格 `SKILL.md` 与摘要绑定的来源参考。它同时有语义版本与内容摘要，存放在
专用隔离目录，不进入 Agent 源目录、Registry 或可执行导入路径。新包默认是
`pending_review`；Candidate 的接受决定不能代替对该包精确摘要的独立人工审核。

## Skill Reuse Match

系统用当前 Work Case 的文本与附件线索，对当前工程师可见的已批准、逐字节
验证通过的 Skill Package Revision 做确定性匹配。只有唯一高置信结果才能进入方案；
并列、低置信、未审、已拒或字节漂移都表示未匹配。匹配是系统路由事实，不是
LLM 可以自行声明的建议字段。

## Skill Reuse Binding

将一次真实任务执行与某个精确 Skill Package Revision 咬合的不可变证据，至少
包含 Package id、版本、Package digest、来源 Candidate digest、匹配策略与匹配依据摘要。
创建任务和运行时均必须重新验证包状态与字节，并把方法内容注入该次执行与追加
审计事件。主对话中的“将复用某 Skill”标签本身不是 Reuse Binding。

## Skill Reuse Application

运行时对某个精确 Skill Reuse Binding 的实际使用证据。仅有匹配、绑定或把方法放入
上下文不算 Application；模型型 Agent 必须存在一次携带同一 Application digest 的成功
`chat` 或 `vision` 调用，确定性 Workflow 则必须返回运行时给出的逐字段精确 receipt。
`model.profile=none` 的确定性 Workflow 还必须在不可变 Agent Package 中显式声明
`workflow.skill_reuse_application: deterministic_receipt_v1`；未声明时自动复用在建任务前
fail-closed。
`embed`、空 Workflow、失败调用和 Workflow 自报审计事件均不能代替该证据。

## Independent Work Case Evidence

来自不同任务与不同来源工作段、且有独立实际执行和完成或签发摘要的 Reuse
Application 证据。同一任务修订、重试、重放或同一原子工作段的批次成员不能通过重复
记数伪造独立证据。至少两份 Independent Work Case Evidence 只是进入更高层组合评估的
必要条件，不代表 Workflow 或 Agent 已经形成。内容稳定的 Work Case fingerprint 只用于
保守去重上传 id、文件名、顺序等非语义变化，不证明两个工作在语义上独立。

## Composition Eligibility

由 Independent Work Case Evidence 得出的只读资格投影。Workflow Candidate 还必须出现稳定的
多 Skill 组合、依赖、输入输出绑定或人工停止点；同一 Skill 被多次复用不能自动形成
Workflow。Agent Candidate 必须晚于精确的 Approved Workflow Revision，并另行证明责任、
工具、知识和权限边界的稳定性。Composition Eligibility 不写包、不注册、不晋级。

## Workflow Revision

一个或多个 Approved Skill Revision 的运行组合，声明顺序、依赖、输入输出绑定与
停止条件。单一 Skill 不必被包装成 Workflow；Task Pattern 里的线性步骤也不自动
构成 Workflow Revision。

## Agent Package Revision

把责任人、模型画像、工具与知识白名单、权限、输入输出、Workflow 和部署边界封装
在一起的版本化运行单元。它只有在通过既有 Package Schema、Registry、Eval 与人工
晋级门后才可运行；Approved Skill 或 Workflow 不能自行升级成 Agent。

## Review Readiness

草稿的结构是否完整到足以交给工程师审核。Review Readiness 不判断工程内容是否
正确，也不表示已提交审核、已批准、已签发或已经成为平台资产。

## Review Decision

具名责任人对某个精确草稿摘要作出的独立决定。Review Decision 与 Draft Bundle
是不同对象；未来的批准不能改写原草稿，只能引用其精确摘要形成新记录。

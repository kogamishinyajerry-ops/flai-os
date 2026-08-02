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
该修订可以进入后续材化或组合评估，不等于已生成 `SKILL.md`、已注册、可执行、已发布
或已晋级。

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

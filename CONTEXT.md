# FLAi-OS Domain Context

## Work Case

一次已经真实发生、由工程师负责的具体工作实例。Work Case 是资产抽象的来源，
不是可复用资产本身，也不等于一段脱离平台来源的提示词。

## Generalization

工程师对某个 Work Case 所做的可复用抽象，说明何时需要、要交付什么、需要
哪些输入、遵循哪些步骤，以及必须保留的人工判断、证据和不适用边界。
Generalization 是待核输入，不代表平台已经理解或认可该工作。

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

## Review Readiness

草稿的结构是否完整到足以交给工程师审核。Review Readiness 不判断工程内容是否
正确，也不表示已提交审核、已批准、已签发或已经成为平台资产。

## Review Decision

具名责任人对某个精确草稿摘要作出的独立决定。Review Decision 与 Draft Bundle
是不同对象；未来的批准不能改写原草稿，只能引用其精确摘要形成新记录。

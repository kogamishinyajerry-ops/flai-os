# ADR-0048：能力发布身份采用 ReleaseKnowledgeBinding，任务快照只作运行证据

- 状态：产品与实施准备方向已接受（委托人在设计会话中确认，2026-07-23；不构成组织签发、试点、发布或上线授权）
- 关联：ADR-0057、ADR-0058
- 取代范围：ADR-0058 中把“权威知识版本快照”或未限定的 `knowledge scope` 直接作为能力发布包身份字段的表述

能力发布包必须在运行前拥有稳定、可复算的身份，但任务时可访问和实际命中的知识由认证主体、任务时间、授权状态、适用范围及来源有效性共同决定。如果把任务时快照写入发布包 manifest，同一能力会随 actor、时刻和命中变化而产生循环身份，Bench 也无法比较同一 release 的多次运行。

本 ADR 明确：

1. 能力发布包只冻结 `ReleaseKnowledgeBinding`。它至少表达允许的 authority/scope、必需与禁止集合、版本选择策略、目录根摘要、检索与锚点规则、外部活态声明及各自摘要，并参与 release digest。
2. 每次任务或 Bench run 按精确 release、认证主体、任务 `as_of`、当前授权和 Binding 解析独立的 `TaskKnowledgeSnapshot`。快照记录实际版本、锚点、缺失、冲突、有效性、分类和整体摘要，绑定运行证据但不改变 release digest。
3. Bench 必须证明 Task Snapshot 符合 Release Binding；不符合、无法重建、授权未知或关键依据缺失时，对应 case 为 `failed|invalid|unknown`，不能通过生成新 release 身份掩盖。
4. 索引名称、向量库状态、检索结果列表和“当前最新版”均不能代替 Binding 或 Snapshot。外部活态若影响准入且不可冻结，必须显式降低可复现性结论。
5. 本 ADR 不授权数据库、公开 Interface、知识导入、真实内网数据或发布流程改动。实现前仍需另行冻结持久化合同、摘要算法、授权复核、冲突语义和 invalid-first fixtures。

# ADR-0058：FLAi Bench 采用冻结能力发布包、四轨评测与不可抵消门

- 状态：产品方向已接受（委托人在本次设计会话中确认，2026-07-23；不构成组织签发、试点或上线授权）
- 关联：ADR-0018、ADR-0029、ADR-0048、ADR-0051、ADR-0053、ADR-0057

FLAi-OS 将现有 Eval Runner、评测快照、用例策展、人工评审和晋级证据扩展为统一的 FLAi Bench 基准评测底座。FLAi Bench 可以作为平台中有辨识度的项目和产品能力出现，但不得建立第二条评测执行链、第二套晋级事实源或只供展示的模型排行榜。评测必须复用真实 Runtime、Tool、事件和审核路径，旁路执行不能作为发布证据。

尚无 `QualificationDecision` 与 `DeploymentBinding` 的候选若要生成准入证据，必须先取得具备职责的 Eval maintainer 签发的 `EvaluationAdmission`。该版本化事实绑定 evaluator/service actor 与 scope、精确 release/approved synthetic fixture/pack/rubric/Gate Policy/environment digest、允许动作、零外部效果、资源与 Token 预算、TTL 和 `ExecutionEpochSnapshot`，且可暂停、撤销或过期。Kernel 只有在全部绑定精确匹配时才派生 `origin=eval` 审计标签并进入同一真实执行链；客户端标签、普通用户、真实数据、未列 fixture、Connector/Delivery 副作用、错 digest、过期或 epoch 漂移全部 fail-closed。EvaluationAdmission 既不授予普通用户 effective callability，也不替代资格或部署签发。

评测的基本对象不是抽象模型或单个 Agent 版本号，而是一份冻结的“能力发布包”。它至少绑定 Agent 配置与版本、Prompt、Workflow、输入输出 Schema、解析后的实际模型 endpoint/route/trust bundle、参数档与 tokenizer id/version/package digest、Tool 及 Adapter 版本、Sandbox/执行镜像/资源策略、预算档、权限与网络策略、完整 canonical `ReleaseKnowledgeBinding` 及 `binding_digest`、评测用例包、人工 rubric、Gate Policy 和环境档版本。Binding 总摘要至少覆盖 allowed authority/scopes、required/prohibited sets、version selection、catalog root、retrieval/anchor policies 和 external-live declarations；任一字段变化都必须改变 binding/release digest。每次运行独立记录 `TaskKnowledgeSnapshot` 并证明符合 Binding；缺失、不一致、冲突未决、来源未授权或知识状态 unknown 均不能通过 mandatory gate。任务快照不反向改变 release digest。任一发布关键成分变化都形成新的被评对象，旧评测结果不得自动继承。

能力发布包必须区分内容身份与来源 envelope。`release_digest` 只由规范化 identity payload 及冻结实体摘要生成；`release_id`、创建时间、创建人、签名、显示元数据、Git commit 和文件时间戳不进入内容身份。同一 identity payload 无论由谁、何时重复冻结都得到同一摘要；改变模型 endpoint/route/trust bundle、预算档、Gate Policy、环境档或其他身份成分必须改变摘要。

能力发布包中的每一项必须有可验证版本或内容摘要。无法冻结的外部工具状态、工程文件、模型服务或知识源必须被明确标记为外部活态及证据边界；如果它会影响准入结论而又无法重建，本次运行只能记为不可复现或证据不完整，不能冒充可发布的全绿结果。现有 Eval Snapshot 对 Agent 包和 eval_cases 的冻结继续保留，但必须在实施时补齐 model、tool、sandbox/policy、ReleaseKnowledgeBinding 与外部状态清单，并在每次 run 记录 TaskKnowledgeSnapshot。

FLAi Bench 采用四条互补评测轨道：

1. **确定性回归**：验证契约、固定输入输出、状态机、产物、失败路径和 tamper witness，由机器断言判定；
2. **工程质量**：验证正确性、完整性、可采用性和领域细则，由版本化真人评审记录判定；
3. **安全治理**：验证越权、提示注入、数据泄露、密级传播、网络外联、破坏性动作、并发与取消、审计完整性、无依据结论和假绿路径，由对抗用例与绝对门判定；
4. **运行效率**：记录时延、Token、估算成本、并发、资源消耗和稳定性，只有在具名 SLO 或预算门存在时才作为硬门，否则只作优化证据。

四轨结果组成证据矩阵，不折算成一个可以互相抵消的综合总分。安全治理、诚实性、依据链和关键回归属于不可抵消门：任何必测项 failed、invalid、skipped、unknown 或证据不可解析，都不能被文案质量、平均分、速度或低 Token 消耗抵消。不同 Agent 的领域评分不得脱离 rubric 横向排名；同一能力版本只有在评测包、rubric 和环境等级可比时才显示新旧差异。

LLM-as-Judge 可以用于初筛、聚类、解释差异和给真人提供评审建议，但不能单独写入 pass、晋级、签发或生产准入。人工质量判定必须来自认证身份或可验证的具名评审证据；`honesty` 与 `traceability` 等门为严格布尔值，任何 false 都是有效失败，不能被其他高分覆盖。

评测资产实行 `draft → approved → retired` 生命周期。运行样本、用户反馈和线上失败可以生成 draft 候选，但只有 Eval 维护者或具名领域人员可以批准金标准和预期结果；AI 不得把自己的输出自动固化为正确答案。真实与 synthetic 用例必须显式区分，密级和授权沿输入、快照、运行产物与报告传播。已批准用例内容变更必须产生新版本和摘要，不能原位改软断言继续沿用旧证据。

首批基准包与三条 Phase 0A 黄金工作流一一对应：智能办公包重点验证数字、单位、公式、表格和图片不被静默改变，以及改动可对照、可撤销；CFD 算例体检包重点验证问题定位到真实文件字段、不写原算例、不启动求解、依据与假设分离；会议行动包重点验证不虚构决策、负责人或期限，责任字段缺失和来源冲突会阻止正式签发。具体阈值和样本规模必须随各自领域 rubric 单独版本化，不在本 ADR 中拍脑袋设数。

发布或晋级所引用的 FLAi Bench 运行必须能够反查能力发布包摘要、评测包版本、每个 case 的真实任务与证据、人工评审身份和所有不可抵消门结果。统计和战略视图可以投影这些事实，但无权手工改写评测状态。

本 ADR 决定评测机制和事实边界，不授权当前混合工作树上的 Runtime、Schema 或数据库改动。实施前必须固定 capability-release manifest、四轨结果 envelope、必测门矩阵、可比性规则、三套首批基准包、LLM 评审辅助边界，以及至少覆盖“缺版本、外部活态、未知门、skipped 冒充通过、AI 自批金标准”的 invalid-first fixtures。

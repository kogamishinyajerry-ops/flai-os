# Production Snapshot Assembler V1｜七责任域具名评审控制包

> 评审对象：`flai.production-snapshot-assembler.read.v1`
>
> 冻结文件：`docs/product/FLAi-OS_V0.2_Design_Package/16_Production_Snapshot_Assembler_Read_Contract.md`
>
> 冻结 SHA-256：`8f791b5c9a5c5e3c9d18ef0168d23fe0ec5c9cc24f024f4e374c82de15357f24`
>
> 共同冻结依赖：Stage C Observer/Adapter source、fixtures 与 conformance tests，逐文件摘要见
> `review-manifest.json.target.normative_dependencies`
>
> 当前评审状态：`PENDING_ASSIGNMENT`
>
> 当前评审计划：`DRAFT-PENDING-ASSIGNMENT`
>
> 当前实施授权：`false`

## 1. 目的与边界

本目录把冻结合同第 13 节要求的七个责任域组织为七组互相独立、可机械检查的 `ReviewDecisionCore + DecisionSeal/AuditReceipt`。评审对象同时绑定合同和合同明确列为共同规范的 Stage C Observer/Adapter source、fixtures 与 conformance tests；任一依赖漂移都会使结构门失效。它只服务于设计合同评审，不实现 Production Snapshot Assembler，不修改生产 Schema、API、状态机或运行配置。

安全、兼容性和失败码技术预审可以作为评审输入，但它们是 AI 辅助审查，不具组织签发权。聊天中的“接受”、Git 用户名、机器账号、测试通过、文件提交或模型结论都不能代替真实责任人的组织身份和签署证据。

七域全部明确 `approve`、且组织认可的包外 verifier 已真实核验主体、任命、签署/审计凭证、吊销和发现项状态后，只能得到：

```text
contract_review = APPROVED
implementation_authorized = false
```

实施仍须依据冻结合同第 13.2 节另开精确切片、明确变更范围并取得单独授权。

## 2. 冻结对象

评审人开始评审和签署前都必须运行：

```bash
shasum -a 256 \
  docs/product/FLAi-OS_V0.2_Design_Package/16_Production_Snapshot_Assembler_Read_Contract.md
```

结果必须逐字等于：

```text
8f791b5c9a5c5e3c9d18ef0168d23fe0ec5c9cc24f024f4e374c82de15357f24
```

任何正文变动都会产生新摘要。新摘要不是本评审包的对象，必须停止评审、重新冻结合同，并使已有七域决定全部失效；不得把旧签名迁移到新内容。

## 3. 七域编组

实际指派时使用[七责任域评审指派回填单](ASSIGNMENT_INTAKE.md)，不要在聊天中传递秘密或凭据原文。

| 序号 | 责任域 | 必须由谁评审 | 当前指派 | Decision Core / Seal |
|---|---|---|---|---|
| 01 | Control Kernel / 架构 | 对 Control Kernel Module 边界和公开 seam 有正式职责的真人 owner | `UNASSIGNED` | [Core](records/01-control-kernel-architecture.review.json) / [Seal](seals/01-control-kernel-architecture.seal.json) |
| 02 | Identity / Authorization | 对企业身份、对象授权、ACL/classification 和撤权语义有正式职责的真人 owner | `UNASSIGNED` | [Core](records/02-identity-authorization.review.json) / [Seal](seals/02-identity-authorization.seal.json) |
| 03 | 数据 / SQLite | 对 SQLite 仓储、一致性读和性能边界有正式职责的真人 owner | `UNASSIGNED` | [Core](records/03-data-sqlite.review.json) / [Seal](seals/03-data-sqlite.seal.json) |
| 04 | 安全 / 密码 | 对 receipt、信任策略、算法和密钥生命周期有正式职责的真人 owner | `UNASSIGNED` | [Core](records/04-security-cryptography.review.json) / [Seal](seals/04-security-cryptography.seal.json) |
| 05 | ExecutionBroker / Sandbox | 对执行组合边界、Sandbox 证明和阶段 witness 有正式职责的真人 owner | `UNASSIGNED` | [Core](records/05-executionbroker-sandbox.review.json) / [Seal](seals/05-executionbroker-sandbox.seal.json) |
| 06 | Knowledge | 对知识四钥 provenance、权威性和适用性边界有正式职责的真人 owner | `UNASSIGNED` | [Core](records/06-knowledge.review.json) / [Seal](seals/06-knowledge.seal.json) |
| 07 | 工作台 / Observer | 对 Stage C Observer 合同、失败体验和诊断边界有正式职责的真人 owner | `UNASSIGNED` | [Core](records/07-workbench-observer.review.json) / [Seal](seals/07-workbench-observer.seal.json) |

不能从 Git 作者、聊天显示名、本机用户名、管理员账号或 AI 名称推断上述责任人。允许一位真人兼任多个域，但每个域都必须有独立的职责作用域、逐项回答和签署记录；组织的职责分离制度如禁止兼任，应以制度为准。

## 4. 身份与签署要求

先在 [review-manifest.json](review-manifest.json) 的七个 `reviewer_assignment` 中登记责任人，并由组织身份/任命事实核验：

- `reviewer_display_name`：便于人阅读的真实姓名；
- `reviewer_actor_id`：来自企业 IdP、人员主数据或正式签署系统的稳定主体标识，不能只填显示名；
- `reviewer_principal_type`：必须为 `human`；
- `reviewer_role_assignment_ref`：证明该主体对该责任域具有决定权的稳定任命引用；
- `segregation_of_duties_exception_ref`：同一主体覆盖多个责任域时的具名、限时职责分离豁免；无兼任时保持 `null`。

七域分配完成后，把 `review_plan_status` 改为 `FROZEN-FOR-REVIEW`，再计算 `review-manifest.json` 的 raw-byte SHA-256。每份 Decision Core 必须逐字绑定该 `review_plan_digest`，从而避免评审期间静默替换责任人或问题集合。

问题正文的签署真相源是 `review-manifest.json.question_catalog`，不是本 README 的展示文案。校验器同时冻结 question ID 和完整问题正文；把问题缩成一句“是否同意”、只保留 ID 或更换问题后沿用旧决定都会失败。

每份 Decision Core 记录：

- `review_round_id` 与 `review_plan_digest`；
- 由追加式审计账本分配的唯一 `decision_id`、本轮 `decision_revision=1` 与空的前序摘要；
- 评审人的显示名、稳定 `actor_id`、`principal_type=human` 与任命引用；
- `responsibility_scope`：本次决定覆盖的明确职责边界；
- `decision`：只允许 `approve`、`changes_required` 或 `reject`；
- `reviewed_contract_id` 与 `reviewed_contract_digest`：必须精确绑定本包冻结对象；
- `reviewed_at`：带时区的 RFC 3339 时间；
- `review_answers[]`：共同问题和本域问题的逐项结论与理由；
- `findings_refs[]`：发现项或处置记录的稳定引用；

Decision Core 完成后，计算其 raw-byte SHA-256。对应 Decision Seal/AuditReceipt 必须绑定该 `decision_core_digest`、同一 `reviewer_actor_id`、签名凭据或审计主体、可信时间、`contract-review` key usage / audit event type、包外 Trust Policy 以及验签/审计核验 receipt。签名证据不能反向写入 Decision Core，因此不存在“记录摘要包含签名、签名又覆盖记录摘要”的循环。

本地脚本只验证引用和摘要闭合，不能自行证明企业 IdP、角色任命、数字签名或审计系统是真实可信的。`trust_verification_receipt_ref` 必须来自组织认可的包外可信验证通道；不能把本包自带的公钥、自声明状态或一个看起来像 URI 的字符串当作信任根。

因此当前 `verify_review_gate.py` 即使看到七份填写完整的 Core/Seal，也只会到达 `PENDING_EXTERNAL_VERIFICATION`，并以非零状态退出。只有后续实现并独立评审一个能够使用包外固定信任根、实际解析 actor/role/signature、findings、SoD exception、追加式决定历史、吊销和时间证据的 verifier，才允许引入真正的 `PASSED` 路径；不能通过把 manifest 状态改成“verified”解锁。

模板中的 `null`、`pending` 和空数组是明确的未完成状态，不得为了通过检查填入 `TBD`、`N/A`、示例姓名、共享账号或伪造凭证。

## 5. 每域必须明确回答的问题

### 所有责任域共同回答

1. `COMMON-01`：我确认评审对象是合同 `flai.production-snapshot-assembler.read.v1` 的上述精确 SHA-256；本决定只评审只读设计合同，不声明 production-ready，不授权实现，不授权生产 Schema/API/状态机变更。

### 01｜Control Kernel / 架构

1. `module_ownership`：Assembler 是否只属于 Control Kernel，且没有把 Identity、Authorization、ExecutionBroker、Knowledge 或 Observer 的裁决权吸入自身？
2. `public_seam`：唯一公开调用面、内部 WitnessResolver seam 和依赖方向是否足够明确且可保持深 Module？
3. `no_second_state_machine`：合同是否保证只读、无业务写入，并且不会创建第二任务状态机或第二控制面？

### 02｜Identity / Authorization

1. `authenticated_opaque_context`：认证上下文是否只能由受信通道铸造，且调用方无法伪造 actor、role、ACL 或 reality？
2. `acl_classification_existence`：对象存在性、ACL、clearance、classification 与字段投影是否在释放前 fail-closed？
3. `release_fence`：actor/session、credential epoch、ResourceEnvelope、AuthorizationDecision 和 verification-policy 的二次 fence 是否覆盖撤权与竞态？

### 03｜数据 / SQLite

1. `single_read_transaction`：业务事实是否在一个 SQLite read transaction 中冻结，外部验签与 release fence 是否不会混入新旧事实？
2. `tail_window`：event tail window、总数、current event 和重复/冲突检查是否确定且不静默截断？
3. `query_only`：连接、仓储和失败路径是否保证 read-only/query-only，无隐式迁移或写副作用？
4. `performance_bounds`：读取规模、超时、锁占用和大对象策略是否有可实施的硬边界，未知时是否拒绝而非退化放行？

### 04｜安全 / 密码

1. `strict_receipt_schema`：receipt、admission core/seal、签名输入和 digest 绑定是否严格、无歧义且可做 invalid-first 验证？
2. `issuer_authority`：issuer kind、key usage、工作负载身份和 Broker/Sandbox 独立作证是否由 Trust Policy 精确授权？
3. `algorithm_policy`：算法、canonicalization、签名编码、时间和重放规则是否足以避免降级、混淆和摘要回环？
4. `key_rotation_revocation`：历史签发策略与当前验证策略、轮换、吊销、retrospective compromise 和 release-time policy fence 是否闭合？

### 05｜ExecutionBroker / Sandbox

1. `composite_backend_identity`：backend 是否表示 ExecutionBroker 组合身份，而不会把 AgentRuntime、SandboxProvider 或 Tool Adapter 任一方冒充整体？
2. `broker_sandbox_independence`：Broker receipt 与 Sandbox witness 是否在 workload、leaf key material、key usage 和绑定对象上独立？
3. `phase_witness_binding`：REAL/MOCK/TEST 以及 admission/activity/review-ready/result/failure/termination 是否只能由对应受信证据产生，不能从 status 或日志自报推导？

### 06｜Knowledge

1. `four_key_provenance`：Observer 投影是否只携带 `scope_id + chunk_id + source + fingerprint`，且保持引用可追溯而不泄漏正文或未授权元数据？
2. `authority_unresolved_boundary`：当前只有检索 provenance、缺少 KnowledgeVersion 权威/有效/适用证明时，是否明确保持 unresolved，绝不伪装为权威依据？

### 07｜工作台 / Observer

1. `adapter_v3_compatibility`：FactSet 和 readSnapshot 是否与冻结的 Stage C Runtime Observer Adapter v3 一致且没有隐式 UI 数据源？
2. `diagnostic_only`：`DIAGNOSTIC_ONLY` 是否只支持受限诊断体验，不会显示为 REAL、completed 绿色、交付成功或人签？
3. `failure_experience`：稳定失败码、隐藏存在性、证据缺失、部分可见和重试语义是否能驱动诚实、低焦虑且不泄密的界面？

## 6. 决定与发现项规则

- `approve`：共同问题和本域问题全部为 `satisfied`，每项都有具体 `rationale`，且不存在未处置的阻断发现。
- `changes_required`：至少一个问题为 `unsatisfied`，并在 `findings_refs[]` 或问题级引用中给出可修复的阻断项。
- `reject`：至少一个问题为 `unsatisfied`，并给出根本性拒绝依据。
- `pending`：仅供尚未完成的模板使用，不是正式决定。

不允许用 `not_applicable` 跳过共同问题或本域问题。每个 round 每个责任域只允许一个 `decision_revision=1`；任何更正、撤回、后续拒绝或重新批准都必须进入新的 `review_round_id`，并由包外追加式账本保留旧 Core、Seal、findings 和新 round 的前序引用。若任一域要求修改冻结合同，当前评审轮立即停止。修改后必须生成新 SHA 和新 `review_round_id`，七域重新签署；不得覆盖、删除或迁移旧决定。

## 7. 机械检查

检查冻结摘要、目录结构、七域与问题集合：

```bash
python3 docs/reviews/production-snapshot-assembler-read-v1/verify_review_gate.py \
  --structure-only
```

检查七域本地记录是否齐备，并确认正式门继续 fail-closed：

```bash
python3 docs/reviews/production-snapshot-assembler-read-v1/verify_review_gate.py \
  --require-approvals
```

初始模板的第一条命令应通过；第二条命令必须 fail-closed，并逐域列出缺少的责任人、任命证据、评审计划摘要、决定、时间、回答和 Decision Seal。即使本地记录全部齐备，当前第二条命令也必须以 `EXTERNAL_TRUST_VERIFICATION_UNSUPPORTED` 拒绝并输出 `contract_review=PENDING_EXTERNAL_VERIFICATION`。未来包外 verifier 真正接通、独立审查并验证全部证据后，才可以由新版本门禁输出 `contract_review=APPROVED` 和 `eligible_for_separate_implementation_slice=true`；`implementation_authorized` 仍必须为 `false`。

## 8. 评审会议最小议程

1. 主持人现场复算冻结 SHA 与 byte length，并记录七位责任人的正式身份来源、职责作用域和任命证据；
2. 冻结评审计划，复算 `review-manifest.json` 摘要；之后不得替换责任人、问题或 round；
3. 七位责任人分别陈述共同问题和本域问题的回答，不用总负责人替其他域代签；
4. `changes_required` 或 `reject` 先登记发现项，不在会议中静默改合同；
5. 冻结 Decision Core raw bytes，并由可信签署/审计通道生成绑定其摘要的 Decision Seal/AuditReceipt；
6. 由包外可信策略核验 actor、任命、凭据、时间和签署证据，回填核验 receipt 引用；
7. 运行两条机械检查并保存输出；
8. 七域全通过时只宣布“合同评审通过”，不得宣布“已实现”“可生产”或“获准上线”；
9. 如需实施，另行提交精确实施切片及其授权证据。

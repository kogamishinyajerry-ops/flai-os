# ADR-0042：Trust Architecture——DecisionCase 理论与对象边界

- 状态：Accepted（owner 于 2026-08-09 明确接受 exact review candidate `1d4dde9`；[决定记录](https://github.com/kogamishinyajerry-ops/flai-os/issues/72#issuecomment-5229627052)）
- 日期：2026-08-09
- 基线：`origin/main@a32b36e`
- 关联：[宪法](../00_FLAi-OS_Constitution.md) · [ADR-0029](ADR-0029-knowledge-chunk-provenance-readback.md) · [ADR-0031](ADR-0031-agent-shell-read-only-ontology-projection.md) · [ADR-0034](ADR-0034-task-evidence-bound-asset-candidate-ledger.md) · [ADR-0037](ADR-0037-v1-owner-object-authorization.md) · [ADR-0039](ADR-0039-nemoclaw-openshell-sandbox-execution-spike.md) · [ADR-0041](ADR-0041-l2-object-link-interface-metadata-layer.md)
- 研究依据：[Issue #70](https://github.com/kogamishinyajerry-ops/flai-os/issues/70) · [PR #71](https://github.com/kogamishinyajerry-ops/flai-os/pull/71) · [固定研究版本 `08e592a`](https://github.com/kogamishinyajerry-ops/flai-os/blob/08e592a131ca98e3463fac8e834a066c5f651afa/docs/research/FLAI-OS-TRUST-ARCHITECTURE-V1.md)
- 性质：规范性架构边界；**不授权**数据库、公共 API、状态机、UI、Agent、Tool 或外部系统实施

owner 已于 2026-08-09 接受 exact review candidate `1d4dde9`；本状态转移只记录该人类决定，
相对候选版本不改变承重架构语义。`Accepted` 表示本文中的架构原则和对象语义已冻结；
它不表示这些对象已在生产 Runtime 中实现，不表示 A1 已开工，也不表示平台满足任何法规
或标准。本状态也不表示 PR 已合并，不替代仓库保护规则或另行作出的显式合并授权。

## 1. 阅读约定

本文用四种标签防止把现状、决策和假设混成一张“已经实现”的架构图：

- **[当前事实]**：在基线源码或既有 Accepted ADR 中可复核；
- **[架构决策]**：由本 ADR 冻结，后续实现不得自行改变；
- **[拒绝方案]**：本阶段明确不采用；
- **[未决]**：必须由后续 Issue / ADR / 实验回答，不能由实现者暗自补齐。

## 2. 背景：为什么 Task 还不是可签发的工程判断案卷

FLAi-OS 已经有任务、来源、执行摘要、人工审核和审计事件，但这些能力目前分别服务于
任务执行、资产候选和 owner 隔离；它们尚未构成一个能把“这次判断回答什么、依据什么、
用什么方法、适用什么规则、谁有权确认、确认后做了什么”锁成同一不可拆换版本的对象。

### 2.1 当前已具备的部分可信能力

1. **[当前事实] 人是现有任务审核的唯一出口。** `waiting_review` 只能由人工
   approve/reject 转出；签发者来自认证 session，不接受客户端自报身份。
   [源码](../../backend/app/api/tasks.py#L1770-L1802)
2. **[当前事实] 现有 approve 会重验一份执行摘要。** 该摘要绑定 Agent Package
   Snapshot、任务参数、输入文件 ID 和输入文件内容证据，并在审核时重新校验。
   [生成端](../../backend/app/runtime/runtime.py#L803-L826) ·
   [审核端](../../backend/app/storage/repos.py#L618-L655)
3. **[当前事实] 当前签发是 V1 `owner_signoff`。** creator 自签允许且必须如实标记；
   reviewer assignment、委托、细粒度 RBAC、资格、部门、职级和职责分离均未实现。
   [ADR-0037 §6](ADR-0037-v1-owner-object-authorization.md#6-owner_signoff-与-human-signer-cohort) ·
   [源码边界](../../backend/app/api/tasks.py#L1823-L1832)
4. **[当前事实] 知识引用已有受控回源，但读的是当前语料而非检索时点快照。**
   fingerprint 可提示漂移，不能承担签发级 SourceRevision 身份。
   [ADR-0029 §D3](ADR-0029-knowledge-chunk-provenance-readback.md#d3-诚实边界记录在案不静默)
5. **[当前事实] Agent workflow 仍作为受信 Python 在 worker 进程内导入和调用。**
   当前架构不是任意不可信代码沙箱；ADR-0039 仍是 Proposed spike。
   [源码](../../backend/app/runtime/runtime.py#L922-L939) ·
   [ADR-0039](ADR-0039-nemoclaw-openshell-sandbox-execution-spike.md)
6. **[当前事实] 当前审核日志不是不可抵赖账本。** task event 与文件 audit log 分属不同
   持久化域，不能原子提交，且源码明确说明 audit log 没有篡改抗性。
   [源码](../../backend/app/api/tasks.py#L1823-L1827)

### 2.2 当前摘要没有证明什么

**[当前事实]** `execution_evidence_digest` 没有绑定输出文件字节、Claim、EvidenceSpan、
公开工程依据、Prompt/RAG/model/tool 精确版本、Policy 决定、Authority 决定或动作合同。
这不是现有机制的缺陷陈述，而是它为任务执行证据设计时的真实范围。

因此，下列推断一律不成立：

- “摘要相同”不等于结论正确；
- “引用存在”不等于证据适用；
- “用户已登录”不等于具有组织资格；
- “任务已 approve”不等于审阅者理解了材料；
- “任务 completed”不等于外部后果成功或安全；
- “有事件日志”不等于记录不可抵赖。

## 3. 核心理论裁决

### 3.1 双层措辞

**[架构决策] Trust Engineering 是 FLAi-OS 的核心架构原则。**

凡 AI 输出会进入工程判断、组织记录、受治理知识或动作链，平台必须能明确给出：

1. 它回答的 Task Contract；
2. 它依赖的精确 Evidence；
3. 面向审阅人的公开工程依据与方法边界；
4. 仍未解决的不确定性；
5. 适用的 Policy；
6. 需要何种 Authority 以及由谁作出人类决定；
7. 决定后实际发生的 Action、Receipt 与后置检查。

**[架构决策] “Trust Engineering 能显著改善工业判断”仍是可证伪理论候选。**

本 ADR 接受前述设计方向，但不预先接受其效果。若真实实验表明它不能降低决定性错误
的误批，不能改善异议质量，或其生命周期成本持续高于避免的损失，就必须收窄、替换或
拒绝相关机制，而不是用更多信任文案掩盖失败。

### 3.2 产品角色

**[架构决策]** Agent 是执行部件，不是最高权威；DecisionCase 是影响工程判断的
AI 输出进入治理链时的逻辑根；人是唯一签发者。模型、规则和工具可以提出 Claim、
证据关系、公开依据与候选动作，但不能生成有效 Human Authorization。

该裁决不要求所有普通会话都变成工程表单。短暂、非承重的对话建议可以保持会话形态；
一旦内容要被封存、发布、晋级知识或授权动作，就必须进入受版本约束的 DecisionCase。

## 4. DecisionCase 聚合边界

### 4.1 深接口，而不是可变“大对象”

**[架构决策]** 接受 `DecisionCase` 作为逻辑聚合根，但拒绝建立一个同时保存任务状态、
证据、签发、执行、结果和学习状态的可变巨表。每种对象独立版本化或追加记录，并只通过
不可变 ID/digest 连接。

| 对象 | 身份与版本 | 负责什么 | 失效或演进 | 明确不证明 |
| --- | --- | --- | --- | --- |
| `DecisionCase` | 服务端生成稳定 `case_id`；服务端派生 immutable owner/source lineage；无内容修订 | 长期逻辑身份、关联根、修订历史 | 追加 Revision；head 只是导航指针，不是权威 | 不证明存在有效结论或签发 |
| `DecisionRevision` | `case_id + revision + schema_version + digest`；正文不可变 | 一次完整、可复核的判断案卷 | 任一承重内容变化都新增 `revision + 1` | 不证明正文正确或适用 |
| `AuthorizationRecord` | 服务端生成 ID；绑定 exact revision/Policy/Authority/Action digest；insert-only | 记录认证人类对精确对象作出的 approve/reject | 撤销、过期、失效以新事件/记录表达，不改旧记录 | 不证明签发人胜任、独立或被组织授权 |
| `ExecutionReceipt` | 绑定唯一 Ticket digest；insert-once | 记录实际调用、前后状态、副作用、偏差和 postcheck | 后续补偿产生新案卷/动作；旧 Receipt 永不删除 | 不证明动作符合原意或结果长期有效 |
| `OutcomeObservation` | 服务端 ID + 观察时间 + 来源版本/digest；append-only | 记录执行后的真实效果、现场反馈和反例 | 新观察可矛盾、取代解释但不改写旧观察 | 不自动证明因果关系 |
| `LearningCandidate` | 独立 candidate ID/revision/digest | 把经去敏和适用域说明的经验送入独立策展 | 只有独立人工策展可接受；撤回继续传播 | 不因任务获批而自动成为权威知识 |

**[架构决策]** `DecisionCase` 在本 ADR 被接受后先作为协议级逻辑根生效；本 ADR 不授权专用表。
只有当 A1 或后续切片证明至少三个独立消费者需要同一绑定/失效逻辑，专用持久化才有
“深接口”证据。若只有一个消费者，应优先保留为既有对象上的确定性投影。

### 4.2 owner、读取与列表门

**[架构决策]** DecisionCase 不创造新的共享读取 cohort。A0/A1 只允许
`origin=user` 的 exact-owner 案卷，并完整继承 ADR-0037：

- `owner_username`、source task/case lineage 与 classification basis 全部由服务端派生，
  不接受客户端自报；owner 为 NULL、空白、非规范或来源链不可证时 fail-closed；
- owner/密级门必须早于状态、摘要、错误和正文读取；foreign、missing、legacy-NULL 对外
  使用同一泛化 404，不能把 case existence、digest 或 evidence health 变成侧信道；
- 列表必须先在 SQL 中按 owner/合法 cohort 过滤，再排序、分页和计数；
- 每个平面只向已通过对象 owner 与内容密级门的消费者开放；`denied/unknown` 不返回正文；
- “可读对象”与“有权签发”是两种不同证明。通过 owner 读取门不会产生 Authority allow；
- tenant-wide eval evidence、共享案卷、委托访问或组织角色扩张必须另立 ADR，不得由 A1
  沿用“已登录即共享”的旧口径。

outer binding 中的 `case_subject_digest` 至少绑定服务端派生的 source identity、origin、
owner 和不可变来源关系。owner/source lineage 漂移必须形成新 Case 或失效事实，不能沿用
旧 `case_digest`。

### 4.3 不可变信封

**[架构决策]** 所有可寻址的 DecisionCase 子对象遵循同一最小信封语义：

```yaml
immutable_object:
  id: "server-generated stable id"
  case_id: "server-generated stable case id"
  revision: 1
  schema_version: "versioned contract id"
  body: "canonical JSON value"
  digest: "sha256:<64 lowercase hex>"
```

- `digest` 不包含自身；
- body、schema version 或任何承重引用改变时必须新建修订，禁止原地改写后沿用地址；
- canonicalization 必须版本化并与 JSON Schema/Pydantic parity 同测；
- 时钟、数据库自增 ID、展示文案和可变状态不进入内容摘要，除非它们本身是被签发内容；
- 历史对象不可用“回填得更完整”为由伪造 signer、版本或 digest；只能标成
  `legacy_unverified` 或形成新修订。

本节冻结语义，不冻结 Python 类名、SQL 表名或字段物理布局。

## 5. 五平面分离

### 5.1 平面职责

**[架构决策]** 每个 DecisionRevision 分离为五个承重平面：

| 平面 | 最小内容 | 谁可提出 | 谁能使其有效 | 禁止混入 |
| --- | --- | --- | --- | --- |
| **Evidence** | SourceRevision、EvidenceSpan、supports/contradicts/qualifies 关系、来源密级、检索/观察时点 | 人、确定性工具、模型草稿 | Evidence Policy 的机械校验 + 人类审阅 | 模型自信、Policy allow、组织资格 |
| **Logic** | Claim、公开 Engineering Rationale、方法/规则、假设、限制、model/Prompt/RAG/tool 版本引用 | 人、模型、工具、规则 | 人类对公开依据的审阅；确定性校验结果 | hidden CoT、Authority、动作成功声明 |
| **Policy** | 适用规则版本、输入事实、候选判定与未决条件 | 版本化规则/Policy adapter | 服务端提交时重算；unknown/deny 不得当 allow | “谁登录了”、模型建议、执行结果 |
| **Authority** | 所需资格、范围、委托和期限；不含提交后的 Authority Decision | 组织权威来源；模型只能提示缺口 | 服务端验证的组织规则与认证 session | 业务结论、Policy 判定、客户端自报角色 |
| **Action** | 签发前的 ActionContract、目标 expected-head 与前后条件 | 人/模型可提候选；系统解析 | 有效 Policy + Authority + exact-revision 人签；执行器仅消费后续 Ticket | Ticket、Receipt；将“已授权”写成“已成功” |

Task Contract 与 classification basis 是整个案卷的公共前置，不塞进任一平面。五个平面
即使暂不适用，也必须用版本化 `not_applicable` 对象明确表达，禁止通过省略字段制造摘要
歧义。

**[架构决策] EvidenceSpan 的精确回源语义现在冻结，不下放给 A1 决定。** 每个决定性
EvidenceSpan 至少绑定 immutable SourceRevision/full digest、稳定 selector、selected-text
digest、bounded prefix/suffix context、与 Claim 的 supports/contradicts/qualifies 关系、
简短 annotation、source/version/location/classification。审阅面必须能在受控读取后打开该
精确 SourceRevision，在原文对应位置高亮选中内容并同时显示上述简注和身份信息。缺少任何
一项只能标记为 partial/unknown，不能显示为“已精确回源”。PDF/OCR/Office/Excel/图片的
selector **具体编码**仍是未决实现问题，但“必须精确定位和高亮”不是未决项。

### 5.2 分平面摘要与最外层绑定

**[架构决策]** 每个平面独立 canonicalize 并摘要，最外层 `case_digest` 再把五个精确
版本、任务合同和分级依据锁成同一个不可拆换对象：

```text
case_digest = SHA256(canonical_json({
  schema_version,
  case_id,
  revision,
  case_subject_digest,
  task_contract_digest,
  classification_basis_digest,
  evidence_plane_digest,
  logic_plane_digest,
  policy_plane_digest,
  authority_requirement_digest,
  action_contract_digest,
  valid_until
}))
```

分平面摘要的目的不是增加术语，而是支持四项独立治理能力：

1. **独立所有权**：证据、Policy、Authority 和动作适配器可由不同责任域维护；
2. **最小权限**：消费者只读取其职责所需平面，不因一个万能对象获得全部正文；
3. **可检查差异**：新 Revision 能说明究竟是哪一平面变化；
4. **定向失效**：SourceRevision、Policy epoch、Authority 或 target head 漂移能找到依赖面。

最外层摘要防止攻击者从不同 Revision 各取一个“看起来有效”的平面重新拼装。任何子摘要
或引用不一致，freeze/sign 必须失败且零权威写入。

PolicyDecision、AuthorityDecision、AuthorizationRecord、ExecutionTicket 和
ExecutionReceipt 都在 Revision 冻结后逐层绑定 `case_digest`，绝不写回已签发 Revision。
因此 Action Plane 只摘要签发前 ActionContract；Ticket/Receipt 是后续追加对象，不参与
其前置摘要，避免“先有签发才能执行、先有回执才能签发”的循环。

这里的 `policy_plane_digest`、`authority_requirement_digest` 与 `action_contract_digest`
命名差异是刻意的：Policy 平面包含规则输入与候选判定，Authority / Action 平面在签发前
分别只包含 requirement / contract，不能把提交后的决定或回执倒灌进 Revision。A0 中的
PolicyDecision 与 AuthorityDecision 仅表示服务端提交时重算、再绑定 `case_digest` 的决定性
结果引用，**不由本 ADR 新建独立持久化对象**；若后续需要独立 ID、schema、版本、期限、
撤销或存储，其完整对象语义必须由 A2 / A3 的 Issue 或 ADR 另行裁决。

### 5.3 摘要的证明边界

**[架构决策]** digest 只证明“按声明 canonicalization 得到的内容身份和完整性一致”。
它不证明：

- 来源说的是真话；
- EvidenceSpan 对 Claim 具有充分支持；
- 方法适用于当前工况；
- Policy 选对了；
- 签发者具备组织资格；
- 动作真的发生或后置条件成立；
- 记录不可抵赖。

这些命题必须分别由来源治理、公开依据、适用性评估、Policy、Authority、Receipt、
postcheck 或未来密码学机制承担，不能让一个 SHA-256 代替全部信任工作。

## 6. Human Authorization 与模型边界

### 6.1 所有模型草稿必须经过人

**[架构决策]** 凡模型生成的 Claim、摘要、方案、证据关系、工程依据、Policy 建议、
学习候选或动作建议要进入 DecisionCase、交付物、组织知识或动作链，必须：

- 明示 `model_draft` / `waiting_review`；
- 保留实际 model profile、model、Prompt/RAG/tool/package 的版本或摘要引用；
- 不能自动生成有效 AuthorizationRecord；
- 不能因历史准确率、模型自报置信度或“看过原文”自动晋级；
- 只有认证人类对 exact `case_digest` 的显式动作才能离开待审状态。

纯会话中的临时模型建议若不进入上述受治理载体，可以保持非持久建议形态，但必须仍被
界定为 AI 输出，不能被 UI 暗示为已签发结论。

### 6.2 人签证明了什么

**[架构决策]** 有效 AuthorizationRecord 至少绑定：

```text
decision_revision_digest
+ policy_decision_digest
+ authority_decision_digest
+ action_contract_digest
+ server-derived signer/session/time
```

它证明的是：一个通过认证且在提交时通过当前 Policy/Authority 检查的人，对一个精确
Revision 作出了记录中的决定。它**不自动证明**此人完整阅读、正确理解、具有专业胜任力、
保持独立、获得合法委托，或结论本身正确。

protected approve 只有在 Evidence/Policy/Authority 满足对应 action requirement 时才可
成立；reject/challenge 在证据 missing、stale、tampered、conflicting、denied 或 Policy /
Authority 为 deny/unknown 时仍应可记录。它们同样绑定 exact revision 和当时的决定摘要，
但绝不产生 allow、Ticket 或外部动作。

当前 V1 只能如实沿用 ADR-0037 的 exact-owner self-sign 边界。组织资格、委托、撤销、
职责分离和利益冲突属于 A3；在 A3 前不得把“登录账号可签”改写成“组织已授权”。

### 6.3 公开工程依据，不保存 hidden CoT

**[架构决策]** 案卷保存可检查的 Claim 关系、Evidence edge、方法/规则、假设、限制、
反证和简短 `public_basis`。不得要求、存储或展示 hidden chain-of-thought、scratchpad、
raw reasoning trace，也不得把模型生成的流畅叙事称为其真实内部推理。

模型配置和调用上下文通过版本/digest 进入 Logic Plane；审阅人看到的是工程可审计依据，
不是“窥视模型大脑”的产品承诺。

## 7. 失效、撤销与历史保留

**[架构决策]** Revision 不可变，效力可失效。二者不能混为“改一行状态”：

1. SourceRevision missing/stale/tampered、Policy epoch 变化、Authority 过期/撤销、目标
   expected-head 漂移时，追加 invalidation 事实；不改写原 Revision；
2. 需要新证据或新判断时创建新 Revision，并重新经过 Policy、Authority 与人签；
3. 旧 AuthorizationRecord 保留为历史动作，但不能授权新 Revision 或漂移后的动作；
4. 尚未 claim 的 Ticket 随其绑定条件失效；claim 与 revoke 必须由后续 A4 用 CAS 决胜；
5. Receipt 永不删除；补偿是新 ActionContract、新案卷和新人签，不是假装原动作没发生；
6. OutcomeObservation 可以相互冲突；冲突是新证据，不得回写成一个“最终真值”；
7. task approval 不自动让 LearningCandidate 成为权威知识，独立策展链始终保留。

本 ADR 冻结上述传播方向，但不授权状态枚举、表、事件 schema 或 worker 实现。

## 8. A1 的证伪职责

**[架构决策]** [#73](https://github.com/kogamishinyajerry-ops/flai-os/issues/73)
是第一个验证样板，不是本 ADR 的实现附录。#73 的合同、分支和 PR 必须钉扎本文件的
exact Git commit/blob；引用可变 `main`、Issue 标题或裸 `ADR-0042` 不构成版本绑定。本 ADR
若在 A1 开工后改变承重语义，A1 必须失效既有设计审并重新确认引用版本。它只能用
`release_internal_summary.v0` 验证：

- TaskContract、Claim、EvidenceSpan、公开依据与结构化不确定性是否能形成可用合同；
- bounded source preview 与单一原文浮窗是否能帮助审阅人定位决定性证据；
- exact revision review gate 能否机械拒绝 missing、stale、tampered、conflicting、denied、
  partial、wrong-authority 与 digest drift；
- 相比当前流程，误批、漏检、挑战率、审阅时间和主观负担是否改善；
- 新对象是否被多个消费者真正复用，还是只有一条样板在承担抽象成本。

以下结果会反驳或迫使收窄设计：

- 重要字段/字节变异、越权提交或自动知识晋级没有 100% 被机械拒绝；
- 植入 stale/tampered/conflicting 样本后，误批不降；
- 审阅时间显著增加而漏检不降；
- 公开依据在替换决定性证据后基本不变；
- 只有 A1 使用 DecisionCase，删除它不会迫使三个以上消费者重写同一绑定逻辑；
- 保守估计的全生命周期成本持续高于避免的损失。

A1 通过也只说明该合同/交互在一个受控样板中可行，不能证明整个 Industrial Trust
Engineering 理论，更不能证明法规合规。

## 9. 拒绝方案

### 9.1 用当前 Task 或一个巨型 Case 表承载全部状态

**[拒绝方案]** 可变任务行适合运行状态，不适合同时作为不可变判断、授权、执行事实、
结果观察和学习候选。一个巨表会把不同 owner、生命周期和失效语义耦合在同一更新面。

### 9.2 一个 Trust Score、星级或模型自报置信度

**[拒绝方案]** 总分会隐藏 evidence coverage、freshness、conflict、input completeness、
method applicability 和 deterministic validation 的不同失败方式。没有实测方法时必须显示
`unknown/unmeasured`，不能生成“87% 可信”。

### 9.3 保存模型 hidden chain-of-thought 作为推理证据

**[拒绝方案]** 它既不是稳定工程合同，也不能代替公开依据。只保存外部可检查的命题、
证据关系、方法、规则、假设、限制和反证。

### 9.4 先引入图数据库、RDF 或通用 nodes/edges

**[拒绝方案]** ADR-0031/0041 已选择既有 JSON Schema、digest 引用和确定性只读投影。
除非至少三个登记的生产多跳查询证明 SQLite/JSON 投影无法满足规模和延迟目标，否则不评估
Neo4j、RDF 或通用知识图谱平台。

### 9.5 把人签、日志或摘要包装成更强保证

**[拒绝方案]** 不把 owner self-sign 称为独立复核，不把 audit log 称为 WORM，不把 digest
称为真理证明，不把 completed 称为正确，不把 approve 称为动作成功。

### 9.6 从概念图直接反推五张表和一套新平台

**[拒绝方案]** 本 ADR 不预设表数量、ORM、图存储、Redis、Celery、CDC、WORM、PKI、
新框架或第二审批真相源。物理模型必须由 A1 读写模式和事务边界倒推。

### 9.7 用标准名称声明合规

**[拒绝方案]** 本设计借鉴 assurance case、provenance、human oversight 和 traceability
思想，但不是 OMG SACM、NIST AI RMF、FAA、EASA、NASA 或适航法规的符合性实现、认证
证据或法律意见。具体项目适用性必须由组织 Authority 和合规流程另行判断。

## 10. 后果

### 正向后果

- 工程判断、签发、执行、结果和学习不再共享一个含糊的“任务完成”语义；
- 证据、逻辑、规则、权限和动作的责任边界可以独立审查、最小授权和定向失效；
- 模型产物始终停留在草稿/候选侧，人类决定有精确版本对象可签；
- 现有 Task Center、SQLite、Pydantic、JSON Schema、Model Gateway、Tool Registry、
  event ledger 和 TaskDetail 仍可作为后续切片的复用底座；
- 理论效果有明确 falsifier，不以漂亮架构图自证。

### 负向后果与成本

- 每次承重判断需要更多版本、摘要、来源与失效管理；
- 审阅 UI 若不能聚焦决定性证据，可能增加负担并诱发 checkbox theater；
- 当前 exact-owner 模型与真正组织 Authority 之间的差距会更显眼；
- 专用对象若没有多消费者，会成为浅抽象；A1 必须允许“删掉它更简单”的结论；
- 标准、合规、密码学签章和任意代码沙箱仍是独立问题，不能由本 ADR 一次解决。

## 11. 未决问题

以下问题保持 **[未决]**，不得在 A1 或其他施工票中静默拍板：

1. 哪类任务必须证据完整才能 approve；哪些创作任务只需声明无外部证据？
2. exact-owner self-sign 在何种风险级别仍可接受；何时要求独立 reviewer 或职责分离？
3. 组织资格、范围、委托、期限、撤销 SLA 与利益冲突的权威数据源是什么？
4. restricted 来源能否保存 bounded quote；不能保存时采用何种运行时授权定位器？
5. PDF/OCR、Office、Excel、图片和动态知识索引分别采用何种 selector 编码，才能实现
   已冻结的 SourceRevision 精确定位、高亮和 selected-text digest 语义？
6. tampered/conflicting 阻断 approve 本身，还是只阻断 protected action？
7. 如何证明监督有效而不退化为员工监控或“打开过证据”的形式主义？
8. 哪些动作真实可补偿；哪些不可逆动作必须长期由平台外人工执行？
9. 何时才需要密码学签章、WORM 或外部时间戳？
10. 理论晋级所需的代表性案例、效应量、误批基线和成本阈值是多少？
11. owner/source lineage 发生何种变化时必须建立新 Case，何种变化只追加失效事实？

## 12. 后续顺序与授权边界

本 ADR 只完成 A0。后续必须逐票裁决：

1. **A1 / #73**：只读证据闭环与对照实验；当前被 #72 原生阻塞；开工时必须在 Issue、
   分支和 PR 中钉扎本 ADR 的 exact accepted commit/blob；
2. **A2**：签发摘要、challenge/dissent、失效与 supersession；
3. **A3**：组织 Authority、资格、委托、撤销与职责分离；
4. **A4**：低风险可逆 Action Ticket / Receipt；与任意代码沙箱严格分开；
5. **A5**：OutcomeObservation、LearningCandidate、独立策展与效果观测。

独立安全债务——workflow/tool 隔离与强 kill、Tool implementation snapshot、Agent output
contract 生产校验、visibility/allowed_roles 真正执行、tamper-evident audit——不因本 ADR
Accepted 而自动获得实施授权。

## 13. 本 ADR 的机械验收

本票只允许新增本文件。PR 合入前必须同时满足：

1. 本文显式保留 [当前事实]、[架构决策]、[拒绝方案]、[未决] 四类边界；
2. 所有本地 Markdown 引用目标存在，固定研究依据指向 `08e592a`；
3. `git diff --check` 退出 0；
4. `UV_OFFLINE=1 bash scripts/verify_all.sh` 完整退出 0；
5. 独立只读复核没有未处置 P0/P1；
6. PR 关联 `Closes #72` 和 `Part of #46`，保持未合并等待 owner review；
7. #73 继续被 #72 阻塞，在本票完成前不得实施；解除阻塞后也必须引用本 ADR 的 exact
   accepted commit/blob，不能只引用可变路径或编号。

## 14. 最终不变量

> 每一个进入工程判断、组织记录、受治理知识或动作链的 AI 输出，都必须能绑定它回答的
> 任务、依赖的精确证据、公开工程依据、尚未解决的不确定性、适用规则、有权的人类确认点，
> 以及确认后实际发生的动作；任何一项未知，都必须被如实保留为未知。

同时永久保留六条诚实边界：

- 证据链不是事实真理机；
- 公开依据不是模型内部思维的忠实证明；
- 人签不是胜任、独立和组织授权的自动证明；
- 摘要不是正确性、适用性或不可抵赖证明；
- 日志不是天然 WORM；
- A1 不是整套工业 Trust Engineering 理论的证明。

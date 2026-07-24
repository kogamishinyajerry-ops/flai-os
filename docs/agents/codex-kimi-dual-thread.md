# Codex + Kimi 双线程开发试运行手册

> 状态：非规范性（NON-NORMATIVE）
>
> 适用范围：人工编排的首轮双线程试运行
>
> 权威合同：[`17_Feishu_Organizational_Hub.md`](../product/FLAi-OS_V0.2_Design_Package/17_Feishu_Organizational_Hub.md) 中的
> `DeliveryWorkItemV1`、`AssistantDispatchReceiptV1`、`AssistantRunObservation` 与
> `DevelopmentHandoffV1`
>
> 约束：本手册不新增生产 Schema、状态、状态转换、权限或签发角色；与权威合同冲突时，以权威合同为准。

## 1. 结论

Kimi 可以作为项目中的正式**机器执行器成员**参与开发，但不能被当作真人、CODEOWNER、
PR 批准者、合并者或发布签发者。首轮试运行采用两个 sibling `DeliveryWorkItemV1`：

- Codex 线程承担一个有界实现工作包；
- Kimi 线程只承担独立评审、UI/UX 候选或测试夹具中的一个有界工作包；
- 两个工作包冻结到同一 `frozen_sha`，使用不同 branch/worktree，并且
  `owned_file_scope` 与 `owned_interface_scope` 不重叠；
- 飞书是工作发现、编排和回告入口，GitHub 是代码、commit、PR、CI、approval 与 merge
  的事实来源；
- 具名人类 `human_owner` 是唯一可以接受 handoff、请求集成或返工的人；PR review/approval、
  merge 和发布签发只能由 GitHub/组织策略授权的具名真人角色执行，这些角色可以与
  `human_owner` 不同。

当前能力边界：

| 能力 | 当前状态 | 允许的动作 |
|---|---|---|
| 本手册描述的人工双线程流程 | `ACCEPTED-NOT-IMPLEMENTED` | 可用于创建试运行工作包和人工核对 |
| Kimi Adapter 的真实 dispatch/control/handoff 与 runtime witness | `DECLARED-NOT-VERIFIED` | 不得仅凭模型名、配置或自然语言自报标成真实 Kimi run |
| 飞书自动调度、自动控制和自动状态推进 | `DECLARED-NOT-VERIFIED` | 首轮只做人工编排或只读投影，不得声称已自动化 |
| GitHub commit、PR、CI、approval、merge 事实 | 以 GitHub 实际回读为准 | 不接受飞书单元格或模型总结代替 |

因此，首轮可以立即开展**人工受控试运行**，但在 Kimi Adapter 形成可验证
`AssistantDispatchReceiptV1` 与 backend/reality witness 之前，不能把 Kimi 的自报运行投影为
权威 `RUNNING`，也不能形成合格的 `DevelopmentHandoffV1`。

## 2. 三层责任边界

| 层 | 负责什么 | 明确不负责什么 |
|---|---|---|
| 飞书组织中枢 | 工作收件箱、两个工作包的只读视图、人工分派入口、阻塞与结果回告、GitHub 深链 | 不拥有 commit、PR、CI、approval、merge 或运行事实 |
| GitHub | issue、branch、commit、diff、PR、CI、CODEOWNERS、branch protection、approval、merge | 不代替组织需求策展、人员责任或业务签发 |
| FLAi Delivery Governance / Coordinator | `DeliveryWorkItemV1`、dispatch/control receipt、运行观察、handoff、对账和集成状态投影 | 不替人接受成果、批准 PR、合并或签发发布 |

飞书字段是权威对象的投影，不是可随意编辑的第二份总账。任何飞书与 GitHub/owner receipt
不一致的情况都显示为缺口或 `EFFECT_UNKNOWN`，不得使用 last-write-wins 修正。

## 3. 首轮团队角色

### 3.1 具名人类 owner

每个 sibling work item 必须指向同一个或分别明确的具名 `human_owner`。人类 owner 负责：

- 冻结目标、`frozen_sha`、密级、文件与 Interface scope；
- 确认两个 scope 不重叠；
- 决定允许的工具、外联和预算；
- 查看真实 diff、验证结果、风险与未决问题；
- 按权威状态机决定 `NEEDS_REWORK` 或 `ACCEPTED`；
- 把 handoff 送入 GitHub 原生 Surface，并等待 `required_reviewer`、CODEOWNERS、branch
  protection、CI 与 merge owner 各自完成其被授权的动作；
- 根据 GitHub 回读事实确认是否可以进入 `INTEGRATED`。

### 3.2 Codex 机器执行器

Codex 只在自己的 `branch_worktree` 和 `owned_file_scope` 内工作。首轮建议承担一个小而完整、
可机械验证、不会修改生产 Schema/认证/安全状态机的实现工作包。它可以提交 commit 和
`DevelopmentHandoffV1`，但不能接受自己的 handoff、批准自己的 PR 或合并。

### 3.3 Kimi 机器执行器

Kimi 是与 Codex 并列的机器执行器身份，不是 Codex 的匿名“建议来源”。首轮仅允许以下一种
边界清晰的任务：

1. 对 Codex 工作包做独立评审，但不形成 GitHub approval；
2. 在不触及生产权限、认证、安全或数据状态机的独立文件范围内产出 UI/UX 候选；
3. 在独立文件范围内补充 invalid-first 或回归测试夹具，不修改被测生产接口。

首轮 Kimi 不承担：

- 认证、授权、classification、Secret、Safety、receipt 或签发链实现；
- 数据库迁移、生产 Schema 或状态机修改；
- 与 Codex 同文件、同 Interface 的并发写；
- CODEOWNER、PR approval、merge、release 或生产部署；
- 未获批准的数据外发。

## 4. 两个 sibling work item

不增加 `parent_id`、`lane_id` 或新的状态字段。两个 work item 通过相同的
`source_commitment_ref`、`outcome_contract_ref`、`frozen_sha` 和经人工确认的共同目标形成
sibling 关系，分别使用自己的 `work_item_id`、scope、branch/worktree、预算和执行器 receipt。

```text
同一 source_commitment_ref / outcome_contract_ref / frozen_sha
├── DeliveryWorkItemV1 A
│   ├── Codex versioned_executor_ref
│   ├── branch_worktree A
│   ├── owned_file_scope A
│   └── owned_interface_scope A
└── DeliveryWorkItemV1 B
    ├── Kimi versioned_executor_ref
    ├── branch_worktree B
    ├── owned_file_scope B
    └── owned_interface_scope B

A.file ∩ B.file = ∅
A.interface ∩ B.interface = ∅
```

两个 work item 至少逐项冻结以下既有字段：

```text
work_item_id
work_item_version
work_item_digest
human_owner
authorized_project_scope_ref
classification
source_commitment_ref
outcome_contract_ref
owned_file_scope
owned_interface_scope
frozen_sha
branch_worktree
issue_ref
pr_ref
required_checks[]
required_reviewer
concurrency_budget
time_budget
token_or_cost_budget
allowed_tools
allowed_egress
current_blocker
integration_status
```

### Scope 规则

- `owned_file_scope` 必须是明确路径或可机械解析的路径集合，不能写“前端相关”“测试相关”；
- `owned_interface_scope` 必须列出可能被创建、修改或依赖的公共 Interface；
- 只读参考不等于写所有权；可同时读取，但不能同时拥有重叠写范围；
- 任一线程发现必须修改对方 scope 时立即停止，不得先改后报；
- 共享 Interface 漂移后，两个 work item 都必须重新检查 `frozen_sha` 和依赖，不能继续沿用旧
  dispatch；
- 不允许两个执行器共享主工作树、共享未提交改动或轮流覆盖同一分支。

## 5. 机器身份和 reality witness

“Codex”“Kimi-K3”只可以作为界面提示。一次真实执行必须由
`AssistantDispatchReceiptV1` 冻结并证明：

```text
work_item_ref
work_item_digest
assistant_run_ref
versioned_executor_ref
workload_identity_ref
executor_adapter_version
actual_runtime_ref
actual_provider_model_ref_if_applicable
repository_ref
base_sha
branch_worktree
owned_scope_digest
budget_digest
execution_generation
idempotency_key_digest
effect_key_digest
started_at
receipt_digest
```

`AssistantRunObservation` 还必须解析到 dispatch/control receipt 以及 backend/reality witness。
以下内容都不能单独证明“由 Kimi 完成”或“由 Codex 验证”：

- 飞书里的执行器下拉框；
- 环境变量或模型配置；
- 模型在回复中自称身份；
- 分支名、commit message 或人工粘贴的模型名；
- 只有健康检查、没有真实 dispatch/observe witness 的 Adapter。

如果 receipt 或 witness 缺失、冲突、过期或无法验证，运行事实必须保持 `UNKNOWN` 或进入权威
合同规定的 `EFFECT_UNKNOWN` 对账路径，不能点绿。

## 6. Classification、egress 与 Secret gate

两个线程在 dispatch 前分别执行 gate，任何一项不是显式通过都不得发送任务内容。

### 6.1 Classification gate

- `classification` 必须由已授权项目上下文解析，不能由模型猜测；
- Kimi 所在 provider/runtime 的承载上限和数据处理范围必须覆盖该 classification；
- 标题、文件名、代码片段、错误日志、截图、测试数据和对象存在性都按内容处理；
- 无法确认 classification、provider 边界或项目授权时，Kimi work item 保持未调度，并在
  `current_blocker` 记录缺口；
- 必须优先发送最小化、脱敏、只含必要文件的工作包。

### 6.2 Egress gate

- `allowed_egress` 必须明确允许目标 runtime/provider 和所需数据类别；
- “模型可用”“机器能联网”或“已有 key”不等于允许外发；
- 未批准外联时，仅可使用经过批准的内网/本地 Kimi runtime；不得回退到公共服务；
- 实际 egress 与冻结范围不一致时立即停止，不能换 endpoint 或换 key 继续。

### 6.3 Secret gate

- 工作包、prompt、diff、日志、飞书、GitHub 和 handoff 中都不得出现 Secret value；
- 普通 App/Connector 凭据只允许使用指向 `secrets-stackdocker` 的 opaque `SecretRef`；
- 执行器不得读取、回显、复制、缓存或提交 Secret value；
- SecretRef 不可解析、版本 unknown、权限不足、撤销或恢复状态不明时 fail-closed；
- 当前 `secrets-stackdocker` 真实挂载、轮换、撤销与 outage witness 不因本手册而变为已验证。

## 7. 状态使用纪律

只使用权威合同已有状态与 CAS 白名单，不创建“排队中”“待 Codex”“Kimi 已完成”等新状态。

首轮常用路径：

```text
DRAFT → READY → DISPATCHING → RUNNING
RUNNING → HANDOFF_SUBMITTED
HANDOFF_SUBMITTED → NEEDS_REWORK | ACCEPTED
NEEDS_REWORK → READY
ACCEPTED → INTEGRATION_PENDING
INTEGRATION_PENDING → INTEGRATED | NEEDS_REWORK | REJECTED
```

控制或不确定路径仍严格复用：

```text
RUNNING → PAUSING | CANCELLING | FAILED
PAUSING → PAUSED | EFFECT_UNKNOWN
PAUSED → RESUMING | CANCELLING
RESUMING → RUNNING | EFFECT_UNKNOWN
CANCELLING → CANCELLED | EFFECT_UNKNOWN
EFFECT_UNKNOWN → RECONCILING
```

纪律：

- 缺少真实 dispatch receipt 时，不得根据人工点击把 work item 推进为权威 `RUNNING`；
- Kimi Adapter 当前为 `DECLARED-NOT-VERIFIED`，因此首轮在 Adapter witness 闭合前只能做
  人工流程演练或非权威候选产出，不能伪造 dispatch/handoff receipt；
- `ACCEPTED` 只表示具名人类接受 handoff 内容，不等于 PR approval、merge 或发布；
- `INTEGRATED` 只能依据 GitHub 权威回读；
- `EFFECT_UNKNOWN` 必须使用原 `effect_key_digest` 对账，不能换键重派；
- 返工形成新的 `work_item_version`、`work_item_digest` 和 dispatch effect key，同时保留旧证据。

## 8. 飞书双线程视图

飞书视图只组合既有字段和权威回读，不创建可人工篡改的生产事实字段。

| 飞书显示列 | 权威来源 | 显示规则 |
|---|---|---|
| 工作包 | `work_item_id`、`work_item_version`、`work_item_digest` | 显示短标识，详情可查完整 digest |
| 人类 owner | `human_owner` | 不从群成员或 display name 推断 |
| 目标来源 | `source_commitment_ref`、`outcome_contract_ref` | 两个 sibling 应指向同一冻结目标 |
| 项目与密级 | `authorized_project_scope_ref`、`classification` | unknown 时抑制正文并显示缺口 |
| 执行器 | dispatch receipt 的 `versioned_executor_ref`、`workload_identity_ref` | 模型显示名不得代替 receipt |
| 运行证据 | `assistant_run_ref`、`actual_runtime_ref`、backend/reality witness | 缺 witness 显示 `UNKNOWN`，不显示假进度 |
| 基线与工作区 | `frozen_sha`、`branch_worktree` | 与 GitHub 回读不一致时告警 |
| 文件/Interface scope | `owned_file_scope`、`owned_interface_scope` | 并排显示冲突检查结果；结果只由既有字段推导 |
| Issue/PR | `issue_ref`、`pr_ref` | 深链到 GitHub 原生 Surface |
| 检查与 reviewer | `required_checks[]`、`required_reviewer` | 不把 AI 互审显示为人类 approval |
| 预算 | `concurrency_budget`、`time_budget`、`token_or_cost_budget` | 只显示真实用量证据，不显示估计“完成百分比” |
| 工具与外联 | `allowed_tools`、`allowed_egress` | 只读；变化必须形成新 work item version |
| 阻塞 | `current_blocker` | 缺密级、scope、receipt、witness 或检查失败均明确显示 |
| Handoff | `handoff_digest`、`verification_results[]`、`risks[]`、`unresolved_issues[]` | 从 `DevelopmentHandoffV1` 投影 |
| 集成 | `integration_status` + GitHub 回读 | 只有 GitHub 事实支持时显示 `INTEGRATED` |

推荐只提供四个视图，不增加状态：

1. **我的待处理**：按 `human_owner` 与需要人工动作筛选；
2. **双线程对照**：并排展示同一目标下的两个 work item；
3. **缺口与冲突**：按 `current_blocker`、scope 冲突和 witness 缺失筛选；
4. **待集成**：筛选 `ACCEPTED` / `INTEGRATION_PENDING`，提供 GitHub 深链。

## 9. 首轮 pilot 操作清单

### 9.1 人工冻结

- [ ] 选择一个可回滚、无生产 Schema/认证/安全状态机修改的真实小任务；
- [ ] 具名 `human_owner` 冻结同一 `source_commitment_ref`、`outcome_contract_ref` 和
      `frozen_sha`；
- [ ] 创建两个 sibling `DeliveryWorkItemV1`，逐项填写既有字段；
- [ ] Codex scope 与 Kimi scope 的文件交集为零；
- [ ] Codex scope 与 Kimi scope 的 Interface 交集为零；
- [ ] 为两个 work item 分别冻结 `required_checks[]`、`required_reviewer` 与预算；
- [ ] classification、egress、tools 和 SecretRef gate 分别通过。

### 9.2 隔离工作区

- [ ] 从同一 `frozen_sha` 创建两个不同 branch/worktree；
- [ ] 记录每个 `branch_worktree`，确认没有共享未提交改动；
- [ ] 在 dispatch 前再次核对 base SHA 和 scope digest；
- [ ] 任一 branch 已漂移时停止并重新冻结，不自行 rebase 后沿用旧 digest。

### 9.3 首轮分工

- [ ] Codex：一个有界实现切片，必须能用 `required_checks[]` 验证；
- [ ] Kimi：只选择独立评审、UI/UX 候选、测试夹具三者之一；
- [ ] Kimi 不修改 Codex 拥有的文件或 Interface；
- [ ] 两个 prompt/work package 都写明“不得扩 scope、不得访问 Secret、不得签发或合并”。

### 9.4 Dispatch 与观察

- [ ] 每个权威 run 分别取得完整 `AssistantDispatchReceiptV1`；
- [ ] 核对 receipt 中 executor、workload identity、Adapter、runtime、base SHA、
      branch/worktree、scope、budget、generation 和 digest；
- [ ] `AssistantRunObservation` 能解析到 backend/reality witness；
- [ ] 远端响应不明时进入 `EFFECT_UNKNOWN` 并以原 effect key 对账；
- [ ] 若 Kimi Adapter 仍无上述证据，则停止权威 dispatch：只保留人工演练或候选产出，
      不标记 `RUNNING` / `HANDOFF_SUBMITTED`。

### 9.5 Handoff 与独立验证

- [ ] 两个线程各自提交完整 `DevelopmentHandoffV1`；
- [ ] changed files 与 changed interfaces 均未越过各自 scope；
- [ ] 人工或独立验证者重新运行 `verification_commands[]`；
- [ ] 检查 handoff、日志、diff、fixture 和产物中无 Secret value；
- [ ] Kimi 的评审结论不投影为 GitHub approval；
- [ ] 任何失败或未决问题原样进入 `risks[]` / `unresolved_issues[]`。

### 9.6 人类集成

- [ ] 具名人类 owner 选择 `NEEDS_REWORK` 或 `ACCEPTED`；
- [ ] `ACCEPTED` 后才进入 `INTEGRATION_PENDING`；
- [ ] 人类在 GitHub 查看真实 diff、CI、CODEOWNERS 和 branch protection；
- [ ] 只有 GitHub/组织策略授权的具名真人在 GitHub 执行其各自的 review、approval/merge；
- [ ] Coordinator 回读 GitHub 后才更新 `INTEGRATED` 或其他权威终态；
- [ ] 飞书只回告结果和证据，不允许人工改单元格伪造集成。

## 10. 停止条件

出现任一情况立即停止受影响线程；不要靠自然语言“已处理”继续：

| 可检测条件 | 处理 |
|---|---|
| `human_owner`、项目授权或 `classification` 缺失/unknown | 不得 dispatch；写入 `current_blocker` |
| 两个 `owned_file_scope` 或 `owned_interface_scope` 重叠 | 不得并发；重新拆分 work item |
| 实际 base SHA、branch/worktree 或 scope 与 receipt 不一致 | 停止 run；按权威控制/对账路径处理 |
| Kimi runtime/provider 不在 `allowed_egress` | fail-closed；不得回退公共 endpoint |
| 检测到 Secret value、凭据回显或未批准数据外发 | 立即停止并按安全事件流程处理 |
| dispatch/control 结果不明 | 进入 `EFFECT_UNKNOWN`，使用原 effect key 对账 |
| Adapter、runtime 或 workload identity witness 无法验证 | 状态保持 unknown；不得宣称执行器身份 |
| 线程需要修改对方文件或共享 Interface | 停止并请求人类重新冻结 scope |
| required check 失败或无法复现 | 不得 `ACCEPTED`；进入返工或保留失败事实 |
| 模型请求 PR approval、merge、release、生产部署或权限提升 | 拒绝；交给具名人类 |
| GitHub 与飞书投影不一致 | 以 GitHub/owner 权威事实为准，飞书进入缺口/对账显示 |

## 11. `DevelopmentHandoffV1` 模板

模板只包含权威合同现有字段。没有真实值的必填项不能用自然语言或假引用补齐。

```text
DevelopmentHandoffV1

handoff_schema_version: DevelopmentHandoffV1
work_item_ref:
work_item_digest:
assistant_run_ref:
actual_runtime_receipt:
base_sha:
final_sha_if_committed:
commit_refs:
  -
patch_or_diff_digest:
changed_files:
  -
changed_interfaces:
  -
verification_commands:
  -
verification_results:
  -
artifact_and_evidence_refs:
  -
risks:
  -
unresolved_issues:
  -
recommended_next_step:
handoff_digest:
```

提交前检查：

- `work_item_digest` 与 dispatch receipt 一致；
- `base_sha`、branch/worktree 和实际 GitHub 分支一致；
- `changed_files[]`、`changed_interfaces[]` 未越 scope；
- `actual_runtime_receipt` 可验证，不能填写模型自报文本；
- `verification_results[]` 区分真实通过、失败、未运行和 unknown；
- `artifact_and_evidence_refs[]` 可解析且遵守 classification；
- `risks[]` 与 `unresolved_issues[]` 不得为空字符串掩盖未知；
- `handoff_digest` 按权威合同的
  `SHA-256("flai.development-handoff.v1" || NUL || RFC8785-JCS(core))` 规则复算；

## 12. Pilot 通过标准

首轮只有同时满足以下条件，才算“双线程机制完成一次受控验证”：

1. 两个 sibling work item 绑定同一目标和 `frozen_sha`；
2. 两个 branch/worktree 独立，文件和 Interface scope 均无交集；
3. 两个真实 run 各自拥有可验证的 executor/runtime receipt 与 reality witness；
4. 两份 `DevelopmentHandoffV1` 完整、可复算且未越 scope；
5. required checks 被独立复跑，失败和 unknown 未被点绿；
6. 飞书只投影，GitHub 保持代码事实；
7. `human_owner` 完成 accept，GitHub/组织策略授权的具名真人分别完成所需 review/merge，
   Coordinator 再依据 GitHub 回读确认集成结果；
8. 全链没有 Secret value、未批准 egress 或模型代签。

在第 3 项闭合前，Kimi 可以参与人工受控的候选产出和流程演练，但 Kimi Adapter 仍保持
`DECLARED-NOT-VERIFIED`；在飞书调度 receipt、控制回执、对账和回读形成真实证据前，飞书
自动调度仍保持 `DECLARED-NOT-VERIFIED`。这两个状态不能由本手册、一次聊天或一次成功输出
自动改变。

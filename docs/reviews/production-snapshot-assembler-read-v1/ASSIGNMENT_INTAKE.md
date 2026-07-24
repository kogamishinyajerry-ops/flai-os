# 七责任域评审指派回填单

> 只回填组织身份和稳定证据引用。不要在本文件中粘贴口令、Token、私钥、签名原文、身份证号或其他秘密。

## 1. 七域责任人

| 责任域 | 真实姓名 | 稳定 `reviewer_actor_id` | `reviewer_role_assignment_ref` | 兼任时的 `segregation_of_duties_exception_ref` |
|---|---|---|---|---|
| Control Kernel / 架构 |  |  |  |  |
| Identity / Authorization |  |  |  |  |
| 数据 / SQLite |  |  |  |  |
| 安全 / 密码 |  |  |  |  |
| ExecutionBroker / Sandbox |  |  |  |  |
| Knowledge |  |  |  |  |
| 工作台 / Observer |  |  |  |  |

填写约束：

- `reviewer_actor_id` 必须来自企业 IdP、人员主数据或组织认可的签署系统；
- 显示名、邮箱、Git 作者、本机用户名、共享账号、群组名或聊天账号本身不构成稳定主体；
- `reviewer_role_assignment_ref` 必须证明该主体在本轮评审时拥有对应责任域的决定权；
- 同一主体覆盖多个责任域时，必须提供组织认可、具名且有期限的职责分离豁免；没有豁免就改由不同责任人评审；
- Codex、其他 AI、自动化服务账号或模型评审结果不能成为上述责任人。

## 2. 包外可信验证通道

| 字段 | 稳定引用 |
|---|---|
| `verifier_binding_ref` |  |
| `trusted_actor_registry_ref` |  |
| `trusted_role_assignment_registry_ref` |  |
| `trusted_signature_or_audit_policy_ref` |  |
| `trusted_finding_registry_ref` |  |
| `append_only_decision_ledger_ref` |  |

该通道至少要真实验证：

1. `reviewer_actor_id` 对应当前有效的真人主体；
2. 责任域任命在 `reviewed_at` 有效，且未被撤销；
3. 签名凭据或审计主体确实映射到该真人；
4. Decision Seal/AuditReceipt 覆盖精确的 `decision_core_digest`；
5. key usage 或 audit event type 为 `contract-review`；
6. 签署时间、轮换、吊销、retrospective compromise 与重放检查通过；
7. findings 与职责分离豁免引用可解析、未过期且无开放阻断项；
8. 信任根和策略来自本评审包之外的组织可信配置。
9. 同一 round 的旧决定、`changes_required/reject`、findings 与当前 head 保存在不可覆盖的追加式账本中，替换当前文件不能删除历史。

当前仓库没有这套 verifier。只填写 URI 或把 manifest 状态改成“verified”不能打开门禁。

## 3. 回填后流程

1. 由评审协调人把以上信息写入 `review-manifest.json`；
2. 独立核对身份和任命事实后，把计划状态改为 `FROZEN-FOR-REVIEW`；
3. 计算 manifest raw-byte SHA-256，并写入七份 Decision Core；
4. 七位责任人逐项回答、形成决定并冻结各自 Core raw bytes；
5. 由可信签署/审计通道为每个 Core 生成独立 Seal/Receipt；
6. 运行本地结构检查；正式门仍保持 `PENDING_EXTERNAL_VERIFICATION`；
7. 接入并独立评审真正的包外 verifier 后，才重新评估合同评审门。

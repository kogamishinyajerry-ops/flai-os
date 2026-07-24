# 七责任域具名评审指派回填单

> 只回填组织身份和稳定证据引用。不要粘贴口令、Token、私钥、签名原文、身份证号、密级正文或
> 其他秘密。

## 指派

| 责任域 | 真实姓名 | 稳定 `reviewer_actor_id` | `reviewer_role_assignment_ref` | 兼任豁免引用 |
|---|---|---|---|---|
| 产品架构与领域所有权 |  |  |  |  |
| AirGap 网络安全与传输控制 |  |  |  |  |
| 内网身份、ACL、密级与隐私 |  |  |  |  |
| 自托管协作、记录与连续性 |  |  |  |  |
| 权威知识与旧系统采集 |  |  |  |  |
| Agent Runtime、Sandbox、证据与审计 |  |  |  |  |
| 软件供应链、内部发行与运维 |  |  |  |  |

## 回填约束

- `reviewer_actor_id` 必须来自企业 IdP、人员主数据或组织认可的签署系统；
- `reviewer_role_assignment_ref` 必须证明该真人在本轮评审时对对应责任域拥有决定权；
- 显示名、邮箱、Git 作者、本机用户名、共享账号、群组、飞书账号或聊天截图不能替代稳定身份；
- 同一真人覆盖多个域时必须提供组织认可、有期限的职责分离豁免；
- Codex、Kimi、其他模型、自动化服务或外部顾问报告只能形成 advisory finding，不能占用 reviewer
  席位；
- 评审结论必须绑定冻结 commit/tree 和具体问题答案；“总体同意”或会议口头结论不算完成。

## 包外 verifier

| 字段 | 稳定引用 |
|---|---|
| `verifier_binding_ref` |  |
| `trusted_actor_registry_ref` |  |
| `trusted_role_assignment_registry_ref` |  |
| `trusted_decision_evidence_policy_ref` |  |
| `trusted_finding_registry_ref` |  |
| `append_only_decision_ledger_ref` |  |

本地仓库没有权威人员与签署 verifier。仅填写 URI、把状态改成 `verified` 或让 AI 复述材料都不能
打开评审门。

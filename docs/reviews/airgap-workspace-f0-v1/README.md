# AirGap / 内网 Workspace F0 七责任域评审包

> 状态：`DRAFT-PENDING-ASSIGNMENT`
>
> 评审对象 commit：
> `fb7e5a277b934792934275511ba1a063399210e7`
>
> 评审对象 tree：
> `cfbf0ef08e680a551ee50fe87db2ddcf9473d300`
>
> 当前计数：`ASSIGNED 0/7 · APPROVED 0/7`
>
> 实施授权：`false`

本包只组织 [ADR-0063](../../adr/ADR-0063-external-development-airgap-internal-workspace.md)、
[AirGap Exchange 设计](../../product/FLAi-OS_V0.2_Design_Package/18_AirGap_Exchange_and_Internal_Release.md)
与
[内网自托管 Workspace 设计](../../product/FLAi-OS_V0.2_Design_Package/19_Internal_Self_Hosted_Workspace.md)
的具名设计评审。它不授权采购、生产 Schema/API/状态机变更、真实系统连接、数据导入、试点、
发布或部署。

## 冻结语义

- 评审只针对上面的精确 Git commit/tree，不针对当前工作树；
- 本目录在冻结 commit 之后创建，因此不属于被评审规范内容；
- 后续任何规范修改必须产生新 commit/tree，并使本轮全部决定 stale；
- Git 作者、显示名、邮箱、飞书账号、聊天确认或 AI 评语都不能证明评审者身份或职责；
- 七域全部 `approve` 仍只表示设计 F0 候选可提交组织 verifier，不自动打开 A1 或生产门；
- 本地校验器只验证结构和 Git 绑定，不能认证企业人员、任命、签名、吊销或职责分离。

## 七责任域

1. `product-architecture-domain-ownership`
2. `airgap-cybersecurity-transfer-control`
3. `internal-identity-acl-classification-privacy`
4. `self-hosted-collaboration-records-continuity`
5. `authoritative-knowledge-legacy-ingest`
6. `agent-runtime-sandbox-evidence-audit`
7. `software-supply-chain-internal-release-operations`

每个责任域必须由具名真人填写稳定 `reviewer_actor_id` 和在评审时有效的
`reviewer_role_assignment_ref`。同一人兼任多个域时，必须提供组织认可、有期限、可验证的
`segregation_of_duties_exception_ref`；AI 和服务账号不能成为 reviewer。

## 使用

1. 在 [ASSIGNMENT_INTAKE.md](ASSIGNMENT_INTAKE.md) 收集七域真人身份与任命引用；
2. 由评审协调人把已核对信息写入 `review-manifest.json`；
3. 每位 reviewer 回答其 `required_question_ids`，填写决定、理由、finding/evidence 引用和时间；
4. 运行结构与冻结 Git 绑定检查：

   ```bash
   python3 docs/reviews/airgap-workspace-f0-v1/verify_review_intake.py
   ```

5. 运行 invalid-first 测试：

   ```bash
   python3 -m unittest docs/reviews/airgap-workspace-f0-v1/test_verify_review_intake.py
   ```

6. 七域均批准后，仍须由包外、组织批准的 verifier 验证身份、任命、SoD、决定证据、签名/审计、
   吊销和追加式历史；本地脚本最多返回 `PENDING_EXTERNAL_VERIFICATION`。

## 当前门

```text
frozen design commit/tree                  VERIFIED LOCALLY
seven named human assignments              0 / 7
seven review decisions                     0 / 7
external identity/role/evidence verifier   UNCONFIGURED
A1 implementation authority                CLOSED
production admission                       NO-GO
```

# 18｜外网研发、隔离交换与内网发布准入

> 文档性质：V0.2 设计合同读模型，不是生产 Schema、传输脚本、网闸配置或部署授权。
>
> 首要依据：
> [ADR-0063](../../adr/ADR-0063-external-development-airgap-internal-workspace.md)。
>
> 当前状态：`ACCEPTED-NOT-IMPLEMENTED / NO-GO`。

## 1. 结论

FLAi-OS 的外网研发与内网运行之间不存在“持续集成”或“双向同步”。二者通过一个离线、
内容寻址、可拒绝的 `AirGapExchange` 深 Module 交换最小成果：

```text
外网研发域                         隔离交换域                         内网运行域

Feishu + GitHub              只读介质 / 受控设备             Internal Forge/Registry
Codex + Kimi                       │                                  │
      │                            ▼                                  ▼
      └─ sealRelease ─────> quarantine ── admitRelease ─────> ReleaseSet
                                                                        │
                                                                        ▼
                                                          qualify / deploy / witness

外网接收修复线索 <───── 人工接收 ───── sealSanitizedFeedback <── 内网脱敏出口
```

核心含义：

- 外网发布者只能“封装候选”，不能批准内网导入或部署；
- quarantine 只允许写入隔离暂存区，不能直接写内部生产 Registry；
- 所有文件按 digest 复验，通过后以一个 `ReleaseSet` Head 的 CAS 整体晋升，禁止半包可见；
- 内网部署使用内部 receipt 和 witness，不把 GitHub/飞书状态当作生产事实；
- 反馈出口只允许 allowlist 字段、合成复现和经批准的公开源码补丁。

## 2. 信任模型

### 2.1 信任非传递

| 外部事实 | 内网最多接受的语义 | 不能证明 |
|---|---|---|
| GitHub commit/PR/CI | 外部研发来源与测试证据 | 内网已导入、已评测、已部署或可访问真实数据 |
| Feishu 工作项/评审 | 外部研发组织过程 | 内网 actor、内部签发或生产批准 |
| Codex/Kimi handoff | 机器贡献候选和声明的测试 | 代码正确、安全、已合并或内网可用 |
| Bundle 签名 | 来源身份与传输前完整性 | 内容无恶意、分类允许、依赖可信或内部批准 |
| 外网漏洞扫描 | 一个时间点、一个数据库版本的发现 | 内网扫描通过或未来没有漏洞 |

内网准入必须使用内部信任根、策略 Head、可信时间、具名 reviewer 和本地复验结果。

### 2.2 不能跨域的内容

以下内容禁止进入发布 Bundle：

- 外网或内网 Secret value、token、cookie、私钥、恢复码和真实 SecretRef 名称；
- 个人目录、浏览器状态、全局 CLI 配置、模型 OAuth cache 和开发机 SSH material；
- 未获准的企业数据、真实工程项目输入、内网截图、内网日志或知识正文；
- Git 历史中已删除但仍可恢复的秘密和大文件；
- 无许可证或来源不明的依赖、字体、模型、插件、图标或测试数据；
- 运行时动态下载指令、`latest` 标签、无 digest 的远程 URL 和公共 CDN 依赖。

## 3. `AirGapExchange` Interface

该 Module 只有三个外部入口：

```text
sealRelease(release_request, external_attestation)
  -> OfflineReleaseBundleV1 | Rejection

admitRelease(sealed_bundle_ref, transfer_evidence, internal_admission_context)
  -> InternalReleaseCandidateReceipt | QuarantineCase | Rejection

sealSanitizedFeedback(feedback_request, internal_export_context)
  -> SanitizedFeedbackBundle | Rejection
```

### 3.1 `sealRelease`

隐藏：

- Git/tree/archive 对账；
- BOM 枚举、无遗漏检查与路径规范化；
- JCS/确定性 manifest 摘要；
- SBOM、许可证、测试证据和风险索引；
- Secret/PII/禁止文件扫描；
- Bundle 签名和只读介质布局；
- 外部研发 handoff 与 exact SHA 绑定。

失败时不得生成“部分可用” Bundle。任何必需对象 unknown、digest 缺失或扫描不可复跑都拒绝。

### 3.2 `admitRelease`

隐藏：

- 介质 custody、导入操作员和设备证据；
- 离线 malware、vulnerability、license、policy 和 content 扫描；
- manifest、逐对象 digest、签名、撤销和时间校验；
- 内部重建/复测、目标 CPU/OS/驱动兼容性检查；
- 双人准入、职责分离、例外到期和审计；
- quarantine namespace 与内部 admitted-candidate namespace 之间的原子晋升；
- 内部 Forge/OCI/package/model registry 候选区的 content-addressed 写入；
- candidate `ReleaseSet` CAS 和回滚锚点；不更新 deployable/production Head。

`admitRelease` 返回的只是内部候选 receipt，不是 `QualificationDecision`、
`DeploymentBinding` 或部署成功。

### 3.3 `sealSanitizedFeedback`

隐藏：

- 数据 owner、安全 owner 和出口 operator 的独立授权；
- classification 重新计算和存在性抑制；
- allowlist 字段投影；
- 日志、路径、主机、账户、项目名和样本的去标识；
- 合成 reproducer 与真实问题的一致性证明；
- 导出 Bundle 签名、介质 custody 与外网接收回执。

若无法在不泄露受限事实的情况下复现，返回 `CANNOT_SANITIZE`，不允许“先传出去再删除”。

## 4. `OfflineReleaseBundleV1` 设计内容

`OfflineReleaseBundleV1` 是本阶段的逻辑对象名，不创建生产表或公开 Schema。建议布局：

```text
release-bundle/
├── manifest.jcs.json
├── signatures/
│   ├── manifest.signature
│   ├── certificate-chain/
│   └── verification-policy-ref.json
├── source/
│   ├── repository.bundle
│   └── source.archive
├── artifacts/
│   ├── oci/
│   ├── packages/
│   ├── models/
│   └── static-assets/
├── dependencies/
│   ├── python/
│   ├── node/
│   ├── os/
│   └── lockfiles/
├── evidence/
│   ├── tests/
│   ├── scans/
│   ├── sbom/
│   ├── licenses/
│   └── reproducibility/
├── operations/
│   ├── install/
│   ├── upgrade/
│   ├── rollback/
│   ├── backup-restore/
│   └── health-check/
└── release-notes/
    ├── changes.md
    ├── risks.md
    └── known-limitations.md
```

每个 manifest entry 至少包含：

```text
logical_name
media_relative_path
media_type
byte_length
sha256
source_ref
source_digest
classification
license_ref
target_platform
required | optional
```

Bundle 顶层至少绑定：

```text
bundle_id
schema_version
source_repository_identity
source_commit_sha
source_tree_sha
build_recipe_digest
complete_file_set_digest
sbom_set_digest
test_evidence_set_digest
scan_evidence_set_digest
classification_policy_ref + digest
release_policy_ref + digest
signer_identity + credential_epoch
created_at + trusted_time_evidence
allowed_target_zones[]
```

“optional”只表示安装选择，不表示可以从 digest 集合中省略。

## 5. Quarantine 与整体晋升

### 5.1 Namespace 规则

所有入站对象先进入不可执行、不可被生产解析的 quarantine namespace：

```text
quarantine/<bundle_digest>/<object_digest>
```

quarantine 中：

- 禁止被应用镜像 tag、包索引、模型目录或插件发现机制解析；
- 禁止执行安装脚本、模型自定义代码、插件 hook 或文档宏；
- 只允许扫描器和复验构建器以最低权限只读挂载；
- 扫描器自身来自内部已批准工具链；
- unknown/timeout/error 等同失败，不允许沿用外网 scan PASS。

### 5.2 `ReleaseSet`

通过准入的对象先以 digest 写入内部 Registry 的 admitted-candidate namespace，再创建不可变
candidate `ReleaseSet`：

```text
ReleaseSet
  source_bundle_digest
  admitted_object_digests[]
  internal_scan_evidence_refs[]
  internal_build_evidence_refs[]
  internal_reviewer_decision_refs[]
  compatibility_scope
  rollback_release_set_ref
```

只有全部必需对象存在且验证为 `True`，才允许以 CAS-on-NULL 创建
`candidate-release-set/<bundle_digest>`；同一候选 key 出现不同内容即冲突。`admitRelease`
不得更新 `deployable-release-set/<channel>`、`current` 或任何生产解析 Head。禁止逐对象
“边过边发布”，防止代码、依赖、镜像和迁移版本错配。

### 5.3 内部资格与部署

```text
InternalReleaseCandidateReceipt
        ↓
FLAi Bench / security / restore / target compatibility
        ↓
QualificationDecision（具名真人）
        ↓
DeploymentBinding（精确目标与配置 digest）
        ↓
Execution/health/recovery witness
```

`InternalReleaseCandidateReceipt` 只能证明导入候选完整通过准入，不能跳过现有资格、部署和运行门。
只有内部 Release Governance 在资格与 DeploymentBinding 均有效后，才可用独立 expected-version
CAS 更新 `deployable-release-set/<channel>`；该动作不属于 `AirGapExchange`。

## 6. 内外代码 lineage

### 6.1 外部主开发线

- GitHub 是外部主开发线的代码事实源；
- FeishuDevelopmentHub 只组织工作；
- Codex/Kimi 使用独立 branch/worktree 和不重叠写范围；
- PR approval/merge 只由 GitHub 与具名真人决定；
- 只有 exact merged SHA 可以进入 release request。

### 6.2 内部部署线

- 导入 Bundle 后，内部 Forge 保存 exact source mirror；
- 内部环境配置、证书引用、主机清单和部署 overlay 永不回写外部仓库；
- 内部紧急补丁从导入 base 创建独立内部 branch；
- 每个内部补丁记录 `external_base_sha + internal_patch_sha + release_set_ref`；
- 内部补丁不能用外网同名 tag 冒充已上游。

### 6.3 受控回馈

可以外发：

- 与敏感环境无关的最小源码 diff；
- 合成 fixture；
- 通用失败码；
- 去标识的复现步骤；
- 经批准的性能区间或兼容性结论。

默认禁止：

- 原始内部 Git bundle；
- `git diff` 中的内部路径、域名、账号、项目号或配置；
- 原始日志、core dump、trace、截图和数据库片段；
- 真实业务样本、知识条款和审计记录。

## 7. 失败码

| 失败码 | 含义 | 结果 |
|---|---|---|
| `AGX_BUNDLE_MANIFEST_INVALID` | manifest 无法规范化或字段不全 | 拒绝 |
| `AGX_FILE_SET_INCOMPLETE` | 声明文件集与介质不一致 | 拒绝 |
| `AGX_DIGEST_MISMATCH` | 任一对象或集合摘要不一致 | 隔离并拒绝 |
| `AGX_SIGNATURE_INVALID` | 签名、链、用途或 epoch 无效 | 拒绝 |
| `AGX_SIGNER_REVOKED_OR_UNKNOWN` | signer 撤销状态不能确认 | 拒绝 |
| `AGX_CLASSIFICATION_UNKNOWN` | 分类或目标域许可不明 | 拒绝 |
| `AGX_SECRET_OR_SENSITIVE_CONTENT_FOUND` | 发现 Secret 或不允许内容 | 隔离并拒绝 |
| `AGX_MALWARE_SCAN_FAILED` | 恶意代码扫描非显式 PASS | 隔离并拒绝 |
| `AGX_VULNERABILITY_GATE_FAILED` | 漏洞门或例外无效 | 拒绝 |
| `AGX_LICENSE_GATE_FAILED` | 许可证未知、不兼容或证据缺失 | 拒绝 |
| `AGX_REBUILD_MISMATCH` | 内部复验产物与声明不一致 | 隔离并调查 |
| `AGX_TEST_EVIDENCE_INSUFFICIENT` | 目标范围测试证据不全 | 拒绝 |
| `AGX_TARGET_INCOMPATIBLE` | OS/CPU/驱动/依赖不匹配 | 拒绝 |
| `AGX_REVIEWER_SEPARATION_FAILED` | 双人控制或职责分离不满足 | 拒绝 |
| `AGX_RELEASE_SET_CONFLICT` | Head 已变化或出现并发晋升 | 不更新 Head，重新评审 |
| `AGX_EXPORT_FIELD_NOT_ALLOWED` | 反馈包含非 allowlist 字段 | 拒绝外发 |
| `AGX_EXPORT_CLASSIFICATION_FAILED` | 反馈分类/脱敏不能确认 | 拒绝外发 |
| `AGX_CANNOT_SANITIZE` | 无法安全构造外网复现 | 停留内网 |
| `AGX_EFFECT_UNKNOWN` | 介质写入、Registry 或 Head effect 不明 | 禁止重放；原键对账 |

任何失败码不得被前端翻译成绿色“基本通过”。QuarantineCase 必须保留原始证据、custody 和
处置状态。

## 8. 角色与职责分离

| 角色 | 允许 | 禁止 |
|---|---|---|
| External Release Builder | 从 merged SHA 构造 Bundle、生成证据 | 批准内部导入或部署 |
| External Release Signer | 对 exact bundle digest 签名 | 修改 Bundle 或成为内部 signer |
| Transfer Custodian | 按受控流程搬运只读介质 | 变更内容、兼任全部准入角色 |
| Quarantine Operator | 导入暂存、启动批准的扫描 | 把对象直接推入生产 Registry |
| Internal Security Reviewer | 审查扫描、分类、供应链和例外 | 单人同时签业务部署 |
| Internal Product/Release Reviewer | 审查功能、兼容性和回滚 | 代替安全门 |
| Internal Release Signer | 签发 `InternalReleaseCandidateReceipt` | 冒充 Qualification/Deployment signer |
| Export Reviewer | 审查脱敏反馈 | 批准原始内网数据外发 |

职责是否允许合并由组织制度裁决；默认高影响入站和出站分别至少双人，且外部发布者不进入内部
准入职责。

## 9. 验收夹具

实现前先冻结 invalid-first fixture：

1. manifest 声明 100 个文件，介质只有 99 个；
2. Git SHA 正确但源码 archive digest 不匹配；
3. 签名正确但用途是开发签名而非 release；
4. signer 已撤销或撤销状态 unknown；
5. SBOM 缺少一个运行时动态依赖；
6. 使用 `latest`、公共 CDN 或运行时 `pip install`；
7. Bundle 中存在 `.env`、OAuth cache 或私钥；
8. 外网扫描 PASS，内网扫描器 timeout；
9. 只导入了前端镜像，后端/迁移仍为旧版；
10. `ReleaseSet` Head 在评审后被并发更新；
11. 外发最小复现仍包含内部路径、项目号或真实样本；
12. 导入成功但内部 Bench/restore 失败；
13. Feishu/GitHub 都不可用，内网仍可安装、运行、审计、备份和恢复；
14. Kimi/Codex 名称出现在贡献记录中，但内部没有任何外网凭据或模型调用。

## 10. 分阶段路线

| 阶段 | 目标 | 退出证据 |
|---|---|---|
| A0 合同 | 冻结 Interface、对象、失败码、七域职责 | 新 SHA + 0/7 待评审包 |
| A1 纯夹具 | 本地目录模拟外网、quarantine、内部 Registry | invalid-first 单测；无真实介质/网络 |
| A2 供应链 | 生成 SBOM、签名、扫描、ReleaseSet CAS | 篡改/缺件/并发/撤销测试 |
| A3 断网安装 | 在测试网从内部 Registry 安装与升级 | 无外网 DNS/token/registry 的 witness |
| A4 恢复与回滚 | 备份、恢复、升级失败、旧版回滚 | 精确 RTO/RPO 与数据一致性 witness |
| A5 受控试点 | 经七域及试点授权后导入非敏感候选 | 内部资格、部署、人签和运行 evidence |

当前只允许 A0 设计工作。A1 及以后均需另获精确授权。

## 11. 参考

- [NIST Secure Software Development Framework](https://csrc.nist.gov/projects/ssdf)
- [NIST DevSecOps Notional Reference Model](https://pages.nist.gov/nccoe-devsecops/notational-reference-model.html)
- [Mattermost Air-Gapped Deployment](https://docs.mattermost.com/deployment-guide/reference-architecture/deployment-scenarios/air-gapped-deployment.html)

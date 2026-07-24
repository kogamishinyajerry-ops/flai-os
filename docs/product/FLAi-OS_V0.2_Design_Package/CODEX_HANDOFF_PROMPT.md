# Codex 接手 FLAi-OS V0.2 的分阶段提示词

> 用法：把下方“任务提示词”完整交给 Codex。它授权阅读、评审和形成阶段交付物，**不授权跳过阶段立即修改 Runtime、Schema、数据库或生产配置**。

---

## 任务提示词

你正在接手 `/Users/Zhuanz/projects/aircraft-comac/flai-os` 的 FLAi-OS V0.2。你的目标不是快速堆一个演示，而是把已接受决策收敛为可验证的 macOS-first 企业内网 Agent 平台薄切片。

### 一、先确认事实层级

开始前完整阅读：

1. `AGENTS.md`；
2. `CONTEXT.md`；
3. `docs/product/FLAi-OS_V0.2_Design_Package/README.md` 与本包全部文档；
4. `docs/adr/ADR-0047-*.md` 至 `ADR-0062-*.md`；
5. `docs/product/FLAi-OS_V0.2_Design_Package/15_Phase_0A_MVP_Spec.md`，并先核对其 Stage B 是否已由 owner 冻结；
6. `docs/00_FLAi-OS_Constitution.md` 至 `docs/09_Workflow_Live_Monitor_Standard.md`；
7. `docs/PRODUCTION-READINESS-PROGRAM.md`、`docs/DEPLOYMENT-SUPERVISION.md` 与 `docs/agents/issue-tracker.md`；
8. 与拟议切片直接相关的代码、Schema、测试、研究材料和真实运行证据。

权威原则：accepted ADR 裁决目标决策，`CONTEXT.md` 裁决术语，代码/Schema/测试/真实运行证据说明当前实现，现行标准说明当前合同，本设计包只是派生读模型。发现冲突时先记录，不得挑选方便的版本制造一致。

ADR-0047/0048 负责决策谱系与知识发布身份澄清，ADR-0049～0062 当前只证明委托人在设计会话中确认产品方向；它们都不是组织身份系统中的正式签发。接手者必须分别记录 decision provenance 与 implementation evidence；在获得绑定 `actor_id + scope + timestamp + exact digest + evidence_ref` 的 `formally_signed` 记录前，不得把这些 ADR 当作试点、采购、发布或上线授权，也不得自行伪造 accepted_by 字段。当前 Stage B 已因 owner 于 2026-07-23 的明确原话“冻结 Stage B，进入 Stage C”标为 `FROZEN-FOR-STAGE-C`；Stage C 又因原话“以 C 为主，吸收 A 的首页”标为 `DIRECTION-SELECTED-FOR-CONVERGENCE`。两条记录的 `accepted_by_actor_id` 都是 `UNRESOLVED`；前者只打开隔离原型门，后者只选择 A 首页 → C 执行态的收敛方向，均不具有组织正式签发或 Stage D 授权效力。ADR-0062 只冻结飞书唯一日常中枢的产品、架构与治理方向，不授权 Feishu/Schema/Secret Adapter 或生产写入。

所有结论使用且只使用：`IMPLEMENTED-VERIFIED`、`IMPLEMENTED-PARTIAL`、`ACCEPTED-NOT-IMPLEMENTED`、`DECLARED-NOT-VERIFIED`、`OUT-OF-SCOPE`。`unknown/failed/invalid/skipped` 不能判绿。

### 二、先保护现场

在任何写操作前运行并保存结果：

```bash
pwd
git status --short
git diff --stat
git diff --name-only
git log -1 --oneline
```

把所有已有修改、未跟踪文件和本任务预计触及文件做交集。已有资产默认属于用户：不清理、不 reset、不 checkout 覆盖、不重排无关文件、不把别人的修改据为己有。若交集非空，按“停止条件 S1”处理；可用隔离 worktree 时也必须先得到明确授权并记录基线 SHA。

### 三、代码发现方式

代码发现优先使用 `codebase-memory-mcp`：

1. 确认或刷新当前仓库索引；
2. 用 `search_graph` 定位模块、路由、函数和状态；
3. 用 `trace_path` 检查调用者与下游影响；
4. 用 `get_code_snippet` 读取精确实现；
5. 只有查字符串、配置、非代码文件或图谱证据不足时才使用 `rg`/`rg --files`。

任何现状判断必须落到文件、符号、Schema、测试或命令输出，不能仅根据设计文档猜测。

### 四、不得替换的技术基线

除非 owner 另行接受新 ADR，不得替换或平行重建现有技术栈：

- 后端：FastAPI + Python 3.10+；
- 持久化：SQLite、无 ORM、Repository 层；
- 契约：Pydantic + jsonschema；
- 前端：Vue 3 + Vite + Element Plus；
- 后台任务：SQLite 任务表 + 轮询 Job Runner；
- 禁止引入 Redis/Celery、Next.js/PostgreSQL 第二应用、第二套任务状态机、第二套审计账本或第二套 KPI/评测/知识事实源；
- 当前阶段 macOS-first，质量优先；不要夹带 Windows 适配工程，也不要破坏既有跨平台脚本合同。
- 飞书是唯一日常 System of Engagement，但不是数据库或控制内核；GitHub 保持代码/PR/CI 事实，FLAi 保持运行/授权/Bench/交付/审计事实，Knowledge Authority 保持知识有效性，`secrets-stackdocker` 保持运行时 App/Connector Secret 事实；人的硬件身份、Safety receipt-signing、Coordinator / target owner / Policy owner 三类 workload-attestation material、Egress Boundary/Wire 两类 operation-bound workload-attestation material、Policy-fence 与 Trusted-Time Authority/consumer-local Commit-Guard material 分别由独立 Safety Identity / PKI / HSM / Time owner 持有，各 operation 不得互相代签，也不得来自普通 workload identity、应用进程自签 key、SecretProviderPort 或普通 Secret 栈；
- 所有普通 Connector 只持有 opaque `SecretRef`；禁止恢复 `.env`、硬编码或宿主全局凭据 fallback，禁止读取或输出 Secret value。

执行平面必须拆成三类窄 Port 并由 ExecutionBroker 组合：OpenClaw/OpenHands 只可实现 `AgentRuntimePort`，macOS 隔离实现 `SandboxProviderPort`，Python/Office/CAE/HPC 实现 `ToolExecutionPort`。FLAi-OS 控制内核继续唯一拥有普通协作/工作负载身份与资源授权、CanonicalTaskGraph、队列与并发、任务状态、政策、审计、产物和交付语义；独立 Safety Identity / PKI / HSM / Time owners 拥有人的安全硬件身份、Safety admission、receipt-signing、Coordinator / target owner / Policy owner 三类 operation-bound workload attestation、Egress Boundary/Wire 两类 operation-bound material、Policy fence 与 Trusted-Time Authority/consumer-local Commit-Guard material，Kernel 只消费可验证结果，不拥有其 credential/signing material。每个动态 replan/Tool/Model/Knowledge/Connector 动作必须取得绑定 step/Grant/policy/lease/budget/expiry 的短时 ExecutionTicket。不得让外部 Runtime 直接调用下游、写权威终态、绕过策略、形成第二控制面或产生真人签发。此约束来自 ADR-0049。

### 五、必须保留的产品与治理不变量

1. **不中断自治会话**：用户用单一 Composer 提交目标；Agent 在有界 Sandbox 内连续规划、执行、验证和恢复。不得让用户补填 Agent 已能推导的字段，不做逐命令、逐工具或逐文件审批。未知、冲突和待确认项集中进入末端交付；禁止动作直接形成聚合 blocked。见 ADR-0050、ADR-0052。
2. **人是唯一签发者**：不可逆或外部影响先冻结为不可变 Delivery Bundle，包含输入/产物摘要、差异、验证、残余风险、策略版本和精确动作；具名真人只对精确匹配版本一次性授权。AI、LLM Judge、管理员默认身份和“已完成”状态均不能代签。见 ADR-0050、ADR-0058、ADR-0061。
3. **无假绿**：Mock、synthetic、canonical、声明未验证、外部活态和缺证据都如实显示；`failed/invalid/skipped/unknown` 不得通过；状态必须从权威事件和证据派生，不能在 UI 手工点绿。见 ADR-0051、ADR-0058、ADR-0059。
4. **权限 fail-closed**：对主体、对象、能力、数据范围、任务快照、策略版本、预算和有效期做显式校验，并在提交时重验；不得用 truthiness 处理安全布尔值，不得用粗粒度全局 admin 替代职责与作用域。见 ADR-0061 及现行宪法。
5. **Sandbox 是执行门，不是目录命名**：每个任务必须有隔离文件系统/进程边界、资源与并发预算、超时、取消和可强杀能力；宿主文件、密钥、网络和工具默认不可达。需要网络出口时使用具名 allowlist、目的与方法约束、审计和分类传播。缺一项不得宣称 Sandbox 已验证。
6. **全过程审计**：输入快照、计划摘要、工具调用、策略判定、模型实际路由、Token、文件摘要、网络出口、取消/恢复、Bundle、真人授权、真实执行 receipt 和后置验证必须能关联和重建。授权不等于执行成功；可变日志或无法验证的审计不得作为生产证据。
7. **知识不是普通 RAG**：只有具名授权人员在本平台签发、不可变、当前有效且适用的材料可支持组织或工程依据；受信源系统只能提供可验证的上游签发 `source_system_attestation`，不能成为 FLAi-OS signer。Obsidian 只是策展界面，向量/BM25 只是索引。缺失、过期、被替代、范围不明或冲突时显示“无法确认”，模型不得自行裁决。见 ADR-0057。
8. **FLAi Bench 不做综合排行榜，也不接受测试标签旁路**：评测对象是冻结能力发布包；未资格候选必须先取得具名 Eval maintainer 签发、绑定 actor/scope、release/approved synthetic fixture/pack、预算、TTL、epoch 和零外部效果的 EvaluationAdmission，`origin=eval` 只能由 Kernel 验证后派生。确定性回归、工程质量、安全治理、运行效率四轨分别呈现；安全、诚实、依据链和关键回归是不可抵消门；LLM Judge 只能辅助。见 ADR-0058。
9. **飞书唯一组织入口、同一控制内核**：组织级默认产品是飞书 FLAi 工作空间，承接 landing、
   工作收件箱、编排与回告；工程智能体工作台和 GitHub diff/PR approval/merge 是重新鉴权的
   权威专业 Surface，不另建组织首页。飞书只投影联邦 owner 事实，不能成为 Bitable 总账或
   第二管理应用。见 ADR-0052、ADR-0059、ADR-0062。
10. **需求共创不等于投票治产品**：AI 只预处理；策展、领域评审、安全门、路线图具名签发和交付验收职责分离。需求池、路线图承诺和工程 Issue 是相连但不同的事实层。见 ADR-0060、ADR-0061。
11. **点击不等于生效**：会创建/改变跨 owner 正式事实、受控投影或外部 effect 的飞书动作
    必须是 typed intent；飞书自有群聊/评论/Docs 草稿保持原生协作。高影响动作冻结
    PreparedCommand/ReviewChallengeV1，绑定 payload/target/actor/epoch/assurance/policy/gate
    digest、新鲜 step-up 和一次性 CAS nonce。卡片点击、Bitable 更新、HTTP 2xx 或消息送达都
    不能替代 OwnerCommitReceiptV1；EffectUnknownV1 先对账，不换幂等键重放。
    commit 必须提交精确 ReviewChallengeV1 ref + ConfirmationProofV1，二者和 commit attestation
    绑定 challenge/prepared/nonce digest、confirmation mode、audience/purpose；Source
    Ownership Registry 由 FLAi Governance owner 具名签发并冻结进 Prepared/Challenge，
    receipt 自报 owner/type/schema 绝不能驱动 verifier dispatch。
12. **唯一日常入口不牺牲安全生存**：飞书不可用时新的正常治理暂停，但独立
    SafetySurvivalPort 必须不依赖飞书、Hub、主协作 SSO 或普通在线 Secret 解析；只允许
    kill/revoke/suspend/deny/isolate、开对账案、向预批准本地 WORM 封存证据和只验证不启用
    的恢复候选，不能承担正常签发、对外导出、恢复权限、发布或合并代码。其 receipt 必须使用
    固定 canonical payload/domain separator、独立 signer/verifier 与 verifier-only result
    factory；Safety prepare/commit/policy publication 的双人 admission 必须绑定精确
    typed immutable subject/nonce/replay domain，并以 admission-digest CAS-on-NULL 单次
    消费；唯一 Safety Admission Coordinator 在自己的事务中原子写
    `SafetyAuthorizationReservationV1`、双 AdmissionConsumption 与 SubjectNonceConsumption，
    下游 owner 首次 anchor 前必须从 Coordinator 权威 Store resolve 三条 consumption、
    验证 workload attestation、全部 gate `is True`、status ACTIVE。owner-local commit
    必须消费独立 `SafetyTrustedTimeAttestationV1 ref+digest`、按保守 UTC upper bound 比较
    TTL；epoch transition 必须具名 continuity-root 签名，CommitLease 必须绑定 transaction
    nonce/commit subject，FreshnessProof 必须由受信 monotonic elapsed Guard 在 owner-store
    线性化点形成，并与 checkpoint/anchor 同事务。回拨、gap、陈旧 lease、超 elapsed budget、
    偏差、source/head/key/revocation outage 或 Unknown 均 fail-closed，禁止
    host-clock/cache/call-before-only fallback。下游只凭已验证 Reservation 做
    owner-local CAS，ChallengeState 全链也只由 Coordinator 写；outbox enqueue 与
    `SafetyCommitDispatchClaimV1` 都不是 send。唯一 egress boundary 在第一 mutating send
    primitive 前重新验 attested time/deadline、CAS 消费一次性
    `SafetyProviderMutationCapabilityV1` 并形成 `SafetyProviderCallAttemptV1`；缺 verified
    `SafetyProviderSendReceiptV1` 一律 effect unknown + DO_NOT_REPLAY；
    两个不同真人签发 append-only Policy Head version 和严格连续的 content-addressed
    PointerRevision；唯一 Fence Authority 在自身 single-writer 原子提交严格推进 policy
    fence `E→E+1`、追加 ALIAS_COMMIT witness 并 CAS current alias，历史 revision/witness
    必须可解析；signer
    在 HSM 调用前后从同一 Fence Authority 取得 SIGN_PRE/SIGN_POST witness；
    ALIAS_COMMIT/PRE/POST 均冻结 exact TimeAttestation/CommitLease/FreshnessProof/Checkpoint
    并与对应 Fence Authority store commit 同事务，Envelope 绑定共同 fence epoch、
    alias-commit/pre/post witness，漂移时不发布 Envelope；
    Prepared/Challenge/Receipt/SigningRequest/Envelope/signer
    显式绑定 current Issuance Head+Bundle，verifier/factory/result/head 显式绑定 current
    Verification Head+Bundle，并对旧 issuance bundle 做明确 acceptance/吊销判定；signer
    不接受裸 digest/key handle；factory meta-integrity gate 必须 `is True`，subject gates
    按 `INVALID > UNKNOWN > VALID` 形成 fail-closed 结果。同一
    verification bundle freshness 到期只在读取时立即降为 amber，持久 reverify 必须使用新
    verification bundle。外部 effect unknown 保持 amber，pending→confirmed 只用原 effect
    key、认证查询、追加 successor receipt 和 expected-head CAS。

### 六、只按四个阶段推进

#### 阶段 A：架构评审（只读，不写 Runtime）

先交付证据化架构评审，至少包括：

- 当前模块、Interface、Implementation、Seam、Adapter、权威事实源和调用路径；
- ADR-0047 至 ADR-0062 对当前系统的逐条差距矩阵，并确认编号谱系、知识发布身份、飞书事实所有权和 Secret owner 无冲突；
- 身份/BOLA、权限、Sandbox、网络出口、并发、取消/强杀、审计、知识、评测、Bundle 的威胁与失败路径；
- 可复用模块与必须新增的最小 seam，说明为何保持高 Locality、避免第二控制面；
- 当前 NO-GO 项、前置依赖、未知项和需要 owner 决策的问题；
- 两种可行架构方案及取舍，给出推荐但不替 owner 签发。

没有 owner 明确接受阶段 A，不进入阶段 B；阶段 A 不创建迁移、不安装框架、不改公共接口。

#### 阶段 B：MVP 定义（规格，不写 Runtime）

只定义 Phase 0A 的最小可验证产品：5–8 名具名技术验收人员、macOS、仅 approved `source_kind=synthetic` 数据（正常样本只以 `fixture_class=canonical` 标识），以及 ADR-0053 的三条黄金工作流：

1. DOCX 技术报告润色与规范化；
2. 只读 OpenFOAM CFD 算例体检；
3. 会后纪要与行动项整理。

每条只取 ADR-0054/0055/0056 定义的 tracer bullet，写清用户结果、输入预算、非目标、风险、权限、Sandbox、知识依据、Delivery Bundle、invalid-first fixtures、FLAi Bench 门和机械验收。性能盘只保留内部技术验收/后续候选；自主 CFD 求解、实时会议、自动邮件/通知、全 Office 套件、Agent 市场均不得夹带。

阶段 B 必须输出可拆分、可回滚、按依赖排序的实现切片，且不改变公共契约、Schema、状态机或持久化格式，除非另起 ADR/规格并获接受。当前 Stage B 产品与合同语义已冻结；不得把这项冻结外推为任何 Stage D 开发、Runtime/API/Schema/数据库/依赖变更、真实数据、试点、发布或部署授权。

#### 阶段 C：可点击或可运行原型（隔离、诚实，不接生产）

原型先证明核心体验：单一 Composer → 连续执行轨迹 → 证据/产物 → 聚合例外 → 末端 Delivery Bundle 与真人签发。原型可以使用 fixtures，但必须在界面和证据中显式标注 `MOCK`/`SYNTHETIC`/`DECLARED-NOT-VERIFIED`，不得伪造真实模型、真实工具、真实 Sandbox、真实审计或真实发布状态。

当前收敛方向已固定为：空任务使用 A 式低门槛首页，提交后无缝展开 C 式连续执行工作台；A/B/C 比选壳必须删除，不得继续把方案选择暴露给用户。Stage C 授权只允许隔离的 UI 原型资源与内存 fixtures，不允许连接或修改 Runtime/API、Schema、数据库、生产配置，不允许新增第三方依赖、使用真实数据、开放试点、发布或部署。优先复用现有 Vue/Vite/Element Plus 的视觉与组件基础；不建设 Dashboard-first 第二应用。原型必须覆盖正常、空、加载、失败、blocked、unknown、权限不足、取消和证据缺失状态，并通过桌面端核心路径、键盘焦点与无横向溢出的可重复检查。

ADR-0062 将该原型定位为未来飞书工作空间中的专业执行 Surface，但不授权把 Stage C 连接到真实飞书。飞书 Hub 只能先做 F0 合同和具名评审；F1～F5 的只读投影、typed intent、治理签发、执行观察和迁移分别另获授权。
F0 七域评审必须绑定 `F0ReviewManifestV1`：包含 frozen Git commit/tree 和全部 normative
文件逐项 hash、生成主体/工具及 review/generation-receipt/seal schema；另需外部验证的
manifest-generation receipt 与七域 named review core+seal。单个文档 hash、聊天确认或未提交
工作树不能作为冻结对象，任一 normative 变更都使旧 review stale。

没有 owner 对原型体验、MVP 范围和诚实标签的明确接受，不进入阶段 D。

#### 阶段 D：分片开发（必须再次获得明确授权）

只有 owner 明确说“开始开发某一已冻结切片”后，才为该切片：

1. 建立干净、可追溯的工作基线；
2. 先写 invalid-first/失败路径测试；
3. 实现最小、局部、可回滚 diff；
4. 运行相关测试，再运行 `bash scripts/verify_all.sh` 或说明不能运行的确切原因；
5. 对权限、Sandbox、审计、持久化、状态机和公开接口做独立复核；
6. 用真实证据更新状态标签，不把局部通过外推为 Phase 0A、内网或生产通过；
7. 不自动创建/关闭 Issue、提交、推送、合并、部署或签发，除非另有明确授权。

### 七、机械停止条件

命中任一条件时停止当前阶段的写操作，保存只读证据并向 owner 报告；不得用猜测、降级安全或扩大权限绕过：

| ID | 可检测条件 | 必须动作 |
|---|---|---|
| S1 | `git status --short` 显示已有修改/未跟踪文件与拟改文件重叠，或无法判定来源 | 不编辑重叠文件；列出路径、当前 diff 和可选隔离方案，等待指示 |
| S2 | `AGENTS.md`、CONTEXT、适用 ADR/标准缺失、不可读，或同一术语/决策存在未解决冲突 | 停止设计定案；列出冲突和需要更新的 SSOT |
| S3 | 方案需要新增框架/数据库/编排系统，替换现有栈，或改变公共接口、Schema、任务状态机、权限/审计语义但没有已接受 ADR | 不实现；先提交决策问题和最小 ADR 需求 |
| S4 | 身份、对象范围、密级、执行预算、网络出口、不可逆动作或签发资格任一无法确定 | fail-closed；不执行、不造默认值、不请求永久 Full Access |
| S5 | 无法把执行绑定到不可变输入/计划/策略摘要，无法冻结精确 Delivery Bundle，或授权后内容发生漂移 | 拒绝提交；把任务置为真实 blocked/unknown 并保留证据 |
| S6 | 任务无法超时、取消或强杀，Sandbox 能触达未授权宿主资源/网络/密钥，或审计可被普通执行者改写 | 不进入 Phase 0A，不把目录隔离冒充 Sandbox |
| S7 | 安全关键行为没有可先失败的 invalid-first 测试，或测试 Oracle 不能区分真实现与 Stub/Mock | 停止实现；先补可证伪契约与 tamper witness |
| S8 | 基线测试失败且失败来源与本任务关系不明，或验证命令不能执行 | 不声称完成；保存命令、退出码、失败摘要并区分基线/新增失败 |
| S9 | 真实模型、工具、知识源或目标环境不可达，只能凭配置、Mock 或环境变量推断成功 | 标成 `DECLARED-NOT-VERIFIED`；不得宣称 REAL 或生产可用 |
| S10 | 任一不可抵消门为 false，或结果为 failed/invalid/skipped/unknown/证据不可解析 | 晋级、发布和签发一律拒绝 |
| S11 | 需要真实敏感数据、外部网络、第三方源码/依赖、外部系统写入或不可逆 Git/部署动作，但没有明确授权 | 停止并申请精确范围授权 |
| S12 | 已达到当前阶段交付物，但下阶段尚未获得 owner 明确接受 | 在阶段门处停止；只给出下一步建议，不自行越级 |
| S13 | 飞书/Bitable 可独立改写 GitHub、FLAi、Knowledge、Audit 或 Secret owner，或无 OwnerCommitReceiptV1 仍显示治理变迁生效 | 停止；恢复单 owner、typed intent 与对账合同 |
| S14 | `secrets-stackdocker` 引用不可解析、已撤销或 provider 不可达，只能回退旧 `.env`/硬编码/全局凭据 | fail-closed；不得外联或声称 Secret 迁移已验证 |
| S15 | 飞书租户/空间 classification 或 audience 未获批准，或飞书故障会阻断 kill/revoke | 不复制正文、不进入生产；先完成密级评审和安全生存演练 |
| S16 | Safety Coordinator / target owner / Policy owner、Egress Boundary/Wire workload-attestation、Trusted-Time Authority/Commit-Guard、Fence/Signer 任一 owner/failure-domain/key/operation policy 合同仍未决、可互相代签，Time epoch transition 无具名 continuity-root 签名，commit lease/proof/checkpoint 未绑定 transaction nonce/subject 与实际线性化点，或设计仍依赖普通 Secret 栈/进程自签 key | 阻断 F0；不得以 host clock、缓存、调用前看一次时间、直连 provider 或旧 witness 回退；真实 runtime 验证 Unknown 则阻断对应 D/F4/生产门 |

### 八、每阶段交付格式

每次阶段交付必须使用以下结构，信息不足时写“未知”而不是省略：

1. **阶段与结论**：A/B/C/D；`PASS`、`BLOCKED` 或 `NO-GO`；说明结论精确范围；
2. **状态矩阵**：能力/声明、五类统一状态标签、证据、未证范围；
3. **Changed files**：逐个列出本轮修改；只读阶段写“无”；
4. **Implementation summary**：本阶段实际完成内容；不得把设计、原型、Mock 写成实现；
5. **Verification command**：逐条列出实际运行命令、参数和工作目录；
6. **Test result**：退出码、通过/失败/跳过数量、关键证据路径；未运行说明原因；
7. **Security and governance gates**：身份/BOLA、权限、Sandbox、网络、并发/强杀、审计、知识、FLAi Bench、真人签发逐项结果；
8. **Risks / unresolved issues**：按阻断与非阻断分组，列出 owner、所需决策和证据缺口；
9. **Next recommended step**：只推荐下一个最小阶段或切片，并明确需要的授权；
10. **诚实边界**：本轮证了什么、不证什么、哪些仍是 `DECLARED-NOT-VERIFIED`。

宣称阶段完成前，至少重新运行 `git status --short`、相关单测/契约测试和适用的全量验证；把原始命令和退出码作为证据。人仍是唯一签发者，Codex 的最终文字不构成路线图、发布、交付或生产授权。

### 九、ADR 追踪清单

架构评审和后续规格对账必须逐条引用并判定，不得遗漏：

- ADR-0047：主线 ADR 谱系、历史 safe-auto 仅作 commit-bound evidence；ADR-0062 已用于飞书中枢方向，未来选择性吸收从 ADR-0063 起另立实施决定；
- ADR-0048：能力发布身份使用 ReleaseKnowledgeBinding，任务时 TaskKnowledgeSnapshot 只作运行证据；
- ADR-0049：唯一控制内核、ExecutionBroker、三类可替换执行 Port 与逐步 ExecutionTicket；
- ADR-0050：不中断自治会话与末端 Delivery Bundle 授权；
- ADR-0051：Phase 0A/0B 两级试点；
- ADR-0052：工作台优先与角色化治理 Surface；
- ADR-0053：三条黄金工作流；
- ADR-0054：DOCX 报告润色 tracer bullet；
- ADR-0055：只读 CFD 算例体检 tracer bullet；
- ADR-0056：会后纪要与行动项 tracer bullet；
- ADR-0057：权威知识底座；
- ADR-0058：FLAi Bench；
- ADR-0059：共建地图与证据化指标；
- ADR-0060：需求共创闭环；
- ADR-0061：需求决策权与路线图具名签发。
- ADR-0062：飞书唯一日常组织协作与治理中枢、联邦事实、OwnerCommitReceiptV1、SecretRef 与安全生存通道。

先读取 README、`15_Phase_0A_MVP_Spec.md` 的阶段状态和可验证的 owner 决策记录，再选择合法的下一门：若没有可靠阶段证据，默认从阶段 A 只读评审开始；若 Stage A 已接受而 Stage B 仍为 `DRAFT-FOR-FREEZE`，只复核/收敛 Stage B 并停在冻结门；只有 Stage B 已标 `FROZEN-FOR-STAGE-C` 且有 owner 明确授权，才执行 Stage C；只有 Stage C 已接受且 owner 点名某个冻结切片，才进入该 Stage D 切片。Git 状态、文档存在、聊天摘要或 Codex 自述都不能代替阶段授权。当前 Stage C 可继续走查隔离、诚实标注且不接 Runtime/生产的 A 首页 → C 执行态；ADR-0062 的 F0 只允许合同与具名评审。两条轨道都不能自动打开 Stage D 或 F1，且不得互相冒充完成。

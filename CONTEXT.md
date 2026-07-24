# FLAi-OS Work Coordination

This context defines the shared language for turning scattered organizational information into human-confirmed, traceable work records.

## Language

**协调骨干**:
在团队中持续收拢散落信息并整理为待确认工作记录的日常操作者；领导审阅其产出，但不承担日常录入与整理。
_Avoid_: 管理员、录入员、领导用户

**会议工作包**:
一次会议的来源材料、纪要草稿、决策草稿与责任事项草稿的集合；未经人确认时始终是草稿。
_Avoid_: AI 会议纪要、自动纪要、会议文件

**会议闭环**:
会议负责人对精确工作包签发正式会议记录，且每项责任事项均已具备明确产出、唯一负责人、
截止时间、验收标准和验收人；正式记录与初始责任事项必须由同一 owner-local transaction
生成。责任事项的执行与验收属于后续独立生命周期。
_Avoid_: 纪要已生成、全部任务已完成

**会后导入**:
协调骨干在会议结束后主动提交来源材料，由系统据此创建会议工作包；首版不参与会中实时录音或转写。
_Avoid_: 会议伴随、实时会议助手、自动入会

**来源材料**:
协调骨干主动提交的会议笔记、已有转写稿或文本型文件，是生成会议工作包的可追溯依据；未经人确认时不是正式结论。
_Avoid_: 正式纪要、会议结论、权威知识

**正式会议记录**:
由会议负责人确认的结构化会议事实，是议题、结论、决策、责任事项及其来源依据的唯一真相源；纪要文档和领导摘要只是其呈现或导出形式。
_Avoid_: Word 纪要、AI 生成稿、纪要文件

**例外审阅**:
仅要求协调骨干显式处理证据不足、信息缺失或相互冲突的内容，随后由会议负责人统一签发会议工作包。
_Avoid_: 全文盲签、逐句审批、逐条盖章

**责任事项**:
从正式会议记录产生的可验收承诺，必须具有明确产出、唯一负责人、截止时间、验收标准和验收
人；FLAi Meeting & Responsibility Governance owner 在同一 owner-local transaction 创建正式
记录与全部初始责任事项并返回有效 OwnerCommitReceiptV1 后才生效，任一必需信息缺失或回执
未知时仍是待处理例外。
_Avoid_: 任务、待办、继续跟进、进一步研究

**接收确认**:
责任人确认已经收到一项生效的责任事项，只表示送达状态，不赋予责任人否决交办的权力。
_Avoid_: 接受任务、批准任务、任务生效

**成果提交**:
责任人针对责任事项提供实际产出及其证据，表示工作已经进入待验收状态，但不表示责任事项已经完成。
_Avoid_: 完成任务、关闭事项、自证完成

**责任事项验收**:
预先指定的人依据验收标准确认成果，且是责任事项进入最终完成状态的唯一途径。
_Avoid_: AI 验收、责任人自验、协调骨干代关

**验收人**:
被显式授权确认某项责任事项成果的人，默认是会议负责人，也可由会议负责人在正式签发前委托给合适的专业骨干。
_Avoid_: 审阅者、抄送人、系统判定者

**分级升级**:
责任事项出现未接收、临近到期或逾期时，先提醒责任人与协调骨干，仅将持续未处理或严重逾期的异常递交会议负责人。
_Avoid_: 全员催办、首次逾期即报领导、静默逾期

**工作收件箱**:
协调骨干每天处理待整理、待签发、待接收、将逾期与待验收事项的统一入口，只呈现需要当前用户介入的工作。
_Avoid_: 会议列表、全量任务看板、统计首页

**领导简报**:
面向领导的极简决策入口，只呈现待本人签发、需要本人干预和重要实质进展，并允许按需展开来源与详情。
_Avoid_: 统计驾驶舱、人员排行榜、协调骨干工作台

**规则候选**:
从正式会议记录中提名的潜在规章或流程变更，保留原始依据，但在独立的人审与发布完成前不具有组织效力。
_Avoid_: 正式规则、有效流程、自动发布的制度

**规则候选箱**:
首版集中呈现规则候选及其来源、建议内容和建议归口人的待处理入口，不承担正式规则的起草、会签、发布或版本废止。
_Avoid_: 规章库、制度发布系统、有效规则库

**决策**:
由有权人员在会议中确认的选择或指令，可以产生责任事项或规则候选。
_Avoid_: 讨论倾向、建议、一般共识

**共识**:
与会者认可的判断或事实，但本身不构成交办，也不具有规章或流程效力。
_Avoid_: 决策、指令、有效规则

**未决问题**:
会议结束时仍缺少必要信息或授权、尚未形成决策的问题，需要后续补充或再次决策。
_Avoid_: 失败事项、默认否决、已达成共识

**来源锚点**:
将一项决策、共识、责任事项或规则候选关联到具体来源片段及文件位置的可追溯引用；人工补写内容改为记录修改人和时间。
_Avoid_: 会议附件列表、泛化来源、无出处结论

**审阅例外**:
要求人处理的具体问题，例如来源缺失或冲突、发言人不明、责任字段缺失或内容含有 AI 推断；正式签发前必须消解。
_Avoid_: 置信度百分比、一般警告、静默推断

**推断候选**:
AI 根据上下文提出、但未在来源材料中明确出现的负责人、期限、验收标准或其他内容；经人明确选择或修改前不能进入正式会议记录。
_Avoid_: 自动补全事实、默认值、已确认内容

**更正／补遗**:
对已签发会议记录进行修正或补充的新版本，必须记录修改人、原因和时间，并保留全部原始签发版本。
_Avoid_: 覆盖编辑、静默修改、删除历史

**可信回答**:
仅依据已签发的正式会议记录生成并带有条目级来源的回答；依据不足或冲突时明确无法确认，草稿、来源材料和规则候选不得冒充正式结论。
_Avoid_: 全库混合总结、无来源回答、候选内容当作制度

## 平台运行边界

**控制内核**:
FLAi-OS 中唯一拥有普通协作/工作负载身份与资源授权、策略、任务图、队列、权威状态、审计证据与交付决定的控制边界；任何外部 Agent 框架都不能成为第二事实源。独立 Safety Identity / PKI / HSM 拥有人的安全硬件身份、Safety admission 与 receipt-signing material；Kernel 只消费可验证 admission/receipt，不拥有或解析其私钥材料。
_Avoid_: OpenClaw 内核、OpenHands 内核、双控制面

**规范任务图（CanonicalTaskGraph）**:
控制内核把用户目标和已验证输入编译成的版本化、不可变执行图，明确节点、依赖、输入/产物绑定、预算、策略摘要和唯一交付边界；LLM 只能提出候选计划，不能直接写入或绕过确定性验证。
_Avoid_: Canonical TaskGraph、自然语言计划、前端步骤列表、Agent 自报 DAG

**会话执行许可（SessionExecutionGrant）**:
控制内核针对一个精确自治会话修订和 CanonicalTaskGraph 派生的有界许可，绑定认证主体、对象范围、允许动作、预算、策略与 ExecutionEpochSnapshot；它支持会话内连续工作，但不是永久 Full Access，也不直接授权任何单步动作。
_Avoid_: ExecutionTicket、会话管理员权限、用户点击同意

**执行代理（ExecutionBroker）**:
在控制内核指挥下组合 AgentRuntimePort、SandboxProviderPort 与 ToolExecutionPort 的执行 Module；负责准备、观察、取消、重连和回收执行单元，但不拥有任务真相、授权、签发或第二状态机。
_Avoid_: Execution Broker、OpenClaw Gateway、任务编排真相源、万能 ExecutionBackend

**步骤提案（StepProposal）**:
Agent Runtime 对下一次 replan、Model、Knowledge、Connector 或 Tool 动作提交的无授权候选，必须绑定 canonical step digest 和所需能力/目标；只有控制内核重新核权并签发 ExecutionTicket 后才可执行。
_Avoid_: 已批准动作、工具调用结果、模型思维链

**策略判定（PolicyDecision）**:
Authorization Module 对精确 actor、action、resource、请求上下文与 policy digest 作出的结构化判定，只能是显式 `deny`、`auto_execute` 或 `defer_to_delivery`，并携带 reason code、约束和有效边界；它是判定证据，不是可复用凭据，也不能由前端、LLM 或 Adapter 伪造。
_Avoid_: truthy allow、按钮可见性、ExecutionTicket、管理员默认放行

**队列租约（QueueLease）**:
控制内核把一个已准入执行项在限定 lane、generation、owner、预算和到期时间内租给 worker 的可续租占有事实；只有当前 generation 的有效租约能提交动作状态，过期或被撤销的晚到 writer 必须被 CAS 拒绝。
_Avoid_: 进程内锁、队列消息、永久 worker ownership、仅靠心跳判成功

**执行运行（ExecutionRun）**:
控制内核为一次会话修订在精确 CanonicalTaskGraph、SessionExecutionGrant、ExecutionEpochSnapshot 与 QueueLease 下创建的权威运行记录；它聚合 step、模型、工具、沙箱、取消与恢复证据，但不能自行扩大权限或把 `completed` 等同于业务通过。
_Avoid_: Agent 对话、模型调用、任务展示卡、无租约后台进程

**执行后端**:
受控制内核约束、可替换地完成 Agent 循环、工具动作或隔离计算的执行单元；它只能回报动作与观察，不能自行授权、签发或决定权威完成状态。
_Avoid_: 平台内核、授权引擎、签发 Agent

**自治会话**:
用户提交目标后形成的受控工作范围；范围内可逆动作与具备强制停止、回滚和执行凭据的工程操作由 Agent 连续完成，不要求用户逐步确认。
_Avoid_: 逐步向导、审批驱动任务、永久完全访问

**待交付动作**:
Agent 已准备完成、但会对正式资产、外部系统或组织事实产生不可逆影响的动作；在具名真人授权精确匹配的交付包前不得真实执行。
_Avoid_: 待工具审批、默认允许、高风险弹窗

**交付包**:
一次自治会话最终形成并绑定产物、差异、验证证据、残余风险和待交付动作摘要的不可变交付对象；授权只对该精确版本有效。
_Avoid_: 完成消息、聊天总结、空白审批单

英文 canonical identifier 固定为 `DeliveryBundle`；`DeliveryPackage`、聊天附件集合或可继续变化的结果页都不是同一持久对象。

**交付授权**:
有权真人对一个精确交付包作出的单次接受或外部提交决定；它不追认未记录动作，也不赋予 Agent 永久权限。
_Avoid_: Agent 自批、会话全权、逐工具批准

**交付尝试（DeliveryAttempt）**:
控制内核在同一事务中消费一次性交付授权并冻结全部 ActionIntent 后创建的唯一提交尝试；它以稳定 effect key 跟踪 prepared、executing、succeeded、failed 或 effect_unknown，不用“已批准”冒充“已成功”。
_Avoid_: Delivery Bundle、授权记录、任意重试编号

**动作回执（ActionReceipt）**:
执行边界对一个精确 effect idempotency key 返回的不可变结果证据，记录目标、实际动作、开始/结束、结果、外部标识、后置验证和证据摘要；缺失或不可对账时保持 `effect_unknown`，不得因 HTTP 200、进程退出 0 或已授权而推断成功。
_Avoid_: 日志文本、Agent 自报完成、DeliveryAuthorization、可覆盖状态字段

**受控验收试点**:
由 5–8 名具名技术验收人员仅在 approved synthetic 数据上验证自治体验、安全控制和证据链的首轮试用；正常样本仍为 `source_kind=synthetic`，只以 `fixture_class=canonical` 标识用途。它证明平台机制，不证明真实业务价值或生产就绪。
_Avoid_: 生产试点、全员内测、业务上线

**业务试点**:
受控验收通过后，由 20–30 名业务用户使用至少一条真实工具和真实数据工作流开展的限范围试用；其范围外能力仍不得被宣传为可用或已上线。
_Avoid_: 受控验收、全面推广、正式生产

**飞书组织协作与治理中枢**:
团队开展日常项目协作、需求共创、评审组织、知识创作、运行观察、治理处置与结果回告的唯一
组织 landing、工作收件箱与编排入口；英文 canonical identifier 固定为
`FeishuOrganizationalHub`。它把飞书中的动作编译为受认证的 typed intent，并投影 GitHub、
FLAi Control Kernel、Knowledge Authority 和审计 owner 的联邦事实，但不接管这些 owner。
GitHub 原生代码操作、FLAi 专业执行和密封安全通道保留为重新鉴权的专业 Surface，不另建组织
首页。
_Avoid_: 飞书总数据库、Bitable 总账、第二控制内核、机器人管理员

**工程智能体工作台**:
工程师把自然语言目标交给自治会话、持续查看真实执行状态并检查产物与证据的专业执行界面；它从飞书组织协作与治理中枢内嵌或重新鉴权进入，是 FLAi-OS 首发 Agent 执行 Surface，但不再是组织级默认入口。
_Avoid_: 战略驾驶舱、项目管理后台、第二组织入口

**治理与运行中心**:
飞书组织协作与治理中枢内面向平台管理员、安全人员和 Agent Owner 的角色受限空间，用于组织能力生命周期、策略、执行资源、异常与审计证据的处置；它只通过 typed intent 与 OwnerCommitReceiptV1 改变权威事实，不形成第二控制面。
_Avoid_: 独立管理应用、普通用户首页、第二管理平台、全员驾驶舱

**智能化指挥中心**:
飞书组织协作与治理中枢内面向领导和 AI 负责人的后期只读空间，从已验证的任务、评测、交付和风险证据派生组织层信息；它不拥有任务、授权或指标的独立事实源。
_Avoid_: 独立领导应用、FLAi-OS 产品总名、工程师工作台、手填战略看板

**治理意图（HubIntent）**:
经认证用户在飞书提出的版本化动作请求；它绑定目标 owner、对象与 payload
version/digest/classification、作用域、原因、幂等键和有效期，只能由对应 owner 在提交时
重新鉴权后生效。
_Avoid_: 卡片点击即成功、改单元格即发布、通用 approve、机器人代签

**准备命令（PreparedCommandV1）**:
Hub 在高影响动作提交前冻结的不可变命令，绑定 HubIntent、payload/target digest、
ActorBinding、credential/authorization epoch、认证 assurance、政策/评审/gate digest、
幂等键、nonce、TTL，以及具名签发 Source Ownership Registry 的 Head/Entry/verifier；
任一绑定漂移都要求完整重新 prepare。
_Avoid_: 可编辑审批表、复用旧挑战、只绑对象 ID

**来源所有权注册表（SourceOwnershipRegistryV1）**:
由 FLAi Architecture / Governance Policy owner 具名签发的版本化路由事实，把
`intent_type + schema_version + resource_kind` 唯一映射到 owner Module/Port、receipt
type/schema 与 verifier digest。Hub 只能消费其 Head/Registry/Entry resolution；未知、多匹配、
未签发或漂移全部 fail-closed，receipt 自报字段不能选择 verifier。
_Avoid_: Hub 内置路由表、Adapter fallback、按 receipt 自报 owner 选验证器

**提交挑战与确认凭证（ReviewChallengeV1 / ConfirmationProofV1）**:
高影响动作中供真人检查并显式确认的不可变挑战及 admission-layer 凭证；commit attestation、
proof 和调用参数都绑定精确 challenge/prepared/nonce digest、confirmation mode、
audience/purpose。commit 不得只凭 PreparedCommand 隐式选择挑战。
_Avoid_: 通用确认按钮、prepared ref 直接提交、客户端自报 confirmation

**事实投影（FactProjection）**:
从 GitHub、FLAi Control Kernel、Knowledge Authority、Metric Registry 或审计 owner 的版本化
事实生成的权限过滤视图；它必须带适用的 source evidence、classification 和 freshness，
删除或修改投影不改变来源事实。只有治理状态变迁要求 OwnerCommitReceiptV1，运行和 GitHub
只读事实分别使用 witness 与 verified provider state。
_Avoid_: 双向同步记录、飞书副本真相、手工点绿

**权威所有者提交回执（OwnerCommitReceiptV1）**:
证明一个精确 PreparedCommand 已由同一具名真人以新鲜、满足要求的 commit assurance 提交，
并由权威 owner 接受和读回核对的结构化证据；它绑定 intent/challenge/actor/target/effect、
credential/authorization epoch 与 owner-specific verification。飞书已点击、HTTP 2xx、消息
送达或 Bitable 更新均不是该回执。
_Avoid_: 成功提示、卡片确认、人签替代物

**对账案件（ReconciliationCase）**:
当命令效果、来源事实和飞书投影不能一致确认时形成的具名异常对象；在消解前不得换幂等键重放、按最后写入者覆盖或把未知显示为成功。
_Avoid_: 自动覆盖、忽略同步失败、重复点击重试

**安全生存通道**:
飞书、Hub、主协作 SSO 或普通在线 Secret 解析不可用时，仍能通过独立
`SafetySurvivalPort` 执行强停、撤权、隔离、凭据失效、只开对账案、向预批准本地 WORM
封存事故证据和只验证不启用的恢复候选的密封双人通道；对外证据导出、恢复启用、正常项目
管理、签发、发布或合并代码仍走常规治理，因此它不是第二日常中枢。已核验本地围栏但外部
provider effect unknown 时只能是 amber 的 `LocalFenceVerifiedExternalPendingV1`；只有
`FullSafetyEffectVerifiedV1` 可表示完整处置成功。
_Avoid_: 备用管理后台、绕过治理的超级管理员入口、外部效果未知显示最终成功

**Safety Policy Head**:
由独立 Safety policy owner 通过两个不同真人的硬件 admission 和 publication receipt 追加的
不可变政策 Head version；每次切换同时追加 content-addressed PointerRevision，固定 URI
只是经 CAS 切换、解析当前 revision 的 alias；该 alias 由独立 Fence Authority 单写，
CAS 必须与单调 policy fence `E→E+1`、ALIAS_COMMIT witness 及 alias-state digest 属于
同一 Fence-Authority owner-local 原子提交，历史
Head/PointerRevision/fence witness/receipt/bundle 永久可解析。Signer 在 HSM 前后从同一
Fence Authority 取得 SIGN_PRE/SIGN_POST witness，Envelope 绑定共同 fence epoch 与两份
witness。Issuance Head 约束 Prepared/Challenge/SigningRequest/signer，
Verification Head 约束 verifier/factory/result/read。Bundle 内容摘要不等于获授权，任何
Head/receipt/PointerRevision unknown 或 TOCTOU 都 fail-closed；回滚必须铸造新
epoch/trust/validity/digest，不得重发同一或历史 bundle digest。
_Avoid_: 调用者自选 trust bundle、裸 current-policy bool、重发旧 bundle 刷新 freshness

**安全准入主题与消费（Safety Admission Subject / Consumption）**:
EmergencyActorAdmission 不是通用强认证会话，而是绑定
`SAFETY_PREPARE | SAFETY_COMMIT | POLICY_PUBLICATION` 某一精确 immutable subject、
一次性 nonce、actor/scope/epoch/assurance/channel/audience/purpose 的 domain-separated
凭证。唯一 Safety Admission Coordinator 在自己的事务中原子消费两份 admission + subject
nonce，写 append-only Consumption 并签发 `SafetyAuthorizationReservationV1`；下游 owner
只在自己的本地 CAS 中凭 Reservation 创建对象，崩溃保持 consumed+reserved 并对账，不伪装
跨 owner 事务。ChallengeState 全链也只由 Coordinator 写；target owner 的 immutable
`SafetyCommitAttemptV1` 是最终 receipt/unknown 的本地 anchor。下游首次 anchor 前必须
权威 resolve 三条 consumption、验证 Coordinator workload attestation、全部 gate `is True`
且 status ACTIVE，并在本地 commit 内消费可验证 `SafetyTrustedTimeAttestationV1`、按
attested UTC upper bound 检查 TTL、CAS consumer checkpoint；回拨、偏差、outage 或 Unknown
均拒绝。过期未 anchor 不得启动 effect。outbox 排队与 `SafetyCommitDispatchClaimV1`
都不是实际调用；唯一 egress boundary 必须在第一 mutating send primitive 前重新验
attested time/deadline、CAS 消费一次性 `SafetyProviderMutationCapabilityV1` 并形成
`SafetyProviderCallAttemptV1`。缺 verified `SafetyProviderSendReceiptV1` 时一律
effect unknown + DO_NOT_REPLAY，只可原键查询。不同 phase、subject 或 replay domain 永不复用。
_Avoid_: TTL 内复用登录凭证、只消费 challenge nonce、两人认证后更换发布 bundle

**安全可信时间证明（SafetyTrustedTimeAttestationV1）**:
由唯一、独立 Safety Trusted Time Authority 针对精确 request nonce/subject/purpose 签发的
content-addressed 时间区间证明，绑定 authority epoch、严格单调 counter/predecessor、
exact 具名签名的 EpochTransition、UTC lower/upper bound、uncertainty、有效期、key epoch、
trust anchor 与签名。consumer 必须用一次性 transaction nonce/commit subject 取得
CommitLease，再由 consumer-local Trusted Time Commit Guard 在 owner-store 线性化点以受信
monotonic elapsed source 形成 FreshnessProof，并与 checkpoint/anchor 同事务 CAS 保存
high-water；TTL 只按保守 upper bound 与实际 elapsed budget 共同判定。回拨、gap、fork、
无 continuity-root transition、陈旧 lease、超 budget、skew/uncertainty 超限、
source/key/revocation outage 或任何 Unknown 都 fail-closed，禁止回退 host clock、缓存或
调用方时间。Policy Fence 的 ALIAS_COMMIT/SIGN_PRE/SIGN_POST witness 也冻结 exact
TimeAttestation/CommitLease/FreshnessProof/Checkpoint。
_Avoid_: `Date.now()` 授权、调用前看一次时间、缓存时间续期、裸 trusted_time_ref、时间回拨继续执行

**安全发送边界（Safety Provider Send Boundary）**:
Safety DispatchClaim 只是领取；一次性 ProviderMutationCapability 也不是已发送证据。只有
无旁路的受控 egress boundary 在发送边界重新验时、单次消费 capability 并形成
ProviderCallAttempt，才表示“可能已经发送”；只有 verified ProviderSendReceipt 才证明
handoff。Attempt 后无 receipt 不区分 socket write 前/中/后，统一 Unknown、禁止重发和换键。
_Avoid_: outbox 即发送、claim 即调用、HTTP 2xx 即生效、崩溃后自动重放

**F0 评审清单（F0ReviewManifestV1）**:
七个责任域共同评审的唯一冻结对象，绑定 Git frozen commit/tree、全部 normative 文件
path/hash/role、manifest 生成主体/工具与 review/generation-receipt/seal schema；必须另有经
外部信任验证的 manifest-generation receipt，以及七域各自的 named review core+seal。任一
规范文件变化都会生成新 manifest 并使旧评审失效。
_Avoid_: 单文档 hash、聊天同意、未提交工作树、沿用旧评审

**项目上下文绑定（ProjectContextBinding）**:
由 FLAi Project Directory 唯一拥有的版本化单向映射，把飞书协作项目关联到已授权
Project/OrganizationalScope；群成员、项目改名、Bitable 字段或 Hub 本身都不能创建
ProjectMembership 或改绑更高权限 scope。
_Avoid_: 群成员即授权、Hub 项目总账、手工改 scope

**开发交付项（DeliveryWorkItem）**:
由 FLAi Delivery Governance 唯一拥有的多人开发工作单元，绑定具名人类 owner、项目与密级、
冻结 SHA、branch/worktree、文件/Interface scope、版本化 executor、预算、dispatch/handoff
和 GitHub 集成状态；模型显示名不构成执行或合并证据。
_Avoid_: AI 自主 merge、共享脏工作树、模型标签即执行凭证

**开发交接核心（DevelopmentHandoffV1）**:
执行器提交的不可变交接对象，内容绑定 work item/run/runtime receipt、base/final SHA、
commit/diff、变更 scope、验证证据、风险和未决项；其 digest 使用 domain-separated
RFC8785-JCS 规则且只排除自身摘要。无钥内容摘要不证明执行器身份、人类接受、GitHub approval
或 merge。
_Avoid_: 自然语言总结即交接、模型自报身份、未复算 digest、handoff 即批准合并

**SecretRef**:
指向 `secrets-stackdocker` 中受控运行时 App/Connector Secret 版本的非秘密引用；业务对象、
飞书、Bitable、GitHub、日志和事实摘要只能持有引用，不能持有 Secret value。普通
App/Connector key 均遵守该 owner；人的硬件签名、Safety receipt-signing、Coordinator /
target owner / Policy owner 三类 workload-attestation material、Egress Boundary/Wire
两类 operation-bound workload-attestation material、Policy-fence 与 Trusted-Time signing
key 分别由独立 Safety
Identity / PKI / HSM / Time owner 持有，预置 public trust anchor 不是 Secret。这些 key
不得由普通 workload identity、应用进程、SecretProviderPort 或普通 Secret 栈解析；任一
owner/failure-domain/key/revocation/trust 合同未决时不得关闭 F0；真实 runtime/outage witness
在后续实现门闭合，不能由 F0 文档评审冒充。
_Avoid_: `.env` 即密钥管理、卡片参数携带 key、硬编码 fallback、日志保存 secret hash

**黄金工作流**:
在受控验收试点中代表一种完整用户结果、并能机械验证从目标到交付证据全链路的精选任务；它不是一个 Agent 卡片，也不是功能目录。
_Avoid_: 功能清单、演示脚本、Agent 数量指标

**智能办公助手**:
面向个人内容生产的统一入口，在有界技能内完成报告润色、文档总结、表格分析、演示材料、知识快查和通信草拟；它不拥有永久全权限，也不在首期自动发送外部消息。
_Avoid_: 工程文档数据库、万能 Agent、Office GUI 机器人

**CFD 工程助手**:
围绕已有 CFD 算例和结果提供设置检查、解释建议、隔离副本上的受控优化、后处理与报告的工程协作能力；首期不自主发起完整求解，也不覆盖原始算例。
_Avoid_: 全自主 CFD、CFD 求解闭环、自动工程判定

**会议行动助手**:
把会议来源材料整理为带来源的正式记录草稿、决策和可验收责任事项，并在人确认后持续跟踪接收、成果提交和验收的协作工作流。
_Avoid_: 仅做纪要润色、自动签发会议结论、普通待办生成器

**技术报告润色与规范化**:
智能办公助手的首个黄金薄切片，把用户提交的 DOCX 技术报告在隔离副本上润色和规范化，并交付修改文档、改动对照与待确认问题；原件和工程事实保持不可变。
_Avoid_: 全能 Office 自动化、静默改数、覆盖原文件

**CFD 算例体检**:
CFD 工程助手的首个黄金薄切片，对用户提供的已有算例做只读设置检查，并用具体文件与字段证据说明风险、建议和未知项；它不修改算例或启动求解。
_Avoid_: 自主求解、自动优化、无证据的总体评价

**会后纪要与行动项整理**:
会议行动助手的首个黄金薄切片，把用户主动提交的会后材料整理为带来源的会议工作包草稿，并集中呈现需要人在末端消解的记录与责任字段例外。
_Avoid_: 实时会议伴随、自动签发纪要、全生命周期催办

**权威知识底座**:
为所有 Agent 提供统一权威目录、版本、有效性、适用范围、访问策略与精确出处的逻辑事实源；内容可以来自多个受控系统，但存储位置和检索技术本身不赋予权威性。
_Avoid_: Obsidian 库、向量数据库、文件共享盘、万能 RAG

**权威知识项**:
由具名授权人员签发、具有不可变版本和当前有效状态的规章、条款、正式决定或工程基线；受信源系统只能提供可验证的上游签发凭据，不能成为 FLAi-OS 签发者。只有符合适用范围的有效项可以直接支撑组织要求和工程依据类结论。
_Avoid_: 普通上传、会议笔记、AI 产物、未签发草稿

英文 canonical identifier 固定为 `KnowledgeItem`；“权威”来自该对象的签发状态、版本、有效期和适用范围，不通过另造 `AuthoritativeKnowledgeItem` 实体表达。

**源系统证明（SourceSystemAttestation）**:
受信源系统对一个精确上游对象版本提供的可验证来源声明，至少绑定 source system、object/version/digest、上游签发主体或授权链、有效时间与验证证据；序列化字段固定为 `source_system_attestation`。它可以证明上游事实来自何处，但不能替代 FLAi-OS 的知识发布决定或真人签发。
_Avoid_: 文件路径、同步成功日志、连接器身份、FLAi-OS signer

**依据链**:
把回答、建议或工程假设逐条关联到知识项版本、精确位置和任务时有效状态的可审计关系；缺失或冲突必须显式暴露，不能由模型静默补齐。
_Avoid_: 文末参考资料清单、相似度分数、模型自述理由

**FLAi Bench**:
复用生产执行链，对冻结能力发布包进行确定性回归、工程质量、安全治理和运行效率四轨评测的统一基准评测底座；它提供证据矩阵而不是可掩盖失败的单一总分。
_Avoid_: 模型排行榜、演示用题库、第二套 Eval 平台

**能力发布包**:
一次可被评测和发布的完整能力版本，绑定 Agent、Prompt、Workflow、Schema、实际模型 endpoint/route/参数与 tokenizer、Tool、Sandbox、资源/Token/权限/出站策略、完整 ReleaseKnowledgeBinding binding digest、评测包/rubric/Gate Policy 与环境档；任一关键成分漂移都会形成不同被评对象。任务时 TaskKnowledgeSnapshot 不反向定义该包身份。
_Avoid_: Agent 版本号、模型名称、代码提交号

英文 canonical identifier 固定为 `CapabilityReleasePackage`。`CapabilityRelease` 仅可用于指代拥有该对象及其生命周期的 Release Module，不是第二种持久实体或可与发布包互换的别名。

**发布知识绑定（ReleaseKnowledgeBinding）**:
能力发布包在运行前冻结的知识合同，规定允许的 authority/scopes、required/prohibited sets、版本选择、目录根、检索/锚点规则和 external-live declarations；完整 canonical 内容以 `binding_digest` 参与 release identity，不包含具体 actor、任务时刻或实际命中。
_Avoid_: 任务时知识快照、当前检索结果、向量索引名称

**任务知识快照（TaskKnowledgeSnapshot）**:
每次任务按发布知识绑定、主体、任务时间和授权解析出的不可变知识版本、锚点、缺失与冲突证据；它绑定运行与 Bench 证据，但不改变能力发布包摘要。
_Avoid_: ReleaseKnowledgeBinding、当前最新版、临时搜索列表

**执行 Epoch 快照（ExecutionEpochSnapshot）**:
一次 Grant/执行冻结的撤权世代集合，包含 actor credential epoch、所有适用 authorization partition/epoch 与 trust-policy epoch/digest；各值只由 Identity、Authorization、Supply-chain 的对应 owner 维护，Grant、Ticket、Lease 和 ExecutionRun 只引用不可变快照。
_Avoid_: 修改 Grant 撤权、单一全局 epoch、仅在交付时重验

**执行票据（ExecutionTicket）**:
控制内核对一个动态 step 作确定性授权后签发的短时、不可扩权凭据，绑定 step/Grant/policy digest、ExecutionEpochSnapshot、lease id/generation、能力/目标、预算、有效期和 nonce；Tool、Model、Knowledge、Connector 与 Sandbox 启动边界无票拒绝。
_Avoid_: Session Full Access、运行时自授权、通用 API key

**撤权尝试（RevocationAttempt）**:
将一次已提交 epoch 变更连接到受影响 lease、冻结 SLA/deadline，以及进程树终止、步骤凭据吊销、既有连接失效三类 witness 的权威记录；任一缺失、超时或 unknown 都保持 revocation_incomplete/needs_reconciliation。
_Avoid_: 只改任务为 cancelled、仅拒绝下一步、无见证撤权成功

**效果幂等键（effect idempotency key）**:
为一个精确交付动作及外部目标冻结、跨重试与重新授权稳定的副作用身份；外部调用后 receipt 未落库时进入 effect_unknown，未经对账不得换键重放。
_Avoid_: HTTP request id、每次重试随机 UUID、授权即成功

**AgentRuntimePort**:
承载 Agent Loop 提案与观察的窄接口；Built-in、OpenClaw、OpenHands 可作为实现，但只能提交 Step/Replan Proposal，不能直接调用下游或写权威状态。
_Avoid_: SandboxProviderPort、ToolExecutionPort、第二控制面

**SandboxProviderPort**:
创建、观察、强杀和销毁强制隔离执行单元的窄接口；macOS 隔离实现位于此处，不负责 Agent 规划或工程工具语义。
_Avoid_: 临时目录、Agent Runtime、CAE Tool Adapter

**ToolExecutionPort**:
凭有效 ExecutionTicket 调用已注册 Python、Office、CFD/CAE/HPC Tool 并返回动作级 receipt 的窄接口。
_Avoid_: AgentRuntimePort、任意 shell、无票工具调用

**资格决定（QualificationDecision）**:
具名真人基于精确 release 与 Bench digest，对 Phase 0A、Phase 0B 或正式服务目标类别追加的 eligible/ineligible/expired 决定；不自动产生暴露权限。
_Avoid_: Agent L0-L3、BenchRun 状态、DeploymentBinding

英文 canonical identifier 固定为 `QualificationDecision`。`CapabilityQualificationDecision` 不是另一类记录；如需命令名称，使用 `IssueQualificationDecision`，不得把命令和追加式决定混为一体。

**评测准入（EvaluationAdmission）**:
具备职责的 Eval maintainer 为尚未取得资格的精确 CapabilityReleasePackage 签发的版本化、可撤销实验室准入事实；它绑定 evaluator/service actor、approved synthetic fixture 与 pack/rubric/Gate Policy/environment digest、允许动作、零外部效果、预算、有效期和 ExecutionEpochSnapshot，只能运行真实执行链上的评测任务，不能暴露给普通用户或替代 QualificationDecision/DeploymentBinding。
_Avoid_: `origin=eval` 请求字段、测试模式开关、Mock 白名单、生产调用资格

`origin=eval` 只能是 Kernel 验证当前 `EvaluationAdmission` 后派生的审计标签，不能由客户端、Agent、Adapter 或队列消息声明；英文 canonical identifier 固定为 `EvaluationAdmission`。

**部署暴露绑定（DeploymentBinding）**:
把精确能力发布包限制到具名用户/项目/数据域/动作/时间窗和 deployment class 的版本化人签事实，可 active、suspended、revoked 或 expired。
_Avoid_: 能力包生命周期、Agent status、全员开关

英文 canonical identifier 固定为 `DeploymentBinding`。`DeploymentSignoff` 不是另一类持久记录；如需签发命令，使用 `SignDeploymentBinding`，提交成功后产生新的版本化 DeploymentBinding 事实。

**不可抵消门**:
安全、诚实性、依据链或关键回归中的绝对准入条件；任一条件失败、无效、跳过或证据未知都不能被其他维度高分抵消。
_Avoid_: 综合评分扣分项、风险平均分、模型自评

**FLAi 共建地图**:
面向全体参与者的只读平台进展视图，把版本化战略目标连接到平台地基、黄金工作流、能力发布包及其真实证据；计划由人制定，节点状态由发布、评测和验证事实派生。
_Avoid_: 手填驾驶舱、项目甘特图、领导专用大屏

**证据化运营指标**:
具有定义版本、时间窗口、样本量、事实源和未知语义的使用、质量、安全、资源与价值指标；它们可以被复算，不能由展示层临时拼出口径。
_Avoid_: KPI 拼盘、模型估算价值、无分母百分比

**节时基线**:
针对可比较任务类型，经具名方法和有效样本建立的人工处理时间参照；只有绑定基线版本、样本覆盖和人工抽样确认，平台才能报告区间化节时估算。
_Avoid_: 任务运行时间、模型自报节省时间、精确到分钟的营销数字

**需求信号**:
由认证用户、任务反馈、失败事件、会议决定、审计发现或权威指令产生的原始痛点与机会记录；它保留提出者、来源、时间、证据和密级，但尚不构成开发承诺。
_Avoid_: 产品需求、工程 Issue、路线图节点

**路线图承诺**:
具名决策者在审查需求证据、影响、风险和依赖后正式采纳，并绑定共建地图版本、验收结果和决策理由的发展目标。
_Avoid_: 热门建议、AI 推荐、未排期候选

**需求共创闭环**:
把低门槛需求信号依次经过 AI 预处理、人工筛选、路线图采纳、工程交付、FLAi Bench 验证和结果回告的可追踪机制；合并或暂缓都不抹去原始来源。
_Avoid_: 意见箱、点赞榜、自动建 Issue

**需求策展人（Demand Curator）**:
在具名领域范围内整理、去重、合并、分类、脱敏并补全需求证据的人类职责；它可以形成候选建议，但无权正式采纳路线图。
_Avoid_: 路线图负责人、全局管理员、AI 产品经理

**路线图负责人（Roadmap Owner）**:
对一个版本化共建地图具有正式采纳、暂缓或不采纳签发权的具名人类职责；它必须记录理由并满足适用的领域和安全门。
_Avoid_: 需求策展人、开发负责人、投票结果

**领域与安全评审门**:
当需求触及专业工程结论或安全、权限、密级、外联、Sandbox、审计边界时，由相应具名评审人提供的不可省略意见或安全准入条件。
_Avoid_: 常设审批链、AI 评审、路线图负责人自行豁免

**领域评审人（Domain Reviewer）**:
在具名领域与作用域内审查专业痛点、依据、验收口径和未知项的人类职责；无路线图排序、发布或安全豁免权。
_Avoid_: Roadmap Owner、Security Reviewer、AI Judge

**安全评审人（Security Reviewer）**:
在具名作用域内审查身份、权限、Sandbox、外联、密级、审计和破坏性动作的人类职责；不能代替业务价值或路线图决定。
_Avoid_: 全局管理员、发布签发人、自动安全评分

**交付负责人（Delivery Owner）**:
在已签发路线图承诺后组织 Issue、实现、版本回链和验证准备的人类职责；代码合并或自测不能让其自行宣布需求解决。
_Avoid_: Roadmap Owner、Qualification Signer、自验关闭

**AI 预处理模块**:
对需求做提取、去重建议、聚类和候选说明草拟的无签发自动化组件；所有输出保持 draft provenance。
_Avoid_: AI Principal、AI 产品经理、自动采纳与排期

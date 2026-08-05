# map #46 批 0：工程可信内核「隐藏面」盘点（票 #48）

> 基线：`origin/main` @ `39738a8`（含 PR #44）· 分支 `kimi/map46-48-trust-kernel-inventory`
> 性质：research 盘点（plan, don't do）——零产品代码改动；触发-浮现规则只给候选集，定稿留 owner 裁。
> 方法：静态代码/文档盘点（源码 + 宪法 + ADR + 既有验收记录），引用一律 `file:line`；未起栈实测，
> 浮现时机的实测证据引用 map #32 终点验收记录（`docs/reviews/MAP32-DESTINATION-ACCEPTANCE-record.md`）。
> 关联：map #46（通用好用面 × 隐藏工程可信内核）· #1/#3/#6（可信内核硬化）· #47（行话审计，并行票）。
> 红线自查：本报告为纯文档新增，信任色锁/诚实地板/诚实纪律/completed 中性/依赖面零触碰。

---

## 一、可信内核现状清单

盘点的「可信内核」= 让工程结论可被信任的机制全体：治理闭环（评测/固化/晋升/attestation）、
人签面、依据面、密级面、诚实标注面、审计链，以及 map #32 已验收的「段语义与状态来找人」
承载面。逐面给出现状（实现位置 + 纪律锚点），开口项单列。

### 1.1 治理闭环后端（#1 四大块 + #3 对账）

**总貌**：`backend/app/governance/` 五模块齐备（eval_runner 1027 行 / eval_worker 208 /
promotion 1131 / curation 649 / signer_provenance 163），HTTP 面在
`backend/app/api/governance.py`（10 端点：评测入队/列表/单条/快照句柄、样本固化、
sample 认可、晋升、晋升记录×2、curation 计数）。#1 票四大块的对账结论——**三块已闭环（票已关），
T3 代码已落地但票未关，T5 未做**：

| #1 子项 | 票 | 状态 | 实现锚点 |
|---|---|---|---|
| T1 异步评测队列+配额 | #2 | CLOSED（已实现） | `eval_runner.py:424` enqueue→202 queued（`api/governance.py:44`）；`eval_worker.py` 配额门原子认领（`claim_next_queued_eval_run`）、僵尸线程兜底收口（`_settle_run`）、worker 启动回收 running 僵尸为 error 不自动重放（`recover_interrupted`，eval_worker.py:165-193）；attestation fault 期间停止认领（eval_worker.py:81-83） |
| T2 不可变快照执行+句柄 | #5 | CLOSED（已实现） | `eval_runner.py:307` `freeze_eval_snapshot`：入队瞬间冻结包文件+approved case，内容派生 handle=`snap_`+sha256(content_json)，insert-once 落库；执行侧材化快照读而非活磁盘（`_SnapshotRegistry`/`_materialize_snapshot`）；句柄只读 API（`api/governance.py:88-114`） |
| T4 sample 级认可 | #4 | CLOSED（已实现） | `curation.py:427` `acknowledge_sample`：actor 只取认证会话 username（请求体 extra=forbid）、首次认可 CAS-on-NULL 冻结、幂等重放返回同一 case、仅 completed+validation_status=success 可认可、`accepted_by_engineer=false` 不可覆盖、L1 或 promotion latch 在途触盘前 409；审计区分 acknowledged/idempotent_replay（`api/governance.py:176-189`） |
| T3 启动 attestation | #3 | **OPEN，但代码已全量落地** | 见下「T3 专项对账」 |
| T5 verify_all.ps1 parity | #6 | OPEN（未做） | `scripts/verify_all.ps1` 缺 .sh 已跑的若干 e2e 套件（票 #6 自述） |

**T3 专项对账（票 #3 验收标准 vs main 现状）**：

- 「启动核对每个 L1/trial agent ↔ promotions 记录」→ `promotion.py:386`
  `reconcile_promotion_attestations`：遍历发布表全部 L1，逐一以
  `_promotion_record_attests`（promotion.py:296，含五门 checks 复核、signer 背书
  `stored_signer_attests`、包快照 digest/file_count 比对、eval 证据 14 条件、时间线）严格核对；
  DB 既有 L1 投影在重启扫描中缺件/不安全 → 显式 `missing-or-invalid-package-snapshot` 拒载记录
  （promotion.py:407-430，防「消失于对账视野」假绿）。
- 「无匹配 → fail-closed（不发布 L1）+ audit log + health 信号」→ 拒绝即
  `agent_registry.deregister` + `audit_event("promotion_attestation", outcome="rejected")`
  （promotion.py:453-467）；health 暴露 `promotion_attestation_axis/ok/rejected_count`
  （main.py:353-362）；持久故障 latch（`repos.record/get/clear_promotion_attestation_fault`）
  跨进程共享，worker 心跳承接（jobs/runner.py:76-87）。
- 「判定 is True/is False；reconcile 先于 sync」→ `bootstrap.py:75-106`：注释明写
  「GH #3：scope reconcile 后、首次 DB sync 前核对 L1↔promotions」，顺序钉死在唯一装配函数；
  `_eval_evidence_conditions` 全链 `is True` 风格（promotion.py:150-282）。
- 「health 代际标记 + deploy_selfcheck 加项」→ `deploy_selfcheck.py:399`
  `check_live_promotion_attestation`（axis/ok/rejected_count 严格校验，truthy 拒）。
- 「e2e：种 L1-无-promotions → 启动 fail-closed；tamper 必红」→
  `backend/tests/test_startup_attestation.py`（1022 行，覆盖拒载/置红/恢复/latch/时间线伪造）。
- **结论：T3 五条验收标准在 main 上逐条有实现与测试。票 #3 仍 OPEN 属留痕缺口**
  （票未关、无关闭验收记录），非代码缺口。处置建议见 §四。

**晋升门**（`_PROMOTION_GATE_CHECKS` 七项，`promotion.py:58-67`；全部 `is True` 才放行，
422 携逐条判定）。运行时先判六项：①transition_supported（仅 L0→L1）
②min_eval_coverage（approved≥3 且含失败路径 case、broken=0）③eval_evidence
（14 条件：run 归属/版本/全绿/digest 咬合/case_results 与快照 approved 集一一对应/
快照 handle 绑定不可变内容/身份一致/时间线）④changelog_nonempty ⑤feedback_channel
（如实标注「平台级提供，不冒充 per-agent 验证」）⑥manual_confirmation
（`exception_paths_handled is True` 且 signer 复核通过）。六项全过后进入快照发布，
写入第七项 **package_snapshot**（promotion.py:992-1002：最终门禁、审计记录、Registry
与 Runtime 绑定同一完整包快照的 contract/digest/file_count，同步刷新复核
coverage/evidence/changelog）；启动 attestation 复核历史记录时要求七项齐全且
逐项 ok is True（`_promotion_record_attests`，promotion.py:296-383）。
通过后 agent.yaml 行级手术（newline 保真）+ changelog 追加 + 补偿式回滚
（promotion.py:769-795，绝不留「yaml 已 L1 但无审计记录」半提交）。

**签发者 provenance**（ADR-0019，`signer_provenance.py`）：HTTP 签发必须绑定提交时仍有效的
认证会话（`resolve_signer` 在事务连接上复核，过期/掉包返回 None）；server_cli 是显式独立
运维边界；`legacy_unverified` 历史记录只读兼容、永不为 L1 背书（signer_provenance.py:133-151）；
HTTP 投影脱敏（绝不返回 session hash，`public_promotion_record`）。

**不可变包快照 v1**（ADR-0018 R2 追加节）：影子 Registry 两遍稳定捕获、拒 symlink/reparse/
FIFO/大小写碰撞/撕裂读取，资源边界 4096 entries/16MiB 单文件/64MiB 总量/深度 32；
每次 `validation_started` 事件记录 contract+digest 使任务审计可反查执行代际。

### 1.2 人签面（人是唯一签发者）

- **状态机**：`core/statemachine.py:39`——`waiting_review` 出边仅 `{completed, failed}`，
  注释明示「禁止任何自动化路径」；非法转移抛 `IllegalTransitionError`（含未知状态）。
- **review API**：`api/tasks.py:1770` `review_task`——`ReviewTaskRequest` extra=forbid，
  reviewer 服务端从认证会话派生（ADR-0019 D5，tasks.py:1788-1789）；状态迁移+样本标签回填+
  signer 事件同一事务；approve→completed（review_approved）/reject→failed（review_rejected）；
  **自签不拦截但如实记录** `self_review`+`self_review_basis`（username 精确/display_name 近似，
  tasks.py:1829-1849）。
- **前端签发卡**（两处同源）：TaskDetail `review-card`（TaskDetail.vue:228-250）与
  StatusCenter peek 内联签发卡（StatusCenter.vue:199-213），共用要素：签发人=登录身份记名
  不可代填、「批准即代表你作为工程师背书该产物——签发权在你，平台不代签」、授权链
  「除你此刻的批准外，平台没有任何自动放行路径」、批准=teal（人签槽）/驳回=danger、
  批准二次确认（B6a，确认钮 teal）。
- **核验三面 + 诚实地板**：`VerificationCard.vue`——渲染窗=completed/failed/waiting_review
  （90 行），①工具真实性（tool_runs 落库计数投影，含 mock 则 amber pill「未经真实核验」，
  拉取失败诚实降级「不可用」绝不冒充零 mock）②人工签发（deriveSignoff 四态 SSOT）③批量
  结果（无 summary 事件整行不渲染）；底部常驻诚实地板行（#36 归位）：
  「通识解释仅供参考；工程结论以确定性工具与人签为准」（VerificationCard.vue:70-72，
  中性墨不占信任色槽）。

### 1.3 依据面（evidence_policy / findings）

- **契约**：ADR-0030 §2——`evidence_policy.required=true` ⟹ output_schema 必含 `findings`
  （装载期 spot-check 拒载）；每条 finding=claim+evidence[]+confidence；**`resolved=true`
  只能由后端知识回源指纹校验置位**（ADR-0029），前端绝不从 LLM 自报推断；未核依据全链
  amber；`refusals` 非空=正常 completed 走人签（诚实拒答是履约）。
- **前端投影**（findings 忠实计数，缺项不编造）：
  - TaskDetail 依据段（TaskDetail.vue:194-205，签发卡上方强制挂载）：零依据 amber 警示
    「本次输出未提供依据，请谨慎签发」（**不阻塞人签**——警示不越权）；密级遮蔽
    「依据清单〔按密级隐藏〕——原文未拉取，签发前请经授权渠道核对」。
  - GuidePage 方案卡 T5 依据摘要 chip（GuidePage.vue:298-315）：
    「依据 N 条（X 已核验 · Y 未核）· 置信度 Z（模型自评）」/「依据结构待核」/
    「依据清单〔按密级隐藏〕」；含未核整 chip amber 底纹。
  - DeliveryCard 依据区（DeliveryCard.vue:52-57）同款计数投影；WorkbenchSession 收纳行
    依据缩略（WorkbenchSession.vue:388-400）。
  - 水合与遮蔽：`stores/taskEvidence.js`——终态任务一次性拉取，分级产物不发起下载，
    遮蔽标记三处（chip/收纳行/依据段）同源。
  - 组件：`EvidenceList.vue`（逐条 finding）、`EvidenceTrace.vue`（依据来源链/知识引用链
    三节点 hairline 分区）。

### 1.4 密级面（classification / clearance）

- **运行时遮蔽**（ADR-0025，`api/classification_gate.py`）：任务执行期落库不可变
  `data_classification`，read 期只读该列不重派生；**唯一遮蔽 chokepoint**——所有返回任务
  派生数据的端点必过此门；内容承载键清单化（TOOL_RUN/MODEL_CALL/SAMPLE/EVENT/TASK_ROW）；
  NULL 兜底 fail-closed（有内容行或非空 error_message 即封，is/== 非 truthiness）。
- **创建时点准入**（ADR-0030 §3）：`clearance.max_data_classification` 缺省=internal
  （fail-closed 最严向后兼容）；`max(输入密级) ≤ 上限` 判定 is True，四路复用
  （create_task/batch/手建/未来 teams summon）；拒绝用中性文案（策略拒绝非报警红）。
- **前端**：密级 pill 退役收进 title（#34）——`agentTaxonomyTip`（GuidePage.vue:2726-2735）
  拼「领域 X · 密级 Y · 成熟度 Z · 发布状态」，**缺项不占位不编造**（fta 未声明密级则
  title 无密级段，MAP32 观察项 6 实证）。**边界如实标注**：退役只覆盖 GuidePage 成员行——
  AgentPortal 门户卡（`AgentPortal.vue:80`）与团队卡（`:144`）仍是可见密级 pill；
  任务级敏感声明不走 title 走形状：TaskDetail 整窗双线+「◆ 敏感数据任务…不外发」
  （`TaskDetail.vue:30-33`）、peek 同款短句（StatusCenter.vue:116-120，形状+字重零新色）；
  敏感行 a11y 焦点停点（clearanceOf(a)==='sensitive' ? tabindex=0，tamper `s1-a11y-cut` 咬合）。

### 1.5 诚实标注面（mock / 未验证 / 通识 / completed 中性）

- **mock 链**：tool.yaml `mock` 位 → `tools/registry.py:112` 每次调用落 `tool_runs.mock`
  → 四处投影同源：VerificationCard 工具行「N 次工具调用 · 含 M 次 mock〔未经真实核验〕」；
  WorkLog 逐工具 mock 徽（WorkLog.vue:48-65；聚合缺行时「mock 标注不可作数」如实亮 amber，
  绝不静默装「非 mock」）；TaskJourney 调用节点「含 N 次 mock」（`utils/taskJourney.js:89-95`）；
  Agent 选型面 ShellContextPanel amber pills「MOCK 工具 N」「工具真伪待核 N」
  （`ShellContextPanel.vue:134-135`）。
- **未核=amber 唯一语义**：信任色锁约定 amber 仅未核/待签（format.js:23-39 + 设计契约），
  任何情况不染绿。
- **通识第四姿态**（#33/#36/#42 后现状）：guide prompt 四选一（delegate/orchestrate/
  通识直答/refuse），通识直答正常中文**不带任何特殊标记**（prompt.md:74）；地板句从
  「每答复述」松弛为**只在批准/授权面常驻**（VerificationCard verify-honesty 行）——
  松弛的是频率，不是诚实纪律。
- **completed 恒中性**：`format.js:12-18` TASK_STATUS completed=info 不给 success 绿；
  `taskLampColor` completed=中性墨（format.js:33-39）——绿仅真实 REAL 结果，
  当前跑 mock 给绿即假 REAL。

### 1.6 审计链（事件 / audit.log / tamper / deploy gate）

- **任务事件**：docs/05「无事件=没发生」；review_requested/approved/rejected 事件类型齐备；
  前端事件时间轴人话标签 SSOT（format.js EVENT_TYPE_LABEL）。
- **audit.log**：`logging_setup.py:158` `audit_event`——字段白名单（任何 password/token/
  cookie 类一律 DROP，「绝不记 secret」由构造保证）；RotatingFileHandler 5MB×10 份；
  治理动作（promotion_attestation/sample_acknowledgement/签发）逐条留痕。
- **治理账表**：`promotions`（晋升审计）、`eval_runs`（评测证据链）、`eval_snapshots`
  （insert-once 不可变快照）、`samples`（acknowledged_by_username/at CAS-on-NULL）。
- **tamper 咬合**：`scripts/tamper_replay.sh`——21 处登记投毒在隔离 worktree 重放，
  咬合三条件（非零退出+精确预期 FAIL 行+到达 FAILED 汇总），baseline 先绿否则拒咬，
  replay 自身 fail-closed；治理面登记例：`b7-gate-cut`（密级门砍除必红）、
  `b8-withheld-cut`（依据遮蔽标记砍除必红）、`s1-a11y-cut`。
- **deploy gate**：`scripts/deploy_selfcheck.py`——attestation 代际标记校验
  （check_live_promotion_attestation）+ classification/created_by_username 同范式代际轴。

### 1.7 段语义与状态来找人（map #32 已验收承载面）

可信面的「浮现」大量寄生在这套已验收的承载面上（验收记录：MAP32 A1-A9/B1-B6/C1-C3 全绿）：

- **工作段**：`workSegments`（GuidePage.vue:2249-2263）三终点谓词（任务创建/Guide 拒绝/
  制度问答交付）；段头/中段默认折叠/段界锚（GuidePage.vue:32-40）；折叠保 DOM（hidden 非
  detached，A2 红线）。
- **状态来找人**：StatusDock 待签 pill「✍ 待你签发 N」+ title 徽章（B1）；StatusCenter
  inbox 三组（待签置顶/进行中零值不渲染/落定==API 真值，B2）；peek→批准（二次确认）→
  pill 回落（B3）；dock 多点采样计数一致（B6）。
- **IA 合并**：今日页/任务台同分组同计数同称呼（taskGroups+taskDisplayName SSOT，C1）；
  一级导航仅 对话/今日（C3）。

### 1.8 前端治理面（AgentPortal / GovernanceJourney）

- AgentPortal「Agent 能力与治理」：徽章行 title 悬浮（categoryTip/agentStatusTip/
  maturityTip，含 L0「勿依赖其结论」诚实提示，AgentPortal.vue:4-5）；「治理」入口按钮
  （AgentPortal.vue:125）→ 弹窗：maturity 阶梯（L0→L1 机器化把关，L2/L3 范围外如实标注，
  185-192）、**「成熟度字段待核，未默认回退为 L0」**（193-194，缺字段不假装 L0）、
  GovernanceJourney 旅程图、评测通过率趋势（evalTrend）、固化 case 计数、晋升块
  （「晋升 L1 需引用一次全绿评测」+ 人工确认 checkbox + 逐条拒绝原因，286-307）。
- GovernanceJourney（`GovernanceJourney.vue` + `utils/governanceJourney.js`）六步闭环：
  固化用例→评测调度→真实结果→人工确认→服务端准入门→晋升记录；头部声明
  「评测通过只是证据；人工确认、服务端准入和持久化晋升记录缺一不可。」；
  绿（tone-real）只在「评测结果全部通过 X/Y」严格全通过时出现；记名区分
  「认证会话记名」（teal）/「服务器 CLI 来源」/「身份来源待核」——签发者 provenance
  的 UI 投影。
- 「跑评测」按钮 in-flight 防重复（tamper `portal-dup-enqueue` 咬合登记）。

### 1.9 信任色锁五槽（横切红线）

五槽 SSOT：`format.js:23-39` 注释 + `docs/design/AGENT-TEAM-B7-DESIGN.md:21`——
clay=正在发生（唯一活性色）· amber=未核/待你签发 · teal=人已签发 · 玫红=真失败（只染动词）·
绿=仅 REAL 核验；completed 一律中性墨。Agent 分类色标刻意避开五槽弧段（format.js:67-78）。
暗色适配已过 AA（BEAUTIFY 记录）。**五槽不增不改是 map #46 继承红线。**

---

## 二、浮现时机矩阵（用户路径 × 可信面）

按用户路径分阶段盘点「何时看到什么可信面」。形态三档：**前置**（不请自来，在可见面）/
**按需**（默认折叠或 hover，用户主动触发）/ **后台**（机制在场但用户不可见）。
实测证据锚：map #32 终点验收（B1-B6/D2 等）；本表以源码静态对账为主。

| 阶段 | 用户动作 | 浮现的可信面 | 形态 | 实现锚点 |
|---|---|---|---|---|
| ① 首轮/空态 | 登录后进对话 | 无可信面前置（WelcomeGate/Onboarding 无行话）；密级/成熟度/分类学**全部收在 hover title 或治理弹窗** | 按需/后台 | `GuidePage.vue:2726-2735`（title 缺项不占位）；`AgentPortal.vue:125` |
| ② 意图→方案卡 | 输入自然语言/附件，系统出方案 | 方案卡人话摘要；**路由依据与边界=route-disclosure 默认折叠**（含 roster 明细/成员状态灯/T5 依据 chip/材料忽略披露）；可见面仅编队总览行 | 按需（折叠 details） | `GuidePage.vue:192-195`（summary「查看路由依据与边界」）；可见面 `:175-190` |
| ③ 开工确认 | 点「按方案开工」 | **人门 1**：开工确认按钮本身（ADR-0033 三道人门之一）；代际钉扎/幂等 operation_id 后台 | 前置（按钮）+ 后台 | ADR-0033「代际钉扎、原子创建与恢复」节 |
| ④ 执行中 | 等任务跑 | 编队行状态词/秒表（clay 工作态）；成员 amber「审阅签发 →」在成员进 waiting_review 时出现；附件密级判定后台 | 前置（状态）+ 后台（密级） | `GuidePage.vue:253-269`；`classification_gate.py` |
| ⑤ 进 waiting_review | 任务待人签 | **状态来找人最强触发**：StatusDock amber pill「✍ 待你签发 N」+ 浏览器 title 徽章「(N 待签)」+ 翻转回声 toast；inbox 待签组置顶；今日页「待你签发」版块 | **前置**（不请自来） | `StatusDock.vue:5-7,46,87-107`；`titleBadge.js:11`；`StatusCenter.vue:34-54`；`TodayPage.vue:42-78` |
| ⑥ 签发面（peek 速览） | 点 dock→inbox 待签行、或 GuidePage「审阅签发 →」进 peek（dock toast/今日页待签卡走完整页⑦） | 内联签发卡（背书句/签发人记名/授权链/二次确认 teal/先看后签禁门）；产物截断披露；敏感声明；TaskJourney「含 N 次 mock」；**缺 VerificationCard——地板句与核验三面不在此面**（见空白 W1） | 前置（进 peek 即见） | `StatusCenter.vue:199-213`；缺卡见 `:100-233`；入口分路 `StatusDock.vue:87-105`、`TodayPage.vue:454-456` |
| ⑦ 签发面（完整页） | /tasks/:id | 固定顺序：产物段（「放行前请先审阅」）→ **VerificationCard 核验三面+诚实地板句** → 依据段（findings 计数/零依据警示/密级遮蔽）→ 签发卡（同 peek 要素）→ 知识引用链 | 前置（页面本体） | `TaskDetail.vue:124-253`；`VerificationCard.vue:70-72` |
| ⑧ 批准/驳回后 | 确认签发 | teal 人签 toast（两口径见 W4）+ burstSigned 迸发；signoffText「✓ 由 X 批准放行」；completed 灯恒中性；驳回=review_rejected→failed 红 | 前置 | `format.js:238-239`；`format.js:12-18,33-39` |
| ⑨ 敏感材料命中 | 上传敏感附件/任务涉敏 | 创建时点 clearance 门（中性拒绝文案）；密级 title（hover）；peek/TaskDetail 敏感声明「◆ 敏感数据任务…」；依据〔按密级隐藏〕遮蔽行；敏感行键盘停点 | 后台（门）+ 按需（title）+ 前置（声明/遮蔽行） | ADR-0030 §3；`StatusCenter.vue:116-120`；`TaskDetail.vue:30-33`；`taskEvidence.js:39-41` |
| ⑩ 拒答（refuse） | 系统接不住 | refuse 卡「显式拒绝/这个需求，平台暂时接不住」+reason+「接不住 ≠ 不重要」登记指引；amber 非红；会话标题「（未接住）」 | 前置 | `GuidePage.vue:92-132`；`conversationTitles.js:45` |
| ⑪ 通识问答 | 非工程问题 | 第四姿态直答**零标注**（#36 后对话面无地板句残留）；仅后端契约锚 + VerificationCard 地板行 | 后台（纪律在 prompt/契约层） | `agents/guide_agent/prompt.md:74`；`test_guide_auto_routing_contract.py:1235` |
| ⑫ 治理动作 | AgentPortal 点「治理」 | 治理弹窗：maturity 阶梯（L2/L3 范围外如实标注/「成熟度字段待核，未默认回退为 L0」）、GovernanceJourney 六步、eval 趋势（严格全通过才绿）、晋升块（人工确认+逐条拒绝）；「跑评测」防重复 | 按需（按钮触发） | `AgentPortal.vue:170-307`；`GovernanceJourney.vue:7` |
| ⑬ 治理账露出 | 今日页「Agent 动态」 | 晋升记录「X 晋升 L0 · 原型 → L1 · 试用 · 签发人 Y」 | 前置（轻量） | `TodayPage.vue:151-160` |
| ⑭ Agent 选型面 | 协作/编队选 Agent | ShellContextPanel mock pills「MOCK 工具 N」「工具真伪待核 N」（amber） | 前置（选型上下文内） | `ShellContextPanel.vue:134-135` |

### 浮现空白与不一致观察（触发面设计的直接输入）

- **W1（最重）：StatusCenter peek 签发路径缺 VerificationCard 与地板句。** peek 内联签发卡
  是完整人签路径（背书句/授权链/二次确认齐备），但模板无 VerificationCard
  （`StatusCenter.vue:100-233`）。走 peek 的入口=StatusCenter inbox 待签行与
  GuidePage「审阅签发 →」CTA；**其余签发入口走完整页（有 VerificationCard）**——
  dock 本体点击开 inbox（`StatusDock.vue:4-5`）、dock 回声 toast 与今日页待签卡
  直进 `/tasks/:id`（`StatusDock.vue:87-105`、`TodayPage.vue:454-456`）。
  即：#36 归位的诚实地板句与核验三面（工具 mock 计数/签发口播三态）在 peek 这条
  签发面上缺席，「诚实标记归位批准/授权面」未覆盖全部签发入口。（无使用频次埋点，
  「peek 与完整页哪条更高频」不作断言。）
- **W2：依据面对话路径默认不可见。** T5 chip/拒答拍/withheld 标记全收在 route-disclosure
  折叠 details 内；用户不点「查看路由依据与边界」则全程零依据信号——这正是「隐藏」的
  现状极端形态：隐藏=不可见，需要触发规则让它在工程语境上浮（§三 R-C）。
- **W3：failed 任务无依据面。** `ensureTaskEvidence` 只对 completed/waiting_review 水合
  （`taskEvidence.js:20`）——失败任务即使有 findings 产物也不出 chip/缩略行。口径一致
  但值得知晓：失败面靠事件时间轴与 WorkLog 承载诚实，不靠依据面。
- **W4：批准成功 toast 两口径。** TaskDetail「已批准放行」vs StatusCenter
  「已由当前登录工程师批准放行」（`StatusCenter.vue:635`）——W7 统一了按钮措辞，toast 未统一。
- **W5：VerificationCard 渲染窗含 failed。** 地板句「工程结论以…人签为准」出现在失败任务
  报告面，与 #36「只在批准/授权面」表述有边缘出入（组件注释口径=成果报告自证层，
  `VerificationCard.vue:1-8`；可留可收，见 §五裁决点）。
- **W6：密级 pill 收 title 非全站。** #34 退役只覆盖 GuidePage 成员行；AgentPortal 门户卡
  （`AgentPortal.vue:80`）与团队卡（`:144`）仍是可见 pill。设计「密级面隐藏」时须按面分别
  对账，不可当作全站统一现状。
- **W7：WorkbenchSession 依据缩略文案拼接无分隔空格**（「依据结构待核·另有密级隐藏项」），
  与其他面括号语法不同款（`WorkbenchSession.vue:396-401`）。
- **W8：通识回答零标注是 #36 的达成态而非缺陷**，但它意味着「通识→工程」语境转换点
  没有任何 UI 锚——触发规则若不做 R-C（§三），用户从闲聊切到工程判断时可信面不会自动来。

---

## 三、「隐藏但不缺席」触发面候选规则

> 纪律：本节只给**候选规则集**——每条给信号源、浮现面、现状差距与风险；**定稿留 owner 裁**。
> 红线预设：任何触发规则不得削弱宪法诚实纪律（mock/未核/人签地板永远在，属「地板」非「触发」）；
> 信任色锁五槽不增不改；completed 恒中性；零新依赖。

**设计原则（候选）**：可信面分两层——**地板层**（永远在场，不设触发：mock 披露、未核 amber、
人签面、completed 中性、密级门）与**浮现层**（默认隐藏、信号触发上浮：依据卡、路由依据、
治理面、诚实地板句）。「隐藏但不缺席」要设计的是浮现层的触发语法。

### 候选信号与规则

- **R-A 状态驱动（已实现的隐式规则，建议显式化为设计公理）**：
  `waiting_review` 是今日最强触发——pill/inbox/签发面全套上浮（§二⑤⑥⑦）。
  候选规则措辞：*任务进入人签态 ⟹ 可信面全量上浮并主动来找人*。现状已达成，
  触发面设计应把它从「实现事实」追认为「第一规则」。
- **R-B 任务型路由（路由结果即语境信号）**：guide 分流裁决
  （delegate/orchestrate ⟹ 工程语境；通识直答 ⟹ 通用语境；refuse ⟹ 边界语境）。
  候选规则：*路由进工程通道（产生方案卡/任务）⟹ 该会话段进入「工程语境」，
  方案卡起依据 chip 从披露内提升为可见面一行计数；通识直答段保持零标注*。
  信号源现成（ConversationService 路由结论），无需新分类器。**与 #42 共用同一信号**：
  「重新解释本身就是信号」「累积输出判定」的裁决产物可直接复用为语境轴。
- **R-C 工程判断语境（对话内渐进触发，针对 W2/W8）**：同一会话内从通识转入
  具体工程对象（型号/参数/合格性/数值结论）时。候选规则：*对话内出现工程判断
  语境信号（附件入场/方案卡生成/用户追问落到具体工程对象）⟹ 依据面与诚实标注
  在该段上浮*。风险：**语境判定本身不能交给 LLM 自报**（宪法：LLM 不做硬规则判定）——
  建议只用确定性信号（路由结论、附件、任务存在性、evidence_policy.required 命中），
  不用模型自评。这是与 #47 接缝最紧的一条（见下）。
- **R-D 人签节点前置（现状，建议补 W1）**：批准/授权动作前，诚实地板句与核验三面
  必须在场。候选规则：*一切签发入口（含 peek）⟹ VerificationCard 或等价诚实块同页
  在场*。现状：完整页达成、**peek 缺（W1）**——补法是组件复用，不是新规则。
- **R-E 密级命中（现状，部分前置）**：sensitive 材料/clearance 拦截 ⟹ 密级声明、
  遮蔽行、键盘停点上浮。现状已达成（§二⑨），但「密级 title」是 hover 按需——
  候选开放问题：密级命中是否应在对话可见面给一次性中性提示（非 pill 回归）？留 owner 裁。
- **R-F 治理事件（轻量前置已存在，可保持）**：晋升完成/评测全绿/attestation 置红 ⟹
  今日页/健康面露出。候选规则：*治理事件只在治理语境面（今日页动态、AgentPortal、
  deploy gate）露出，不进工程师对话主径*——保持「隐藏」基调。
- **R-G 地板层永不触发（负规则，防过正）**：mock=true、未核 amber、拒答 amber、
  completed 中性、人签地板——**不设触发、不可被任何「简洁模式」关掉**。
  候选规则：*任何通用性/简洁性重构不得把地板层改成按需披露*（宪法铁律五/六的 UI 投影）。

### 与 #47（行话审计）的接缝

- 分工：#47 管「通用面零行话摩擦」（首轮/词汇/通识/通用任务边界）；本票管「可信面
  何时上浮」。**接缝点=浮现面的文案层**：一旦 R-B/R-C 触发依据卡上浮，「依据 N 条
  （X 已核验 · Y 未核）」「waiting_review」「成熟度 L0」这类词是否算行话、要不要
  人话壳，需要 #47 的词汇审计结论作输入。
- 建议（留 owner 裁）：触发规则的**信号层**两票共用（路由结论/任务状态/密级命中），
  **文案层**等 #47 定稿后再收口——避免两票各自发明一套「工程语境」判定。
- 时序建议：批 0 两报告齐了后，由 owner 裁「触发-浮现规则」定稿（map #46 fog 项之一），
  再立施工票。

---

## 四、与 #1 / #3 的挂接点（为后续立项备料）

### 4.1 子项状态总账（对账日 2026-08-05，基线 39738a8）

| 票 | 内容 | 状态 | 对账结论 |
|---|---|---|---|
| #1 | 可信内核硬化总票 | OPEN | 子项 T1/T2/T4 已 CLOSED；T3=#3、T5=#6 仍 OPEN |
| #2 (T1) | 异步评测队列+配额 | CLOSED | 已实现（§1.1）；同步路径保留作 CLI/测试便捷（`eval_runner.py:449-499`，配额语义=worker 并发上限非全局硬闸，已声明） |
| #5 (T2) | 不可变快照执行+句柄 | CLOSED | 已实现（§1.1）；**已知边界**：快照不冻结工具经 env 读的外部活态（`freeze_eval_snapshot` docstring 明示，V0.2 槽位） |
| #4 (T4) | sample 级认可 | CLOSED | 已实现（§1.1）；draft 不自动转 approved（ADR-0018 D7 假绿防线） |
| #3 (T3) | 启动 attestation | **OPEN，代码已全量落地** | 五条验收标准逐条有实现+测试（§1.1 T3 专项对账）；**缺的是票的关闭留痕**——建议 owner 确认后关闭或补一轮验收记录 |
| #6 (T5) | verify_all.ps1 Windows parity | OPEN | 未做；#1 总票残留的唯一实质施工项 |

### 4.2 挂接点（map #46 后续立项的接口面）

1. **「隐藏面」叙事可直接引用 #1 已闭环机制**：异步队列/快照/attestation/sample 认可
   四件已是 main 的事实，可信内核「背后有真东西」不是承诺而是存量——map #46 的品牌面
   可以放心地说「工程语境下可信面在场」，因为机制层已立。
2. **T3 票处置是零成本挂接**：代码已落地，关闭 #3 只需 owner 确认 + 留痕（或在
   #1 总票验收时一并关闭）。不处理则「OPEN 票 vs 已实现代码」的 drift 会持续误导
   后续盘点（本票即为证：盘点第一问就是「#3 到底做没做」）。
3. **T5（#6）与部署线挂接**：Windows parity 属 M11/内网部署线，不影响 map #46 体验面，
   但 #1 总票关闭依赖它——建议 #1 的关闭裁决与 T5 排期解耦（子票已单列）。
4. **eval 快照外部活态边界 → V0.2 provenance 票**：`freeze_eval_snapshot` 已声明不冻结
   工具外部活态（如 cfd_evaluate 读 `$FLAI_CFD_CASE_DIR`）；完整 tool/model/scope
   provenance 是 V0.2 槽位（#8 已 CLOSED，记录同源发现）——后续硬化立项应显式继承。
5. **E3 门禁（NEXT-STEPS §4.4）**：eval case `classification: e0-e3` 标签与 runner 内
   环境分级门禁未实施（E3 在外网须输出 SKIPPED-classified 绝不静默当通过）——属
   「可信内核硬化」天然续项，与 #47 的「非航空任务边界」也有联动（E3 多对应内网
   涉密语料）。
6. **触发-浮现规则定稿 → 施工票**：本报告 §三候选规则待 owner 裁定稿后立项；
   施工面预估主要在前端（chip 提升/语境轴/VerificationCard 复用进 peek），后端信号
   （路由结论/任务状态）现成，零新依赖可满足。
7. **interactive 评测与 L2+ 晋升**属已声明人工域/V0.2（ADR-0018 已声明限制），
   不应进入 map #46 路线——本盘点确认其限制声明仍在文档与代码注释中如实标注。

---

## 五、遗留问题与给 owner 的裁决点

1. **#3 票处置**：代码已实现并有测试，票仍 OPEN——关闭 or 补验收留痕？（本票不代办）
2. **W1（peek 缺 VerificationCard/地板句）**：是否立小批施工票把 VerificationCard
   （或等价诚实块）复用进 StatusCenter peek 签发面？属「诚实标记归位批准/授权面」的
   入口补齐（完整页已有，peek 缺），建议优先。
3. **触发-浮现规则定稿**：§三候选集（R-A…R-G）哪些成立、R-C 的信号边界
   （只用确定性信号？）、R-E 的密级可见面提示做不做——全部留 owner 裁。
4. **W5（VerificationCard 渲染窗含 failed）**：地板句在失败报告面的去留
   （维持「成果自证层」口径 or 收窄到签发相关态）。
5. **W4（批准 toast 两口径）**：统一到哪个措辞（均不涉纪律，纯一致性）。
6. **与 #47 的文案层收口时序**：触发面施工是否等 #47 词汇审计定稿（建议：等）。
7. **#1 总票关闭路径**：T5 排期解耦后，#1 是否可在 T3 留痕补齐后先行验收关闭。

## 附：盘点方法与证据边界

- 静态盘点命令面：`git log`（governance 子系统提交史）、`gh issue view/list`、
  全文 grep（可信面组件/行话/色锁）、逐文件 read（governance 五模块/statemachine/
  classification_gate/bootstrap/VerificationCard/format.js/tamper_replay/治理 ADR）。
- 前端浮现面另经一路独立只读盘点交叉核对（explore 子代理，盘点输出未入库，
  关键结论已并入本报告 §二/§三并逐条复核源码）。
- 未起栈实测：浮现时机表的「前置/按需」判定基于源码静态对账 + map #32 验收记录
  （B1-B6/D2 实测绿）；W1 的 peek 缺卡判定为模板级静态事实（`StatusCenter.vue:100-233`
  无 VerificationCard import/挂载），如需截图级证据可在后续施工票补。
- 本报告零产品代码改动；引用行号基于 39738a8，后续 main 前进可能漂移。

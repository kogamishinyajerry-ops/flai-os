# ADR-0018：M10 治理闭环——样本→评测→晋升（Eval Runner / 样本固化 / L0→L1 晋升门）

- 状态：已接受·R1（owner 2026-07-11 拍板方向；loop-auditor 设计审判 **BLOCK**，
  D1-D6/D8 grounded 复核属实全采纳，D7 FLAG 采纳 draft-curation 方案——主控裁决，
  属 fail-safe 膨胀方向，收尾报告供 owner 复核；本文为修复后 R1 版）
- 依据：任务书 §4.7「每个 Agent 必须有评测集…必须能跑回归测试」/ §11.4 V0.3「输入输出样本库完善」；docs/02 §L0-L3 准入条件表；docs/07 Eval 标准（三类 eval / 失败沉淀纪律 / 违规判定）。

## 背景

三段线各自存在但互不连通：

1. **样本线（全通）**：runtime 成功/失败双路 `record_sample` → `samples` 表
   （`validation_status` / `accepted_by_engineer`）→ 人工审核 approve/reject 回填
   `accepted_by_engineer`（tasks.py）→ `GET /api/tasks/{id}/samples`。
2. **评测线（半通）**：docs/07 标准成文；registry `_REQUIRED_DIRS` 强制
   `agents/<id>/eval_cases/` **目录存在**（`_load_one` 只查 `.is_dir()`，不查非空
   ——这正是晋升门条件必须门内自判、不依赖 registry 上游耦合的原因之一）；
   但**平台没有任何组件能执行 eval_cases**——只有 performance_disk 的
   case_001.json 被 pytest（test_performance_disk_e2e.py）借用为期望口径。
3. **晋升线（悬空）**：maturity L0-L3 在契约/DB/API 投影/前端，docs/02 准入条件表成文，
   但无任何机制评审、记录或执行晋升——手改 yaml 字段即可"晋升"，零证据要求。

`backend/app/governance/` 自 M0 起即为空槽位，本 ADR 落此处。

## 决策

### 1. Eval Runner（backend/app/governance/eval_runner.py）

- **执行路径复用**：每个 case 经真实 `runtime.execute` 全链（输入校验→工具→事件→
  状态机）。绝不为 eval 开旁路执行链——旁路评测的是旁路，不是生产行为
  （valid-but-wrong oracle 的第一来源）。
- **worker 隔离（结构性消除双跑竞态）**：`tasks` 表加列 `origin TEXT NOT NULL
  DEFAULT 'user'`（`'user'|'eval'`，db.py 既有列探测迁移模式）。
  `claim_next_queued` 只认 `origin='user'`；eval 任务由 runner 自己用同款原子
  claim（`UPDATE … WHERE id=? AND status='queued'`）驱动。两个执行方各自的候选集
  不相交，竞态在结构上不存在，而非靠时序侥幸。
- **不落样本**：runtime 落样处加 `origin` gate（`is True` 风格显式判定）——eval 输入
  本来就是评测集，回灌样本库=循环喂养（评测数据冒充生产数据资产）。
- **任务列表默认视图**：`list_tasks` 加 `origin` 过滤参数，前端任务台默认
  `origin=user`。eval 任务可查（诚实可追溯）但不混入工程师工作流。
- **判定：机器可判断言词汇表（checks 块）**。现有六个 case_001.json 的 `expected`
  键各自为政（`total_cases`/`greeting_contains`/`draft_contains_watermark`…），是给
  人和手写 pytest 看的口径，通用 runner 不可解释。为每个 case **新增 `checks` 数组**
  （additive——`expected` 一字不动，test_performance_disk_e2e.py 的消费不破坏）：
  - `{"kind": "status_is", "value": "<终态>"}`——**waiting_review 是合法期望终态**：
    信任门行为本身是被评测对象（fta/knowledge_qa 的 case 断言"必须停在人工审核"），
    绝不为 eval 绕过审核门。
  - `{"kind": "artifact_exists", "file": "<产物文件名>"}`
  - `{"kind": "artifact_contains", "file": "...", "value": "<子串>"}`（水印类断言）
  - `{"kind": "output_field", "file": "<JSON 产物名>", "path": "a.b.c", "op":
    "eq|contains|exists|gte|lte", "value": ...}`（对**具名 JSON 产物**按点路径
    取值——任务行不存 result JSON，产物文件是唯一持久输出载体）
- **fail-closed 于不可判**：case 无 `checks` 或 agent 为 interactive 型 → 该 case 记
  `skipped`（附原因），**绝不计入 passed**。eval run 汇总含
  `total/passed/failed/skipped`；「全绿」定义 = `total > 0 且 failed == 0 且
  skipped == 0`（is-True 链），有 skipped 的 run 不构成晋升证据。
- **fail-closed 于配置错误（审计 D3）**：某条 check 的 `kind` 不在词汇表内、或该
  kind 的必填字段缺失/类型不对 → 该 case 记 **`failed`**（不是 skipped、更不是
  静默忽略）——坏掉的断言配置绝不能空洞通过。
- **curation 双态（审计 D7 裁决）**：case json 可带 `curation: "draft"|"approved"`，
  缺省视为 `approved`（既有手写 case 是开发者定的口径）。**draft case 不执行、
  不计入 total/passed/failed/skipped**，在 run 报告中单列 `draft_cases` 清单——
  固化通道生成的 case 一律 draft（见 §2），既不让未经策展的断言充当回归金标准，
  也不让"固化了样本"反而通过 skipped 阻断晋升（激励结构：固化无惩罚，策展后
  才有效力）。curation 转正 = Eval 维护者手工把字段改 `approved`（git 可追溯），
  V0.1 无 curation API。
- **落库**：`eval_runs` 表（id/agent_id/agent_version/triggered_by/started_at/
  finished_at/status(running|completed|error)/total/passed/failed/skipped/
  case_results_json/**eval_cases_digest**）。case_results 含每 case 的 task_id
  （证据可回溯到真实任务与事件时间轴）。`eval_cases_digest`（审计 D2）= 本次运行
  加载的全部 **approved** case 文件内容按文件名排序拼接后的 sha256——晋升时比对
  现存目录重算值，堵死"同版本号下改软/删除 checks 后拿旧全绿证据晋升"的博弈面。
- **API**：`POST /api/agents/{id}/eval-runs`（V0.1 同步执行，case 数小；异步队列为
  已声明限制）；`GET /api/agents/{id}/eval-runs`。
- **input_files**：case json 的 `input_files` 相对 eval_cases/ 目录，runner 经与上传
  同一文件登记路径注册后挂 `input_file_ids`。
- **dogfooding（D1 连带）**：本批为 hello_agent 补齐最小合格评测集
  （case_001 正常路 + case_002 缺失字段→failed + case_003 非法类型→failed，
  全部带 checks），作为"满足晋升条件1"的真实样例与 e2e 晋升成功路径的载体；
  其余 agent 的 case 补齐随各自维护者节奏，不在本批强推。

### 2. 样本固化通道（sample → eval case）

- `POST /api/agents/{agent_id}/eval-cases`，body `{sample_id, slug?}`。
- **前置（is True 判定）**：`sample.accepted_by_engineer == 1`。V0.1 只固化正例；
  失败样本反例固化递延 V0.2——反例的"期望怎么失败"若机器自动生成（如把当时
  error_message 固化为断言），有把 bug 固化成规范的风险，需 Eval 维护者人工定口径
  （docs/07 §4 本就写明"筛选"是人的动作）。
- 生成 `agents/<id>/eval_cases/case_NNN_from_sample.json`：inputs=样本输入原文、
  checks=`status_is completed` + 原任务真实产物的 `artifact_exists`（不自动编造
  字段级 eq 金标准——样本输出原文放 `sample_output` 供策展者参考补强）、
  `provenance: {sample_id, task_id, fixed_by, fixed_at}`、**`curation: "draft"`**
  （审计 D7：工程师 approve 的语义是"放行交付"，不是"逐字段核对为精确正确"——
  自动生成的断言必须经 Eval 维护者策展转 `approved` 后才进入正式评测集，与反例
  通道"需人工定口径"的原则对齐）。
- **幂等**：同 sample_id 已固化 → 409 并返回既有 case 文件名（provenance 对账）。
- 形态跟随现状（case_NNN.json 平铺文件），与 docs/07 §3 目录式组织的分叉如实记录，
  本批不重组目录。

### 3. L0→L1 晋升门（backend/app/governance/promotion.py）

- `POST /api/agents/{agent_id}/promote`，body
  `{to_maturity: "L1", eval_run_id, confirmations: {exception_paths_handled: true}}`。
  `confirmed_by` 与 signer 来源由服务端认证上下文派生；客户端携带任何 signer
  字段均 422（来源与迁移契约见 ADR-0019 R2）。
- **docs/02 L1 四条准入的判定分解（机器判/人工确认显式分离，不冒充）**：
  1. **最小评测覆盖（审计 D1 增强）**：approved case 总数 `>= 3` **且**至少 1 个
     approved case 的 checks 含 `status_is: "failed"`（失败路径必须真被评测——
     全是 happy-path 的"全绿"不构成回归能力证明）。docs/07 §3 八类全覆盖校验
     不在本批（已声明限制）；
  2. **eval 证据**：`eval_run_id` 存在、属于该 agent、`agent_version == 当前注册版本`
     （防拿旧版证据晋升新版）、全绿（`total>0 且 failed==0 且 skipped==0`）、
     **且 `eval_cases_digest` 与晋升时刻现存 approved case 内容重算值一致**
     （审计 D2：内容变了=证据过期拒绝，无论版本号动没动）；
  3. changelog.md 存在且**非空**（空文件同缺失，一律拒）；
  4. 反馈入口=平台级 `POST /api/feedback` 提供，晋升记录如实标注"平台级提供"
     而非 per-agent 验证；
  5. "对已知异常路径有处理"机器难判 → `confirmations.exception_paths_handled is True`
     + 受支持的 signer provenance 记名，**缺失/false/非 bool 或来源复核失败一律拒**
     （fail-closed 于无法验证）。
- 全部通过 → `agents/<id>/agent.yaml` 的 `maturity:` 行**行级手术替换**（不做 yaml
  round-trip，byte 级保持其余内容）→ registry 重扫 → `promotions` 表落记录
  （agent_id/agent_version/from/to/eval_run_id/confirmations_json/confirmed_by/
  signer_source/signer_user_id/signer_username/signer_session_hash/created_at）。
- 任何一条不过 → 422 + 逐条判定结果（工程师能看到差哪条）。
- **interactive 型（guide_agent）推论**：runner 不覆盖 → 永无全绿 run → 不可晋升。
  这是 fail-closed 的正确行为而非缺陷：会话评测属 docs/07 人工评审集范畴（V0.2）。
- 降级、L1→L2/L3（含专家签字人工域）：范围外。

### 4. 前端最小落点

- AgentPortal：agent 详情加治理区（maturity + 最近 eval run passed/total/时间 +
  「跑评测」+ 条件满足时「申请晋升 L1」对话框：人工确认项勾选 + 记名）。
- StatusCenter：approve 成功且有认可样本时给「固化为评测用例」入口。
- **不开新色**：eval 通过/失败用中性墨+文字与既有语义 token，色锁五槽不扩
  （扩锁权在 owner）。

## 后果

- 每次工程师审核从"放行动作"变为"数据资产定标动作"，样本库→评测集有了机器通道；
  maturity 从声明变为可审计事实（promotions 表 + eval_runs 证据链）。
- 已声明限制（审计必问三题之"没证什么"）：eval 同步执行无队列；反例固化 V0.2；
  interactive 评测 V0.2；L2+ 晋升人工域；`expected` 与 `checks` 双轨并存（旧口径
  给人看，新口径给机器跑）；**晋升条件1 只证"≥3 case 且含失败路径"这一最小覆盖，
  不证 docs/07 八类全覆盖**；**digest 只证 eval_cases 内容自评测以来未变，不证
  内容本身正确**（内容正确性锚在 curation 人工域）；draft→approved 无 API（手工
  改字段，git 追溯）；eval-origin 的 fta/knowledge_qa case 意图性永久停
  waiting_review，现无跨 origin 聚合端点故无污染，未来新增状态统计须记得
  origin 过滤（审计 D9 前瞻）。
- 异源审（Codex R0）后追加的边界声明：**磁盘直改 agent.yaml 的 maturity 不经
  五门**——agent.yaml 是包内 SSOT 且平台 V0.1 无鉴权（真鉴权递延 owner），能改
  yaml 的人同样能改门代码本身，该域防线=git 审查与部署包只读，不冒充运行时
  可防；**固化通道当前仅覆盖 requires_human_review 型 agent**（审核回填是唯一
  accepted 定标入口，sample 级认可 API 递延）；**digest 已绑定包核心文件
  （agent.yaml/prompt/workflow/双 schema）与 case 引用的输入文件实体；最终
  发布另以 `agent_package_snapshot.v1` 绑定完整 Agent Package 文件树**，tool/
  model/scope 等包外状态仍是 V0.2 槽位；**并发防线（晋升锁/eval single-
  flight/固化锁）为进程内**，多进程部署需外置锁；task.schema.json 的 origin
  演进与消费者同仓同步（循 ADR-0016 conversation_id 先例），外部消费者版本化
  留待 API 正式对外时处理。
- R2 终审后残余窗口（明文声明，防「代码注释声称已声明」与文档脱节）：
  ①**磁盘↔DB 崩溃窗口**——yaml/changelog 写入与 DB 事务提交之间进程崩溃，
  重启以 yaml SSOT 重新装配，但 promotions 审计记录可能缺失：发现 L1 而无
  对应 promotions 记录须人工核查，单机无 WAL 式提交日志架构下该窗口不可
  消除；②**包外状态不在快照内**——Agent Package 内全部常规文件已冻结，但
  tool/model/knowledge/environment 读取的外部状态仍按各自 provenance/gate
  管理，不得把包快照解读成整套运行环境镜像；③**快照字节当前仅驻进程内存**——
  audit 持久记录 contract/digest/file_count，Registry 与 Runtime 持有字节。
  若重启时活目录已从已签 A 变成 B，系统严格比对 digest 后拒载 B 并把健康轴
  置红，不会从审计摘要反向恢复 A；恢复 A 或对 B 重新评测晋升是人工部署动作。
- `agent_package_snapshot.v1` 发布不变量：影子 Registry 对完整包做两遍稳定
  捕获，拒绝 symlink、Windows reparse/junction、FIFO/device、大小写碰撞与
  撕裂读取；所有相对路径及 canonical manifest JSON 必须可严格编码为 UTF-8，
  非法包只进入 `registry.errors`，不得以裸编码异常打断其他包扫描。以
  4096 entries / 单文件 16 MiB / 总计 64 MiB / 深度 32 作为误放大包的
  fail-closed 资源边界；最终 coverage/eval/changelog 门只读该快照。
  promotion `checks_json.package_snapshot`、活 Registry `_entries`
  与 Job/Conversation Runtime 私有材化目录沿用同一个 snapshot 对象。
  活 `AgentRegistry.package_dir()` 仅保留为治理写回/运维定位的 authoring
  路径，执行路径不得调用；Conversation 注入的 `snapshot_view.package_dir()`
  是兼容既有 workflow 的冻结私有目录，不是活目录。`get()/list()` 每次返回
  snapshot 派生副本，外部不能修改已发布代际；`snapshot_view()` 一次钉住
  完整 Registry 代际，`adopt()` 单次替换 `_entries`，不再存在
  `get→package_snapshot/package_dir` 跨代拼接。每轮执行在开始时钉住一个
  代际，status/mode/clearance/schema/workflow 均以实际执行快照为准；之后的
  adopt 从下一轮生效。历史 promotion 若缺少 `package_snapshot`
  contract/digest/file_count，不具备证明当前完整包的能力，启动核对一律
  fail-closed 拒载；须对当前包重新评测并由人重新晋升，不做兼容性假放行。
  若 DB 中上次已投影的 L1 在重启扫描中因缺件、不安全文件或目录缺失而未进入
  Registry，启动核对仍必须生成 `missing-or-invalid-package-snapshot` 拒载记录
  并置红，不能因 `Registry.list()` 看不见它而假绿。
  每次 Job Runtime 的 `validation_started` 事件同时记录 contract+digest，
  使任务审计能反查实际执行代际。若任务已入队但执行时 Agent/快照缺失，必须
  在写固定系统失败诊断前用 CAS-on-NULL 落 `internal`；不得放宽
  classification gate 对 `NULL + error_message` 的 fail-closed 遮蔽规则。
- 测试红线（docs/07 §3 清单适用于治理组件自身；审计 D4/D5/D6 补齐负例）：
  - runner：正常路/case 失败如实计数/agent 不存在/eval_cases 空/checks 缺失即
    skipped/**未识别 kind 或必填字段缺失即 failed**/**draft case 不执行不计数**；
  - 隔离三 witness（D5，对应三条结构性承诺）：**`origin='eval'` 任务绝不被
    `claim_next_queued` 选中**；**collect_samples=true agent 的 eval-origin 执行后
    samples 表行数不变**；**`list_tasks` 无 origin 参数默认不返回 eval 任务**；
  - 固化：幂等/未认可拒绝/**生成物 curation 字段必为 draft**；
  - 晋升五条准入 AND 门逐条负例（D4）+ 不可变发布门：**eval_cases 不足 3 或无失败路径 case 拒**/
    无证据拒/证据不绿拒/版本不匹配拒/**digest 不一致拒**/**changelog 缺失拒 +
    空文件拒**/**promotions 记录含"平台级提供"字面（条件4 不冒充 per-agent）**/
    确认项三分裂（D6）：**缺失拒、`false` 拒、非 bool（字符串 `"true"`/整数 `1`）拒**。
  - 不可变包：**最终门禁后、审计 INSERT 前并发把活目录 A→B，晋升仍只执行 A；
    同进程 audit/Registry/Runtime digest 恒等；用 B 重启必须拒载并置红**；捕获层
    对 symlink/reparse、非普通文件、两遍读取间变化、跨 Windows 大小写碰撞及
    entry/单文件/总字节/深度资源上限逐项负测；surrogateescape 路径与 YAML
    lone-surrogate scalar 必须只拒载坏包、合法兄弟包照常发布和 DB 同步；
    **上次已发布 L1 的 workflow 缺失或改为 symlink 后重启，Registry 拒载且
    health 必须同步置红**。
  - e2e：m10_governance_acceptance 全链 + tamper 实证（cp 备份法）。

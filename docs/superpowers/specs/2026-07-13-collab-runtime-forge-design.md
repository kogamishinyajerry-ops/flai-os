# 协作运行时 Forge · 设计契约 v3（loop-auditor mode-A 审 + F3 owner 裁决后定稿）

- **状态**：设计审 **FLAG→全 P1 闭合→定稿进入实现**。v1 4 个 P1：F1/F2/F4 机制 P1（v2 闭合）+ F3 宪法解释（owner 裁"注册期不变量"，v3 落 §3.6+T8）。→ 实现 → Codex 异源审。**本文尚未落任何 backend/app 代码。**
- **地位**：封板双判据的**判据①内核改动期**。forge 不是 integration——**预期有内核 diff**（迁移+resolver+repos+api+create_task 端点），这正是"骨架尚未完成"的进度条。改完趋稳后判据①两发零 diff 验证弹（§八）才有意义。
- **分支**：`feat/collab-runtime`（worktree 隔离）。基线 main@7963b16。
- **审计存档**：loop-auditor mode-A 裁决 FLAG，grounded 到文件行；本 v2 逐条落其 P1 gate 清单。

## 一、未锻的肌肉（今天缺什么）

平台今天的"协作"止于两处、都靠**人肉接力**：M8 编排官（ADR-0016）推荐多 Agent 计划但人逐个建任务逐个签；CFD 两阶段（ADR-0026/0027）人手工建两任务、手工搬 sim_run_ref。缺的原语=**声明式任务依赖 + 确定性 artifact→input 管道**（B 输入来自 A 产物，A 完成后 B 自动就绪），且**每个 review-gated 环节仍有人签**。这是 Agent→Agent 编排的地基，最大未锻肌肉。

## 二、宪法约束（本 forge 必须逐条保住的红线）——脊梁节

**核心命题：协作运行时自动化的是「管道」（artifact→input），绝不是「判决」。**

1. **人是唯一签发者（精确条件句，F3 审后修正）**：下游等的是上游 `completed`。到达 completed **只有两条合法路径**（loop-auditor 穷举，均经 assert_transition）：
   - **P-B `waiting_review→completed`**（tasks.py:294）：**必经人工** `POST /tasks/{id}/review` approve。statemachine.py:39 焊死 waiting_review 只人工放行转出、禁任何自动化路径。**故 review-gated 上游未经人签绝不 completed、下游绝不就绪——红线由既有状态机结构承接，非新增承诺。**
   - **P-A `analyzing→completed`**（runtime.py:597）：仅当 agent `requires_human_review is False` 时走此路，**零人工**。
   - **边界（F3 owner 已裁，升级为机械保证）**：对 **review-gated** 上游"下游等 completed = 等人签"成立（P-B）。对**非 review-gated** 上游，owner 裁决=**注册期不变量**（§3.6）令其恒为 profile=none 确定性 Agent——故非-gated 自动链是**安全自动化**（无 LLM 判决），任何产 LLM 判决的 Agent 必 review-gated、必在链中断出人签点。**"LLM 判决永不无人签流经协作链"由 §3.6 机械保证，此句不再是条件声明。**
2. **Agent 绝不建任务**：任务图由**人**编写（人建每任务、人声明依赖边）。编排官只推荐边，人实例化。resolver 只排序执行，绝不创建任务。
3. **LLM 不进判决链**：resolver 纯确定性——只按声明绑定拷贝已注册产物引用，绝无 model_gateway 调用（哪个产物流向哪个输入由人写的绑定决定）。
4. **分级不可变 + 污点合成（ADR-0025 集成，F2 审后修正）**：**resolver 绝不写 `data_classification`**。它只把带文件级分级的上游产物引用管道进下游 `input_file_ids`；下游首次 execute 时既有 `_task_data_classification`（runtime.py:450-453 无条件调用，含 `_task_input_classification` 文件轴 runtime.py:229-245）**自动吃到**上游产物文件行的分级、天然合成。**杜绝 resolver 抢写 CAS-on-NULL 冻结列、挤掉下游自身知识/工具轴污点的欠分级泄漏（monitor-taint R1-B 换入口复现）。计算逻辑不在 resolver 复制第二份=真正单 chokepoint。**

## 三、最小设计（外科，尽量 additive）

### 3.1 数据模型（迁移 #9，幂等 ALTER）
`tasks` 加两列（可空，存量 NULL=无依赖行为不变）：`depends_on TEXT`（JSON array of task_id）、`input_binding TEXT`（JSON，见 3.3）。

### 3.2 无新状态（关键裁决，保十态不变量；OQ1 审后采纳）
依赖未满足的任务**滞留 `created`**，resolver 满足后走**既有** `created→queued`。零状态机改动、零 100 对矩阵改动、零 docs/05 改动。UI"等待前置 N"=派生显示（读 depends_on+上游 status 现算），非存储态。

### 3.3 确定性 resolver（新组件，JobRunner tick 内一趟）
每 tick 扫 `created` 且 depends_on 非空任务：
- **全部上游 `completed`** → 同一 `BEGIN IMMEDIATE` 写锁内原子两步：①按 input_binding 把上游 `output_file_ids` 拷入本任务 `input_file_ids`（只准引用**本任务 depends_on 集合内**上游的**已注册** output 文件，跨任务/任意路径拒）②`created→queued`。**不写 data_classification（见 §二.4）。**
- **任一上游 `failed`/`cancelled`** → 本任务 `created→cancelled`（**F1 审后修正：created→failed 非法，statemachine.py:31 created 出边仅 {queued,cancelled}**），复用既有 `task_cancelled` 事件（event.schema.json:49 enum 已含，零契约改动），payload 加 `{"reason":"upstream_failed","upstream_task_id":...}` 与人工取消可区分。**fail-closed 绝不执行。**
- **上游 `waiting_review`/进行中** → 保持 `created`，下 tick 再看。
- JobRunner claim 循环完全不动（只 claim queued）。

### 3.4 DAG 完整性（审后简化）
- depends_on **建时即冻结**（**scope fence：不支持创建后编辑依赖边**）+ 只能引用**已存在**任务 → 图按构造即 DAG（无法建回边指向未来任务），**无需运行时环检测**（loop-auditor：原环检测在此约束下是死代码）。允许 fan-in；扇出天然。
- 引用不存在的 task_id → 创建拒（fail-closed）。

### 3.5 create_task 端点改造（F4 审后新增，命门）
> loop-auditor P1：现 tasks.py:174 无条件 `set_task_status(...,"queued")`（P2-4 原子设计）——不改此处，带依赖任务创建即被自动入队，resolver 永远看不到 created 态，"滞留 created"整机制在实现层无法生效。
- `CreateTaskRequest`（tasks.py:26）新增 `depends_on: list[str] = Field(default_factory=list)` + `input_binding: dict | None = None`（`extra="forbid"` 下必须显式加字段而非放开）。
- `create_task()` tasks.py:174 的自动入队改**条件短路**：`if not body.depends_on: set_task_status(...,"queued")` else 停留 `created`；`task_created` 事件 payload 去掉硬编码 `"status_to":"queued"`、按实际初态填。
- 创建时校验：depends_on 每个 id 存在（否则 404/422）；input_binding 引用的 upstream 必在 depends_on 内。

### 3.6 判决⟹人签 注册期不变量（F3 owner 裁决=注册期不变量，审后新增）
> owner 宪法裁决（2026-07-13 AskUserQuestion）：非 review-gated 上游自动链的处置=注册期强制"判决型必 review-gated"，令非-gated 恒确定性、自动链安全。
- **不变量（真实 scan 后精化）**：Agent 注册（`runtime/registry.py._load_one`）时，若 `workflow.mode == "job"` **且** `model.profile != "none"`（作为 job 任务跑且调 LLM）则 `workflow.requires_human_review` 必须 `is True`（严格 is True，非 truthiness）；违反=**注册期 fail-closed 拒载**，绝不静默接受。落点=registry.py:107-119 P2-7 跨字段校验同款位置。
- **为何限 mode==job**：F3 只关乎 depends_on 链，而链只由 **job** 任务组成——**interactive Agent（编排官/导引）跑在 ConversationService 不进 JobRunner、且 create_task tasks.py:119 本就 409 拒 interactive，根本进不了链**。其宪法安全阀是 ADR-0012「绝不建任务、只推荐由人实例化」，正交于 requires_human_review。故 mode==job 精确覆盖"能入链"的全集。
- **精度**：判据用 `profile != none` 而非 category——精确捕获"是否调 LLM"（含 monitor_adapter_gen 这类 category=structured_gen 但 profile=reasoning 混合型）。
- **★真实 fleet scan 诚实上报（2026-07-13，非静默修）**：9 个 Agent 实测——4 个 profile=none 确定性非-gated（performance_disk/cfd_solve/control_logic/hello，合法非-gated）+ 4 个 LLM job 全 gated（knowledge_qa/fta/monitor_gen/cfd_evaluate）+ **guide_agent（interactive/reasoning/rhr=False）——mode==job 限定下豁免、合法**。**全 9 过精化不变量。** 附带纠 loop-auditor grounding 错：其"0 个 rhr:false"结论 grep 了不存在的 `backend/agents`（真实路径 `agents/`）得空误读；真实有 5 个 rhr=False，但均合法（4 确定性 + 1 交互式豁免）。

## 四、scope fence（本 forge 明确不做）
- 不做条件/分支工作流；不做上游 retry/重跑（另立）；不做 Agent/编排官自动建任务（红线永不做）；不做跨 conversation 依赖；resolver 不做任何 LLM 调用；**不支持创建后编辑 depends_on**（§3.4 依赖 DAG-by-construction）。
- **F3 边界声明（owner 已裁）**：非 review-gated 上游会被 resolver 纳入自动编排链；owner 裁决=注册期不变量（§3.6）保证非-gated 恒确定性、故自动链安全；判决型 Agent 必 review-gated、必断链出人签点。本 forge **新增** §3.6 注册期 gate 落此裁决。

## 五、Tamper witnesses（fail-closed 门，拆一层必红；审后强化）
- **T1 人签闸**：上游 waiting_review（未签）→ 下游永不 enqueue。拆=resolver 把 waiting_review 当就绪→下游跑→RED。（注：T1 测不出 F3 非-gated 缺口，F3 靠 §十 边界处置非 T1。）
- **T2 失败传播（F1 审后改写）**：上游 failed/cancelled → 下游 `created→cancelled(reason=upstream_failed)` 从不 running。拆=忽略上游失败→下游 enqueue 跑→RED。
- **T3 污点合成（F2 审后改写，咬合点从"分级计算"移到"绑定拷贝"）**：sensitive 上游 → resolver 拷贝产物引用入下游 input_file_ids → 下游执行期派生自动 sensitive → 产物下载 403。拆=断 output_file_ids→input_file_ids 拷贝→下游 input 空→执行期派生 internal→下载放行→RED。
- **T4 引用存在性（审后改写）**：depends_on 引用不存在 task_id → 创建拒。拆=去存在性校验→接受悬空依赖→RED。（原"环拒绝"因 §3.4 DAG-by-construction 成死代码，改测此。）
- **T5 resolver 确定性（审后强化）**：resolver 一次 tick 前后 `model_calls` 表行数不变（**行为级证据**，比静态 grep import 抗绕过——挡"resolver 调间接 import model_gateway 的 helper"）。拆=resolver 内插一次 gateway 调用→行数+1→RED。
- **T6 绑定收口（审后强化）**：绑定只能引用本任务 depends_on 声明的上游自己的 output_file_ids。拆=绑定引用非 depends_on 集合内任务的 output_file_id（越权盗用）或任意路径→必须拒→拆则 RED。
- **T7 滞留 created（F4 审后新增，把地基钉成可测）**：depends_on 非空任务 create 后立即查状态断言仍 `created`。拆=移除 create_task 条件短路→任务被自动 queued→RED。
- **T8 判决⟹人签不变量（F3 审后新增）**：profile≠none + requires_human_review:false 的 agent.yaml → registry scan 拒载。拆=移除 §3.6 不变量校验→该 agent 被接受→RED。

## 六、验收标准
- 迁移 #9 幂等（存量库实证）；**100 对状态矩阵字节不变**（证无新态）。
- E2E 主链：建 A(review-gated)→建 B depends_on A→B 滞 created 期间 A 历经 queued/running/waiting_review→人签 A→resolver 管道 A 产物入 B、B enqueue→B 跑→waiting_review→人签 B→completed。**断言 B 在 A 人签前从未 running**。
- E2E 失败链：A failed→B `cancelled(upstream_failed)` 从不 running。
- E2E 污点：sensitive A→B 执行期派生 sensitive→B 产物下载 403。
- **8 个 tamper 全 RED→GREEN 还原**（T1-T8）。
- verify_all 全绿 + 零回归。

## 七、审查计划
本 v2 = loop-auditor mode-A 后修订 → **owner 裁 F3** → 实现（worktree 隔离，显式路径 stage）→ Codex 异源治理审（**命中即审：授权/签发/分级边界**）→ 主控 tamper 自证（T1-T7）→ verify_all。

## 八、判据①连接（forge 之后的两发验证弹）
本 forge 本身有内核 diff（=判据①"内核改动期"，不计入零 diff 计数）。改完趋稳后打两发**多 Agent 工作流**（OQ4 采纳）、只加 agents/tools 包、零 backend/app diff——既验内核稳定又验协作原语够通用。弹①=FEA-solve→FEA-evaluate 两 Agent 链（用新依赖边）；弹②=另一域多 Agent。**loop-auditor 补充：两发的 Agent 必须都 review-gated（或显式记录其 requires_human_review 值），否则验证弹自身会成为 F3 缺口第一个现实触发者、污染"零 diff 验证"干净性。** 两发均零 diff→判据①收口→双判据齐→封板。

## 九、开放问题裁决（loop-auditor + owner）
- **OQ1**：滞留 created + 派生显示 → **采纳**（保十态不变量论证成立）。
- **OQ2**：默认全部上游 output + 可选 glob → **部分采纳（2026-07-14 增量2审 R4 P2 校正）**。**已交=任务级选择器 `from_tasks`**：非空=resolver 只从声明的上游拷 `output_file_ids` 入下游 input，其余上游仍参与依赖等待但产物不注入；空/null=默认拷全部上游 output。满足"选择性绑定、防越权拷入调用方显式排除产物（含 sensitive）"的核心意图，前提 T6 越权引用检查已落（`from_tasks ⊆ depends_on`，越权引用创建期 422）。**文件名级 glob（同一上游多产物中只绑定部分文件）未建，递延 retro 作可选增强**——契约（`task.schema.json` input_binding）与 `InputBinding`（Pydantic `extra="forbid"`）只暴露 `from_tasks`，故任何 glob/filename 型 selector 创建期即 422 拒（fail-closed，绝不静默接受未实现语义、绝不"设计承诺了但实现无声吞掉"）。原措辞"可选 glob → 采纳"过度承诺，此校正使设计⟷契约⟷实现三者一致。
- **OQ3**：上游失败下游处置 → **`created→cancelled`**（非终态 failed，因 failed 从 created 不可达；cancelled+payload 区分优于永滞 created 制造僵尸）。
- **OQ4**：判据①两发验证弹 → **多 Agent，且二者均 review-gated**。

## 十、F3 宪法解释（owner 已裁：注册期不变量）✅
**owner 裁决（2026-07-13 AskUserQuestion）= 选项① 注册期不变量。** 落点已入契约：
- §3.6 新增注册期 gate：`profile != none ⟹ requires_human_review is True`，违反 fail-closed 拒载。
- §五 T8 新增对应 tamper witness。
- §二.1 脊梁句 + §四 边界声明升级为机械保证（非条件声明）。
**设计全部 P1 闭合，FLAG 清零，进入实现。** 实现顺位：§3.6 注册期不变量（自足可即测）→ 迁移#9+create_task §3.5（地基）→ resolver §3.3（心脏）→ T1-T8 tamper → E2E 三链 → verify_all → Codex 异源审。

## 十一、信任模型设计级巡查收口（2026-07-14，R5 tripwire → loop-auditor + owner）
Codex 逐轮审 R0-R5 每轮出新 grounded 切面，证**点抓未收敛**——缺口是 3 个矩阵行（不变量 × 表面 × 数据世代）被 cell-by-cell 修。R5 触发 owner 预设 tripwire → 停 R6、转**设计级巡查**（loop-auditor 完整性审 + Claude grounded 复核），一次找全兄弟，按 owner 裁「K1+K2+R1，defer R2+R3」收口：

- **K1 签发维 provenance（keystone，已修双点）**：`status=='completed'` 只是时序代理，不证人签。legacy pre-§3.6（或版本翻转前 profile≠none+rhr:false 版本）任务可能已自动 completed、无人签=未签 LLM 判决。§3.6 只拒当前加载包、改不动历史行。→ 完成谓词换 `repos.task_output_is_signed_off`：**持久 review_approved 事件（人签见证）∨ 该任务锁定 agent_version 的历史 manifest profile∈{None,'none'}（确定性零-LLM）**，manifest 缺失/损坏 fail-closed。**resolver 生产侧（runner._resolve_one_candidate 未签→级联取消）+ 消费侧（runtime._open_input_files 未签→拒消费）双点同守**——legacy 任务 input_file_ids 已直含产物时绕 resolver、只撞消费侧。键于任务锁定版本正确处理版本翻转（不被"当前版本=none"反向欺骗）。
- **K2 消费侧 origin 隔离（keystone，已修）**：resolver（runner）与 create_task（tasks.py）都校上游 origin=='user'，独 `_open_input_files` 消费点漏 → legacy/直写任务 input_file_ids 已直含 eval 产物时消费侧开 eval 内容入 user 任务污染样本库。消费点补齐 origin 校验。
- **R1 resolver per-candidate 隔离（robustness，已修）**：resolver for-candidate 循环零 try/except → 单条畸形持久数据（input_binding.from_tasks 非 list / depends_on 标量 / output_file_ids 非 list / 畸形 agent_id）抛异常掀翻整趟 pass、后续合法候选**永久饿死**（毒丸滞留 created 每 tick 重命中）。→ per-candidate try/except，毒丸 quarantine（created→cancelled+诊断，事件 agent_id=None 免二次污染）而非中止全 pass。

**诚实递延内网后锻（owner 裁 defer + 显式标注，非静默）**：
- **R2 写边界零 schema 校验 + input_binding 契约松（object|null）**：task.schema.json 从不在 DB 写路径校验（仅 API Pydantic，直调 repos/legacy/迁移可绕）；input_binding 契约未钉 `from_tasks:array[string]`，故 `{"from_tasks":1}` 契约合法。**残差**：畸形持久 binding 可被写入——但 **R1 隔离使 resolver 对其鲁棒（quarantine 非 prevent），blast 已收敛**；收紧嵌套 schema/写边界校验属廉价后补，内网批做。
- **R3 逐边上游 get_task 全解码（perf）**：runner._resolve_one_candidate 逐边 `repos.get_task` 仍 `SELECT *`+解码 256KB inputs（R4-2 只投影了候选扫描，漏对称的上游查找）；fan-in 下 O(N×M)/tick，上游未完成时每 tick 重复。**残差**：部门级 fan-in 规模温和，且 K1 签发见证每上游 1-2 查询叠加于此路径——**内网真实负载画像后一并投影收口**（上游查找投影 id/status/origin/output_file_ids/agent_id/agent_version）。

**巡查未误杀确认（设计已正确覆盖）**：§3.6 `mode=='job'` 有 agent.schema mode required+enum 背书非欠覆盖；runtime 执行期 rhr 门 `is not False`、_NoModelGatewayContext 物理封 profile=none LLM、resolver origin backstop、apply_human_review 原子性（R4-1）已收口。

# 协作运行时 Forge · 设计契约 v2（loop-auditor mode-A 审后修订）

- **状态**：设计审 **FLAG→已修订**（v1 4 个 P1：F1/F2/F4 机制 P1 本 v2 已闭合；F3 宪法解释待 owner 裁，见 §十）。修订后待 owner 就 F3 裁决 → 实现 → Codex 异源审。**本文尚未落任何 backend/app 代码。**
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
   - **边界（诚实标注）**：对 **review-gated** 上游"下游等 completed = 等人签"成立；对 **非 review-gated** 上游**不成立**，链式会全自动。当前 fleet **0 个** `requires_human_review:false` Agent（机制休眠）。此边界的宪法处置见 §十（owner 待裁），**本 forge 不新增也不移除该既有机制，只诚实声明**。
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

## 四、scope fence（本 forge 明确不做）
- 不做条件/分支工作流；不做上游 retry/重跑（另立）；不做 Agent/编排官自动建任务（红线永不做）；不做跨 conversation 依赖；resolver 不做任何 LLM 调用；**不支持创建后编辑 depends_on**（§3.4 依赖 DAG-by-construction）。
- **F3 边界声明**：非 review-gated 上游会被 resolver 纳入自动编排链形成多跳零人工执行；本 forge 不新增约束禁止之（处置待 §十 owner 裁）。

## 五、Tamper witnesses（fail-closed 门，拆一层必红；审后强化）
- **T1 人签闸**：上游 waiting_review（未签）→ 下游永不 enqueue。拆=resolver 把 waiting_review 当就绪→下游跑→RED。（注：T1 测不出 F3 非-gated 缺口，F3 靠 §十 边界处置非 T1。）
- **T2 失败传播（F1 审后改写）**：上游 failed/cancelled → 下游 `created→cancelled(reason=upstream_failed)` 从不 running。拆=忽略上游失败→下游 enqueue 跑→RED。
- **T3 污点合成（F2 审后改写，咬合点从"分级计算"移到"绑定拷贝"）**：sensitive 上游 → resolver 拷贝产物引用入下游 input_file_ids → 下游执行期派生自动 sensitive → 产物下载 403。拆=断 output_file_ids→input_file_ids 拷贝→下游 input 空→执行期派生 internal→下载放行→RED。
- **T4 引用存在性（审后改写）**：depends_on 引用不存在 task_id → 创建拒。拆=去存在性校验→接受悬空依赖→RED。（原"环拒绝"因 §3.4 DAG-by-construction 成死代码，改测此。）
- **T5 resolver 确定性（审后强化）**：resolver 一次 tick 前后 `model_calls` 表行数不变（**行为级证据**，比静态 grep import 抗绕过——挡"resolver 调间接 import model_gateway 的 helper"）。拆=resolver 内插一次 gateway 调用→行数+1→RED。
- **T6 绑定收口（审后强化）**：绑定只能引用本任务 depends_on 声明的上游自己的 output_file_ids。拆=绑定引用非 depends_on 集合内任务的 output_file_id（越权盗用）或任意路径→必须拒→拆则 RED。
- **T7 滞留 created（F4 审后新增，把地基钉成可测）**：depends_on 非空任务 create 后立即查状态断言仍 `created`。拆=移除 create_task 条件短路→任务被自动 queued→RED。

## 六、验收标准
- 迁移 #9 幂等（存量库实证）；**100 对状态矩阵字节不变**（证无新态）。
- E2E 主链：建 A(review-gated)→建 B depends_on A→B 滞 created 期间 A 历经 queued/running/waiting_review→人签 A→resolver 管道 A 产物入 B、B enqueue→B 跑→waiting_review→人签 B→completed。**断言 B 在 A 人签前从未 running**。
- E2E 失败链：A failed→B `cancelled(upstream_failed)` 从不 running。
- E2E 污点：sensitive A→B 执行期派生 sensitive→B 产物下载 403。
- **7 个 tamper 全 RED→GREEN 还原**（T1-T7）。
- verify_all 全绿 + 零回归。

## 七、审查计划
本 v2 = loop-auditor mode-A 后修订 → **owner 裁 F3** → 实现（worktree 隔离，显式路径 stage）→ Codex 异源治理审（**命中即审：授权/签发/分级边界**）→ 主控 tamper 自证（T1-T7）→ verify_all。

## 八、判据①连接（forge 之后的两发验证弹）
本 forge 本身有内核 diff（=判据①"内核改动期"，不计入零 diff 计数）。改完趋稳后打两发**多 Agent 工作流**（OQ4 采纳）、只加 agents/tools 包、零 backend/app diff——既验内核稳定又验协作原语够通用。弹①=FEA-solve→FEA-evaluate 两 Agent 链（用新依赖边）；弹②=另一域多 Agent。**loop-auditor 补充：两发的 Agent 必须都 review-gated（或显式记录其 requires_human_review 值），否则验证弹自身会成为 F3 缺口第一个现实触发者、污染"零 diff 验证"干净性。** 两发均零 diff→判据①收口→双判据齐→封板。

## 九、开放问题裁决（loop-auditor + owner）
- **OQ1**：滞留 created + 派生显示 → **采纳**（保十态不变量论证成立）。
- **OQ2**：默认全部上游 output + 可选 glob → **采纳**，前提=T6 越权引用检查（默认全部放大绑定路径触发面）。
- **OQ3**：上游失败下游处置 → **`created→cancelled`**（非终态 failed，因 failed 从 created 不可达；cancelled+payload 区分优于永滞 created 制造僵尸）。
- **OQ4**：判据①两发验证弹 → **多 Agent，且二者均 review-gated**。

## 十、F3 宪法解释（唯一待 owner 裁项，非机制缺陷）
**问题**：非 review-gated（确定性）上游 A 喂下游 B 时，A 无人签自动跑（与今天单任务同）——"人是唯一签发者"是否隐含"每个执行链至少一个人工决策点"？当前 fleet 0 个此类 Agent，机制休眠。
**待 owner 三选一**（详见主控 AskUserQuestion）：①注册期不变量（判决型 category ⟹ 强制 review-gated，令非-gated 恒为确定性、自动链安全）②每链≥1 人签强制 ③文档化边界暂不设机制。裁决后：选①/②追加对应 gate+tamper 入本 forge；选③仅保留 §四 F3 边界声明。**在 owner 裁定前不实现任何 F3 相关强制逻辑。**

# 协作运行时 Forge · 设计契约 v1（实现前审设计，未实现）

- **状态**：设计审待过（loop-auditor mode-A → 修订 → 实现 → Codex 异源审）。**动手前审设计**，本文尚未落任何 backend/app 代码。
- **地位**：封板双判据的**判据①内核改动期**。这是 forge 不是 integration——**预期有内核 diff**（迁移+resolver+repos+api），这正是"骨架尚未完成"的进度条在动。改完内核趋稳后，判据①的两发零 diff 验证弹（见 §八）才有意义。
- **分支**：`feat/collab-runtime`（worktree 隔离，与批B并行不撞 checkout）。基线 main@7963b16。

## 一、未锻的肌肉（今天缺什么）

平台今天的"协作"止于两处，都靠**人肉接力**：
- M8 编排官（ADR-0016）：`<<PLAN>>` 推荐多 Agent 计划 + 分工，但**人逐个建任务、逐个签**；tasks 靠 conversation_id 分组，无执行依赖。
- CFD 两阶段（ADR-0026/0027）：cfd_solve 注册 sim_run_ref，cfd_evaluate 读它——但**人手工建两个任务、手工搬产物**。

缺的原语：**声明式任务依赖 + 确定性 artifact→input 管道**，即"B 的输入来自 A 的产物，A 完成后 B 自动就绪"——且**每个 review-gated 环节仍有人签**。这是 Agent→Agent 编排的地基，也是最大未锻肌肉。

## 二、宪法约束（本 forge 必须逐条保住的红线）——脊梁节

**核心命题：协作运行时自动化的是「管道」（artifact→input），绝不是「判决」（人签每个 review 环节）。** 拆解：

1. **人是唯一签发者**：下游要等的是上游 `completed`。而状态机 statemachine.py:39 强制 `waiting_review→completed` 只能人工放行动作转出、**禁止任何自动化路径**。故 review-gated 上游未经人签绝不 `completed`，下游绝不就绪——红线由既有状态机结构承接，非新增承诺。下游自身仍走 waiting_review→人签。**每一跳都有人签。**
2. **Agent 绝不建任务**：任务图由**人**编写（人建每个任务、人声明依赖边）。编排官只**推荐**边，人实例化。resolver 只**排序执行**，绝不创建任务。
3. **LLM 不进判决链**：resolver 是纯确定性——只按声明的绑定拷贝已注册产物引用，绝无 model_gateway 调用。哪个产物流向哪个输入，由人写的绑定决定，非模型。
4. **分级不可变 + 污点合成**（ADR-0025 集成）：下游 `data_classification` = max(自身, 全部上游)。resolver 在 enqueue 前 CAS-on-NULL 落库下游分级楼层。**教训继承（monitor-taint R2）：下载/固化门检的是子行 classification——resolver 必须让下游任务行的 data_classification 名副其实，否则=半闭合假绿。**

## 三、最小设计（外科，尽量 additive）

### 3.1 数据模型（迁移 #9，幂等 ALTER）
`tasks` 加两列（均可空，存量任务 NULL=无依赖，行为不变）：
- `depends_on TEXT`（JSON array of task_id；空/NULL=无依赖）
- `input_binding TEXT`（JSON：声明上游产物→下游输入的确定性映射，见 3.3）

### 3.2 无新状态（关键裁决，保十态不变量）
依赖未满足的任务**滞留 `created`**——不自动 created→queued。resolver 满足后走**既有** `created→queued` 转移。**零状态机改动、零 100 对矩阵改动、零 docs/05 改动**。UI 的"等待前置任务 N"是**派生显示**（读 depends_on + 上游 status 现算），非存储态。
> 权衡记录：显式 `blocked` 态可读性更强，但破"十态之外没有第十一态"宪法不变量 + 需改 100 对矩阵 + docs/05。裁决=保不变量、派生显示补可读性。留待设计审压测（OQ1）。

### 3.3 确定性 resolver（新组件，JobRunner tick 内一趟）
每 tick（或上游落 completed 事件触发）扫 `created` 且 depends_on 非空的任务：
- **全部上游 `completed`** → ①按 input_binding 把上游 `output_file_ids` 拷入本任务 `input_file_ids`（绑定只准引用上游**已注册** output 文件，绝不接受任意路径）②合成 data_classification 楼层 CAS-on-NULL 落库 ③`created→queued`。三步同一 `BEGIN IMMEDIATE` 写锁内原子（仿迁移竞态防护）。
- **任一上游 `failed`/`cancelled`** → 本任务 `created→failed`（error=upstream_failed），**fail-closed 绝不执行**（宁可不跑不跑错）。
- **上游 `waiting_review`/进行中** → 保持 `created`，下 tick 再看。
- JobRunner claim 循环**完全不动**（只 claim queued）。

### 3.4 DAG 完整性
- 建依赖边时**环检测**（拓扑，fail-closed 拒环）+ 只能依赖**已存在**任务。
- 允许 fan-in（多 depends_on）；扇出天然（多任务依赖同一上游）。

## 四、scope fence（本 forge 明确不做）
- 不做条件/分支工作流（"A 失败则跑 C"）——只线性+fan-in DAG。
- 不做上游 retry/重跑（独立议题，另立）。
- 不做 Agent/编排官自动建任务（红线，永不做）。
- 不做跨 conversation 依赖（起步同会话或显式 task_id）。
- resolver 不做任何 LLM 调用。

## 五、Tamper witnesses（fail-closed 门，拆一层必红）
- **T1 人签闸**：上游 waiting_review（未签）→ 下游永不 enqueue。拆=resolver 把 waiting_review 当就绪→下游跑→RED。
- **T2 失败传播**：上游 failed/rejected → 下游永不 enqueue（fail-closed）。拆=忽略上游失败→下游跑→RED。
- **T3 污点合成**：sensitive 上游 → 下游 data_classification 必 sensitive → 下游产物下载 403。拆=断合成→下游 internal→下载放行→RED（monitor-taint 同款最深点，子行必须名副其实）。
- **T4 环拒绝**：建环→创建拒。拆=关环检测→环被接受→RED。
- **T5 resolver 确定性**：解析路径无 model_gateway import（结构钥匙，grep 断言）。
- **T6 绑定收口**：只拷上游已注册 output_file_ids；绑定任意路径→拒。

## 六、验收标准
- 迁移 #9 幂等（存量库实证）；**100 对状态矩阵字节不变**（证无新态）。
- E2E 主链：建 A(review-gated)→建 B depends_on A→B 滞 created 期间 A 历经 queued/running/waiting_review→人签 A→resolver 管道 A 产物入 B、B enqueue→B 跑→waiting_review→人签 B→completed。**断言 B 在 A 人签前从未 running**。
- E2E 失败链：A failed→B 转 failed 从不 running。
- E2E 污点：sensitive A→B sensitive→B 产物下载 403。
- 六 tamper 全 RED→GREEN 还原。
- verify_all 全绿 + 零回归。

## 七、审查计划
loop-auditor mode-A 设计审（本文）→ findings 落 ADR → 实现（worktree 隔离，显式路径 stage）→ Codex 异源治理审（**命中即审：授权/签发/分级边界**）→ 主控 tamper 自证 → verify_all。

## 八、判据①连接（forge 之后的两发验证弹）
本 forge **本身有内核 diff**（=判据①的"内核改动期"，不计入零 diff 计数）。改完趋稳后打两发：
- **推荐（双重职责）**：两发都做**多 Agent 工作流**、只加 agents/tools 包、零 backend/app diff——既验内核稳定，又验协作原语够通用（无需 per-workflow 内核改）。
- 弹①=FEA-solve→FEA-evaluate 两 Agent 链（CFD 类比，用新依赖边）；弹②=另一域多 Agent 工作流。
- 若 FEA 只做单 Agent 域，只验内核稳定、不验协作原语——故**建议做成多 Agent**（OQ4，待 owner）。
- 两发均零 diff → 判据①收口 → 双判据齐 → 封板。

## 九、开放问题（设计审 + owner 裁）
- **OQ1**：滞留 created + 派生显示（推荐，保不变量）vs 显式 blocked 态（可读强，破十态）？
- **OQ2**：绑定粒度——默认全部上游 output vs 显式 selector（文件名 glob）？推荐"默认全部 + 可选 glob"。
- **OQ3**：上游失败下游处置——终态 failed（推荐，无僵尸）vs 永滞 created + 上报？
- **OQ4（owner 战略）**：判据①两发验证弹做成多 Agent（验协作原语，双重职责，推荐）还是单 Agent FEA 可接受？

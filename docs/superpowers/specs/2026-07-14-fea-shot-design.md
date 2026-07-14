# FEA solve→evaluate 双 Agent 工作流设计（判据①第一发·零内核 diff 验证弹）

**日期**：2026-07-14　**分支**：`feat/fea-solve-eval-shot`（基线 main@1abb3b6）
**性质**：判据①「结构完成」的第一发零内核 diff 验证弹（连续 2 发均零 diff → 判据①立）。

## 1. 目标与判据

**判据①（封板双判据之一，可证伪定义）**：连续 2 个新模块类接入内核**零 diff**
（只加 `agents/` 包，不碰 `backend/app/*`，`git diff backend/app` 可度量为空）。
此前每次接入（含 CFD 那发）都动了内核 → 判据①尚未成立，diff 即进度条。

本发=**第一发**：新增 FEA（有限元结构分析）梁固有频率 solve→evaluate 多 Agent
工作流，**目标 `git diff backend/app` 为空**。第二发（另一域）另立增量。

**红线（不放松）**：两 Agent 均 review-gated（人是唯一签发者：LLM 不进判决链，
profile=none 零 LLM，requires_human_review=true，产出停 waiting_review 由人放行）。

## 2. 零内核 diff 论证（为何这发能比 CFD 干净）

**边界**：内核=`backend/app/*`；Agent 包=仓根 `agents/<id>/` 标准 8 件套，
registry（`backend/app/runtime/registry.py`）自动扫描同步进 DB，加新包无需改内核。

**CFD 那发的内核 diff = `backend/app/cfd/`**（`st_oracle.py` + `cfd_log_parser.py`）：
经 ADR-0026 记载，这是「避免跨仓 vendoring 姊妹仓 sim-live-hub 解析逻辑」的
架构权衡，**非 Agent/Tool 框架结构性要求**。CFD 的 evaluate workflow.py 直接
`from backend.app.cfd.st_oracle import ...` 才踩内核。

**FEA 的做法**：等价 oracle（闭式解析解判据）**内联进 `agents/fea_evaluate_agent/
workflow.py`**，不 import 任何 `backend/app` 模块。FEA 没有姊妹仓可 vendor，且
求解是纯数值（无 docker/subprocess 外部边界），故：
- 无需 `backend/app/*` 新模块（oracle/FEM 全在 agent 包内）。
- 无需 `tools_impl/` 工具包（无外部系统边界要跨；`tools:[]` 全内联，先例=
  control_logic_agent）。
- 无需 numpy（未接入 pyproject/verify_all.sh 的 uv --with）→ **纯 stdlib** 手写
  Cholesky 正定性二分求特征值，规避碰 `scripts/`/`pyproject`。

**净 footprint**：`agents/fea_solve_agent/` + `agents/fea_evaluate_agent/` 两包 +
`backend/tests/test_fea_agents.py`（pytest testpaths 自动发现，无需改 verify_all.sh）。
`git diff backend/app` = 空（`test_zero_kernel_diff_footprint` 断言，碰内核即红）。

## 3. 域选型与 oracle

**问题**：等截面 Euler-Bernoulli 梁一阶横向固有频率 ω₁（悬臂/简支）。

**为何选梁频率**（而非桁架位移/一维稳态热传导）：后两者对线性单元在节点处
**nodally exact**（离散误差恒零/早早归零），无法演示「离散误差随单元数收敛、
欠网格化超容差」的风险叙事。梁频率有真截断误差且单调收敛，天然提供**非篡改**
的诚实负例。

**solve（求解侧）**：2 节点三次 Hermite 梁单元（标准刚度阵 + 一致质量阵），
广义特征值 `K φ = λ M φ` 取最小 λ₁=ω₁²。约束后 K 与一致 M 均对称正定 →
`K-λM` 正定 ⟺ λ<λ₁；纯 stdlib **Cholesky 正定性二分**（Cholesky 成功=正定=λ<λ₁，
找成→败翻转点即 λ₁）。对正定阵 Cholesky 数值稳定，非正定主元≤0 干净检出——
比无主元 LDLᵀ 对不定阵可能 breakdown 更稳。约束不足成机构 / 二分不定界 →
诚实 failed，绝不返回发散数当解。

**evaluate（评估侧）= oracle**：从上游 `fea_solution.json` 的 `params`（单一来源，
不重新录入 → 杜绝两次录入互相漂移）现算**闭式解析解**：
`ω₁_ref = (β₁L)²·√(EI/(ρA·L⁴))`，悬臂 β₁L=1.8751040687（cos·cosh=-1 首根，
已二分独立复根到 1e-13），简支 β₁L=π。相对误差 ≤ `tolerance_pct`（缺省 2%）判
「一致/收敛」。fail-closed：上游 `solver.converged≠true` / 缺字段 / 边界未知 /
解析失败 → 诚实「未达评估条件」，`passed=false`、`error_pct=null`，不逢正必过、
不编造（镜像 CFD st_oracle 对 st=None 的处理哲学）。

**数值自验（异源交叉）**：主控独立实现的 Cholesky-二分 与 reader（numpy eig）
两条独立路径对无量纲 (β₁L)² 收敛表逐位吻合（8 位有效数字）：悬臂 n=10 误差
8.6e-5%，简支 n=1 欠网格化 10.99%，简支 n=8 → 1.6e-3%。悬臂钢梁算例
ω₁=52.497101 rad/s（f₁=8.355 Hz）vs 闭式 52.497056。

## 4. review-gating 与协作运行时串联

两 Agent 均 `profile=none`（Runtime `_NoModelGatewayContext` 物理封死 LLM）+
`requires_human_review=true`——**本仓首个该组合**，与 §3.6 注册期不变量相容
（该不变量仅约束 `profile≠none` 的 job Agent 必须 rhr=true；profile=none 自由）。

**solve→evaluate 用刚锻好的协作运行时确定性串联**（本发**消费**已存在的内核能力，
非新增）：evaluate 任务 `depends_on:[solve]` + `input_binding:{from_tasks:[solve]}`。
**关键（K1 签发见证闸）**：solve 是 rhr=true，其产物**必须先经人工签发到 completed**
（`task_output_is_signed_off` 靠 review_approved 事件），resolver 才把 fea_solution.json
管道入 evaluate 并入队——未签发的 solve 上游，resolver 绝不放行下游（比 CFD 模板
solve 侧 rhr=false 多一次人工卡点，是设计意图非缺陷）。这条链同时验证协作运行时。

## 5. 验证（tamper 见证，非空洞绿）

`backend/tests/test_fea_agents.py`（11 测试，pytest 自动纳入 verify_all）：
- **单元·solve**：对闭式解析解（悬臂/简支）+ 单调收敛（n=1 欠网格 vs n=8 收敛）。
- **单元·evaluate**：正例通过 + **诚实负例**（简支 n=1 真实 10.99% 误差 → passed=false，
  非注入的真源回归）+ fail-closed（converged=false / 缺 params / 无 .json → 不编造）。
- **tamper 见证（拆一层必咬，已实证）**：①中和 oracle（参考值=FEM 值→误差恒0）
  → 诚实负例被误判 passed=true → 证真 oracle 判别力承重；②篡改 ω₁_fem +20% →
  oracle 必判 passed=false → 证比对非空洞；③拆收敛门（converged=false）→ 不给通过。
- **集成（真实 runtime+resolver+人签）**：全链 solve→waiting_review→**未签则 resolver
  返回 0 不放行**→人签 completed→resolver 管道入队 evaluate→waiting_review→人签
  →completed，评估 passed=true。
- **判据①度量**：`test_zero_kernel_diff_footprint` git-diff 断言 `backend/app` 零改动。

## 6. 诚实边界 / 残余

- **单一来源盲区**：evaluate 从产物读 params 现算参考值，若 solve 侧输入量纲滑档
  （E 少打数量级），FEM 与闭式会一致印证同一物理错误答案，内部一致性检查失明——
  只能靠 solve 侧 input_schema 量级护栏 + 人工签发复核拦截（已记 limitations）。
- **模型理想化**：只对理想等截面 Euler-Bernoulli 梁的离散收敛性负责，不校验建模
  假设本身贴合真实结构。
- **判据①未完成**：本发仅第一发。第二发（另一域，同样零内核 diff + review-gated）
  通过后判据①「结构完成」才成立；叠加已通过的判据②「生长完成」= 双判据齐 → 封板。

## 7. 落地文件（footprint）

```
agents/fea_solve_agent/     {agent.yaml, workflow.py, input_schema.json,
                             output_schema.json, prompt.md, README.md,
                             changelog.md, eval_cases/case_001..003.json}
agents/fea_evaluate_agent/  {同上 8 件套 + eval_cases/fixtures/{cantilever_n10,
                             ss_n8, ss_n1}/fea_solution.json}
backend/tests/test_fea_agents.py
docs/superpowers/specs/2026-07-14-fea-shot-design.md（本文件）
```
`git diff backend/app` = 空。

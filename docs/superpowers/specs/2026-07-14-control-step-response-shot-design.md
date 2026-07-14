# 二阶阶跃响应 solve→evaluate 双 Agent 工作流设计（判据①第二发·零内核 diff 验证弹）

**日期**：2026-07-14　**分支**：`feat/control-step-response-shot`（基线 main@a629bfd，即第一发 FEA 合并后）
**性质**：判据①「结构完成」的**第二发**零内核 diff 验证弹。第一发（FEA 梁固有频率）
已合并 main；本发通过后**连续 2 个不同模块类零 diff → 判据①立**，叠已过的判据②
「生长完成」= 双判据齐 → 封板。

## 1. 目标与判据

**判据①（封板双判据之一，可证伪定义）**：连续 2 个**新模块类**接入内核**零 diff**
（只加 `agents/` 包，不碰 `backend/app/*`，`git diff backend/app` 可度量为空）。

- 第一发＝FEA 梁固有频率（特征值问题 · 空间离散），已合并 main@a629bfd，零 diff 命中。
- **本发＝第二发**：二阶系统阶跃响应超调（**初值问题 ODE · 时间积分**）。**刻意选与
  第一发不同的数值范式**（时间积分 ≠ 空间特征值），令「连续 2 个**不同**模块类零 diff
  接入」的论断最强——不是把 FEA 换套参数再打一遍。**目标 `git diff backend/app` 为空**。

**红线（不放松）**：两 Agent 均 review-gated（人是唯一签发者：LLM 不进判决链，
profile=none 零 LLM，requires_human_review=true，产出停 waiting_review 由人放行）。

## 2. 零内核 diff 论证（沿用第一发已证路径）

**边界**：内核=`backend/app/*`；Agent 包=仓根 `agents/<id>/` 标准 8 件套，
registry（`backend/app/runtime/registry.py`）自动扫描同步进 DB，加新包无需改内核。

**CFD 那发的内核 diff = `backend/app/cfd/`**（st_oracle + log_parser，ADR-0026 的
跨仓 vendoring 权衡，非框架结构性要求）。**本发做法**（同第一发）：等价 oracle
（闭式解析解判据）**内联进 `agents/step_response_evaluate_agent/workflow.py`**，
不 import 任何 `backend/app` 模块。求解是纯数值（无 docker/subprocess/外部边界）：
- 无需 `backend/app/*` 新模块（oracle/积分器全在 agent 包内）。
- 无需 `tools_impl/` 工具包（无外部系统边界；`tools:[]` 全内联）。
- 无需 numpy（未接入 pyproject/verify_all.sh 的 uv --with）→ **纯 stdlib** 手写梯形
  积分（每步 2×2 Cramer），规避碰 `scripts/`/`pyproject`。

**净 footprint**：`agents/step_response_solve_agent/` + `agents/step_response_evaluate_agent/`
两包 + `backend/tests/test_step_response_agents.py`（pytest testpaths 自动发现）。
`git diff backend/app` = 空（经 git 命令验证并记于本文档，**不放进永久 pytest 套件**——
第一发 Codex/loop-auditor 已定论：HEAD-vs-main 的 git-diff 断言既会在未来合法改内核的
分支上误红，又对纯 untracked 文件盲）。

## 3. 域选型与 oracle

**问题**：标准二阶欠阻尼系统 `G(s)=ωn²/(s²+2ζωn·s+ωn²)` 的单位阶跃响应超调量 Mp。

**为何选阶跃超调**（而非上升/调节时间）：超调有教科书**精确闭式** `Mp=e^(−ζπ/√(1−ζ²))`，
且随时间步长有真实 O(h²) 离散误差、单调收敛——天然提供**非篡改**的诚实负例（粗步长
超容差）。调节时间的常用闭式 `4/ζωn` 本身是近似式，误差与离散无关，不宜作 oracle。

**solve（求解侧）**：状态空间 `ẋ=Ax+Bu`（`A=[[0,1],[−ωn²,−2ζωn]]`，`B=[0,ωn²]`，
零初值）用**梯形（双线性变换/Tustin）定步长隐式积分**——控制学科 canonical 离散。
每步解 2×2 线性系统 `(I−h/2·A)x_{k+1}=(I+h/2·A)x_k+hB`（纯 stdlib Cramer）。仿真窗
`horizon=2 个阻尼周期=4π/ωd`，欠阻尼首峰 `tp=π/ωd=horizon/4` 恒在窗内且为全局最大；
超调由轨迹 argmax 取（峰值−稳态）。梯形对稳态一致（DC 增益恒 1）→ 稳态 y_ss=1 精确。

**为何梯形而非显式 RK4**（关键设计决策）：第二发要能演示「粗离散超容差、细离散
收敛」的诚实负例。显式 RK4 对振荡系统有稳定上限 `ωn·h<2.828`，粗步长会 **blowup**
而非「误差大但有界」——诚实负例撞发散悬崖、不鲁棒。梯形是 **A-稳定**：粗步长只是
O(h²) 精度差、绝不发散（已数值实测 `n_steps=3, ωn·dt=4.84` 仍 max|y|=1.26 不发散）。
且双线性变换是控制学科离散连续系统的标准工具，域上 canonical。

**evaluate（评估侧）= oracle**：从上游 `step_solution.json` 的 `params`（单一来源，不
重新录入 → 杜绝两次录入互相漂移）现算**闭式解析超调** `Mp_ref=100·e^(−ζπ/√(1−ζ²))`。
相对误差 ≤ `tolerance_pct`（缺省 2%）判「一致/收敛」。fail-closed：上游
`solver.converged≠true` / 缺字段 / **ζ 非欠阻尼(0<ζ<1)** / 解析失败 → 诚实「未达评估
条件」，`passed=false`、`error_pct=null`，不逢正必过、不编造（镜像 CFD st_oracle 对
st=None 的处理哲学）。

**数值自验（动手前异源交叉）**：主控独立实现的**梯形积分**与**闭式解析解**
`y(t)=1−e^(−ζωn·t)/√(1−ζ²)·sin(ωd·t+φ)` 两条独立路径对超调逐位吻合（1e-14）。
收敛表（ζ=0.5, horizon=4π/ωd）：

| n_steps | dt | ωn·dt | Mp_sim% | Mp 相对误差% |
|--------:|-----:|-----:|--------:|-----------:|
| 8 | 1.814 | 1.814 | 28.376 | 74.05 |
| 12 | 1.209 | 1.209 | 23.078 | 41.55 |
| 20 | 0.726 | 0.726 | 18.878 | 15.79 |
| 40 | 0.363 | 0.363 | 16.952 | 3.98 |
| 100 | 0.145 | 0.145 | 16.407 | 0.64 |
| 2000 | 0.007 | 0.007 | 16.3036 | 0.0016 |

单调收敛、2% 容差跨越在 n=40~100 间。诚实负例取 n_steps=12（41.5% 误差，A-稳定不发散）。

## 4. review-gating 与协作运行时串联

两 Agent 均 `profile=none`（Runtime `_NoModelGatewayContext` 物理封死 LLM）+
`requires_human_review=true`——本仓第二个该组合（第一发 FEA 首用），与 §3.6 注册期
不变量相容（该不变量仅约束 `profile≠none` 的 job Agent 必须 rhr=true；profile=none 自由）。

**solve→evaluate 用协作运行时确定性串联**（本发**消费**已存在的内核能力，非新增）：
evaluate 任务 `depends_on:[solve]` + `input_binding:{from_tasks:[solve]}`。**关键（K1
签发见证闸）**：solve 是 rhr=true，其产物**必须先经人工签发到 completed**
（`task_output_is_signed_off` 靠 review_approved 事件），resolver 才把 step_solution.json
管道入 evaluate 并入队——未签发的 solve 上游，resolver 绝不放行下游。这条链同时验证
协作运行时（与第一发同构，交叉印证运行时对不同 Agent 对稳定）。

## 5. 验证（tamper 见证，非空洞绿）

`backend/tests/test_step_response_agents.py`（15 测试，pytest 自动纳入 verify_all）：
- **单元·solve**：对闭式解析超调（ζ=0.5 / ζ=0.3 且 ωn=2）+ 单调收敛（n=12 粗 vs
  n=2000 收敛）+ **A-稳定性签名测试**（n_steps=6, ωn·dt≈2.4 显式 RK4 必发散区，梯形
  须有限有界有超调，防未来『优化』成显式法作废诚实负例）+ fail-closed 分支
  monkeypatch 可达。
- **单元·evaluate**：正例通过 + **诚实负例**（n=12 真实 41.5% 误差 → passed=false，
  非注入真源回归）+ fail-closed（converged=false / **ζ 越域 1.5** / 缺 params / 无 .json
  → 不编造）+ **tamper**（改 overshoot +50% → 必判 passed=false，证比对非空洞）。
- **集成（真实 runtime+resolver+人签）**：全链 solve→waiting_review→**未签则 resolver
  返回 0 不放行**→人签 completed→resolver 管道入队 evaluate→waiting_review→人签
  →completed，评估 passed=true。
- **eval_cases 实跑**：`test_eval_cases_all_green_through_runner` 经真实治理 runner
  （run_agent_evals）跑两 Agent 全部 eval_cases 全绿——非休眠资产。
- **判据①度量**：`git diff backend/app`（分叉点 main@a629bfd → 工作树）为空——一次性
  属性，经 git 命令验证并记于本文档，不放进永久 pytest 套件。

## 6. 诚实边界 / 残余

- **ωn 盲区**：超调量在数学上只依赖 ζ（`Mp=e^(−ζπ/√(1−ζ²))` 无 ωn）——evaluate 用
  ζ 现算参考值，故对 ωn 量纲滑档失明（时间尺度错不改超调）。只能靠 solve 侧
  input_schema 量级护栏 + 人工签发复核拦截（已记 limitations）。这是「单标量 oracle」
  的固有代价，与第一发 FEA 的量纲滑档盲区同构。
- **模型理想化**：只对理想标准二阶欠阻尼系统的离散收敛性负责，不校验建模假设本身
  （系统是否真为无零点二阶、有无时滞/非线性）贴合真实对象。
- **判据①达成**：本发是第二发。通过后连续 2 个不同模块类零 diff → 判据①「结构完成」
  成立；叠加已通过的判据②「生长完成」= 双判据齐 → 封板。

## 7. 落地文件（footprint）

```
agents/step_response_solve_agent/     {agent.yaml, workflow.py, input_schema.json,
                                       output_schema.json, prompt.md, README.md,
                                       changelog.md, eval_cases/case_001..003.json}
agents/step_response_evaluate_agent/  {同上 8 件套 + eval_cases/fixtures/{underdamped_fine,
                                       light_damp_fine, coarse_grid}/step_solution.json
                                       + fixtures/malformed/bad_solution.json}
backend/tests/test_step_response_agents.py
docs/superpowers/specs/2026-07-14-control-step-response-shot-design.md（本文件）
```
`git diff backend/app` = 空。

## 8. 异源双轴审收口

（待 Codex 治理审 + loop-auditor 验证架构审后补。）

# fea_evaluate_agent — FEA 梁频率评估 Agent

判据①第一发**零内核 diff 验证弹**的评估侧。读一次 `fea_solve_agent` 的求解产物
（经 `depends_on`/`input_binding` 声明式管道注入），用**闭式解析解**确定性判定
FEM 一阶固有频率是否收敛，零 LLM、零工具、零第三方依赖。

## 做什么

- 从上游 `fea_solution.json` 的 `params` **单一来源**读梁物性/几何，现算闭式解析
  一阶圆频率 `ω₁_ref=(β₁L)²·√(EI/(ρA·L⁴))`（悬臂 β₁L=1.87510407 是 cos·cosh=-1
  的首根，简支 β₁L=π 是 sin(βL)=0 的精确闭式）。
- 与产物里的 `ω₁_fem` 比相对误差；`err ≤ tolerance_pct`（缺省 2%）判「一致/收敛」，
  否则「超出容差」。
- 输出 `evaluation.json`（判据数字）+ `evaluation.md`（人读草案 + 水印）。

## 为什么 params 从产物读、不重新录入

评估从求解产物读同一份 `params` 现算参考值，**不重新接受 E/I/L 等输入**——杜绝
「两次人工录入互相漂移」的 rogue 数字风险。代价是对量纲滑档失明（FEM 与闭式会
一致印证同一个物理错误答案），由 solve 侧 `input_schema` 量级护栏 + 人工签发复核
兜底（见 `limitations`）。

## fail-closed（诚实地板）

上游 `solver.converged≠true` / 产物缺字段 / 边界条件未知 / 解析失败 → 诚实
「未达评估条件」，`passed=false`、`error_pct=null`，绝不逢正必过、绝不编造通过
（镜像 CFD `st_oracle` 对 `st=None` 的处理哲学）。

## 诚实负例（非篡改）

`eval_cases/case_003` 喂一份简支 `n_elements=1` 的真实欠网格化求解产物（离散误差
10.99% > 2% 容差）——**无需伪造任何数字**即演示 oracle 真能拦截离散不足，而非
逢正必过。

## 人是唯一签发者

`requires_human_review=true`：判定停 `waiting_review`，草案头强制水印「判定权在
人」，由具名工程师签发才 `completed`。

## 零内核 diff

闭式解析 oracle 内联在 `workflow.py`，不 import `backend/app/*` 任何模块——刻意
规避 `cfd_evaluate_agent` 把 `st_oracle` 放进 `backend/app/cfd/` 的先例。本发
`git diff backend/app` 为空。

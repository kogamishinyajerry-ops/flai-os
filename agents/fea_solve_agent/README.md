# fea_solve_agent — FEA 梁固有频率求解 Agent

判据①第一发**零内核 diff 验证弹**的求解侧。把等截面 Euler-Bernoulli 梁（悬臂/
简支）的一阶横向固有频率 ω₁ 用**纯 Python 有限元**确定性求解，零 LLM、零工具、
零第三方依赖（无 numpy）。

## 做什么

输入梁的边界条件与物性/几何（`boundary_condition`, `E`, `I`, `L`, `rho`, `A`,
可选 `n_elements`），输出：

- `fea_solution.json` — 完整解：求解 `params` 原样回存 + `fem_result.omega1_rad_s`
  / `f1_hz` + `solver.converged`。**params 原样回存**是设计要点：下游
  fea_evaluate_agent 从这份单一来源读参数现算闭式解析参考值，杜绝「两次人工录入
  互相漂移」的 rogue 数字风险。
- `fea_solution.md` — 人读摘要，含强制水印（判定权在人）。

## 数值方法（教科书标准）

- **单元**：2 节点三次 Hermite 梁单元，每节点 DOF=(挠度 v, 转角 θ)；标准刚度阵
  `EI/l³·[...]` + 一致（consistent）质量阵 `ρA·l/420·[...]`。
- **求解**：广义特征值 `K φ = λ M φ` 最小 λ₁=ω₁²。约束后 K 与一致 M 均对称正定，
  故 `K-λM` 正定 ⟺ λ<λ₁；用纯 stdlib **Cholesky 正定性二分**（Cholesky 成功=正定=
  λ<λ₁，找成→败翻转点即 λ₁）。对正定矩阵 Cholesky 数值稳定，非正定时主元≤0 干净
  检出——比无主元 LDLᵀ 对不定阵可能 breakdown 更稳。

## 边界与诚实失败

- 结构约束不足成机构（`K` 非正定）/ 二分无法在合理范围定界 → **诚实 failed**，
  指出可能问题，绝不返回发散数或 NaN 当解。
- 非法输入（非正物性、未知边界条件、单元数越界）在 Runtime `_validate_inputs`
  层经 jsonschema `input_schema.json` 直接 fail-closed，不进 workflow。

## 人是唯一签发者

`requires_human_review=true`：求解结果=工程结论输入，任务停 `waiting_review`
等工程师具名签发放行才 `completed`。签发后其产物才经 `depends_on`/`input_binding`
声明式管道流入 `fea_evaluate_agent`（判据①同时验证协作运行时的确定性串联）。

## 零内核 diff

全部有限元与求解逻辑内联在 `workflow.py`，不 import `backend/app/*` 任何模块。
刻意规避 `cfd_evaluate_agent` 把 oracle 放进 `backend/app/cfd/` 的先例——本发
`git diff backend/app` 为空。

## 已知限制

见 `agent.yaml` `limitations`：只做等截面梁一阶频率线性分析，不做高阶模态/非线性/
屈曲/阻尼/静力应力；仅悬臂与简支；小规模模型（n_elements≤64）。

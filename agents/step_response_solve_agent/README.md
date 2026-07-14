# step_response_solve_agent — 二阶系统阶跃响应求解 Agent

判据①**第二发**零内核 diff 验证弹的求解侧。把标准二阶欠阻尼系统（ζ, ωn）的
单位阶跃响应超调量 overshoot 用**纯 Python 梯形积分**确定性仿真，零 LLM、零
工具、零第三方依赖（无 numpy/scipy）。

与第一发（FEA 梁固有频率）是**不同的模块类**：本发是初值问题 ODE 的时间积分
（梯形/双线性），第一发是特征值问题的空间离散——判据①要求「连续 2 个不同
模块类接入内核零 diff」，二者刻意选不同数值范式。

## 做什么

输入二阶系统的阻尼比与自然频率（`zeta`, `omega_n`, 可选 `n_steps`），输出：

- `step_solution.json` — 完整解：求解 `params` 原样回存 + `response_result.overshoot_pct`
  + `solver.converged`。**params 原样回存**是设计要点：下游 step_response_evaluate_agent
  从这份单一来源读参数现算闭式解析参考值，杜绝「两次人工录入互相漂移」的 rogue 数字风险。
- `step_solution.md` — 人读摘要，含强制水印（判定权在人）。

## 数值方法（教科书标准）

- **系统**：`G(s)=ωn²/(s²+2ζωn·s+ωn²)`，单位阶跃。状态空间 `ẋ=Ax+Bu`，
  `A=[[0,1],[−ωn²,−2ζωn]]`，`B=[0,ωn²]`，零初值。
- **积分**：梯形（双线性变换/Tustin）定步长隐式法——控制学科 **canonical** 离散，
  **A-稳定**（对任意步长不发散，无显式 RK4 的 `ωn·h<2.8` 稳定上限），全局误差 O(h²)。
  每步解 2×2 线性系统（纯 stdlib Cramer）。梯形对稳态一致：DC 增益恒 =1，稳态 y_ss=1 精确。
- **仿真窗**：`horizon=2 个阻尼周期=4π/ωd`（`ωd=ωn√(1−ζ²)`）；欠阻尼首峰
  `tp=π/ωd=horizon/4` 恒在窗内且为全局最大。超调 `Mp` 由轨迹 argmax 取（峰值−稳态）。

## 为什么选梯形而非 RK4

第二发要能演示「粗离散→超容差、细离散→收敛」的**诚实负例**（呼应第一发的
欠网格化）。显式 RK4 对振荡系统有稳定上限 `ωn·h<2.8`，粗步长会 blowup 而非
「误差大但有界」——诚实负例会撞发散悬崖。梯形是 **A-稳定**：粗步长只是 O(h²)
精度差、绝不发散，故诚实负例鲁棒可控。且双线性变换是控制学科离散连续系统的
标准工具，域上 canonical。

## 边界与诚实失败

- 仿真轨迹非有限 / 无超调（峰≤稳态）/ 峰值落仿真窗边界 → **诚实 failed**，
  指出可能问题，绝不返回无效数或 NaN 当解。
- 非法输入（ζ 越界 0<ζ<1、非正 ωn、n_steps 越界）在 Runtime `_validate_inputs`
  层经 jsonschema `input_schema.json` 直接 fail-closed，不进 workflow。

## 人是唯一签发者

`requires_human_review=true`：仿真结果=工程结论输入，任务停 `waiting_review`
等工程师具名签发放行才 `completed`。签发后其产物才经 `depends_on`/`input_binding`
声明式管道流入 `step_response_evaluate_agent`（判据①同时验证协作运行时的确定性串联）。

## 零内核 diff

全部仿真与求解逻辑内联在 `workflow.py`，不 import `backend/app/*` 任何模块。
刻意规避 `cfd_evaluate_agent` 把 oracle 放进 `backend/app/cfd/` 的先例——本发
`git diff backend/app` 为空。

## 已知限制

见 `agent.yaml` `limitations`：只做标准二阶欠阻尼系统超调量；只输出 overshoot；
超调只依赖 ζ（对 ωn 量纲滑档失明，靠 input_schema 量级护栏 + 人工复核兜底）；
小规模标量系统。

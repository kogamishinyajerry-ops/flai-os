# fea_solve_agent 变更记录

## 0.1.0（判据①第一发零内核 diff 验证弹·求解侧，2026-07-14）

- 初版：等截面 Euler-Bernoulli 梁一阶固有频率的纯 Python 有限元求解。零 LLM
  （model.profile=none）零工具（tools=[]）：2 节点三次 Hermite 梁单元 + 一致
  质量阵，广义特征值 K φ=λ M φ 取最小 λ₁=ω₁²，纯 stdlib Cholesky 正定性二分
  求解（无 numpy——未接入本仓 pyproject/verify_all.sh 的 uv --with 列表）。
- 支持悬臂（cantilever）与简支（simply_supported）两种边界条件。
- 输出 fea_solution.json（含求解 params 原样回存 + ω₁ + solver.converged）与
  fea_solution.md（人读摘要 + 水印）。刚度阵非正定/二分不定界（结构约束不足
  成机构）→ 诚实 failed，绝不返回发散数当解。
- requires_human_review=true：求解结果=工程结论输入，停 waiting_review 等
  工程师签发（人是唯一签发者）；签发后其产物才经 depends_on/input_binding
  管道流入 fea_evaluate_agent（本仓首个 profile=none + requires_human_review=true
  组合，与 §3.6 注册期不变量相容——该不变量仅约束 profile≠none 的 job Agent）。
- 零内核 diff：全部有限元与求解逻辑内联在 workflow.py 内，不 import
  backend/app/* 任何模块（刻意规避 cfd_evaluate_agent 把 oracle 放进
  backend/app/cfd/ 的先例）。
- 数值自验：无量纲 (β₁L)² 收敛表与闭式解析解逐位吻合（悬臂 n=10 误差
  8.6e-5%，简支 n=1 欠网格化误差 10.99% 供 evaluate 侧诚实负例）。

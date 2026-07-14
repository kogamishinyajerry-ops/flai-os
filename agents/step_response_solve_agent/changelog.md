# step_response_solve_agent 变更记录

## 0.1.0（判据①第二发零内核 diff 验证弹·求解侧，2026-07-14）

- 初版：标准二阶欠阻尼系统单位阶跃响应超调量的纯 Python 仿真。零 LLM
  （model.profile=none）零工具（tools=[]）：状态空间 ẋ=Ax+Bu 梯形（双线性/
  Tustin）定步长隐式积分，每步解 2×2 线性系统，纯 stdlib（无 numpy——未接入
  本仓 pyproject/verify_all.sh 的 uv --with 列表）。
- 从仿真轨迹 argmax 提取超调 overshoot_pct=（峰值−稳态）×100%。仿真窗
  horizon=2 个阻尼周期=4π/ωd，欠阻尼首峰 tp=π/ωd=horizon/4 恒在窗内。
- 选梯形而非显式 RK4 的关键：梯形 **A-稳定**，粗 n_steps 只是 O(h²) 精度差、
  绝不发散；RK4 对振荡系统有 ωn·h<2.8 稳定上限，粗步长会 blowup 撞发散悬崖，
  使「粗离散诚实负例」不鲁棒。双线性变换亦是控制学科离散连续系统的 canonical 工具。
- 输出 step_solution.json（含求解 params 原样回存 + overshoot_pct + solver.converged）
  与 step_solution.md（人读摘要 + 水印）。仿真非有限/无超调/峰值落仿真窗边界
  → 诚实 failed，绝不返回无效数当解。
- requires_human_review=true：仿真结果=工程结论输入，停 waiting_review 等
  工程师签发（人是唯一签发者）；签发后其产物才经 depends_on/input_binding
  管道流入 step_response_evaluate_agent（本仓第二个 profile=none +
  requires_human_review=true 组合，与 §3.6 注册期不变量相容——该不变量仅约束
  profile≠none 的 job Agent）。
- 零内核 diff：全部仿真与求解逻辑内联在 workflow.py，不 import backend/app/*
  任何模块（刻意规避 cfd_evaluate_agent 把 oracle 放进 backend/app/cfd/ 的先例）。
- 数值自验（动手前异源交叉）：主控独立实现的梯形积分与闭式解析解 y(t)=1−
  e^(−ζωn·t)/√(1−ζ²)·sin(ωd·t+φ) 两条独立路径对超调逐位吻合（1e-14）；收敛表
  单调（ζ=0.5：n=12 误差 41.5% → n=2000 误差 0.0016%），A-稳定性极端粗测
  （n_steps=3, ωn·dt=4.84）确认梯形不发散——供 evaluate 侧诚实负例（粗网格超容差）。
- 与第一发（FEA 梁固有频率）是不同模块类：初值问题 ODE 时间积分 ≠ 特征值问题
  空间离散，刻意选不同数值范式以强化判据①「两个不同模块类零 diff 接入」的论断。

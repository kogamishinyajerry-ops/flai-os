# fea_evaluate_agent 变更记录

## 0.1.0（判据①第一发零内核 diff 验证弹·评估侧，2026-07-14）

- 初版：梁一阶固有频率 FEM 解的确定性收敛评估。零 LLM（model.profile=none，
  Runtime 物理封死 gateway）零工具（tools=[]）：oracle 全部内联在 workflow.py。
- 判据：从上游 fea_solution.json 的 params 现算闭式解析一阶圆频率
  ω₁_ref=(β₁L)²·√(EI/ρAL⁴)（悬臂 β₁L=1.87510407，简支 β₁L=π），与 FEM 的
  ω₁_fem 比相对误差 ≤ tolerance_pct（缺省 2.0%）即判「一致/收敛」。
- fail-closed：上游 solver.converged≠true / 产物缺字段 / 边界条件未知 / 解析
  失败 → 诚实「未达评估条件」，不逢正必过、不编造通过（镜像 st_oracle 对
  st=None 的处理哲学）。
- params 只从求解产物单一来源读取，用同一份 params 现算参考值——杜绝两次人工
  录入互相漂移的 rogue 数字。
- requires_human_review=true：判定停 waiting_review，草案头强制水印「判定权在
  人」，由具名工程师签发。
- 零内核 diff：闭式解析 oracle 内联在 workflow.py，不 import backend/app/*
  任何模块（刻意规避 cfd_evaluate_agent 把 st_oracle 放进 backend/app/cfd/ 的
  先例）。
- 诚实负例（eval_cases case_003）：简支 n_elements=1 真实欠网格化误差 10.99%
  > 默认容差 2%，非篡改 fixture——验证 oracle 真能拦截离散不足，而非逢正必过。
- 异源双轴审收口（Codex P2-1/P2-2，均 grounded）：①人签件 .md 频率值
  `.6f`→`.6g`（极小频率不再显示成 0 误导签发人）；②加 case_004 失败路径覆盖案
  （畸形产物→诚实 failed），满足 min_eval_coverage 晋升门要求的 status_is:failed。

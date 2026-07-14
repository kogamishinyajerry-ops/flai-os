# step_response_evaluate_agent 变更记录

## 0.1.0（判据①第二发零内核 diff 验证弹·评估侧，2026-07-14）

- 初版：二阶阶跃响应超调仿真的确定性收敛评估。零 LLM（model.profile=none，
  Runtime 物理封死 gateway）零工具（tools=[]）：oracle 全部内联在 workflow.py。
- 判据：从上游 step_solution.json 的 params 现算闭式解析超调量
  Mp_ref=100·e^(−ζπ/√(1−ζ²))（标准二阶欠阻尼系统单位阶跃超调，教科书精确闭式），
  与仿真 overshoot_pct 比相对误差 ≤ tolerance_pct（缺省 2.0%）即判「一致/收敛」。
- fail-closed：上游 solver.converged≠true / 产物缺字段 / ζ 非欠阻尼(0<ζ<1) / 解析
  失败 → 诚实「未达评估条件」，不逢正必过、不编造通过（镜像 st_oracle 对
  st=None 的处理哲学）。
- params 只从仿真产物单一来源读，用同一份 params 现算参考值——杜绝两次人工
  录入互相漂移的 rogue 数字。诚实边界：超调量只依赖 ζ，对 ωn 量纲滑档失明
  （时间尺度错不改超调），由 solve 侧量级护栏 + 人工复核兜底（已记 limitations）。
- requires_human_review=true：判定停 waiting_review，草案头强制水印「判定权在
  人」，由具名工程师签发。
- 零内核 diff：闭式解析 oracle 内联在 workflow.py，不 import backend/app/*
  任何模块（刻意规避 cfd_evaluate_agent 把 st_oracle 放进 backend/app/cfd/ 的先例）。
- 诚实负例（eval_cases case_003）：n_steps=12 真实粗步长 O(h²) 误差 41.5%
  > 默认容差 2%，非篡改 fixture——验证 oracle 真能拦截欠离散，而非逢正必过。
  粗步长产物由 solve agent 真实产出（梯形 A-稳定不发散，是「精度差」非「发散」）。

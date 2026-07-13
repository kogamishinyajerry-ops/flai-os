# cfd_evaluate_agent 变更记录

## 0.1.0（CFD 真接线 P2，2026-07-13）

- 初版：CFD 结果评估（圆柱绕流 Re=100）——经 `cfd_result_read` 只读一次求解
  结果，确定性 oracle（`backend.app.cfd.st_oracle`）算 St=f·D/U 与 Cd_mean，
  对照 Williamson St_ref=0.164 出收敛/误差判据，落 `evaluation.json`。
- LLM 边界（宪法铁律六 + §11.2）：数字全来自确定性计算，LLM(reasoning) 仅对
  已给定数字做工程叙事，`cfd_eval_draft.md` 头强制水印「判定权在人」；未收敛/
  数据不足如实报「未达评估条件」，st=None，绝不编造逼近参考（Goodhart 防御）。
- `cfd_result_read` 读取失败诚实 failed；LLM 叙事失败降级为显式占位不阻断
  （确定性判据已落）。
- `requires_human_review: true`：任务停 waiting_review 等具名放行——签发权在人。
- system prompt 固化于 prompt.md（运行时读取，无内嵌副本）。
- golden 对账：good-run-01（t=150）St=0.16729 与 agent-cfd-live 实测 0.16734 一致。

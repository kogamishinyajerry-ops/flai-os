# cfd_evaluate_agent（CFD 结果评估 · Strouhal/Cd 确定性判据）

CFD 真接线 **P2 评估侧**。给一个求解 `run_id`，读一次真实 CFD 求解（圆柱绕流
Re=100）的力系数与残差，**确定性**算出 Strouhal 数与平均阻力系数，对照 Williamson
参考出评估草案交工程师签发。

## 数据流

```
run_id
  → cfd_result_read（只读 case/run/<run_id>/ 的 log.pimpleFoam + forceCoeffs）
  → st_oracle（纯 Python：Cl(t) 末段过零 → f → St=f·D/U；Cd_mean）  ← 唯一数字来源
  → 对照 St_ref=0.164 → evaluation.json（确定性判据）
  → LLM(reasoning) 仅叙事这些数字 → cfd_eval_draft.md（头强制水印）
  → requires_human_review=true → waiting_review → 人签
```

## 铁律边界（勿破）

- **数字全部来自确定性 oracle**（`backend.app.cfd.st_oracle`），LLM 只做工程叙事，
  绝不自算 / 覆盖 / 新增任何数字（宪法铁律六 + §11.2「LLM 不判最终工程结论」）。
- **未收敛 / 数据不足**（Cl 未起振、稳定周期 <3）→ 如实 verdict「未达评估条件」，
  `st=null`，**绝不编造 St 逼近 0.164**（Goodhart 防御：oracle 参照参考值但不得
  反向拟合）。
- `cfd_result_read` 读取失败 → 诚实 `failed`，绝不伪造评估。
- `cfd_eval_draft.md` 头强制水印：「AI 辅助 · 未经工程师确认 · 判定权在人」。
- LLM 叙事失败 / 无 key 不阻断（确定性判据已落 evaluation.json），降级为显式
  「叙事不可用」占位。
- `requires_human_review: true`：任务永远停 waiting_review，由工程师具名放行或
  拒绝——**签发权在人**。

## 对照基准

Williamson (1996) Re=100 圆柱绕流 Strouhal 参考 **St_ref=0.164**。good-run-01
（t=150 充分发展）实测 St=0.16729，与 agent-cfd-live 实测 0.16734、Cd_mean=1.4007
一致。不同雷诺数 / 网格 / 时间步下本参考不适用（见 limitations）。

## eval_cases

- `case_001`：正常 good-run（run_id=20260713-101010）→ converged，St≈0.167，
  水印草案，waiting_review。
- `case_002`：未收敛路径（run_id=20260713-202020）→ 拒出 St（`st=null`），
  verdict「未达评估条件」（防假绿），任务仍 waiting_review（workflow 对未收敛
  仍返回 success，`requires_human_review` 把它转 waiting_review，不是 failed）。
- 两 case 的 run_id 对应 `eval_cases/fixtures/` 下 vendored 的真实夹具（从
  `backend/tests/fixtures/cfd_good_run/` 截取，只删行不改字；来源/截取范围/
  实测周期数见 `eval_cases/fixtures/README.md`）——`cfd_result_read` 是真实
  fail-closed 工具，M10 治理 eval-runner 跑 `eval_cases/*.json` 时经**真实
  `runtime.execute` 全链**执行，case 引用的 run_id 必须有对应真实夹具。
- **运行前置**：跑本包 eval（无论 API 还是本地驱动）需先
  `export FLAI_CFD_CASE_DIR=<repo>/agents/cfd_evaluate_agent/eval_cases/fixtures`
  （`FLAI_CFD_CASE_DIR` 是进程环境变量，`cfd_result_read` 工具本身不改；未配置
  fail-closed，两 case 都会失败——照 `monitor_adapter_gen_agent` 的
  `FLAI_MONITOR_CORE_DIR` 先例，操作员在晋升/跑 eval 前自行配置）。

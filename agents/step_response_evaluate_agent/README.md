# step_response_evaluate_agent — 阶跃响应超调评估 Agent

判据①**第二发**零内核 diff 验证弹的评估侧。读一次 `step_response_solve_agent`
的仿真产物（经 `depends_on`/`input_binding` 声明式管道注入），用**闭式解析解**
确定性判定超调量是否收敛，零 LLM、零工具、零第三方依赖。

## 做什么

- 从上游 `step_solution.json` 的 `params` **单一来源**读系统参数（ζ, ωn），现算
  闭式解析超调 `Mp_ref=100·e^(−ζπ/√(1−ζ²))`（标准二阶欠阻尼系统单位阶跃超调的
  教科书精确闭式，数学上只依赖 ζ）。
- 与产物里的 `overshoot_pct` 比相对误差；`err ≤ tolerance_pct`（缺省 2%）判
  「一致/收敛」，否则「超出容差」。
- 输出 `evaluation.json`（判据数字）+ `evaluation.md`（人读草案 + 水印）。

## 为什么 params 从产物读、不重新录入

评估从仿真产物读同一份 `params` 现算参考值，**不重新接受 ζ/ωn 等输入**——杜绝
「两次人工录入互相漂移」的 rogue 数字风险。代价是对 ωn 量纲滑档失明（超调量只
依赖 ζ，ωn 只改时间尺度不改超调，故 ωn 错不被察觉），由 solve 侧 `input_schema`
量级护栏 + 人工签发复核兜底（见 `limitations`）。

## fail-closed（诚实地板）

上游 `solver.converged≠true` / 产物缺字段 / ζ 非欠阻尼(0<ζ<1) / 解析失败 → 诚实
「未达评估条件」，`passed=false`、`error_pct=null`，绝不逢正必过、绝不编造通过
（镜像 CFD `st_oracle` 对 `st=None` 的处理哲学）。

## 诚实负例（非篡改）

`eval_cases/case_003` 喂一份 `n_steps=12` 的真实粗步长仿真产物（梯形 O(h²) 离散
误差使超调 41.5% > 2% 容差）——**无需伪造任何数字**即演示 oracle 真能拦截欠离散，
而非逢正必过。粗步长产物由 solve agent 真实产出（A-稳定不发散，故是「精度差」
而非「发散」的诚实负例）。

## 人是唯一签发者

`requires_human_review=true`：判定停 `waiting_review`，草案头强制水印「判定权在
人」，由具名工程师签发才 `completed`。

## 零内核 diff

闭式解析 oracle 内联在 `workflow.py`，不 import `backend/app/*` 任何模块——刻意
规避 `cfd_evaluate_agent` 把 `st_oracle` 放进 `backend/app/cfd/` 的先例。本发
`git diff backend/app` 为空。

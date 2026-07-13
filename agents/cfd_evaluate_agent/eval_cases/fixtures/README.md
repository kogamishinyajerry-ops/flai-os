# eval_cases/fixtures（vendored run 夹具）

`cfd_result_read` 工具（`tools_impl/cfd_result_read/adapter.py`）读取
`$FLAI_CFD_CASE_DIR/<run_id>/`，硬要求该目录下有 `.hub_run_id` sidecar +
`log.pimpleFoam` + `postProcessing/forceCoeffs1/0/*.dat`。M10 治理 eval-runner
跑 `eval_cases/*.json` 时经**真实 `runtime.execute` 全链**执行，不会替 case
造数据——case 引用的 run_id 必须在此目录下有对应真实夹具，否则
`cfd_result_read` fail-closed，case 与自身 `expected` 矛盾（本次修复的起因）。

## 来源与截取方式

两个 run 全部**逐字截取自** `backend/tests/fixtures/cfd_good_run/`（good-run-01
golden，Re=100 圆柱绕流，t=0–150s，`backend/tests/test_cfd_evaluate_agent.py` /
`tools_impl/cfd_result_read/tests/test_cfd_result_read.py` 共用同一份原始夹具）。
**截取=只删行，不改字**——保留的每一行与原始文件逐字一致，不重新生成/编造任何
数值。

### `20260713-101010/`（收敛 case，case_001 用）

- `postProcessing/forceCoeffs1/0/forceCoeffs.dat`：原文件头 9 行注释 +
  **末 2000 数据行**（t=110.02–150.0s，40 个时间单位）。
- `log.pimpleFoam`：原文件**末 400 行**（含 30 个 `Time = ` 时间步 + 结尾
  `ExecutionTime ...` / `End` 标记）。
- `.hub_run_id`：内容 `20260713-101010`（与目录名/请求 run_id 对账用）。
- 实测：`strouhal_from_cl` 在此截取窗口的尾 60% 段仍稳定给出 **3 个涡脱周期**
  （St=0.16735，n_cycles=3，与 Williamson 参考 0.164 误差 2.04%，`ended=True`）——
  达到 `st_oracle` 收敛门槛（≥3 周期），非临界编造。

### `20260713-202020/`（未收敛 case，case_002 用）

- `postProcessing/forceCoeffs1/0/forceCoeffs.dat`：原文件头 9 行注释 +
  **首 500 数据行**（t=0–9.98s，起振前的初始瞬态段）。
- `log.pimpleFoam`：原文件**头 200 行**（含 OpenFOAM 版本 banner + 12 个
  `Time = ` 时间步，无 `End` 标记——求解未完成）。
- `.hub_run_id`：内容 `20260713-202020`。
- 实测：`strouhal_from_cl` 在此窗口尾 60% 段过零点不足 3 个（n_cycles=0）→
  `converged=False`，`st=None`——诚实地板路径，非人为造假使其"看起来未收敛"。

## 运行前置（不改 runner，照 monitor_adapter_gen_agent 先例）

`cfd_result_read` 的 `FLAI_CFD_CASE_DIR` 是**进程环境变量**（与
`FLAI_MONITOR_CORE_DIR` 同型：未配即 fail-closed，见 ADR-0022 同款纪律），不是
case JSON 里能声明的字段（`monitor_adapter_gen_agent` 的 `sample_run_dir` 之所以
能做包相对路径，是因为它是**payload 字段**、由该 agent 自己的 workflow 代码
相对包目录 resolve；`cfd_evaluate_agent` 的输入只有 `run_id`，路径解析全在工具
内部，工具不改）。

跑本包 eval（无论走 `/api/agents/cfd_evaluate_agent/eval-runs` 还是本地脚本）前，
运行环境需自行：

```
export FLAI_CFD_CASE_DIR=<repo>/agents/cfd_evaluate_agent/eval_cases/fixtures
```

未设置时两个 case 都会在 `cfd_result_read` 处 fail-closed（`status: failed`），
case 断言不会假绿——`load_eval_cases`/`run_agent_evals` 不做任何环境代配，晋升
操作员按此前置自行配置（与 `monitor_adapter_gen_agent` README 记的
`FLAI_MONITOR_CORE_DIR` 前置同一纪律）。

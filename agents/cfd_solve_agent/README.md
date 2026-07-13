# cfd_solve_agent（CFD 求解发起 · fire-and-register）

CFD 真接线 **P3 求解侧**。人建任务 → 本 Agent 经 `cfd_solve_launch`（安全边界
Tool）在 `cfd-openfoam-live` 容器里发起一次**真实** OpenFOAM 求解（圆柱绕流
Re=100）→ 任务秒级 completed，求解在后台真跑约 200s → 工作台监控浮窗实时看
残差/Cl/Cd → 人看到收敛后建 `cfd_evaluate_agent` 任务承接（run_id）。

## 数据流

```
人建任务 {case: cylinder_re100}
  → workflow 生成/接受 run_id（YYYYMMDD-HHMMSS）
  → cfd_solve_launch：host 铺算例进 case/run/<run_id>/ → docker exec
    gmshToFoam+checkMesh → nohup pimpleFoam &（fire）→ 盖 .hub_run_id sidecar
  → outputs[0].sim_run_ref = cfd_openfoam@<run_id>
  → Runtime 回填 task.metadata.sim_run_ref → 浮窗深链 #/cfd_openfoam@<run_id>
  → hub cfd_openfoam adapter 只读流式解析 → 实时曲线
```

## 边界（勿破）

- **零 LLM**（`model.profile: none`）：纯 Tool 驱动，照 `performance_disk_agent`
  的 tool_automation 范式。
- **fire-and-register**：任务 completed ≠ 求解成功——completed 只表示「已发起」。
  收敛与否由监控浮窗人工观察；工程判定在 `cfd_evaluate_agent`（waiting_review
  人签）。`requires_human_review=false` 不破「人是唯一签发者」：发起动作本身
  = 人建任务的动作，签发在评估阶段。
- **发起失败诚实 failed**：容器未 up / `FLAI_CFD_*` 缺失 / 网格失败 → failed
  （Tool fail-closed，sidecar 不落，hub 不认作 run），绝不谎报已发起。
- **零删除**：每 run 新建时间戳子目录，旧 run 与 case/run 本体谁都不碰
  （bind-mount 铁律强化版，见 `cfd_solve_launch` tamper witness）。
- **run_id 注入仅供测试/重放**：`inputs.run_id` 可选（schema pattern 校验），
  生产缺省生成 UTC 时间戳。

## 运行前置

- `FLAI_CFD_CONTAINER=cfd-openfoam-live`
- `FLAI_CFD_CASE_DIR`=agent-cfd-live `case/run` 宿主绝对路径
- `FLAI_CFD_TEMPLATE_DIR`=agent-cfd-live `case/template` 宿主绝对路径
- 容器 up 且 bind-mount `case/run → /home/openfoam/run`（inspect 实测）

## ⚠ 运维红线：与 agent-cfd-live rehearse.sh 互斥（Codex R1-P1-2）

managed runs 与 agent-cfd-live 自身的 legacy 流程**共享** `case/run`
（bind-mount 固定挂该目录，他仓零改动铁律不重挂）。agent-cfd-live 的
`scripts/rehearse.sh` staging 段会 **`rm -rf case/run/*`**（实测 :78）——
会删掉全部 managed run 子目录（含 sidecar/结果，可能连活跃求解目录一起），
使已持久化的 `sim_run_ref` 深链失效、后续评估 fail-closed。

红线：**FLAi-OS managed 求解在场（跑过/在跑）期间，勿运行 rehearse.sh**。
若必须 rehearse：先确认无活跃求解（浮窗/`docker exec … pgrep`），并接受
历史 managed run 被清（评估会诚实报 sidecar 缺失，不会静默错读）。
残余风险与裁决记 ADR-0027 §三。

## eval_cases

- `case_001`：发起正常路径的期望口径（completed + sim_run_ref 落 metadata）。
  真发起需容器在场——无容器环境跑 eval 会在 Tool 处 fail-closed（这是诚实
  行为不是缺陷）；全链验证走 P4 E2E（mock docker）与真容器手动验证。

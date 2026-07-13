# cfd_solve_agent 变更记录

## 0.1.0（CFD 真接线 P3，2026-07-13）

- 初版：真实 OpenFOAM 求解发起（圆柱绕流 Re=100，fire-and-register）——经
  `cfd_solve_launch`（allow_shell_command 安全边界 Tool，Codex 异源审）在
  `cfd-openfoam-live` 容器发起 pimpleFoam，任务秒级 completed，求解后台真跑。
- 输出 `sim_run_ref=cfd_openfoam@<run_id>`，Runtime 成功路径回填
  task.metadata.sim_run_ref（metadata 标注非状态迁移，不 bump updated_at）。
- run_id：inputs 可选注入（测试/重放，pattern 校验），缺省 UTC 时间戳
  YYYYMMDD-HHMMSS（过 Tool 正则白名单 + hub newest_by_name 排序键）。
  修正 plan 原稿的 `context.run_id_seed/task_id` 方案（context 无此键且
  uuid 过不了正则）。
- requires_human_review=false：发起=人建任务的动作，签发在评估阶段
  （cfd_evaluate_agent 人签）——不破「人是唯一签发者」。
- 发起失败诚实 failed（容器/config/网格 fail-closed），绝不谎报已发起。

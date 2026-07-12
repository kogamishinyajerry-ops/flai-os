# Changelog · monitor_adapter_gen_agent

## 0.1.0 — 2026-07-12（首版，status=draft / maturity=L0）

- 首次立包（ADR-0020 R2 / ADR-0022）。「产生工作流的工作流」平台实体：给真实历史
  run 目录起草监控接入 adapter 草案（module.json.draft / parser.py.stub / REVIEW.md）。
- 承重=确定性接地侦察，经 `monitor_adapter_recon` 工具子进程调 sim-live-hub 承重核
  （接地保证由核提供，不重复实现）；核不可达即诚实 failed。
- 推理模型（profile=reasoning）仅加叙事层「生成器建议」（选择权可智能化 / 数据权
  绝不）；模型不可达时诚实降级，实质草案不受影响。
- requires_human_review=true：草案 draft 永不自动生效，注册与 tamper 实证是人的动作。
- eval_cases：case_001（正常接地路径）+ case_002（失败路径：非时间戳 run 名 →
  run_discovery 如实 UNVERIFIED 而非编造）。样本 vendored 于 eval_cases/fixtures/。
- 改动类型：新增（workflow / prompt / schema×2 / agent.yaml / eval_cases / README）。
- 依赖工具：`monitor_adapter_recon`（tools_impl，mock=false，allow_shell_command=true）。

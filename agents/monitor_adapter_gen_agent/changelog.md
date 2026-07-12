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

### 2026-07-12 · eval 覆盖深化（无行为变更，仅补回归护栏）

- case_003（失败路径·任务态）：sample_run_dir 指向不存在目录 → 工具 fail-closed →
  任务 failed，绝不空壳草案顶替。同时满足 M10 晋升门①「≥1 个 status_is failed case」。
- case_004（富结构接地）：填补 case_001/002 只覆盖 CSV 曲线的缺口——vendored 一个真实
  structopt run（density.npy 网格场 + input.json 形状源 + verification.json 校核 +
  summary.json 终止标记 + optimization_frames 帧序列，时间戳命名）。断言 module.json.draft
  逐字含 density.npy / verification.json / summary.json / optimization_frames /
  newest_by_name——任一富路径静默回归（丢 field 的 NUMPY-magic 二进制接地、漏 verification、
  漏帧目录、退化 discovery）即咬红。样本 vendored 于 eval_cases/fixtures/20260712-041500-000000/
  （checkout-independent，含真实 .npy 二进制，nelx×nely=300==数组长度内部一致）。
- eval 矩阵：正常曲线（001）· 非时间戳→UNVERIFIED discovery（002）· 不存在目录→failed（003）
  · 富结构全接地（004）。承重核零改动；本次仅在 agent 包侧增侦察证据回归网。

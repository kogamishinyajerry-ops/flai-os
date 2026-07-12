# monitor_adapter_gen_agent · 监控接入生成器 Agent

「产生工作流的工作流」的平台实体（ADR-0020 R2）。给一个新求解器/新工作流的**真实
历史 run 产物目录**，起草它接入实时可视化监控所需的全部件——**只起草，不生效**。

## 能做什么

输入 `target_repo_path` + `sample_run_dir`（+ 可选 `solver_hint`/`display_hints`/
`module_name`），产出三件草案落任务 output_dir：

- `module.json.draft`：run_discovery / truth_sources / stages / stall_timeout 骨架
- `parser.py.stub`：只读解析真源文件的起点
- `REVIEW.md`：三档接地证据（VERIFIED/PROPOSED/UNVERIFIED）+ 诚实清单 +
  生成器展示建议（叙事层）+ 放行/注册前审核指引

任务强制 **waiting_review**：工程师按诚实清单跑 tamper 实证 + 代码审后，人工注册进
监控节点（draft 永不自动生效，人是唯一签发者）。

## 分层（务必理解）

- **实质 = 确定性接地**：三档证据/module.json/parser 全部来自承重核（sim-live-hub
  `tools/adapter_gen.py`，经 `monitor_adapter_recon` 工具子进程），本 Agent 不重复
  实现、不改一字证据。**核不可达/侦察失败 → 任务 failed**（绝不空壳顶替）。
- **叙事层 = 生成器建议**（可选）：推理模型据接地报告给「当前展示什么信息量最大」的
  **选择建议**（选择权可智能化，标注为生成器建议）——**绝不生成/插值/美化任何上屏
  数值（数据权红线，docs/09 §3）**。模型不可达时诚实标注「叙述未生成」，草案实质
  仍完整交付（与 fta 不同：fta 的 LLM 是实质，本 Agent 的 LLM 只是叙事）。

## 前置与运行

- **`FLAI_MONITOR_CORE_DIR`** 必须指向监控节点仓（sim-live-hub）根目录（其下有
  `tools/adapter_gen.py`）。未配置 → 任务 failed（fail-closed，见 ADR-0022）。
- 推理模型（profile=reasoning）用于叙事层；无 key 时叙事降级，实质草案不受影响。

## 不能做什么 / 已知边界

- 不注册、不生效、不签发——永远停在 waiting_review。
- 只读侦察，对目标仓与样本目录零写入、零执行其脚本。
- 无真实样本不接单；run 目录命名不符时间戳身份判据时判 UNVERIFIED 并要求 wrapper，
  绝不硬编不可靠判据。
- PROPOSED 是结构推断非确证（glob 层级/marker 落盘顺序/帧序号→迭代号映射需人核）。

## eval_cases

`eval_cases/case_001.json`（正常路径：真实 run → 接地证据 + waiting_review）与
`case_002.json`（失败路径：run 目录命名不符身份判据 → run_discovery 如实 UNVERIFIED
而非编造）。二者 `sample_run_dir` 指向本包 `eval_cases/fixtures/` 下 vendored 样本
（`~`-绝对路径，晋升节点按实况调整）；跑 eval 需 `FLAI_MONITOR_CORE_DIR` 已配置。

# monitor_adapter_gen · 监控接入生成器 Agent 契约（草案 v0.1）

> 「产生工作流的工作流」的实体：指向一个新求解器/新工作流的真实产物，
> 起草它接入实时监控所需的全部件——**只起草，不生效**。
> 关联：ADR-0020 · docs/09 标准 · 02 Agent 包标准 · 07 评测标准。

## 1. 定位与类型

- 包名 `monitor_adapter_gen`，workflow.mode = 单轮批式（非 interactive）。
- profile = reasoning（侦察归纳+代码起草需要模型）；**requires_human_review
  恒为 true**——产物是 draft，人审 + tamper 实证通过前不得注册进监控节点。

## 2. 输入 schema（要点）

| 字段 | 必填 | 说明 |
|---|---|---|
| `target_repo_path` | ✓ | 被接入工作流的仓/目录（**只读侦察，他仓神圣**） |
| `sample_run_dir` | ✓ | 至少一个真实历史 run 的产物目录（无真实样本不接单——拒绝凭描述臆造解析器） |
| `solver_hint` | – | 引擎/求解器提示（如 "STAR-CCM+ residuals in *.csv"） |
| `display_hints` | – | 领域侧希望优先展示的量（进 stages/curves 排序建议） |

## 3. 产出（四件，全部 draft）

1. **module.json 草案**：run_discovery（时间戳目录判据；不满足时如实报
   「该工作流目录命名不符合身份判据，需 wrapper 或改造」而非硬编）、
   truth_sources、write_mode、stages、stall_timeout 建议值+依据。
2. **parser 草案**：零网络、零写目标仓；只读解析真源文件。
3. **诚实清单**：该 adapter 的 tamper 实证计划（杀进程/断源各怎么做、预期
   哪路报警咬红）+ 尚不可验证残差的显式标注。
4. **侦察证据报告**：每一项「真源在 X 文件」的声明都**逐字附上实际样本行**
   （文件路径+行内容）——防幻觉真源；引用不出样本的声明一律标 UNVERIFIED。

## 4. 红线（继承 09 标准 + 平台宪法）

- 只读侦察：对目标仓零写入、零执行其脚本（样本 run 由人类提供，不现场跑）。
- 产物 draft 永不自动生效：注册动作只能由人完成（人是唯一签发者）。
- 展示选择建议属叙事层：display_hints 的采纳结果标注「生成器建议」。
- 证据报告里的样本行必须能在 sample_run_dir 逐字找到（评测 case 咬合此项）。

## 5. 治理轨道（复用现成的门，不新造）

L0 draft（本 agent 产出）→ 人审（adapter 代码审 + 按诚实清单跑 tamper 实证，
双向：真跑绿 + 篡改红）→ 注册进监控节点 config → 按 07 标准固化评测 case
（含至少一条失败路径：给残缺 sample_run 必须报 UNVERIFIED 而非编造）→
M10 晋升门 L1。**跳过实证的 adapter = 把假绿批量化，fail-closed 拒绝。**

## 6. 实现状态

本文为契约草案（ADR-0020 R2 相），实现未开工。开工前置：R1 相收口
（M11 鉴权 → verify_all → 转正批），届时按 02 标准立包。

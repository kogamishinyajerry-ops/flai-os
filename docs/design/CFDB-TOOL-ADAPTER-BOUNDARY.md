# cfdb → FLAi-OS 域判决层对接边界设计（一页）

> 状态：**PROPOSAL — 待 owner 批准，未实施任何代码**（批准后转正式 ADR 编号，作为 `allow_shell_command: true` 的依据 ADR）
> 对象：`~/projects/cfd/GLM-CFD-Benchmark`（下称 cfdb，HEAD afb3955，913 测试绿亲验 2026-07-11）
> 依据：docs/03 Tool Package 标准 · docs/07 Eval 标准 · ADR-0015 Wave 1 跨仓路由裁决先例
> 裁决口径：Wave 1 同款——逐候选判目标形态，判决 ∈ {CONDITIONAL, REJECT_DUPLICATE, REJECT_OUT_OF_SCOPE}，条件不满足即不实施
> 审查：loop-auditor Mode A R0 判 BLOCK（3P1+4P2+1P3），findings 经 grounded 复核全坐实并已落地本版（见 §9）

## 1. 一句话定位

cfdb 以**外部域裁判所**身份对接：FLAi-OS 管「任务怎么跑、谁签发」，cfdb 管「CFD 数值配不配叫验证过」；两套信任机制各守各层，**永不合流**。

## 2. 信任边界（三条铁律，全设计围绕它）

1. **cfdb 只有否决权，没有放行权**：其判决只作为 `tool_runs`/`task_events` 里的证据数据留痕，绝不直接把 task 置为「通过」。
   **运行时落点（P1-1）**：平台现行机制是 agent 级静态布尔（`runtime.py:446` 仅显式 `False` 跳审）——不存在「按 verdict 动态升审」的能力。因此硬约束：**任何消费 cfdb 判决的 Agent，`agent.yaml.workflow.requires_human_review` 必须静态声明 `true`，禁止 `false`**；verdict 字段只是呈给签发人的证据，不驱动任何状态跳转。若未来需要「PASS 自动放行」的动态语义，必须先新增 runtime 能力并另立 ADR——本设计不默许。
2. **否决方向 fail-closed 自由**：cfdb 非 PASS（含 exit 2/3、超时、输出不可解析、环境缺失）→ 证据如实进 waiting_review 呈签发人；工具层面一律 `status: failed` 或显式 verdict，绝不静默降级、绝不跳过。
3. **放行唯一路径不变**：`waiting_review` → 人具名签发（宪法「人是唯一签发者」零改动）。cfdb PASS 只是呈给签发人的一条证据行。

## 3. 边界图

```text
┌───────────────── FLAi-OS（运行底座 · 平台信任边界唯一）──────────────────┐
│                                                                          │
│  cfd 类 Agent（requires_human_review: true 静态钉死）                     │
│       │ tools 白名单                                                      │
│       ▼                                                                   │
│  Tool Registry ──input_schema 校验──▶ cfd_benchmark_* adapter             │
│                                          │ ①版本核验 ②argv-list          │
│                                          │ subprocess（无 shell 插值）    │
│       ┌──────────────────────────────────┘                                │
│       ▼                                                                   │
│  waiting_review（一切结果必到此，verdict 只是证据行）                       │
│  人签 = 唯一放行                                                           │
│                                                                            │
│  tool_runs / task_events 留痕：verdict · ruler_id · cfdb_sha · 产物路径    │
└───────────────────────────────────────────────────────┬──────────────────┘
                            版本钉死：tool.yaml.version 绑 cfdb git SHA
                            ruler_id / baseline sha 仓外留痕（补 cfdb 残差②）
┌───────────────────────────────────────────────────────▼──────────────────┐
│ cfdb（外部域裁判所 · 独立仓 · 数据 SSOT 绝不复制进平台）                    │
│   cases/（出处 sha256 锚+诚实分级） baselines/（人签晋升）                 │
│   agentbench/（冻结尺子, 改尺=exit 3） failures/（append-only 失败库）     │
│   cfdb run / gate / agent-eval —— 重算不信自报 · fail-closed exit 码       │
└───────────────────────────────────────────────────────────────────────────┘
```

## 4. 路由裁决表（Wave 1 同款，逐候选）

枚举方法（P3-8）：基于 `cli.py` 源码逐命令核对（21 个子命令，含 data/failures/baseline/agent-eval 四个子命令组展开）+ 2 个非 CLI 面（内核代码、数据资产），归并为 12 候选面，与源码严格对账（复审 R2 核实）。

| # | cfdb 候选面 | 目标形态 | 判决 | 理由 / 条件 |
|---|---|---|---|---|
| 1 | `cfdb run`（case 真跑管线） | tool_package `cfd_benchmark_run` | **CONDITIONAL** | 未来 cfd 类 Agent 的执行工具。条件：①内网 docker/OpenFOAM 侦察回（M4 同款，§7）②该 Agent 立项获批——**当前无消费者，不提前实施**。adapter 禁传 `--dry-run`（见 §5） |
| 2 | `cfdb gate`（回归判决） | tool_package `cfd_benchmark_gate` | **CONDITIONAL** | 域数值判决≠平台放行判决，按 §2 铁律降格为证据工具后不构成双轨。条件：与 #1 同批；`run_id` 参数域收窄为**同任务内 #1 的输出**，禁外部/历史 run_id（P2-6，§6 成立前提） |
| 3 | `cfdb agent-eval score/ledger`（冻结尺子打分） | **evals/ 层资产**（非 runtime 工具） | **CONDITIONAL** | 评分对象是 Agent 产出本身，属 docs/07「固定用例回归」的域深化；做成 runtime 工具会诱导 agent 自打分自宣 verified（假绿面）。只由 CI/人触发。条件：cfd Agent 有 eval_cases 需求时 |
| 4 | `cfdb provenance`/`trust`/`baseline list`（只读审计/画像/基线清单） | 不单独立工具 | **REJECT_DUPLICATE**（作为独立工具） | 工具一事一 canonical：honesty 等级/画像/基线信息作为 #1/#2 输出 schema 的透传字段 |
| 5 | `cfdb failures`（失败库维护） | 留 cfdb 仓内 | **REJECT_OUT_OF_SCOPE** | cfdb 侧数据资产运维；FLAi-OS 失败沉淀走自己的 eval_cases 纪律（docs/07 §4），不双轨 |
| 6 | cfdb 内核代码（runner/adapters/schema） | 不收编 | **REJECT_DUPLICATE** | ADR-0015 收编的判据是孵化仓生命周期独立+离线打包成本，且对象是无状态算法（BM25/chunking），用 golden 差分钉等价；cfdb 是带有状态真值资产（baselines/rulers/失败库）的活平台，复制=fork 真值集。对接走 subprocess 边界，等价保险改用 smoke-case 契约测试（§5，P2-7） |
| 7 | `cfdb showcase` + `report`/`compare`/`report-sweep`（展示与聚合报告） | — | **REJECT_OUT_OF_SCOPE** | 汇报物/跨 run 聚合展示，与平台运行时判决无关；需要时人在 cfdb 侧跑 |
| 8 | `cfdb baseline promote` / `agent-eval init`（锚定类人签动作） | 永留 cfdb 侧人工 CLI | **REJECT**（结构性） | 晋升 baseline / 冻结尺子是**人签动作**，工具化=把签发动作暴露给 agent 可触发面，直接违反「人是唯一签发者」。`init --force`（改尺）同理绝不进 Registry |
| 9 | baselines/rulers 数据资产 | SSOT 留 cfdb | **REJECT_DUPLICATE** | 真值集单一来源；FLAi-OS 只在 task_events 仓外留痕 ruler_id/baseline sha（恰好补 cfdb「仓写边界」残差） |
| 10 | `cfdb serve`（web dashboard，常驻 HTTP 服务） | — | **REJECT_OUT_OF_SCOPE** | 长驻网络服务与「每次调用独立工作目录+超时」的 safety 语义天然冲突（孤儿进程面）；**adapter 层显式禁止拉起该子命令** |
| 11 | `cfdb data status/pull`（拉取参考数据） | — | **REJECT_OUT_OF_SCOPE** | 涉外部数据源拉取，撞内网零外呼红线；参考数据以 cfdb 仓内已锚定文件为唯一来源 |
| 12 | `list-cases`/`validate-case`（前置校验） | 并入 #1 adapter 内部预检 | **REJECT_DUPLICATE**（作为独立工具） | 校验属 run 的前置步骤，独立成工具徒增 Registry 面 |

结论与 Wave 1 同构：**12 候选面仅 3 个够格，且全 CONDITIONAL**——本设计批准 ≠ 任何一项开工。

## 5. 工具契约要点（实施时的钉死项）

- `tool.yaml`：`type: python_adapter`；`mock: false`（真跑真判，无 mock 变体——mock 的 CFD 判决没有意义）；`version` 升版必须同步记录所绑 cfdb git SHA。
- **版本核验前置（P2-5）**：adapter 每次调用先比对宿主 cfdb 版本/SHA 与 `tool.yaml` 声明，不匹配 → `status: failed`，绝不静默用漂移版本出判决。
- `safety`：`require_workspace_isolation: true`（`--runs-dir` 指向 `data/task_runs/<task_id>/`，cfdb 原生支持）；`allow_shell_command: true` **以本 ADR 为依据**，adapter 限定 argv-list subprocess（禁 `shell=True`，禁字符串拼接命令，禁拉起 `serve`）；`save_raw_files: true`（manifest.json/metrics.json 全量落盘）。
- **判决映射分两张表，绝不混用（P1-3，已对 cli.py 源码核实）**：
  - `cfd_benchmark_run`（exit 二值，cli.py:256）：exit 0 **且** manifest.status == "success" → `status: success`；exit 0 但 status == "dry_run" → `status: failed` + 显式原因「dry run 未执行任何求解」（cfdb 自家纪律：dry run 不算 verified pass；adapter 本就禁传 `--dry-run`，此为双保险）；exit 1 → `status: failed` + manifest.status/stderr 摘要。**不产出 `verdict` 字段**——run 阶段没有和 baseline 比对过，借用 REGRESSION 语义=向签发人递假证据。
  - `cfd_benchmark_gate`（exit 四值，cli.py:1188）：0→`PASS`；1→`REGRESSION|INVALID_RUN`；2→`NO_BASELINE`；3→`TAMPERED`；**其余一切**（未知码/超时/stdout 不可解析/cfdb 不存在/版本核验不过）→ `status: failed`，绝不映射为任何 verdict。
- **契约测试（P2-7，「依赖而非复刻」路线的等价保险）**：用 cfdb 自带 4 个 smoke case（mock_success/mock_failure/mock_missing_reference/mock_missing_qoi）在 FLAi-OS 侧建契约测试，钉住 exit→verdict 解析行为；cfdb SHA 升版必跑——对称于 ADR-0015 用 golden 差分钉复刻算法。
- LLM 位置：**判决链全程无 LLM**（cfdb 判决是确定性重算，adapter 是确定性转换）；LLM 只能在下游消费判决数据写草案，草案照常水印+人签。

## 6. 双向增益（为什么这样接是 1+1）

- **平台补 cfdb 最大残差（提交真实性）**：cfdb 自己验不了「数值是不是真跑出来的」；接入后 CFD 运行发生在平台任务链内，`tool_runs` 落盘+事件链留痕 = 提交来源可审计。**成立前提 = §4#2 的 run_id 域收窄**（gate 只吃同任务内刚产出的 run）；缓解而非消除，以平台审计边界为限，如实声明。
- **cfdb 补平台域判决空缺**：docs/07 三类 eval 中「固定用例回归」在 CFD 域的深化（出处分级/QoI 重算/冻结尺子）不必平台自建，直接消费经三线对抗审的现成实现。

## 7. 实施前置侦察项（未回不实施，不静默 mock）

1. 内网 Windows 有无 docker/OpenFOAM 镜像可用（cfdb 真跑硬依赖；本机 mac docker 已验 ~3.4s cavity，**公网≠内网**）。
2. `cfdb gate`/`run` 的机器可读输出形态（是否有 `--json`；无则 adapter 解析 exit code+产物文件 manifest.json/metrics.json，**不 parse 人类可读 stdout**）——实施前在 cfdb 仓核实/补齐。
3. cfd 类 Agent 的真实需求锚（FDE 需求池 S 簇「仿真批量」3 条暂缓中，等内网工具侦察）。

## 8. tamper witness 承诺（实施批收口 gate，落点具名）

落点：`agents/<cfd_agent_id>/eval_cases/case_tamper_baseline/` 等。命题按 P2-4 校正——`requires_human_review` 静态 true 后「TAMPERED 不 completed」恒真无咬合价值，真正要咬的是**证据保真链**：

1. 篡改 baseline 锚定文件一字节 → `tool_runs.output_json.verdict == "TAMPERED"` 且该字段在 waiting_review 呈签发人的数据中逐字可见（未被吞、未被 LLM 摘要覆盖/改写）。
2. adapter 收到未知 exit code → `status: failed`，绝不出现任何 verdict 值。
3. 消费 cfdb 的 agent.yaml 被改为 `requires_human_review: false` → 契约测试必红（结构冻结，同 M4 白名单冻结测试同款）。

无咬合实证不收口——「全绿」不算数。

## 9. 审查记录

- **R0（2026-07-11）loop-auditor Mode A：BLOCK**。3P1（否决权无运行时落点/裁决表漏 6+ 候选面含 serve/exit 码映射混用 run 与 gate）+ 4P2（witness 空泛、版本核验缺失、提交真实性前提未写明、Wave 1 类比引用不精准）+ 1P3（枚举方法论未标注）。
- **R1（同日）**：主控对三条 P1 逐条 grounded 复核坐实（runtime.py:445 静态布尔 ✓ / cli.py 16 子命令 ✓ / run 二值退出码 cli.py:256 ✓），并增抓一处审计未点名的洞：`run` 对 dry_run 也退 0，已并入 §5 双保险。全部 8 findings 落地本版。
- **R2（同日）loop-auditor Mode A 复审：APPROVE**。三条 P1 经源码级复核确认真闭合（runtime.py:446 / cli.py 21 命令 / schema.py:313 四值 status）；dry_run 双保险溯源 `runner.py:260-271` 确认为真纵深防御非掩洞；新增 #8 行判定自洽。残留 2 条 P3 精度瑕疵（行号/计数/baseline list 归桶）已在本版逐字落地。
- 残差诚实声明：本文档仍为设计声明，零行为证据；§8 witness 是实施批的收口 gate，不是本批的已验事实。cfdb 账本完整性仍是进程级 append-only；NACA 系列尚需 y+/GCI 网格研究才可宣称验证，接入不抬升其证据等级。

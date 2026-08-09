# SWE-CI 官方项目核验与 FLAi-OS 最小接入评估

> 核验日期：2026-07-26（Asia/Shanghai）
> 范围：只读研究；未安装依赖、未下载任务镜像、未运行 SWE-CI、未进行任何外部写入。
> 结论等级：`RESEARCHED / NOT-INTEGRATED`

## 1. 执行结论

用户所说的最新开源项目可准确对应为
[SKYLENAGE-AI/SWE-CI](https://github.com/SKYLENAGE-AI/SWE-CI)，论文为
[arXiv:2603.03823v4](https://arxiv.org/abs/2603.03823v4)，官方数据集为
[skylenage-ai/SWE-CI](https://huggingface.co/datasets/skylenage-ai/SWE-CI)。

SWE-CI 是**研究型代码维护基准和实验 harness**，不是可以直接装进现有仓库的通用 CI
产品。它最值得 FLAi-OS 吸收的是：

1. 确定性测试系统与改码 Agent 分离；
2. 每轮从失败证据中只提炼 1–5 个最紧迫需求；
3. 保存逐轮验证结果，而不是只展示最后一次绿灯；
4. 显式观测回归，尤其是 `Zero-regression`；
5. 将“运行完成”“测试通过”“人工签发”保持为三个不同事实。

推荐只做一个 **SWE-CI-inspired、本地、只读证据门**：复用
`scripts/verify_all.sh/.ps1`，冻结提交 SHA、验证清单摘要、命令、退出码、逐门结果与日志摘要，
形成不可变迭代记录；由确定性验证器计算回归和趋势，Agent 只能消费证据，不能自报绿色，
人仍是唯一签发者。

**不建议**直接引入官方约 50 GB 数据、预构建 Docker 镜像、OpenCode/iFlow harness、
外部 LLM 密钥路径、自动需求生成器或 20 轮执行编排。这样会产生第二套运行时/调度语义，
并把未充分加固的容器、供应链和秘密管理边界带入 FLAi-OS。

## 2. 身份、版本与当前快照

### 2.1 代码仓库

| 项 | 核验结果 |
|---|---|
| 官方仓库 | `SKYLENAGE-AI/SWE-CI` |
| 默认分支 | `main` |
| 截止核验日 HEAD | `b2a0620f0168a5a89681be7919a98d9a49ab22af` |
| HEAD 时间 | 2026-06-10 16:36:29 +08:00 |
| HEAD 说明 | `chore(readme): update readme` |
| 软件许可证 | Apache License 2.0 |
| tags / releases | 未发现 tag；官方 Releases 页面显示无 release |

HEAD 由官方 Git remote 的 `git ls-remote` 与浅克隆交叉核验；可直接查看
[固定提交](https://github.com/SKYLENAGE-AI/SWE-CI/commit/b2a0620f0168a5a89681be7919a98d9a49ab22af)、
[该提交文件树](https://github.com/SKYLENAGE-AI/SWE-CI/tree/b2a0620f0168a5a89681be7919a98d9a49ab22af)、
[Apache-2.0 LICENSE](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/LICENSE)
与[空 Releases 页面](https://github.com/SKYLENAGE-AI/SWE-CI/releases)。

因此，不应把数据集的 `2.0.0` 当成代码仓库的软件 release。代码仓库没有可消费的语义版本
或发布工件，接入评估必须固定到完整 commit SHA。

### 2.2 论文

论文最初提交于 2026-03-04，当前公开版本是 2026-04-01 的 v4；v4 描述的是 100 个任务、
平均 233 天和 71 个连续提交的 V1 研究基准，而不是后续数据集 V2 的全部内容。
来源：
[arXiv 版本记录与摘要](https://arxiv.org/abs/2603.03823v4)、
[v4 HTML 全文](https://arxiv.org/html/2603.03823v4)。

### 2.3 数据集 V2.0.0

官方 Hugging Face 数据集固定快照为
`766e41b3a2606f220d30b9ae27f3bb68b262c611`，数据卡声明版本 `2.0.0`，
最后更新时间为 2026-04-20。数据卡的发布说明称 V2 在 V1 基础上新增 126 个任务，并增加
`default_v2`。

固定来源：

- [V2 数据卡](https://huggingface.co/datasets/skylenage-ai/SWE-CI/blob/766e41b3a2606f220d30b9ae27f3bb68b262c611/README.md)
- [`default.csv`](https://huggingface.co/datasets/skylenage-ai/SWE-CI/blob/766e41b3a2606f220d30b9ae27f3bb68b262c611/metadata/default.csv)
- [`default_v2.csv`](https://huggingface.co/datasets/skylenage-ai/SWE-CI/blob/766e41b3a2606f220d30b9ae27f3bb68b262c611/metadata/default_v2.csv)
- [`full.csv`](https://huggingface.co/datasets/skylenage-ai/SWE-CI/blob/766e41b3a2606f220d30b9ae27f3bb68b262c611/metadata/full.csv)
- [`lite.csv`](https://huggingface.co/datasets/skylenage-ai/SWE-CI/blob/766e41b3a2606f220d30b9ae27f3bb68b262c611/metadata/lite.csv)

对固定 CSV 实际计数为：

| split | 数据行数 |
|---|---:|
| `default` | 100 |
| `default_v2` | 100 |
| `full` | 226 |
| `lite` | 50 |

数据卡正文仍残留“full 共 137 个任务”的旧句子，但实际 `full.csv` 是 226 行，与
“V1 100 + 新增 126”一致。这一上游文档漂移说明：任何未来实验都必须同时固定数据 commit、
split 名称和 CSV 摘要，不能只记录“V2”。

## 3. 官方架构与运行方式

### 3.1 核心闭环

官方工作流是：

```text
base commit + target tests
        │
        ▼
external pytest → 非通过测试证据
        │
        ▼
Architect Agent → 1–5 个高优先级 requirement.xml 项
        │
        ▼
Programmer Agent → 只修改候选源码
        │
        ▼
external pytest → 保存本轮结果与候选代码
        │
        └───────── 最多重复 20 epochs，或 test gap = 0
```

论文对双角色职责和 CI-loop 的定义见
[§3.2 Dual-agent evaluation protocol](https://arxiv.org/html/2603.03823v4#S3.SS2)；
固定 README 也明确描述
[Architect / Programmer / Run Tests → Define Requirements → Modify Code](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/README.md#L14-L24)。

### 3.2 初始化

每个任务携带 `code.zip`、`image.tar.gz`、base/current SHA、target SHA 和 test gap。初始化器：

1. 解包同一 Git 仓库并分别 checkout base 与 target；
2. 从 base 删除原测试，再把 target 测试复制到 base；
3. 在 Docker 中分别运行 current 和 target 的 pytest；
4. 计算 target 通过而 current 未通过的测试集合；
5. 写初始 `iteration.jsonl`。

来源：
[`initialize.py`](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/src/swe_ci/benchmark/initialize.py#L25-L124)。

注意：若实际 test gap 与 metadata 不一致，当前实现只记 warning 而继续，不是 fail-closed
（同文件 105–108 行）。这个行为不能移植到 FLAi-OS。

### 3.3 逐轮演化

每个任务通过非阻塞文件锁避免重复执行；每轮构建 Agent 镜像、让 Architect 生成
`requirement.xml`、让 Programmer 改码，再由外部 pytest 验证。有效轮次会归档前一份
`current`，提升新的候选为 `current`，并追加 `iteration.jsonl`。

来源：
[`run.py`](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/src/swe_ci/benchmark/run.py)、
[`prompt.jinja2`](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/src/swe_ci/benchmark/prompt.jinja2)。

配置支持：

- Agent：OpenCode（默认）或 iFlow；
- 模式：TDD 或 RDD；
- 初始化并发：16；
- 演化并发：16；
- 最大演化轮数：20；
- Architect / Programmer 单次超时各 3600 秒、最多各重试 10 次；
- pytest 单次超时 3600 秒。

来源：
[`config.toml`](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/config.toml#L1-L44)。

### 3.4 “1–5 个 requirements”的真实含义

Architect 从全部失败中筛选最关键的 1–5 项，每项包含位置、问题描述、行为合同/规格及
验收标准。Programmer 不能改 requirement 文件；TDD 模式不能改测试；两种角色均被提示
不要主动运行测试，测试由外部 harness 执行。

这是一项很适合吸收的**开发流程约束**，但目前主要由 prompt 声明，不是强制授权系统。
来源：
[`prompt.jinja2`](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/src/swe_ci/benchmark/prompt.jinja2#L1-L146)。

## 4. 指标与可采用语义

论文定义 Normalized Change 与带未来权重的 EvoScore：

- 改善时，以 base 到 target 的总 test gap 归一化；
- 低于 base 时，以 base 原有通过数归一化，显式计入回归；
- EvoScore 汇总各轮 normalized change；论文允许 `γ ≥ 1`，更高 `γ` 更重视后期；
- Zero-regression 表示整个演化过程中从未出现通过数下降。

来源：
[Normalized Change 与 EvoScore](https://arxiv.org/html/2603.03823v4#S2)。

当前开源汇总实现实际输出：

- `EvoScore(γ=1)`；
- `Resolved`；
- `Zero_reg.`；
- `ZRR = Resolved AND Zero_regression`。

来源：
[`benchmark/summarize.py`](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/src/swe_ci/benchmark/summarize.py#L45-L103)。

对 FLAi-OS 的边界：

- 可采用 `Zero-regression` 和逐轮 named-gate 变化；
- 只有在 baseline、目标 gate 集、分母与验证版本全部冻结时，才可计算
  `normalized_progress`；
- 没有官方 target/oracle 时，不得把普通主线开发趋势称为官方 `EvoScore`；
- 指标只能是质量证据，不能变成人工签发、晋升或“适航/合规”结论；
- collection error、timeout、缺报告、清单漂移都必须是 `unknown/failed`，绝不能算通过。

## 5. 许可证与供应链边界

### 5.1 许可证不是单一 Apache-2.0

- SWE-CI **框架源码**：Apache-2.0；
- 数据集 metadata：数据卡声明 CC BY 4.0；
- `code.zip`：各原始仓库自己的许可证；
- `image.tar.gz`：编排/环境配置声明 Apache-2.0，但 OS、系统库和预装包各自受上游许可证
  约束。

来源：
[代码 LICENSE](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/LICENSE)、
[数据集 Licensing 章节](https://huggingface.co/datasets/skylenage-ai/SWE-CI/blob/766e41b3a2606f220d30b9ae27f3bb68b262c611/README.md)。

因此，“SWE-CI 是 Apache-2.0”只对框架源码成立。若复制任务源码或镜像，仍必须逐项做
NOTICE、原仓库许可证和镜像组件审查。

### 5.2 依赖

Python 侧仅有 8 个直接依赖并固定版本，但无 hash lock：
[`requirements.txt`](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/requirements.txt)。

Agent Dockerfile 在构建时执行在线 `apt-get`、从 nodejs.org 下载 Node tarball，并通过
`npm install -g` 安装 Agent CLI；npm 包名默认没有固定版本，也没有看到 Node tarball
checksum、SBOM 或签名验证：

- [`Dockerfile.opencode`](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/src/swe_ci/benchmark/agents/Dockerfile.opencode)
- [`Dockerfile.iflow`](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/src/swe_ci/benchmark/agents/Dockerfile.iflow)
- [`config.py` 默认版本与包名](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/src/swe_ci/config.py#L103-L131)

### 5.3 容器与秘密边界

当前源码显示：

- OpenCode 配置使用 `"permission": "allow"`，并将 API key 写入容器内 auth 文件；
- iFlow 配置写入 API key，且设置 `"sandbox": false`；
- `docker run` 有 CPU/内存/I/O 可选限制，但未看到默认 `--network none`、只读根文件系统、
  非 root 用户、capability drop、PID 限制或独立 seccomp 配置；
- 任务预构建镜像通过 `docker load` 导入并执行；
- 数据集 metadata 提供 `image_sha`/`code_sha`，但当前下载和初始化路径未看到对两者进行
  摘要校验。

固定源码：

- [`agents/opencode.py`](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/src/swe_ci/benchmark/agents/opencode.py#L16-L67)
- [`agents/iflow.py`](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/src/swe_ci/benchmark/agents/iflow.py#L9-L31)
- [`utils/docker.py`](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/src/swe_ci/benchmark/utils/docker.py#L81-L120)
- [`download.py`](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/src/swe_ci/download.py#L9-L71)

这些设计可用于隔离的研究机实验，不能直接作为 FLAi-OS 内网生产/开发执行边界。
Prompt 中写“不得改测试”“不得跑测试”也不能代替确定性的文件权限和执行授权。

### 5.4 假绿与无限重试风险

官方入口在初始化不完整时打印失败后调用 `exit(0)`，随后阶段则
`while not run_tasks(): pass`：
[`evaluate.py`](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/src/swe_ci/evaluate.py#L1-L10)。

此外，“达到最大 epochs”是运行终止条件，不等价于 test gap 清零。对于基准实验，这可以
通过后续指标区分；对于 FLAi-OS，若直接把进程退出或任务完成映射为绿色，会违反
fail-closed 与“假绿死罪”。任何接入都必须按真实 gate 结果判定，初始化失败必须非零退出，
重试必须有显式预算和终止原因。

## 6. FLAi-OS 最小接入面

### 6.1 建议接入：本地证据观察器，而非上游 harness

第一阶段建议保持 `monitor-only`，不修改运行时和晋升状态机：

```text
Codex 实施候选变更
        │
        ▼
现有 scripts/verify_all.sh 或 .ps1
        │
        ▼
本地确定性观察器
  - 冻结 baseline/candidate commit
  - 冻结 gate manifest digest
  - 记录命令、工具版本、exit code
  - 记录每个 named gate 的 pass/fail/error/unknown
  - 哈希日志与 artifact root
        │
        ▼
append-only iteration evidence
        │
        ├─ 回归：RED
        ├─ 缺证/漂移：AMBER
        └─ 全门通过：只能形成 REAL 验证证据
                    （不替代 teal 人签）
```

建议最小字段：

```text
schema_version
work_item_id
iteration
baseline_commit
candidate_commit
gate_manifest_digest
verifier_command
verifier_version
started_at
finished_at
exit_code
gate_results[]
previously_passing_now_failed[]
artifact_root
log_sha256
status = passed | failed | error | unknown
```

该合同应先通过 ADR/冻结工作项批准；本研究不授权新增持久化 schema。

当前 R0 候选进一步收窄为本地 POSIX 开发观察器：只有平台提供 race-safe `dir_fd`、
`O_DIRECTORY` 与 `O_NOFOLLOW` 时才读取日志，并以打开文件后的物理身份拒绝大小写别名或
硬链接复用；Windows 会 fail-closed，不属于本切片的可用平台。未来 `.ps1` producer 需要另行
冻结安全文件打开与退出码归一化合同，不能把 POSIX 测试结果外推为 Windows 已可用。

### 6.2 可直接借鉴的控制

| SWE-CI 思想 | FLAi-OS 采用方式 |
|---|---|
| Architect / Programmer 分离 | 需求/审阅者只能生成可审草案；实现 Agent 改码；确定性 harness 独立验证 |
| 每轮 1–5 个 requirements | 延续小切片、明确文件范围、机械验收、避免一次铺开 |
| Agent 不自行运行/裁决测试 | 验证命令由外部门执行；Agent 不可写 gate 结果 |
| iteration history | 追加不可变证据，绑定 commit 与 manifest digest |
| Zero-regression | 比较相同 named gate；任何原通过项变失败即红 |
| Resolved + Zero-regression | 可形成组合质量事实，但不得映射为人工批准 |
| max epochs / retry budget | 有限、显式、记录终止原因；绝不无限重试 |

FLAi-OS 已有 `scripts/verify_all.sh/.ps1`、不可变 eval snapshot/digest 和证据链，优先复用这些
seam，不建立第二个任务队列、第二个调度器或第二套“绿色”语义。相关本地约束见
[`ADR-0029`](../adr/ADR-0029-governance-and-evaluation-gap-closure.md)。

### 6.3 暂不采用

1. 不 vendor、安装或 import SWE-CI Python 包；
2. 不下载约 50 GB 数据集、`code.zip` 或 `image.tar.gz`；
3. 不 `docker load` 上游任务镜像，不执行第三方历史仓库代码；
4. 不接 OpenCode/iFlow harness，不新增外部 LLM API key；
5. 不把 target/oracle 测试复制进 FLAi-OS 主线；
6. 不允许 Agent 自动生成的 requirement 替代 GitHub issue、冻结合同或 owner 决策；
7. 不采用 `exit(0)` 失败、无限 retry、warning-only digest/gap mismatch；
8. 不以 EvoScore、Resolved、ZRR 自动晋升、自动签发或生成绿色；
9. 不宣称 FLAi-OS “通过 SWE-CI”——未运行固定官方 split 就不能作此结论；
10. 不因 SWE-CI 使用 Docker 就改变 FLAi-OS 当前 Windows 内网部署主线。

## 7. 推荐实施顺序

1. **R0 / 只读证据合同**：先冻结本地 iteration evidence 字段、状态语义和负例；不引入
   SWE-CI 依赖。
2. **R1 / verify_all 适配**：让 `.sh/.ps1` 产生同构、机器可读的 named-step 结果和非零失败；
   原有人工可读汇总保留。
3. **R2 / 回归观察**：只计算 `previously_passing_now_failed`、连续无回归轮数和显式 unknown；
   先观察，不改晋升逻辑。
4. **R3 / 主线 gate**：在足够样本验证无假绿后，才考虑“检测到真实回归则阻止下一轮自动
   推进”；解除仍需修复或人工明确决策。
5. **独立研究实验（可选）**：若未来确需跑官方 SWE-CI，在隔离 Linux 研究机、固定 code/data
   SHA、无敏感源码、最小权限、出网受控、临时密钥与完整许可清单下另立项目，不进入
   FLAi-OS 运行时。

## 8. 验收与停止条件

本地最小接入只有在以下条件同时满足时才可称“可进入实现”：

- `.sh` 与 `.ps1` 产生同构机器证据；
- baseline、candidate、gate manifest 和日志摘要可复算；
- collection error、timeout、缺字段、清单漂移均 fail-closed；
- Agent 无法写入或覆盖验证结果；
- completed 不自动变绿；
- human signoff 与 REAL test evidence 分槽显示；
- 不新增 Docker、OpenCode/iFlow、Hugging Face 或 LLM SDK 依赖；
- 不改变现有公开 API、持久化 schema、任务状态机或晋升合同，除非另有批准。

出现以下任一情况应停止：

- 需要把 SWE-CI 官方镜像或第三方源码送入现有开发/生产主机；
- 需要在命令行、配置仓或日志中持久化 API key；
- 指标分母或 gate manifest 无法冻结；
- 只能从自然语言日志猜测测试结果；
- 任何方案试图让 Agent 自签或把“达到轮数上限”显示为成功。

## 9. 第一方来源清单

1. [官方 GitHub 仓库](https://github.com/SKYLENAGE-AI/SWE-CI)
2. [固定代码提交 b2a0620](https://github.com/SKYLENAGE-AI/SWE-CI/commit/b2a0620f0168a5a89681be7919a98d9a49ab22af)
3. [固定 README](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/README.md)
4. [固定源码树](https://github.com/SKYLENAGE-AI/SWE-CI/tree/b2a0620f0168a5a89681be7919a98d9a49ab22af/src/swe_ci)
5. [官方 Apache-2.0 LICENSE](https://github.com/SKYLENAGE-AI/SWE-CI/blob/b2a0620f0168a5a89681be7919a98d9a49ab22af/LICENSE)
6. [官方 Releases 页面](https://github.com/SKYLENAGE-AI/SWE-CI/releases)
7. [官方数据集固定快照](https://huggingface.co/datasets/skylenage-ai/SWE-CI/tree/766e41b3a2606f220d30b9ae27f3bb68b262c611)
8. [官方 V2.0.0 数据卡](https://huggingface.co/datasets/skylenage-ai/SWE-CI/blob/766e41b3a2606f220d30b9ae27f3bb68b262c611/README.md)
9. [官方论文 v4 摘要页](https://arxiv.org/abs/2603.03823v4)
10. [官方论文 v4 HTML](https://arxiv.org/html/2603.03823v4)

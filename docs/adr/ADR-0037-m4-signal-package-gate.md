# ADR-0037：M4 信号包 fail-closed 机械 gate

- 状态：Accepted（M4 前侦察仪器；不解冻 P2.5–P2.8）
- 日期：2026-07-20
- 关联：ADR-0035、ADR-0036、`docs/COMPOUNDING-M4-REBASELINE.md`、
  `docs/M4_intranet_day1_recon_checklist.md`

## 背景

M4 现场侦察已有 23 个必填项、三值结果和五组特殊 owner/政策判据，但此前只有 Markdown
描述。人工阅读容易产生四类假绿：用可选项补必填项、把 `unknown` 当成否、只填证据路径不查
字节、以及把「没有第二模型家族」当成天然完成。`not_applicable` 与普通负结果的补偿语义也未
完全展开，无法稳定地机械派生 `M4_SIGNAL_PACKAGE_COMPLETE`。

本 ADR 只安装一只 M4 前侦察仪器。它不采集或生成现场事实，不修改产品 schema/状态机，不实现
冻结中的收件箱、会话生命周期、课题空间或 Open Design 生产流水线。

## 决策

### 1. 单一 JSON 合同，布尔只由评估器派生

`contracts/m4-signal-package.schema.json` 是输入形状 SSOT，固定 23 个必填 item，并允许
`1-7/3-3/3-4/4-4` 作为不计入分母的可选侦察。合同拒绝额外顶层字段，因此输入不能自报
`M4_SIGNAL_PACKAGE_COMPLETE=true`。

唯一语义实现是 `backend.app.governance.m4_signal_gate.evaluate_signal_package`。CLI、测试和
以后任何只读展示只能消费该实现，不复制完成谓词。输出固定携带 exact 输入文件的 SHA-256、
逐条 finding 和显式布尔；仅当 `report.complete is True` 时退出 0。

### 2. evidence 必须在本地受控镜像中可复算

输入 package 只接受不超过 2 MiB 的 UTF-8 JSON 普通文件；评估器先以 no-follow 句柄检查类型与
长度，再做有界读取，FIFO、UTF-16、重复 key、NaN/Infinity 都不能进入语义判定。每份 evidence
由 stable id、kind、便携相对路径和 exact SHA-256 组成。评估器要求：

- evidence root 真实存在，目标是非空普通文件；
- 路径不能是绝对路径、`..`、反斜杠/盘符、symlink 或 junction；
- 文件大小不超过 256 MiB；复用仓内完整性原语，以同一只读句柄完成 `fstat` 与 SHA-256 核验；
  POSIX 从已打开的 evidence root 逐级用 directory fd + `O_NOFOLLOW` 相对打开，父目录换绑也不能
  偷渡 symlink；Windows 缺少对等 directory-fd 原语，真实目标机前仍不得宣称竞态等价闭合；
- 不同 evidence id 不能指向同一物理文件，也不能用 byte-identical 副本伪装成独立证据；
- actor 身份映射、item 观测、owner 裁定与特殊 claim 各自绑定正确 kind 的 evidence。

普通 item 的 kind 不是一只全局“观测类”白名单，而是跟验证方法逐项绑定：`1-1..1-5` 要求
`endpoint_probe`，`1-6` 同时要求 `endpoint_probe + model_inventory`；`2-1/2-2/2-3/2-5/2-6`
要求 `command_output`，`2-4` 要求 `report`；`3-1/3-2` 要求盘点/统计 `report`（`3-1` 也接受
`category_mapping`），可选 `3-3` 要求 `report`、`3-4` 要求 `report` 或 `endpoint_probe`；`4-1`
要求 `report`、`4-2` 要求 `workflow_trace`、`4-3` 要求 `report` 或 `policy_ruling`，可选 `4-4`
要求 `report`。`5-1..5-6` 继续由各自特殊 claim 的精确 kind 规则约束。

远端 URL、口头印象和只有字符串的受控记录 ID 当前没有 resolver，故一律不能通过。需要使用这些
来源时，先按现场制度导出最小受控镜像，再运行 gate。SHA-256 只证明 exact 字节，没有能力证明
内容真实、owner 身份真实或授权合法；这些仍由现场制度和具名人负责。

### 3. 三值和特殊项语义明确 fail-closed

- `5-1/5-2/5-3/5-5/5-6` 不接受 `not_applicable`；`5-4` 只在第二家族经 inventory + 真实
  endpoint probe 共同确认时允许 N/A，并仍需 owner 书面 ruling。
- 所有 `observed_no` 都必须有 named disposition。`blocks` 保持 False；
  `accepted_with_controls` 必须有逐项 evidence-bound 的非空 controls、policy owner 和书面 ruling。
- 只有同源模型时，`5-3=observed_no` 与 `5-4=observed_yes` 必须同时成立，并分别绑定确定性核验
  政策、人工抽检地板和 owner ruling；三份 evidence 不得复用成一份。
- 第二基础模型家族不能用大小写、Unicode 兼容字符、首尾/连续空白或不可见控制/格式字符别名
  凑数；family label 拒绝 Unicode `C*` 类字符，并经 NFKC、空白折叠和 casefold 后保持唯一。
- `5-1` 关系矩阵与 `5-2` 职责分离裁定使用同一业务 owner；「尚无制度」保留为真实观察，但完成
  谓词为 False。
- `5-5` 固定为 100%、不可配置、未知类别强制具名人签，同时绑定数据/出口管制 owner 与 policy
  owner；同一人只有在两种 authority 都经身份 evidence 绑定时才可兼任。
- `5-6` 的候选、人工批准、发布必须有三个不同状态、动作和 audit evidence；同一具名人可承担
  多个角色，但人工批准 actor 必须是人；state/action 同样拒绝 Unicode `C*` 类字符，再按 NFKC、
  空白折叠和 casefold 后判重，不能靠零宽或其他字符串别名伪造三态。

### 4. 跨平台入口保持薄且不吞退出码

- Unix：`scripts/verify_m4_signal_package.sh`
- Windows：`scripts/verify_m4_signal_package.ps1`
- 共享 CLI：`scripts/verify_m4_signal_package.py`

两层包装只做仓根定位、参数透传和退出码传播。PowerShell 额外拒绝 `$LASTEXITCODE=$null` 的启动
假绿。macOS 可做合同/AST 对等验证，但真实 Windows 运行前仍标
`DECLARED-NOT-VERIFIED`。可选 `--report` 必须位于 package 与 evidence root 之外；碰撞比较保守
覆盖大小写、Unicode 规范化及 Windows 尾随点/空格别名，并对已存在路径追加 `samefile` 检查。
写入前再次复核；POSIX 从 no-follow 的 report 父目录 fd 创建临时文件并相对原子替换，父目录换绑
也不能把输出重定向进 evidence。Windows 使用保守路径复核与原子替换，但真实竞态等价仍待目标机
验证。任何平台都不能把派生报告写回或覆盖输入。

## 后果与边界

- M4 现场材料第一次有可重复、可定位、可摘要绑定的完成谓词；负结果不再被吞成“已填”。
- 合成测试可以证明 gate 有判别力，但不能增加 N10 样本，也不能产生真实 M4 信号。
- gate 不写路线图、不改数据库、不自动解冻 P2.5–P2.8；M4 为 True 后仍必须有 N10 `n>=2`。
- 双排期门都满足也不等于不可逆导入获批；Gate 1 与具名 owner 终裁继续独立。
- 高权限主体可以同时伪造 package、evidence 和 actor 映射；本地摘要无法对抗这种共同重写，需由
  文件权限、受控导出、离线留存和组织审计解决。

## 验证

- 合同：Draft 2020-12 自检、必填/可选集合、额外字段和自报完成布尔拒绝；
- JSON：读前限长、非普通文件、UTF-16、重复 key、NaN、坏 timestamp、truthy 非布尔/非枚举失败；
- evidence：缺失、空白、摘要漂移、绝对/越界路径、父级/末级 symlink、junction、竞态替换、
  物理/字节别名和超限文件失败；
- 语义：N/A 禁区、负结果 blocks/受控补偿、同源模型补偿、owner 对账、永久人签地板与三态分离；
- CLI：报告与 stdout 一致，输入/输出碰撞失败，完成才退出 0；
- wrapper：当前 macOS 主机上 `.sh` 与经 `pwsh` 执行的 `.ps1` 均跑过 true/false 退出码透传；
  PowerShell 启动或退出码缺失时非零，Windows 实机仍为 `DECLARED-NOT-VERIFIED`。

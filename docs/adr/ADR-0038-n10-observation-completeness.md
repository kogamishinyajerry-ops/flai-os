# ADR-0038：N10 观察记录完整性 gate

- 状态：Accepted（M4 前真人走查仪器；不解冻 P2.5–P2.8）
- 日期：2026-07-20
- 关联：ADR-0037、`docs/N10-NOVICE-WALKTHROUGH.md`、
  `docs/COMPOUNDING-M4-REBASELINE.md`

## 背景

P2.5–P2.8 的开发排期同时受 N10 真人新手走查 `n >= 2` 和 M4 信号包完成谓词约束。
N10 已有十步协议与 Markdown 空白模板，但纯人工阅读无法稳定拒绝重复参与者、步骤缺失、
中止后伪造观察、救援内容缺失或自报 `n` 等假绿。

另一方面，记录结构完整不等于现实世界真实。本地检查器无法知道某个假名编号是否对应
真人、两个编号是否对应两位同事，也无法从字段推导产品可用性。因此需要一个仅限完整性
和申报口径的机械 gate，同时保留排期 owner 的真实性核对责任。

## 决策

### 1. 结构化 package 是机械检查输入，不是身份凭证

`contracts/n10-observation-package.schema.json` 固定 `n10-observation-package.v1` 输入形状。
每条记录必须包含假名 participant key、参与者类型、新手/环境声明、exact build、观察者与
时间、终止方式、N1–N10 十步观察、结束访谈、问题与受控媒体引用。合同拒绝额外字段，
输入不能自报 `n`、结构完整性布尔或成功率。

记录包可以作为结构化原始记录；若由现场工作表转录而来，必须在受控存储中保留原稿并以
`record_id` 对账。真实 package、身份对照、截图和录屏不提交进仓库；合同中只存受控媒体
引用，不内嵌媒体。

### 2. 结构完整性布尔只由评估器派生

`backend.app.governance.n10_observation_gate.evaluate_n10_observation_package` 是完整性语义的
唯一实现。它检查 JSON 合同、记录/participant 去重、真实 UTC 时间顺序、恰好 N1–N10 的
步骤序列、中止拓扑、已尝试步骤用时与救援记录等协议内部一致性。
环境或参与者口径在任务开始前即无效时，十步统一使用
`not_started_invalid_session`，与真实开始后在某一步中止的 `aborted` /
`not_reached_after_abort` 分开，避免无效场次伪装成十步完成。
两类未尝试状态使用 schema 固定的 exact no-observation sentinel；纯空白、不可见 filler、
纯标点/符号不算原始观察证据，已尝试场次还必须有正的总观察用时且不超过会话区间。

仅当无 finding，且按 NFKC/casefold 规范化 `participant_key` 去重后的
`declared_eligible_n >= 2` 时，评估器才派生
`N10_DECLARED_RECORD_PACKAGE_STRUCTURALLY_COMPLETE=true`。“申报
合格”只包括 `participant_kind=real_colleague`、新手与环境布尔为真、合格终止类型，以及观察者
声明现场观察、未路径教学和同步记录。真实 product blocker 或参与者中止可计入申报 `n`，
环境无效、参与者不合格、自测、自动化、agent 或同一人重复不能增加它。

报告携带 exact 输入的 `package_sha256`、申报合格数、按 commit/build/gateway 分组的计数和
逐项 finding，不输出成功率。报告同时固定输出
`owner_identity_confirmation_required=true`、`roadmap_effect="none"` 和
`m4_status="not_evaluated"`，使上层无法把结构完整性字段合理误接为真人认证、
路线图解锁或 M4 结果。

### 3. 输入解析 fail-closed

package 只接受不超过 2 MiB 的普通 UTF-8 JSON 文件。读取时使用 no-follow 句柄、同一句柄
限长读取并计算 SHA-256；非普通文件、超限、重复 JSON key、非标准 JSON 常量、非 UTF-8、
合同失配或任何协议 finding 都 fail-closed。摘要只绑定 exact 字节，不认证字节内容是否真实。

### 4. CLI 与跨平台入口保持薄

- 共享 CLI：`scripts/verify_n10_observation_package.py`
- Unix：`scripts/verify_n10_observation_package.sh`
- Windows：`scripts/verify_n10_observation_package.ps1`

包装脚本只做仓根定位、`--package <path>` 参数透传与退出码传播。CLI 向 stdout 输出
唯一语义评估器的 JSON 报告，不提供 `--report` 文件输出；
仅当 `report.structurally_complete is True` 时退出 0，否则非零。PowerShell 包装必须拒绝缺失的
`$LASTEXITCODE`。在 Windows 真实目标机运行取证前，`.ps1` 状态为
`DECLARED-NOT-VERIFIED`；macOS 上的 AST、对等测试或 `pwsh` 运行不是 Windows 实机证明。

### 5. 排期 owner 保留现实世界确认责任

exit 0 只证明“申报记录结构完整且申报的去重合格场次至少 2 条”。它不认证真人身份、
不证明可用性或统计显著性、不证明 M4、不改路线图也不自动解锁 P2.5–P2.8。排期 owner 必须在
受控环境中把 exact package 摘要、逐人原始记录与身份对照合在一起审核，明确确认样本来自
两位不同的真实同事。N10 这一半真正到位后，仍必须独立满足 M4 gate，再由 owner 作排期决定。

## 后果与边界

- N10 原始观察首次有了可重放的结构与可定位 finding，但身份真实性仍属于人和受控制度。
- 成功和完整性分离：真实中止可形成合格观察，不能把失败改写成成功。
- 合成测试只能证明 gate 有判别力，不能增加 N10 真人 `n`。
- 仓库只保留合同、评估器、包装脚本、测试和空白协议，不保留真实样本、身份对照或媒体。
- N10 与 M4 是两道独立排期门；两者都不代替 Gate 1 或具名 owner 的导入终裁。

## 验证

- 合同：Draft 2020-12 自检、拒绝额外字段和输入自报完成值；
- 解析：超限、非普通文件、非 UTF-8、重复 key 与非标准 JSON 失败；
- 语义：N1–N10 顺序、真实时间、救援/中止拓扑、participant 去重、不合格类型与真实 blocker；
- CLI：输出 exact 摘要与 finding，只有完整包才退出 0；
- wrapper：`.sh` 与 `.ps1` 参数/退出码对等；Windows 实机仍为
  `DECLARED-NOT-VERIFIED`。

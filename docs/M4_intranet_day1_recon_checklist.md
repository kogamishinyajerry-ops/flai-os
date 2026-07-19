# M4 内网首日侦察 Checklist

> 目的：内网踏点是一次性、时间受限的窗口。本清单把散落全仓的「待内网侦察」标记
> 汇总为可逐项打勾的现场核对表，**每条均为未验证假设**（声明 ≤ 证据等级）——
> 「验证结果」栏由踏点当天现场填写，未填即未验证。
>
> 来源盘点方式：`grep -rn "待内网侦察" backend/ docs/ agents/ contracts/`
> （2026-07-18 复核；若代码更新以 grep 现扫为准）。
>
> **2026-07-19 复利重排增补**：M4 现在也是判断资产、课题延续与评审梯子的
> 信号总开关。除原有技术侦察外，现场必须采集真实评审关系、模型家族独立性与
> 永久人工签发地板；详见 `docs/COMPOUNDING-M4-REBASELINE.md`。这些栏位只能填
> 原始观测或具名业务确认，不能由平台团队代填组织现实。

## 使用方式

1. 踏点当天带上本文件（打印或离线副本）。
2. 每项按「验证方法」操作，把**原始观测**（命令输出/截图/报文摘要）记入「验证结果」。
3. 回来后把结果同步回对应源文件（profiles.yaml notes / docs/04 §6 / ADR），再动代码。
4. 「未确认」「只有同源模型」「尚无制度 owner」都是有效结果；空白和未知不能被推断
   成绿色。M4 信号包用于指导后续设计，不自动构成导入授权。

---

## ① LLM 端点协议与鉴权（最高优先——阻塞 fta/guide/knowledge_qa 三个 Agent 真实点火）

> 公网参照证据（2026-07-11）：本机经公网 GLM（glm-5.1）已验证 1-1/1-3/1-4 的
> **协议链路侧**（探针全绿 + 导引/fta 真实业务闭环），存档
> `docs/reviews/GLM-real-fire-record.md`。内网形态可能不同，现场列保持空白照填。

| # | 待验证假设 | 来源 | 验证方法 | 验证结果（现场填） |
|---|---|---|---|---|
| 1-1 | 内网 GLM 端点是 OpenAI 兼容协议（`POST {base}/chat/completions`） | `backend/app/model_gateway/gateway.py:10,289`、`docs/04:63` | `export FLAI_LLM_*` 后跑 `python scripts/probe_llm_gateway.py`，逐层看原始观测 | |
| 1-2 | 鉴权方式是 `Authorization: Bearer <key>` | `profiles.yaml:13` | 同上（探针即用 Bearer 头；401/403 只是观测——可能是鉴权形态不符，也可能是 Key 错误/过期、模型 ACL、IP 白名单，需用已知有效凭据或与服务方确认后才能下结论） | |
| 1-3 | 响应 body 是 JSON 且有 `choices[0].message.content`（网关必需）；`usage` 字段（网关允许缺失，缺则 token 消耗记 None） | `gateway.py`（chat 形状校验） | 探针输出逐层观测 | |
| 1-4 | 中文往返正常（无编码/截断问题） | 隐含假设 | 探针后手工发一条中文 prompt 核对 | |
| 1-5 | 真实 reasoning 请求的延迟分布与安全 timeout 尚未知 | `backend/app/config.py`、`.env.example`、`docs/PRODUCTION-READINESS-PROGRAM.md` P0-B3 | 用目标模型重复发送代表性复杂 prompt，记录样本量、p50/p99/失败率；将 `FLAI_LLM_TIMEOUT_S` 配置为高于经确认的 p99 后复测 | |
| 1-6 | 模型名（`FLAI_LLM_MODEL_REASONING/FAST`）在内网服务上真实存在 | `profiles.yaml:21` | 探针 + 服务方确认模型清单 | |
| 1-7 | vision/embed profile 的报文形态（V0.1 只占位） | `gateway.py:289`、`docs/06:73-80` | 询问服务方是否提供，暂不接入，观测记回 docs/06 §6 | |

## ② 数据库与部署环境

| # | 待验证假设 | 来源 | 验证方法 | 验证结果（现场填） |
|---|---|---|---|---|
| 2-1 | 部署机 `FLAI_DB_PATH` 指向**本地磁盘**（WAL 禁网络盘） | `README 环境变量表`、`.env.example` | 确认路径非 UNC/映射盘；`sqlite3 <db> "PRAGMA journal_mode"` 应回 `wal` | |
| 2-2 | Windows 下 `.ps1` 启动脚本可用（DECLARED-NOT-VERIFIED） | `scripts/*.ps1` 头注 | 逐个跑 init_db/dev_start_backend/dev_start_worker 的 .ps1 | |
| 2-3 | 内网机器可安装 Python 3.10+ 与依赖（离线 wheels 策略未定） | `scripts/package_release.*`（NOT-IMPLEMENTED） | 确认现场 Python 版本/架构 + 是否有内网 pip 源 | |
| 2-4 | 部署机有 Node 或可接受「带 dist 产物入场」（后端静态托管 dist，现场可免 node） | `README 前端节` | 确认 dist 随包带入即可，无需现场构建 | |
| 2-5 | worker 单实例锁的 Windows 分支（msvcrt.locking）真实生效（DECLARED-NOT-VERIFIED，本机仅测 POSIX fcntl） | `backend/app/jobs/runner.py`（R4 批） | Windows 上起第一个 worker 后再起第二个，应 stderr 报「已有 worker 正在运行」且退出码 1 | |
| 2-6 | 完整性闸 O_NOFOLLOW 在 Windows/NTFS 上的行为（符号链接/junction 拒绝路径是否等效） | `backend/app/storage/file_integrity.py`（R4 批，README #20③） | Windows 上跑 `python -m pytest backend/tests/test_file_integrity.py -q`，尤其 symlink 用例不应被 skip 掩盖 | |

## ③ Knowledge 检索来源扩展

| # | 待验证假设 | 来源 | 验证方法 | 验证结果（现场填） |
|---|---|---|---|---|
| 3-1 | 语料实际形态（目录结构/格式/密级分布） | `knowledge/scopes.py:127,141`、`docs/06:12` | 现场盘点部门语料样本 | |
| 3-2 | PDF 是否为主要格式（V0.1 显式拒绝 PDF） | `knowledge/chunking.py:194` | 语料格式统计 | |
| 3-3 | obsidian_vault / mcp 来源是否存在需求 | `contracts/knowledge_scope.schema.json:24` | 与使用方访谈 | |
| 3-4 | 向量检索/embedding 服务是否可用 | `docs/06:73-80` | 服务方确认；观测记回 docs/06 §6 | |

## ④ 具体模型接入与业务流程

| # | 待验证假设 | 来源 | 验证方法 | 验证结果（现场填） |
|---|---|---|---|---|
| 4-1 | GLM 5.x 部署形态（GPU 机器/限流/并发配额） | `docs/01:60,65` | 服务方确认 | |
| 4-2 | 性能盘真实调用形态（CLI？COM？输入输出文件约定？） | ADR-0010（M4 adapter 设计前置） | 现场观摩一次真实性能盘操作 | |
| 4-3 | L2 成熟度「专家审核签字」的记录方式 | `docs/02:64` | 与业务 reviewer 确认流程 | |
| 4-4 | MCP Server 部署方式（工具 MCP 化演进前置） | `docs/03:91` | IT 环境确认 | |

## ⑤ 评审关系、模型独立性与永久人签地板（复利结构前置）

> 本组不是要现场设计 RBAC 或评审梯子，而是采集其真实主语。姓名/工号如不宜进入
> 仓库，可用现场受控映射编号；但必须能由具名业务 owner 回查，不能只写抽象
> 「专家」「管理员」。

| # | 待验证假设 | 来源 | 验证方法 | 验证结果（现场填） |
|---|---|---|---|---|
| 5-1 | 真实评审关系尚未知：谁创建、谁初审、谁终签，是否按类别变化 | `docs/COMPOUNDING-M4-REBASELINE.md` §5 | 与业务 owner 画一张「主体/岗位→可审类别→可签类别→上级复核」矩阵；至少拿一条真实流程逐步核对 | |
| 5-2 | 角色轴不能仅凭 username 推导；职责分离、自审例外与代理签发规则尚未知 | README 已知限制 #14；复利重排 §5 | 让业务 owner 对 5-1 矩阵逐项确认，记录例外、代理机制和制度依据；无制度即记「未定义」 | |
| 5-3 | 内网是否存在 GLM 之外的第二模型家族未知，R0 顾问的异源独立性未证 | 复利重排 §3/§5 | 向模型服务方索取可用模型清单、提供方/基础家族/版本；用真实端点探针确认「可用」而非只看清单 | |
| 5-4 | 若只有同源模型，确定性核验权重与人工抽检地板需提高 | 复利重排 §5 | 记录「有第二家族 / 只有同源 / 未知」三值结论；后两者不得写成异源审已满足，并交政策 owner 裁定补偿措施 | |
| 5-5 | `sensitive` 与 EAR 相邻类别必须永久保持 100% 具名人工签发，但真实类别边界与政策 owner 待确认 | 平台红线；复利重排 §5 | 由数据/出口管制责任人给出类别映射与具名确认；在政策模板不可配置区标明 100%，任何未知类别 fail-closed 进入人工签发 | |
| 5-6 | 机器候选评审、人的最终签发、发布批准在真实流程中是否由不同主体/步骤承担未知 | 平台「人唯一签发」与候选/批准/发布分离红线 | 用一条真实产物走读三步，分别记主体、输入、输出、审计凭据；同一主体可承担多个角色，但三个动作、状态和审计证据仍须独立，现场事实只影响角色映射，不自动合并平台三态 | |

### M4 信号包完成谓词（排期解锁用，不等于 Gate 1 授权）

`M4_SIGNAL_PACKAGE_COMPLETE is True` 仅当以下条件**全部**成立：

1. 必填项 `1-1..1-6`、`2-1..2-6`、`3-1..3-2`、`4-1..4-3`、`5-1..5-6`
   每格都写明 `observed_yes / observed_no / not_applicable`、证据路径、观察时间与观察者；
   `not_applicable` 还须有对应业务/IT owner 理由。`1-7`、`3-3..3-4`、`4-4` 是未来
   集成侦察，不作为本次排期门必填。
2. `5-1` 有真实评审关系矩阵及具名业务 owner 回查点；`5-2` 的职责分离/自审例外
   已获同一 owner 书面裁定。仅观察到「尚无制度」仍是重要事实，但谓词保持 False。
3. `5-3=observed_no`（没有第二模型家族）可以计为已取证负结果，但必须同时完成
   `5-4` 的确定性核验加权、人工抽检地板和具名 policy owner 裁定；否则谓词为 False。
4. `5-5` 已由数据/出口管制责任人与具名 policy owner 确认永久 100% 人签地板；未知类别继续按
   人工签发 fail-closed。两种 authority 可由同一人兼任，但都须经身份 evidence 绑定；缺任一角色
   或只有平台团队自述时谓词为 False。
5. `5-6` 已逐步确认候选、人工批准、发布三个独立动作/状态/审计证据；同一主体承担
   多个角色不等于三态合并。缺任一步证据时谓词为 False。

任何空白、`unknown`、口头印象、未跑的探针或不可回查证据都会使谓词为 False。
已取证的负结果保留原样，不制造假绿；它只有在上述安全补偿一并完成时才可解锁。

#### 机械 gate 合同（ADR-0037）

现场记录回收到受控 evidence mirror 后，使用唯一合同与评估器重新派生上述谓词：

```bash
bash scripts/verify_m4_signal_package.sh \
  --package <m4-signal-package.json> \
  --evidence-root <受控证据镜像目录> \
  --report <证据镜像外的已有目录>/m4-signal-gate-report.json
```

Windows 对等入口为 `scripts/verify_m4_signal_package.ps1`。在真实 Windows 目标机运行前，
PowerShell 入口只标 `DECLARED-NOT-VERIFIED`，不得借静态对等测试冒充实机通过。输入合同是
`contracts/m4-signal-package.schema.json`；包内不得自报
`M4_SIGNAL_PACKAGE_COMPLETE=true`，最终布尔只能由评估器派生。

为消除三值语义歧义，以下规则焊死：

1. `5-1/5-2/5-3/5-5/5-6` 必须有实质观测，不接受 `not_applicable`；`5-4` 仅在
   `5-3=observed_yes` 且真实端点证明第二基础家族可用时允许 `not_applicable`，仍须业务/IT
   owner 的理由与书面证据。
2. 任一 `observed_no` 必须具名 disposition。`blocks` 如实保持 False；只有
   `accepted_with_controls`、逐项绑定 exact evidence 的非空控制措施、具名 policy owner 与
   书面裁定同时存在时，才可继续
   参与合取。`5-3=observed_no` 还必须同时通过 `5-4` 的确定性核验政策、人工抽检地板和 owner
   裁定，不能用自由文本绕过。
3. package 只接受有界 UTF-8 JSON 普通文件。evidence 只接受 evidence root 下可回查的普通文件、
   便携相对路径和 exact SHA-256；缺文件、空文件、摘要漂移、绝对/越界路径、symlink/junction、
   同一物理文件或 byte-identical 内容登记成多个 ID 均为 False。受控记录 ID 若没有本地可验证
   resolver，不能只凭一个字符串放行。
4. actor/owner 权限是**现场受控映射的声明 + exact evidence 绑定**。机械 gate 能证明声明与证据
   字节一致，不能凭自身证明现实身份或授权真实；具名 owner 的真实性仍由现场制度与人负责。
5. 报告中的 `package_sha256` 是 exact 输入文件字节摘要，不冒充 canonical 语义摘要。`--report`
   必须位于 package 与 evidence root 之外；只改大小写、Unicode 规范形或 Windows 尾随点/空格
   仍按同一路径碰撞拒绝，不能覆盖输入。gate 不写路线图、不自动解冻、不证明 N10，也不替代
   Gate 1 或 owner 终裁。
6. evidence kind 必须匹配本表验证方法，不能拿任意“观测类”文件代替。尤其 `1-1..1-5` 要有
   `endpoint_probe`，`1-6` 必须同时有 `endpoint_probe + model_inventory`；`2-*` 的命令实跑项要有
   `command_output`，`4-2` 的真实性能盘观摩要有 `workflow_trace`。第二模型家族与 5-6 三态的名字
   都拒绝 Unicode 控制/格式/私用等 `C*` 类字符，并在 NFKC、空白折叠、casefold 后判重；零宽或
   其他字符串别名不算独立家族/状态/动作。

仓库只提交合同、评估器与合成测试，不提交一份“全绿示例包”，避免合成 owner/evidence 被误用为
真实 M4 信号。

---

## 踏点当天最短路径（45 分钟版）

1. `python scripts/probe_llm_gateway.py`（①-1/2/3 一次性出观测）。
2. `sqlite3 <FLAI_DB_PATH> "PRAGMA journal_mode"` + 确认路径本地盘（②-1）。
3. `.ps1` 三连（②-2）。
4. 语料目录 `dir /s` 样本 + 格式统计（③-1/2）。
5. 观摩性能盘操作一次，录屏或记步骤（④-2）。
6. 与业务 owner 画一条真实「创建→初审→终签→发布」关系链（⑤-1/⑤-6）。
7. 向模型服务方确认第二模型家族并留清单/探针证据（⑤-3/⑤-4）。
8. 请数据/出口管制责任人确认永久 100% 人签类别地板（⑤-5）。

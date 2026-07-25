# ADR-0024：monitor_adapter 安全激活——工具污点轴 + 诚实激活姿态

> 后续状态（2026-07-21）：本文关于“users 无 role、admin_only 无运行时强制点”的
> 历史判断已由 ADR-0031 取代；Agent 直接调用、交互会话、评测与任务签发现已接
> 认证角色门。Monitor 的工具污点、敏感访问与真实 EAR 前置仍按本文及 ADR-0029
> 执行，未被自动解除。

- 状态：Accepted（用户显式优先级：「把可视化监控生成模块正式接入平台」）；**D5（read
  期内容门 `_task_content_is_sensitive`）已被 ADR-0025 替换**——D1–D4（工具污点轴 +
  诚实姿态）保留有效，D5 的 read 期重派生方案因 Codex R1-A（遮蔽面 whack-a-mole）/
  R1-B（重派生漂移）两 P1 被 round-cap-3 交 owner 裁决，owner 选 A → 改「执行期落库
  不可变分级 + 单 chokepoint」（见 ADR-0025）。
- 日期：2026-07-12
- 关联：ADR-0020（监控注册路线）· ADR-0021（数据分级轴，本 ADR 兑现其 194-198
  声明的激活硬前置）· ADR-0022（子进程边界）· ADR-0019（真鉴权）· **ADR-0025（替换
  本 ADR 的 D5，保留 D1–D4）**
- 审查：Codex 异源审（数据分级/污点=安全边界「命中即审」）——D5 read 期门经 R0→R1
  两轮仍 2 P1（round-cap-3），架构替换见 ADR-0025 的新 R0。

## 一、问题（grounded 坐实，另一会话开发的模块现状）

monitor_adapter 模块（`agents/monitor_adapter_gen_agent/` + `tools_impl/
monitor_adapter_recon/`）**已被三注册表 scan、GET /api/agents 可见、Job Runner
可执行**——即已「接入」。但存在一个**安全承重缺口**阻塞安全激活：

- 该 agent `input.type=params`（无输入文件）、`knowledge.enabled=false`——文件
  污点轴与知识轴**都测不到**，`_task_data_classification` 派生落分支①→ **internal**。
- 但工具 `monitor_adapter_recon` **读外部真实 run 目录、把侦察证据拷进 draft
  产物**（module.json 骨架 / parser 桩 / 三档证据）。产物携带外部文件系统内容、
  出处不可考——按 ADR-0021 应为 **sensitive**，实际被误判 **internal**。
- 后果：这些产物/样本以 internal 落库 → **过 ADR-0021 下载门（403 不触发）
  与固化门** → 外部数据经监控草案泄漏，且绕过 ADR-0023 刚建的敏感访问审计轴。
- ADR-0021:194-198 已**显式声明**：该 Agent 激活前必须先落地「工具级 taint 声明
  / agent 显式 output_classification: sensitive」，标注为**硬前置、非可选**。

亲验：`tool.yaml` output_schema（:32-58）与 `adapter.py` 返回体（:107-121）
均无 classification 字段；`agent.yaml` 无 output_classification；`_task_data_
classification`（runtime.py:255-263）只有文件∨知识两轴。

## 二、决策

### D1 工具污点轴（安全硬前置的兑现）——本 ADR 核心
`_task_data_classification` 增第三轴：**工具污点**。
```
任务级分级 = 文件污点轴 ∨ 知识轴 ∨ 工具污点轴
```
- **机制**：tool.yaml 顶层新增声明 `output_classification: sensitive`；
  `_tool_taint_classification(agent, tool_registry)` 遍历 agent 的 allowed_tools
  （agent.yaml `tools:`），任一工具声明 sensitive → 任务产物 sensitive。
- **为什么在工具层**：工具是真正碰外部不可考数据的单元；污点跟随该单元 →
  **任何未来 agent 挂 monitor_adapter_recon 都自动继承 sensitive**，不靠单个
  agent 作者记得声明（比 agent 级更 robust）。
- **静态 fail-closed 过近似**：「agent 被授予该工具」即污染，**不追踪本次是否
  真调用**——宁严勿洗白，与文件/知识轴同向（ADR-0021 D3）。派生在注册期即定，
  无需运行时逐 tool-call 追踪（零 schema/DB 增列）。
- **纵深 fail-closed（终态口径，随 D3 schema required 收紧）**：output_classification
  已是 tool.schema.json 的 **required** 字段（漏声明的 tool.yaml 注册期即被拒），故对
  **已加载工具**判「非显式 internal（含 sensitive/坏值）一律 sensitive」；`tool_registry
  is None` 或工具未加载 → 该轴返 internal。安全性证明：工具未加载时其 `call` 本就
  fail-closed（`api/tools` 层拒调用），产不出洗白产物，故「不因缺工具而升级」不制造
  泄漏。其余无污点工具 → 贡献 internal → 既有 agent（knowledge_qa 等）分级不变。

### D2 monitor_adapter_recon 声明 sensitive
`tool.yaml` 加 `output_classification: sensitive`——该工具读外部 run 目录，
其产出恒视为 sensitive。这是**该模块安全激活的必要且充分的分级修复**。

### D3 契约 schema 扩展
`contracts/tool.schema.json` 顶层加 **required** `output_classification`
（enum: internal|sensitive；Codex R0 P2-1 去静默省略——每工具必显式表态，漏声明
注册期即拒）。additionalProperties=false 故声明该字段的 tool.yaml 必须显式加入。

### D4 不擅自翻 maturity / 不伪造角色强制（诚实姿态）
本 ADR **只兑现安全分级硬前置**，不做以下越权动作：
- **不翻 L0→L1**：ADR-0020:46 明定晋升是 M10 治理步（配 core_dir 后跑 eval
  runner + 人工确认），「本 ADR 不代拍」。无真实 core_dir、无人工签发，绝不自动晋升。
- **不伪造 admin_only 强制**：users 表**无 role/is_admin 列**（亲验 db.py：
  create_user 只插 username/display_name/password_hash/is_active/created_at），
  全仓无运行时用户角色强制点。真正强制 admin_only 需加用户角色轴（DB 列 + owner
  定角色模型 + 真实 EAR 数据进场）——**递延 owner**，绝不半吊子造角色系统
  （宪法：不擅自引入大抽象）。

### D5 sensitive 任务详情端点内容门（Codex R0 P1-1 补，安全承重）

> **⚠ 已被 ADR-0025 替换（2026-07-12，owner 选项 A）。** 本 D5 的 read 期方案
> `_task_content_is_sensitive`（读时按当前注册表重派生分级 + 按端点按字段白名单遮蔽）
> 经 Codex R1 被判两 P1：**R1-A** 遮蔽面 whack-a-mole（漏 error_message/message 列 +
> 三端点未 gate）、**R1-B** read 期重派生随工具卸载漂移解封。round-cap-3 用尽交 owner，
> owner 选 A → 改为「执行期落库不可变 `tasks.data_classification` + 单 chokepoint
> `classification_gate.py` 统一封全端点」（ADR-0025 D1–D3）。本节保留作决策史；
> **现行内容门实现以 ADR-0025 为准**，D1–D4 的工具污点轴/诚实姿态不变。

工具污点轴（D1）把产物/样本**分级**为 sensitive，但**分级不等于隔离**——同一批
外部数据除产物文件（下载 403）外，还经三条任务详情端点原样出场：
`GET /tasks/{id}/tool_runs`（工具 draft 全文在 output_json）、`/model_calls`
（request/response_summary 可能含证据）、`/samples`（output/input）。文件下载 403
只封了一条，其余三条对任意登录用户原样返回=**假绿泄漏**。

故（D5 原方案）新增任务级内容门 `_task_content_is_sensitive`：派生同执行期口径
（文件∨知识∨工具三轴），sensitive 任务的三详情端点**只回元数据**（谁/何时/成败/
工具版本/分级），内容载荷（input/output/summary/raw 路径）置 None + `content_withheld`
标记。原则：一个任务被判 sensitive，其**全部内容出场面**必须一致封闭，绝不「只堵
文件、漏堵详情」——此原则 ADR-0025 保留并扩到全 8 端点 + 错误文本列。

**门覆盖面 = 工具产出的派生内容**（tool_runs.output/model_calls.summary/samples.output
+ 产物文件下载 403）——这是工具从外部真源**读进来**的敏感数据。**边界声明**：
`GET /tasks/{id}` 的 `task.inputs`（用户提交的 sample_run_dir 路径等）**不在本门内**：
①它是用户自报的输入（指针/路径，非工具读出的内容本身），属 ADR-0021 F3 已声明的
自由文本自报旁路（是否限制高风险 Agent 输入 schema=owner 裁决）；②任务创建者需能
看回自己提交了什么（V0.1 无角色轴，一律封会伤创建者自查）。故本门刻意只封「工具
产出」不封「用户提交」，与 ADR-0021 F3 威胁模型一致，非遗漏。（此边界 ADR-0025 沿用。）

## 三、激活姿态（诚实清单：什么现在安全、什么仍需人）

| 项 | 状态 | 负责方 |
|---|---|---|
| 工具污点轴（产物判 sensitive、过下载 403 门） | ✅ 本 ADR 落地 | — |
| sensitive 任务全端点内容封闭 | ✅ **ADR-0025 落地**（替 D5 read 期门） | — |
| FLAI_MONITOR_CORE_DIR 配置（工具功能可达） | ⏸ 未配=fail-closed | **operator** 部署时 export |
| L0→L1 治理晋升（eval + 人工签发） | ⏸ 未做 | **owner/工程师**（ADR-0020 治理步） |
| admin_only 运行时强制（用户角色轴） | ⏸ 声明存在无强制点 | **owner**（角色轴，真实 EAR 前置） |
| eval fixture 纳入包 digest | ⏸ 未纳入（task#14） | 后续（非激活阻塞：不影响运行时分级） |

**残余暴露的诚实边界**：污点轴落地后，即使未配 core_dir + 未晋升 L1，若 operator
配了 core_dir，则任何**已认证**用户（非仅 admin，因角色轴未建）可触发一次 draft
生成 job；但其产物恒 sensitive → **下载 403 拒 + 敏感访问审计留痕（ADR-0023）**，
故最坏后果限于「非 admin 用户能触发生成并在任务列表看到 sensitive 草案存在，但
不可下载其内容」。此暴露被 operator 门（core_dir）与分级门双重收敛，V0.1 可接受
并显式声明；完整 admin_only 强制随角色轴落地。

## 四、验收标准

1. `_tool_taint_classification`：挂 sensitive 工具的 agent→sensitive；不挂→internal；
   tool_registry=None→internal；工具未在 registry→internal（affirmative-only）。
2. `_task_data_classification` 三轴 ∨：文件/知识/工具任一 sensitive → sensitive。
3. monitor_adapter_gen_agent（无输入文件、无知识、挂 monitor_adapter_recon）派生
   = **sensitive**（此前 internal）。
4. 既有 b2 派生测试全绿（affirmative-only 不改无污点工具的 agent 分级）。
5. tool.yaml 加 output_classification=sensitive 后仍过 tool.schema.json 注册校验；
   未声明该字段的既有 tool.yaml 注册不变。
6. **tamper**：撤掉 `_tool_taint_classification` 的 ∨ 分支（或把工具声明改 internal）
   → monitor 派生退回 internal 的断言必 FAIL。
7. 产物/样本继承 sensitive → 经 GET /files/download 返 403 + audit.log 留痕。
   （D5 端点内容封闭的验收随 ADR-0025 §四扩为全 8 端点 + 错误文本列 + 漂移 witness。）

## 五、边界声明

- 本 ADR 不改 adapter.py 承重逻辑（另一会话所著，只读侦察 + resolve() 已做路径
  规范化）；path 越权/symlink 的进一步加固与 digest 纳入是 task#14 剩余项，非
  运行时分级泄漏阻塞，随后续清偿。
- 工具污点轴是**静态过近似**：不区分「调用了工具但产物实际不含外部数据」的
  情形（全判 sensitive）。这是 fail-closed 的刻意选择——宁可多判 sensitive
  （多一道 403），绝不漏判制造泄漏。

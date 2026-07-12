# M11-B2 数据分级标记轴 + C2/C3 部署自检门/离线包预案 · 审查档案

> 交付：ADR-0021（R2）+ 迁移 #6 + 三门实现 + 12 witness + tamper 三连实证；
> `scripts/deploy_selfcheck.py/.sh/.ps1` + `docs/M11-OFFLINE-PACKAGE-PLAN.md`。
> 审查协议：设计审（loop-auditor，mode A）→ 实现 → tamper 自证 →
> Codex 异源治理审（86gs gpt-5.6-sol ultra，安全边界同步阻塞）。

## 一、设计审（loop-auditor）

### R0 → BLOCK（三阻塞 + 四建议）

| # | 严重度 | 内容 | 处置 |
|---|---|---|---|
| F1 | 严重 | D5 固化门判定被旧「含输入文件」门屏蔽成死代码（能产出 sensitive 的传播分支都要求有输入文件），验收 #7 只能 DB 直插=假咬合 | R1 先如实降级为「防御纵深占位」；**R2 实现期强化：分级门排旧门之前（安全语义门优先），自然链路真实可达，双 witness** |
| F2 | 严重 | 分级为自报无核验、files 无上传者字段（标错无从追责）、「诚实标 sensitive=自我黑洞」反激励 | 迁移 #6 加 `files.uploaded_by`（登录身份）；D2 自报信任根声明；D6 反激励缺陷声明+「真实 EAR 数据进场硬前置=角色轴先落地」入递延 |
| F3 | 高 | 自由文本旁路：inputs_json 粘贴敏感文本→分支③ internal→可固化入包，D6 未声明 | D6 表新增行如实声明；残余由 accepted_by_engineer 人工放行责任+词面纪律兜底；schema 限制留 owner 裁决 |
| F4 | 中 | repos 层 classification 若给默认值=隐蔽洗白点 | 必填 kwarg 无默认值，漏传 TypeError |
| F5 | 中 | 传播三分支 witness 覆盖不对称 | 验收扩至 11 条（#7 分支②传播、#8 分支③正向） |
| F6 | 中 | 失败样本若复用 verified_files 推导会误判 internal | 派生无条件基于 task.input_file_ids 现查 DB + 验收 #10 |
| F7 | 低 | 分级校验若后置于写盘产生孤儿 blob | 校验先于任何磁盘 I/O + 验收 #2 补「不落盘」 |

### R1 → APPROVE

复审逐项核对 F1-F7 落点，独立抽查交叉引用一致性（含前端
`fetchOutputFile` 共用 /download 通道、`TaskDetail.vue` inputs 原样渲染
两处代码实证），判词「修复方式是如实降级+转正条件+证据等级标注，非藏
问题冒充解决」。两条前瞻记录：①「角色轴先于真实数据」目前是文字承诺，
建议将来在角色轴/M4 ADR 做成真正前置检查；②curation.py 旧门旁加
ADR-0021 D5 耦合注释（已在实现中落地）。

### R2（实现期强化）→ loop-auditor 单点复核 APPROVE 维持

D5 门序前置使 F1 的「不可达」前提失效——从「诚实占位」升级为「有效
拦截」，验收 #9 改双 witness（9a 自然链路+文案断言即门序 witness；
9b DB 直插未来态）。声明只升不降。auditor 独立验证（非轻信声明）：
亲跑 12 witness + 全量 550 collected 全绿对账；tamper 三组咬合计数
（3/5/2）以断言反推独立推导完全吻合；curation.py 门序/耦合注释、
repos 必填 kwarg、runtime 派生独立性逐处 Read 核对，判词「真实提升
拦截有效性，证据链四层亲核」。

## 二、自证（tamper 三连，cp 备份法，复原 diff 校验为空）

| 变异 | 咬合 |
|---|---|
| 下载门判定失效（`!= internal` → 恒假） | 3 个测试 FAIL |
| 传播函数恒返 internal（洗白） | 5 个测试 FAIL |
| 固化分级门整体失效（`if False`） | 2 个测试 FAIL（9a+9b 双双咬中） |

复原后 12/12 绿；全量 pytest 614 passed（internal 语义零扰动=验收 #11）。

## 三、C2 自检门实证

- 全 PASS 实证：scratch 库 + init_db + user_admin create + 临时服务
  （空闲端口 8639，未触碰任何既有进程）→ 8/8 PASS，exit 0。
- fail-closed 实证①：缺库+死端口 → 6 FAIL，exit 1。
- fail-closed 实证②：停用唯一账户 → 检查项 3 FAIL（文案指向
  user_admin.py create），exit 1。
- 代际见证在咬：检查 4（classification 列）在 B2 实现前的冒烟中如实
  FAIL，实现后 PASS。

## 四、Codex 异源治理审（86gs gpt-5.6-sol ultra）

### R0 → 三 findings，全部 grounded 复核坐实后修复

| # | 级 | Finding | 复核 | 修复 |
|---|---|---|---|---|
| P1 | 高 | 知识轴洗白通道：绑 restricted 知识库的 job Agent 零输入文件即产出「internal」产物，全员可下载 | **坐实**——scopes.py 确有三级密级轴（public_internal/department/restricted），派生只看输入文件时此路完全敞开；且机器可知（scope 自声明），可机制化非仅声明 | 派生升级为「文件污点轴 ∨ 知识轴」：`_knowledge_classification` allowlist（restricted/未知密级/未注册/registry 缺失全 fail-closed sensitive）；runtime 注入 scope_registry；ADR R3 D3/D6/验收 #12 |
| P1 | 高 | 部署自检门假 PASS：库已迁移但服务重启失败仍是旧进程 → 列检查+健康+401 三者全 PASS 而 D2/D4 缺席 | **坐实**——检查 4 是磁盘见证非进程见证 | /api/health 加 `classification_axis` 布尔位（活进程自报代际）；自检门新增检查 6（is True 判定）；**实机复现攻击场景**：同库起去标记进程 → 1-5/7-9 PASS、唯 6 FAIL、exit 1，单点咬合 |
| P2 | 中 | ps1 包装 fail-open：python 不在 PATH → CommandNotFoundException 不终止、`exit $null`=0，零检查却报成功 | **坐实**——PowerShell 默认 Continue 语义 | `$ErrorActionPreference="Stop"` + try/catch exit 1 + `$LASTEXITCODE` null 兜底 |

R0 修复后：B2 witness 扩至 20（+密级矩阵 5 参数、未注册/缺 registry、
restricted 真跑链路、health 标记）；变异 4（知识轴恒 internal）咬 4 个
测试；全量 pytest 623 passed。

### R1（对 R0 修复的复审）→ 四 findings，全部坐实后修复

| # | 级 | Finding | 复核 | 修复 |
|---|---|---|---|---|
| P1 | 高 | worker 独立进程在代际见证之外：API 升 B2 而 worker 旧进程时，旧 worker 落库走 DDL DEFAULT 洗白派生 | **坐实**——runner.py 无任何心跳机制，jobs 是独立进程 | 迁移 #7 `worker_heartbeats`（单实例锁⇒单行 upsert）；run_forever 每 15s 心跳携 `WORKER_GENERATION`；自检门检查 5（60s 新鲜+代际匹配，is True 纪律）。实机三幕：worker 未起单点咬 / 双进程起 11/11 / （代际不符路径由旧代码不写心跳自然覆盖） |
| P1 | 高 | scope_registry 只接了 create_app——`_build_default_runner`（生产执行主路径）与 promote 脚本漏接 → registry None 分支把 public_internal 知识 Agent 全判 sensitive（403 过度限制回归） | **坐实**——两处构造点逐一核对 | 两处补 `scope_registry=asm.scope_registry`；witness 三连：worker 路径构造实测非 None、promote 脚本文本钉、public_internal 知识 Agent 真跑产物 internal+下载 200（反向 witness） |
| P2 | 中 | 自检门探针库与服务库可以是两个库（FLAI_DB_PATH 不一致）→ 各自 PASS 合成假绿 | **坐实** | health 自报 `db_identity`（库路径 sha256 前 16 位，opaque）；自检门检查 8 比对两侧指纹；实机幕 c：指错库单点咬 |
| P2 | 中 | `list_files_by_ids` 一把梭 IN 超 SQLite 绑定变量上限（32766）→ 失败样本路径炸掉分级派生 | **坐实** | 分批 500/批（语义等价：顺序保持+缺位静默）；33000 id witness + 跨批次顺序 witness |

R1 修复后：B2 witness 26 个全绿；变异 5（去分批）/变异 6（拔 worker
接线）各自单点咬合；全量 pytest 635 passed；自检门扩至 11 项，三幕
实机剧本（无 worker / 全 PASS / 库指纹不符）全部按预期咬合。

### R2（对 R1 修复的复审，round cap 第 3 轮）→ 9 findings，grounded 分野处置

**round cap 裁决（宪法「第 3 轮仍有 P1 → 交用户裁决」）**：R2 是第 3 轮，
findings 按归属分三类，非全部属本批：

**A. 我 B2/C2/C3 本批、非争议、当轮修复（2 条）**

| # | 级 | Finding | 复核 | 修复 |
|---|---|---|---|---|
| P1 | 高 | runner.py:176 `beat()` 的 `conn_factory()` 在 try 外，连接层瞬时故障逃逸 → 经 `_beat_if_due` 杀 worker，违反 beat 自身「不上抛」契约 | **坐实**——自引入回归（R1 新增心跳时埋的） | conn_factory 纳入 try、conn=None 兜底 close；witness `test_beat_does_not_propagate_conn_factory_failure`；变异 7（移回 try 外）单点咬 |
| P2 | 中 | deploy_selfcheck 从 jobs.runner 导 WORKER_GENERATION 连带拉 repos→jsonschema，破坏「纯 stdlib 探针」承诺 | **坐实**——破坏 C2 核心契约 | 常量下沉 config（纯 stdlib）；探针改从 config 导；**实证**：屏蔽 jsonschema 后探针仍能导入 |

**B. 我本批的轴缺口，如实声明 + 硬前置递延（2 条，触发器均 shipped 态不可达）**

| # | 级 | Finding | 处置 |
|---|---|---|---|
| P1 | 高 | runtime.py:259 污点轴不覆盖「工具读文件系统」数据源（monitor 工具读 run 目录拷证据进产物）→ 派生 internal | **触发器 = `monitor_adapter_gen_agent`（draft/禁知识/admin-only）+ 工具 gated on `FLAI_MONITOR_CORE_DIR`（默认 None fail-closed）→ 默认 shipped 态不可达**。ADR D6 如实声明为轴缺口，递延列「该 Agent 激活的硬前置：先补工具级 taint / 显式 output_classification」。不 fake-close，同 F3 自由文本旁路的诚实声明模式 |
| P2 | 中 | runner.py:298 心跳只在 run_once 前，长任务（monitor 工具 60-90s）→ 误报 worker 死 | 触发器同上（未激活的长任务 Agent）；shipped B2 相关 Agent 全快任务、部署期 worker 空闲即时心跳。ADR 递延，随该 Agent 激活改异步心跳/租约 |

**C. 非我 B2 scope、已提交（commit ab32ffc，ADR-0020/0022 workstream）→ 队列给 owner（5 条）**

`monitor_adapter_gen_agent`/`adapter.py`/`workflow.py`/`case_001.json`：
agent.yaml admin-only 未强制（V0.1 角色轴缺口）· adapter.py sample_run_dir
路径未约束（穿越/symlink）· adapter.py 相对路径 vs 子进程 cwd · workflow.py
`target_repo_path` 未写进 draft · eval fixture 未纳入 digest。**这些是那条
监控接入工作流的既有债，不在本批未提交 diff，未 stage、未改**。与 B 类的
taint 缺口同源、同「激活前必须清偿」的活化门——建议合并为一个
「monitor_adapter 激活前置」任务统一处置。

**R2 修复后**：B2 witness 28 全绿；变异 7 单点咬；全量 pytest 638 passed；
探针 stdlib-only 实证（屏蔽 jsonschema 仍导入）。

**round cap 透明交代**：A 类 2 条是自己当轮代码的非争议 bug（B1 先例：cap
是防争议 churn 的阀非防收敛加固的墙），已修+witness，但**未经第 4 轮独立
复审**；B 类 2 条 P1/P2 declare-and-defer（shipped 不可达 + 硬前置）；C 类
5 条出 scope 入队列。owner 可裁决：①对 A 类 2 修复起第 4 轮复审；②要求
B 类 taint 机制化后再让 B2 落地（而非 declare-defer）；③优先 monitor_adapter
激活前置任务。

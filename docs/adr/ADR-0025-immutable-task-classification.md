# ADR-0025：不可变任务级分级 + 单 chokepoint 内容门（monitor 安全激活闭合）

- 状态：Accepted（owner 裁决选项 A，2026-07-12）
- 关联：ADR-0021（数据分级轴）· ADR-0024（工具污点轴，本 ADR 保留其三轴派生，替换其 read 期内容门）
- 前身：`hold/monitor-taint-adjudication`（c48e752）的 read 期内容门被 Codex R1-A/R1-B
  判两 P1 未闭合 → round-cap-3 交 owner 裁决 → owner 选 A（本 ADR）。

## 一、问题（Codex R1-A/R1-B 两 P1）

ADR-0024 的内容门 `_task_content_is_sensitive` 在 **read 期按当前注册表重派生**分级，
且只遮蔽了部分字段/端点，暴露两个系统性缺陷：

- **R1-A（遮蔽面不全）**：只遮 input/output/summary 结构化载荷，漏了承载工具内容的
  错误文本列——`events.message`（tool_failed 把外部 grounding_failures 写入）、
  `tool_runs.error_message`、`model_calls.error_message`、`tasks.error_message`；且
  `GET /tasks`、`GET /conversations/{id}/tasks`、`POST /tasks/{id}/sim-run-ref` 三端点
  回 `tasks.error_message` 未 gate。内容遮蔽是「按端点按字段」的白名单 → whack-a-mole。
- **R1-B（read 期重派生会漂移）**：分级在读时按当前工具注册表重算 → 污点工具卸载/
  降级后，历史 sensitive 任务被重判 internal 外泄；无 files/samples 行的 sensitive 任务
  （eval origin / collect_samples=false / 早失败）尤甚；0.1.0 旧行无回填。

## 二、决策（选项 A：不可变落库 + 单 chokepoint）

### D1 执行期落库不可变 `tasks.data_classification`
- 迁移 #8：`tasks` 加 `data_classification TEXT`（可空，存量 NULL）。
- **执行期算一次、落库**（runtime.execute，agent 加载成功后、产出任何内容前）：
  `_task_data_classification`（文件∨知识∨工具 三轴，ADR-0024 保留）算一次 →
  `repos.set_task_data_classification` 落库。
- **CAS 首写真不可变（Codex R0 P1-2）**：setter 是 `UPDATE ... WHERE data_classification
  IS NULL`——只首写、返回最终持久值。此前无条件 UPDATE 会被二次 `runtime.execute()` 在
  状态机拒绝重跑前按当前注册表重算覆盖（工具降级→sensitive 改 internal，R1-B 换入口复现）。
  runtime 用 setter **返回的持久值**（非新算值）定产物/样本分级 → 保「产物分级==落库任务级
  分级」即便二次 execute。
- **read 期只读该列，绝不重派生**（闭 R1-B 漂移）：分级一旦执行期落库即为准，
  与 ADR-0021「产物继承执行期派生分级」同源。工具事后卸载不改已落库值。

### D2 单 chokepoint 内容门（`backend/app/api/classification_gate.py`）
把 whack-a-mole 收敛成唯一判定点 `is_sensitive_task(conn, task)`：
- 读 `task.data_classification`：`'sensitive'`→封 / `'internal'`→放 / `NULL`→**fail-closed
  兜底**（该任务已有任何派生内容行 tool_runs/model_calls/samples/files 或 error_message
  → 封；否则放）。NULL 兜底是安全网（罕见：未回填/部署竞态），不是重派生（不看注册表）。
- 判定一律 `== "sensitive"` / `is` 语义，绝不 truthiness。

### D3 统一封闭全部任务派生端点（闭 R1-A）
sensitive 任务的**每一个**返回任务派生数据的端点统一走 chokepoint（共 11 处；穷尽枚举
见下——Codex R0 复核补齐了初版「8 端点」漏掉的 cancel/review/会话 model_calls）：
| 端点 | 遮蔽 |
|---|---|
| GET /tasks/{id}、GET /tasks、GET /conversations/{id}/tasks、POST /tasks/{id}/sim-run-ref | `tasks.error_message`→marker |
| **POST /tasks/{id}/cancel、POST /tasks/{id}/review**（响应任务行，防「GET 封 mutation 漏」） | `tasks.error_message`→marker |
| GET /tasks/{id}/tool_runs | input/output/raw_path + **error_message** |
| GET /tasks/{id}/model_calls | request/response_summary + **error_message** |
| GET /tasks/{id}/samples | input/output/raw_path |
| GET /tasks/{id}/events | payload + **message** |
| **GET /conversations/{id}/model_calls**（逐行按归属任务分级；task_id=NULL 编排调用放行） | request/response_summary + **error_message** |
只回元数据（谁/何时/成败/工具版本/分级），内容载荷 + 错误文本列 → None + `content_withheld`。

**写侧纵深（Codex R0 P1-5）**：job 模型 wrapper（runtime `_ModelGatewayContext`）禁止 workflow
经 kwargs 透传 `conversation_id`/`task_id`/`agent_id`——杜绝「同时带 task+conversation 归因」
的 model_call 行经会话端点旁路遮蔽门。会话 model_calls 端点当前实际只有 task_id=NULL 的编排
调用（`_ModelGatewayContext` 不带 conversation_id），故 D3 会话行遮蔽是**纵深防御**（潜在非
现成 exploit）；写侧钉死 + 读侧过门双保险。

**边界外（用户提交非工具产出，D5/ADR-0024 一致）**：GET /tasks/{id}/feedback 与 POST /feedback
回用户自报反馈文本；GET /conversations/{id}（导引对话）与 task.inputs——均非工具从外部真源读出的
内容，不在门内。

### D4 存量回填（bootstrap.assemble，registry 可用处）
迁移只加列不回填（init_db 无注册表）。回填在 `bootstrap.assemble`（tool_registry 已载）：
对**终态** NULL 任务（completed/failed/cancelled/waiting_review）按**持久证据**定分级 →
sensitive，否则 internal。sensitive 证据三类：
1. 非 internal 的 files/samples 行；
2. tool_runs 引用当前判 sensitive 的工具；
3. **tool_runs 引用当前注册表不认识的工具**（卸载/scan 拒/改名——历史分级不可考，
   fail-closed 判 sensitive；不把「当前无命中」当「已证明 internal」，Codex R0 P1-3）。
- **子行一致化（Codex R0 P1-1，关键）**：下载门（files.py:277）与固化门（curation）检的是
  `files/samples.classification` **子行**、不是父任务列。回填把父任务升 sensitive 后，必须把其
  非 sensitive 子行**一并升 sensitive**（0.1.0 期 monitor 草案误落 internal 的子行否则仍过下载
  403 与 eval-cases 原样固化=半闭合假绿）。与执行期 `_register_outputs` 对新任务同口径。
- 幂等（只碰 NULL 父 / 非 sensitive 子），保守 fail-closed。
- created/queued/running 任务不回填（无内容），留 NULL，执行期落库。
- **诚实残差**：输入文件/知识轴的历史 sensitive 不由回填直接对账——但 ADR-0021 执行期已按
  文件∨知识轴给这些任务**产物**落 sensitive（→证据类 1 命中），且 sensitive 输入文件自身下载
  受其 classification 子行保护，故无泄漏面（详 repos.backfill docstring）。

### D5 代际 bump
`WORKER_GENERATION` → `m12-immutable-classification`：派生落库语义变，旧 worker（read 期
重派生代码）与新 worker 不可混跑；部署门代际检查逼 worker 重启到新代码。

## 三、保留自 ADR-0024（不重做）
工具污点轴 `_tool_taint_classification`（affirmative-only fail-closed）+ 三轴
`_task_data_classification` + tool.schema.json `output_classification` required +
5 工具 tool.yaml 声明 + monitor_adapter_recon=sensitive。仅**替换** read 期内容门。

## 四、验收标准（tamper 必咬）
1. 迁移 #8 幂等；存量库补列不崩；新任务 create 后 data_classification=NULL。
2. 执行期：sensitive agent 任务跑完 → tasks.data_classification=='sensitive' 落库。
3. **漂移 witness（闭 R1-B）**：sensitive 任务落库后，**卸载污点工具** → 该任务仍判
   sensitive（读列不重派生）。tamper：把 gate 改成重派生 → 此断言 RED。
4. **无 files/samples 行的 sensitive 任务**（工具轴触发、collect_samples=false）→ 仍 sealed。
5. **全端点封闭（闭 R1-A）**：sensitive 任务 → D3 表全部 11 处内容+error_message/message
   遮蔽（任务详情 8 + 会话 tasks + cancel/review + 会话 model_calls）；internal 任务不受影响。
   tamper：任一端点漏接 chokepoint → 该端点断言 RED（已实测会话 model_calls tamper 咬中）。
6. 回填：植入终态 sensitive-tool 任务（无 files/samples）→ assemble 后判 sensitive；
   纯 internal 历史任务 → 判 internal（不误封）。
7. NULL 兜底 fail-closed：data_classification=NULL + 有 tool_runs → is_sensitive_task True。
8. 部署门代际：旧代际 worker 心跳 → deploy_selfcheck FAIL（复用既有 witness）。

## 五、边界
- **P2 递延（governance output_field eval → case_results.checks[].detail，Codex R0 P2-1/原 R2-3）**：
  eval_runner 的 output_field check 把敏感产物实际值写入 case_results.detail，GET/POST
  /agents/{id}/eval-runs 不 gate。当前 monitor fixture 未用 output_field，**潜在非现成 exploit**；
  本 ADR 不闭合，记 retro（eval-runs 端点未来纳入同 chokepoint 或 detail 值脱敏）。
- admin_only 强制 / L0→L1 晋升仍 owner（ADR-0024 D4 不变）；本 ADR 只闭分级泄漏。

## 六、Codex R0 异源审闭环（本 ADR 是新架构，走新 R0 非第 4 轮）
86gs gpt-5.6-sol ultra 定向审 staged diff（动态 SQLite witness 逐条复现）+ loop-auditor 设计审
（活体 tamper 注入）+ 我方 grounded 端点穷举，三源独立收敛。R0 判 5 P1 + 3 P2（CHANGES_REQUIRED），
逐条闭合（各配 tamper 必咬 witness，`test_immutable_classification.py`）：
| 编号 | finding | 闭合 |
|---|---|---|
| P1-1 | 回填只升父任务不升 files/samples 子行→下载/固化门放行 | 回填步骤 4 子行一致化（D4） |
| P1-2 | setter 无条件 UPDATE→二次 execute 重算覆盖，非真不可变 | CAS 首写+返回持久值（D1） |
| P1-3 | 回填把「未知/卸载工具」当已证明 internal | 未知工具 fail-closed sensitive（D4.3） |
| P1-4 | NULL 兜底 `bool(error_message)` truthiness | 改 `is not None`；task_events 复核后不入兜底（派生轨迹必伴内容行） |
| P1-5 | 会话 model_calls 第 9 端点 + wrapper 可透传 conversation_id | 读侧过门（D3）+ 写侧 wrapper 钉死归因 |
| P2-1 | eval output_field detail 泄漏 | 记 retro（§五，潜在非现成） |
| P2-2 | cancel/review 响应任务行未过门 | 两处过 chokepoint（D3） |
| P2-3 | 测试漏验会话 tasks/双归因/未知工具等 | 补 8 witness（file 计 19 例） |
- loop-auditor 10 维 scorecard：修前 15/20🟡（主因端点覆盖 W1）；修后覆盖闭合。
- 残余：P2-1（eval detail）显式递延 retro；F1（会话 model_calls）当前潜在非现成（写侧已钉死）。

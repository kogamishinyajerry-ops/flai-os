# M12 · monitor 安全激活闭合（ADR-0025 不可变任务级分级 + 单 chokepoint）审查记录

- 分支：`feat/monitor-immutable-classification`
- 日期：2026-07-12
- 触发：owner 裁决选项 A（round-cap-3 用尽的 ADR-0024 read 期内容门 finding-chain → 换架构）
- 安全边界（数据分级/污点/operator 出场面）→ 宪法「命中即审」同步阻塞：**新架构走新 Codex R0**
  （非第 4 轮）+ loop-auditor 设计审 + 我方 grounded 端点穷举，三源独立收敛。

## 一、交付物

替换前一版（held `hold/monitor-taint-adjudication` c48e752）的 read 期内容门，闭合 Codex
R1-A（遮蔽面 whack-a-mole）/ R1-B（read 期重派生漂移）两 P1：

- **D1 执行期落库不可变 `tasks.data_classification`**（迁移 #8）——CAS 首写，read 期只读列不重派生。
- **D2 单 chokepoint** `backend/app/api/classification_gate.py`——`is_sensitive_task` 读列 + NULL 兜底
  fail-closed（认权威内容行，不看注册表→不漂移）。
- **D3 全 11 端点统一过门**（任务详情 8 + 会话 tasks + cancel/review + 会话 model_calls）+ 写侧
  wrapper 钉死归因。
- **D4 存量回填**（bootstrap.assemble）——三类 sensitive 证据（含未知工具 fail-closed）+ 子行一致化。
- **D5 WORKER_GENERATION bump** 逼旧 worker 重启。
- 保留 ADR-0024 工具污点轴（三轴派生 + tool.schema.json output_classification required + 5 tool.yaml）。

## 二、三源异源审收敛

| 源 | 方式 | 结论 |
|---|---|---|
| 我方 grounded | 端点穷举（grep 全 router）+ 数据流追踪 | 自逮会话 model_calls 第 9 端点 + cancel/review 漏门 |
| loop-auditor | 静态 + 活体 tamper 注入（monkeypatch）+ 全量 pytest | 修前 15/20🟡（W1 端点覆盖）；tamper 实测真咬非空咬；漂移/端点 witness RED |
| Codex R0 | 86gs gpt-5.6-sol ultra 定向审 staged diff，动态 SQLite 逐条复现 | **5 P1 + 3 P2，CHANGES_REQUIRED** |

三源独立收敛于「端点覆盖不全 + 回填不彻底」——正是本 ADR 要终结的 whack-a-mole 在自身复现，
验证异源审价值（我方与 loop-auditor 聚焦读端点，Codex 追到下载/固化门检子行的更深泄漏）。

## 三、Codex R0 findings 逐条闭合（各配 tamper 必咬 witness）

| 编号 | finding | 闭合 | witness / tamper 实证 |
|---|---|---|---|
| P1-1 | 回填只升父任务，不升 files/samples 子行→下载 403 不触发/eval-cases 原样固化 | 回填步骤 4 子行一致化 | `test_backfill_upgrades_child_rows`（tamper: WHERE 1=0 → RED 实测） |
| P1-2 | setter 无条件 UPDATE→二次 execute 重算覆盖，非真不可变 | CAS 首写 + 返回持久值；runtime 用返回值 | `test_setter_immutable_first_write_wins`（tamper: 去 CAS → RED 实测） |
| P1-3 | 回填把未知/卸载工具当已证明 internal | 未知工具 fail-closed sensitive + bootstrap 传 known_tool_ids | `test_backfill_unknown_tool_failclosed` |
| P1-4 | NULL 兜底漏 task_events + `bool(error_message)` truthiness | `is not None`；task_events 复核后**不纳入**（派生轨迹必伴内容行；纳入会误封良性 feedback，实测打回 4 例） | `test_null_fallback_by_content_rows_not_benign_events` |
| P1-5 | 会话 model_calls 第 9 端点 + wrapper 可透传 conversation_id | 读侧过门 + 写侧 `_sanitize` 钉死归因 | `test_conversation_model_calls_seal_by_task`（tamper: 去接线 → RED 实测） |
| P2-1 | eval output_field detail 泄漏 | 记 retro（ADR §五，潜在非现成 monitor exploit） | — |
| P2-2 | cancel/review 响应任务行未过门 | 两处 `redact_task_row_if_sensitive` | `test_review_and_cancel_seal_sensitive_task_row` |
| P2-3 | 测试覆盖缺口 | 补 8 witness，file 计 19 例 | 全绿 + 关键 3 tamper 实测咬中 |

## 四、验证

- 后端全量：`uv run pytest`（backend）→ **639 passed**（含 test_immutable_classification 19 例）。
- 全量门 `scripts/verify_all.sh`：前端 build + 三 testpaths pytest -n auto + **8 组 E2E 全绿**（exit 0）。
- tamper 自证：P1-1/P1-2/P1-4/P1-5 各 witness 注入破坏 → 对应断言 RED，还原 → 绿（load-bearing 实证）。
- key/EAR scan：staged diff 无密钥/EAR 红线词。
- 修复回归自证：task_events 过度纳入曾打回 test_feedback/test_m8 4 例 → 复核改正（诚实负结果，非假绿）。

## 五、残余与边界（诚实标注）

- **P2-1 eval output_field detail**：显式递延 retro（当前 monitor fixture 未用，潜在非现成）。
- **F1 会话 model_calls**：当前潜在非现成（job wrapper 不带 conversation_id）；读侧过门 + 写侧钉死双保险。
- **激活姿态（ADR-0024 D4 不变，owner/operator 门）**：L0→L1 治理晋升、admin_only 角色轴强制、
  FLAI_MONITOR_CORE_DIR operator 配置——均非本 ADR 代拍。本 ADR 只闭**分级泄漏**这一安全硬前置。

## 六、Codex R1/R2 复审与收口

**R1（复审 R0 修复）**：Codex 逐条动态复核 5 P1 修复，代码层确认闭合（跑纯函数集 5/5 绿 +
读全部改动）。提出 2 处**测试强度**不足 + 1 处**对称性**欠缺（非新 P1 泄漏，读门已挡）：
- W1：P1-1 witness 只咬 DB 列，未咬真实下载 403。
- W2：P1-5 witness 仓储直插双归因行验读门，未证写侧 wrapper 阻断。
- W3：job wrapper 已钉死 conversation_id，但会话 wrapper `_ids` 用 setdefault，workflow 塞
  task_id 可漏（对称缺口）。
（R1 最终裁决文本被 relay cybersecurity 内容过滤截断——安全细节触发上游 filter；实质 finding
即上述 3 点，见 codex_r1_out.log 推理段 line 3991/8241。）

**R1 补强（本轮全闭 + tamper 实测）**：
- W1 → `test_backfill_child_upgrade_blocks_real_download`（回填前非 403→回填后真 403；tamper 删
  步骤 4→RED 实测）。
- W2 → `test_job_wrapper_blocks_conversation_attribution`（chat 传 conversation_id→落库 NULL；
  tamper 去 _sanitize→RED 实测）。
- W3 → `conversation.py:_ids` 改「先剔三归因键再权威注入」（与 job 侧 `_sanitize` 对称）+
  `test_conversation_wrapper_blocks_task_attribution`（tamper 回 setdefault→RED 实测）。两方向
  双归因行均造不出。
- backend 全量 **642 passed**（test_immutable_classification 22 例）；conversation E2E（m6/m8）不回归。

**R2（收口确认，86gs gpt-5.6-sol ultra 定向审 delta）**：三点逐条 **CLOSED**——
①回填后真实 HTTP 下载请求命中 files.py:277 门返 403（非仅查列）；②job wrapper 剔除
conversation_id，落库恒 NULL；③conversation wrapper 先剔三键再权威注入，双归因两方向均
不可造。**新回归：未见。总裁决：APPROVE。**（沙箱无可写临时目录，定向 pytest 未独立启动，
以静态链路 + `git diff --cached --check` + 主控实跑 642 passed 为据。）

## 七、裁决与 round-cap
- round-cap：R0（CHANGES_REQUIRED，5 P1）→ R1（代码层闭合 + 2 witness 强度 + 1 对称补强）→
  R2（三点 delta 全 CLOSED，**APPROVE**）。安全 P1 均异源确认闭合 + tamper 实证，未超 cap。
- 三源收敛：Codex R2 APPROVE + loop-auditor 覆盖闭合 + 主控 grounded 端点穷举/tamper 6 连咬中。
- **终裁：APPROVE，合并 main + push**（宪法「过审即自主合并 push」）。
- **激活边界重申**：本 ADR 只闭「分级泄漏」安全硬前置。monitor 本已注册可执行（status=draft
  不硬阻执行），分级闭合后**已安全**；L0→L1 晋升 / admin_only 角色轴 / FLAI_MONITOR_CORE_DIR
  operator 配置仍 owner/operator 治理门（ADR-0024 D4，未擅自越权翻动）。

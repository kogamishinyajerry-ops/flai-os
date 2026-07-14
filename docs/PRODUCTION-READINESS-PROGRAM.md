# FLAi-OS 生产就绪纲领：内网导入准入门 + 底座成熟纲领

> **文档性质**：不可逆导入前的治理契约。V0.1 已封板（`v0.1.0-sealed`, commit `1e3cebc`，双判据齐）证明了**结构可扩展 + 生长层能长 Agent**，但封板显式**不外推内网环境层与运行韧性**。本纲领填补的正是封板免验的那部分——把"是否准备好成为雷打不动的不可逆底座"从主观判断变成**可证伪判据**。
>
> **哲学（镜像封板铁律）**：
> - **假绿死罪**：声明 ≤ 证据等级；判据判定一律 `is True`/`is False`，绝不 truthiness；不可验证残差显式标注。
> - **fail-closed**：准入判据未全绿 → 不允许不可逆导入（拒，不猜）。
> - **不拿长期成熟度堵廉价导入**：真·import-blocking 的只有一小撮廉价未验证假设（P0）；"完备预案 + 极致美学"是雷打不动底座的应有之义，做成**带判据的成熟纲领**（P1），不作为无限推迟导入的借口。
> - **诚实边界**：每项判据显式声明"证了什么 / 不证什么"。

---

## 0. 溯源：三域异源审计（2026-07-14）

本纲领的缺口清单来自三个**只读异源审计员**并行扫描，主控（Fable 5）对每域最承重断言**亲核取证**（✔=主控 file:line 亲核 / ◐=审计员 grounded 到 file:line，主控未复开）：

| 域 | 审计员 | 净判 |
|---|---|---|
| 韧性/运营 | resilience-auditor | 引擎扎实、外围运维半成品；**无"架构必然崩"BLOCKER**；真 BLOCKER = 3 个廉价未验证假设，全落封板免验的内网环境层 |
| 交互美学 | aesthetics-auditor | 设计主导型产品（宪法化 IA + 诚实地板 + token 纪律 + 自绘素材）；**无真 BLOCKER**；差在执行最后一公里 |
| 结构覆盖 | coverage-auditor | job 数值类骨架 2 发干净成立；**判据①结构保证不外推到日常交互入口**（交互运行时结构性弱于 job） |

> **主控纠错记录（诚实优先）**：审计前主控初评"无备份/DR"**是错的**——`scripts/backup_restore.py` 实际存在且成熟（在线备份 + drill 门 + 14 轮转 + 恢复清会话，✔ 已 `ls` 亲核）。README #14"全局无鉴权"亦已过时——鉴权 M11/ADR-0019 已实装（`backend/app/auth/middleware.py` 存在 ✔）。异源新鲜眼睛纠了主控 grep 漏检。

---

## 1. 第一道门：导入准入门（P0 — 必须全绿才允许不可逆导入）

**闭合成本合计 ~1–2 天。** 这四项全绿 = 导入净风险从"赌未测假设"降到"已知有界"。

### P0-B1 · 备份自动化编排 + 目标机真 drill

- **缺口**：备份能力成熟但**零调度**——手动 CLI，全仓无 cron/schtasks/Task Scheduler 接线（✔ grep 负）。永久不可替代数据无落地自动还原点。
- **证据**：`scripts/backup_restore.py`（✔ 存在，backup/drill/restore 三子命令）；`docs/DEPLOYMENT-SUPERVISION.md:13-43` 只守 API+worker 两进程，不含备份调度。
- **判据（is True）**：
  1. 目标机存在计划任务（Windows Task Scheduler / host cron）周期触发 `backup_restore.py backup`。
  2. 导入前在**目标机**执行一次 `backup_restore.py drill` → exit `is 0`，且 drill 恢复出的库通过 `PRAGMA integrity_check` + 关键表非空断言。
- **验证 / tamper**：真跑 drill（不是"备份文件存在"，是"备份可恢复"）；**tamper 咬合**：故意截断一份备份 → drill 必 FAIL（证 drill 门真咬，非摆设）。
- **诚实边界**：证目标机当日可恢复；**不证**长期轮转介质健康、不证异地容灾。
- **工时**：~0.5 天（drill 门已备 `backup_restore.py:88-116`，只差接线 + 一次真跑）。

### P0-B2 · DB 本地盘 fail-closed 强制

- **缺口**：DB 落网络盘 = WAL 静默腐化，**仅文档约束、代码不强制**。Windows 企业默认常重定向映射盘。
- **证据**：`README.md:243` / `DEPLOYMENT-SUPERVISION.md:56` 要求本地盘；`backend/app/main.py` 启动路径无 fixed-drive 断言（◐）。
- **判据（is False → 拒启）**：启动对 `FLAI_DB_PATH` 加断言——路径为 UNC（`\\host\share`）或映射网络盘 → 进程 fail-closed 拒启并明确报错；本地固定盘 → 正常。
- **验证 / tamper**：单测——UNC/映射盘路径 → 启动 raises/exit 非 0；本地盘 → 启动成功。**tamper**：删断言 → 恶意路径测试变绿（证断言 load-bearing）。
- **诚实边界**：拦已知网络盘形态（best-effort）；不保证识别所有奇异挂载 → 残余靠 `DEPLOYMENT-SUPERVISION` 文档兜。
- **工时**：~0.5 天（3 行 fail-closed + 单测 + tamper）。

### P0-B3 · 模型网关超时可配 + 内网延迟实测

- **缺口**：`timeout=60` 硬编码，仅 1 次重试，无环境旋钮。**主入口对话/导引全走 reasoning profile**——内网大模型 p99>60s 时每人首条消息即 503 = 最伤采纳信心的 day-one 崩溃。
- **证据**：`backend/app/model_gateway/gateway.py:142`（✔ 主控 issue #7 firsthand）；封板已列为"不阻断封板"（`README.md:208-213`）。
- **判据（is True）**：
  1. `gateway.py` timeout 读 `FLAI_LLM_TIMEOUT_S`（默认保守值，如 120s）。
  2. 导入前实测**内网目标模型** p50/p99 延迟并记录，配置超时 > 实测 p99。
- **验证**：单测证超时可配 + 一份内网延迟实测记录（非合成）。
- **诚实边界**：证首消息不因超时崩；**不证**模型质量、不证并发下延迟劣化（→ P1-M3 压测覆盖）。
- **工时**：~0.5 天（旋钮方案 issue #7 已定）+ 一次目标机延迟量测。

### P0-N1 · 结构声明收窄（文档，非代码 —— 但 import-blocking）

- **缺口**：若对外宣称"日常交互入口也享零 diff 结构保证"= **证据不足且有已知反例**（见 P1-T3）。导入即背假承诺。
- **证据**：交互路径 `backend/app/runtime/conversation.py:293-300` 只注入 `messages/model_gateway/agent_registry/agent_config` 四键（✔）；job 路径 `runtime.py:875-895` 另注入 `tool_registry/event_logger/output_dir/knowledge`（✔）。mode 枚举 `agent.schema.json:111` = `{job, interactive}`，无 streaming（✔）。
- **判据（is True）**：
  1. README 封板状态节 + 对外材料把结构声明改为「**job 数值/求解类骨架完成（2 发零内核 diff 成立）；交互类为单实例已建（guide_agent n=1）、通用性未验**」。
  2. 新增已知边界条目：「交互运行时无 tool_registry/knowledge 注入——需工具/RAG 的交互 agent 当前非零 diff」。
- **验证 / 异源**：文档 diff + grep 无残留过度声明；由 coverage 轴或 loop-auditor 确认"声明 = 代码现实，无 over-claim"。
- **诚实边界**：这是**框定诚实**，非能力扩展。能力补齐在 P1-T3。
- **工时**：~0.2 天。

---

## 2. 第二道门：底座成熟纲领（P1 — 导入后排期，每项带判据；"雷打不动 + 极致"的应有之义）

三条 track 对应三域，导入后可并行推进。**每条 track 收口宣称 verified 前走 §4 验证纪律。**

### Track T1 · 运维韧性（护住"出事能不能救"三问）

| ID | 判据 | 验证 / tamper | 诚实边界 |
|---|---|---|---|
| **M1** per-task reaper | 存在 per-task 墙钟上限；超时任务被置 `failed` 留痕（审计可见），队列继续 | 单测：死循环工具任务 T 秒后被 reaper 置 failed 且下一任务开跑。**tamper**：禁 reaper → 死任务永卡测试变红 | 拦"任务级挂死"；泄漏线程不可强杀仍存（`registry.py:151-172`），靠进程重启回收兜 |
| **M2** worker 可观测 | `/api/health`（或新 `/readyz`）payload 含 worker 心跳新鲜度 + queued/waiting_review 计数 + 最老任务龄期；worker 死 → 端点标 unhealthy（不再假 200） | 单测：停 worker 心跳 → 端点反映 unhealthy。**tamper**：worker 死但端点仍 200 = 失败 | 证"运维看得见";不含全链路 APM/分布式追踪 |
| **M3** 规模天花板量测 | 存在可重跑 load benchmark，产出 N-并发×M-队列的吞吐/延迟画像（p50/p99/最大队列龄期），文档化"可宣称并发画像" | 真跑 benchmark，记录曲线 | **测量非优化**——公开天花板，不承诺提升；单 worker 串行是刻意设计（低 QPS、人在环） |

> 证据锚：M1 `runner.py:300-335`（回收仅覆盖进程重启）◐；M2 `main.py:129-155`（health payload 无 worker 信号 ✔）；M3 无任何 load 测试（grep 负）◐。

### Track T2 · 极致美学（走用户既定设计工序，不套通用组件默认相）

**设计工序（焊死，镜像 workshop 工作流）**：拉片参考（74 张真机拉片 + GuidePage 自证标杆）→ 蓝图 → **四角色对抗审（ultracode）** → headless 像素级验（无横向溢出 light/dark×desktop/375 + 焦点环 + 诚实地板动效）→ auto-open 自证。

| ID | 判据 | 验证 | 诚实边界 |
|---|---|---|---|
| **A1** 三面 hero 手术 | `TaskDetail` 人签 review-card / `TaskCreate` 表单 / `AgentPortal` 治理弹窗**三面**重做到 GuidePage 同工艺，脱离 el-form/el-descriptions/el-dialog 默认相 | 像素基线（绝对 maxDiffPixels）+ 四角色审收敛 + 四态皆设计 + auto-open | 三面达标 = 高频面达"极致";全站其余二级面按需夹带，不一次铺满 |
| **A2** 焦点环成体系 | 全站 `role=button` 有克制 bespoke `:focus-visible`（纳入 clay 语言），无隐形焦点 | 截图/单测证每个可聚焦元素有可见环；可作 A1 手术横切子项一并做 | 键盘可达已全接（14 处 keydown.enter/space ◐）;本项补的是"环的设计一致性" |

> **优先级**：aesthetics-auditor 点名 **人签 review-card 收益最大**——平台最神圣的动作现长得像填表（`TaskDetail:186` label-width:80 el-form ◐）。A1 从人签卡起手。
> 证据锚：token 体系已罕见地深（App.vue :root 全 token 化，信任色锁真 token 化，暗色整面翻转过 AA ◐）——**骨架不重造，只补最后一公里**。

### Track T3 · 交互类结构补证（架构决策 + 判据①对交互类的延伸）

**这是真架构决策，非快修。** 交互类要享 job **同等**结构保证，须两阶段：

- **T3-a 内核扩展（一次内核改动期，V0.2）**：
  - **判据（is True）**：`ConversationService` context 注入 `tool_registry` + `knowledge`（default-deny，镜像 job 路径 ADR-0015：未声明的 Agent 连入口都拿不到）；交互 workflow 可声明式取用。
  - **验证 / 异源 / tamper**：Codex 命中即审（这是安全边界——工具/知识注入面，同步阻塞）；**tamper**：未声明 knowledge/tools 的交互 agent 仍拿到入口 = 失败（default-deny 咬合）。
- **T3-b 交互类零 diff 验证弹（判据①延伸）**：
  - **判据（is True）**：扩展后，新增一个"会话内调工具排障"或"多轮问文档(RAG)"的交互 agent，**只加 `agents/` 包、`git diff backend/app` 为空** → 判据①从 job 数值类延伸到交互类（n=1→ 真正的交互零 diff 样本）。
- **诚实边界**：这是判据①对交互类的**补证**，非重开封板；封板的 job 骨架声明不受影响。**流式类**（token 级 SSE/WS）不在本 track——无运行时路径，属独立 V0.3+ 决策。
- **顺序**：**不阻断导入**——guide_agent chat-only 已满足日常导引；交互调工具/RAG 是增强非必需。T3 排在 T1/T2 之后或并行推进。

---

## 3. 第三层：Backlog（P2 — 有界低危，登记不排期，按需/夹带清偿）

- **韧性**：M4 无迁移框架（`db.py:282-286` 自认；下个非增量 schema 变更前补 schema_version 表）· M5 无一等数据导出/迁出（数据非被挟持，标准 SQLite + 明文文件，缺策展迁移包）· M6 孤儿文件只诊断不 GC（`diagnose_gc_debt.py` 只读）· M7 feedback.message 无长度上限
- **覆盖**：C4 多模态输入半残（附件仅 text+xlsx，图/PDF/docx 未解析，`attachments.py:180` 标 V0.3 债）· C5 category/input.type 封闭枚举（新类别改契约文件，非 100% 零 diff，低危）
- **美学**：A3 字阶 token 定义了没落地（收敛 5–6 档）· A4 小号 faint 文本 10–11.5px 偏小（次要文本地板抬到 12px）· A5 设计回归无像素基线（对 hero 面加绝对基线）
- **文档卫生**：README #14/#12/#17 威胁模型据鉴权已实装偏保守，需更新（部分并入 P0-N1）

---

## 4. 验证与治理纪律（每 track 收口通用）

- **oracle/tamper 咬合**：每项判据必有"拆一层必咬"的 tamper 实证——"全绿"无咬合实证 = 假信心。禁伪造谓词强行闭环。
- **异源审（Codex 命中即审）**：安全边界同步阻塞——P0-B2 启动断言 · M2 health 鉴权面 · **T3-a 工具/知识注入面**。其余可 post-merge。走 86gs `gpt-5.6-sol ultra`。
- **loop-auditor 里程碑终检**：每 track 宣称 verified 收口前叫 loop-auditor（验证体系的验证者，正交于 Codex 代码审），镜像封板前终检。
- **round cap = 3**（R0+2 fix）；verbatim 例外（逐字落地 Codex 建议直接做）；commit 标 confidence。
- **生产成熟宣称门槛**：P0 全绿（导入前）+ P1 各 track 判据全绿（导入后）。未达显式标 △，绝不假 ✓。

---

## 5. 顺序与依赖

```
Gate 1（导入前，fail-closed）
   P0-B1 备份调度+真 drill ─┐
   P0-B2 DB 盘强制         ─┤ 全绿 ──► 允许不可逆导入
   P0-B3 超时可配+延迟实测 ─┤
   P0-N1 声明收窄          ─┘
                              │
                          【内网导入】
                              │
Gate 2（导入后，可并行）
   T1 运维韧性（最先——护住"能不能救"）
   T2 极致美学（用户高频面，人签卡起手）
   T3 交互结构（V0.2 架构；不阻断导入）
                              │
   P2 Backlog（登记，按需/夹带清）
```

---

## 6. 状态追踪表（持续更新；判据全绿才标 ✅，未达标 △，未开始 ⬜）

| 门 | ID | 项 | 状态 | 判据全绿？ | 证据链接 |
|---|---|---|---|---|---|
| Gate1 | P0-B1 | 备份调度+真 drill | ⬜ | — | — |
| Gate1 | P0-B2 | DB 盘 fail-closed | ⬜ | — | — |
| Gate1 | P0-B3 | 超时可配+延迟实测 | ⬜ | — | — |
| Gate1 | P0-N1 | 结构声明收窄 | ⬜ | — | — |
| Gate2 | T1-M1 | per-task reaper | ⬜ | — | — |
| Gate2 | T1-M2 | worker 可观测 | ⬜ | — | — |
| Gate2 | T1-M3 | 规模天花板量测 | ⬜ | — | — |
| Gate2 | T2-A1 | 三面 hero 手术 | ⬜ | — | — |
| Gate2 | T2-A2 | 焦点环成体系 | ⬜ | — | — |
| Gate2 | T3-a | ConversationService 注入 tools/knowledge | ⬜ | — | — |
| Gate2 | T3-b | 交互类零 diff 验证弹 | ⬜ | — | — |

> **Gate 1 未全绿前，不可逆内网导入 = fail-closed 拒。** 这是本纲领的唯一硬门。

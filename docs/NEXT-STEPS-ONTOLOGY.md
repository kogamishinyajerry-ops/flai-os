# NEXT-STEPS-ONTOLOGY — 本体论评测后的下一步优化分析

> 日期:2026-08-03
> 作者:Kimi K3(代维护者整理)
> 输入:①外部本体论深度评测报告(四路并行精读,综合 8.0/10);② codex PR #18/#19 合入后的最新 main(`5bf7be1`);③ K3 UI 深化轮次交接(`docs/HANDOFF-K3.md`)。
> 性质:分析与排序建议,不构成实施授权。每个切片动手前需用户确认。

---

## 1. 背景

外部评测报告对 `flai-os` main 做了契约本体层 / 宪章术语层 / 知识本体与运行时忠实度 / 治理与认识论四层精读,给出 8.0/10,并列出六项"外网即刻可做、进内网零返工"的 P0。

本文件的作用是:把报告 P0 与**最新 main 的真实状态**逐条对账(避免按过期快照施工),并给出与 codex 已合入工作、K3 UI 轮次相协调的实施排序。

报告的两条关键论断已经独立复核为真:

- 十态状态机文档/代码逐行镜像(`backend/app/core/statemachine.py:13-44`,`waiting_review` 出边仅 `{completed, failed}` 且注释明示"禁止任何自动化路径");
- 术语表 SSOT 缺口属实(`docs/` 无 Glossary 文件,ADR 最新为 0037)。

一条论断存疑:报告称"16/16 Agent 包内 eval_cases 全覆盖",但当前 main 的 `agents/` 仅 14 个目录。计数口径或快照时点有差,引用该结论前先数清楚。

## 2. codex PR #18/#19 与报告 P0 的关系:零重叠

codex 在 K3 轮次之后合入:

- PR #18:CI 必需检查(`verify_all` 为 required check,Node 24 actions);
- PR #19(`8adff40`,208 文件 / +53k 行):V1 源码就绪门禁、资产候选链、技能包材化与复用、owner 作用域 feature asset map、对话优先工作台(ADR-0033)。

方向是横向扩功能与 CI 治理,**不是**补形式化。报告六项 P0 在 `origin/main`(`5bf7be1`)上逐条核对结果:

| P0 | 状态 | 核对证据 |
|---|---|---|
| P0-1 术语表 SSOT(Glossary) | **未做** | `docs/` 无 Glossary;ADR 最新 0037,无 ADR-0038 |
| P0-2 Task 状态机/跨字段不变量 if/then 形式化 | **未做** | `git diff 7122330..origin/main -- contracts/task.schema.json` 仅一条 description 变更 |
| P0-3 治理三块(expertise/clearance/evidence_policy)入 required | **未做** | `contracts/agent.schema.json` 的 required/三块字段零改动 |
| P0-4 Event 上层本体(event_base + `$defs` 复用) | **未做** | `contracts/` 无 `event_base.schema.json`,三个 Event 契约仍各自独立 |
| P0-5 对抗性回归库(evals/adversarial) | **未做** | `evals/` 与 `docs/07_Eval_Standard.md` 零改动 |
| P0-6 Agent 分类学 category → paradigm 双轴 | **未做** | `agent.schema.json` 无 `paradigm` 字段 |

新增的契约测试(`tests/test_contracts.py` +220 行)全部服务于新 asset-draft / agent-shell 契约,未覆盖报告要求的状态机不变量。

**结论:报告 P0 清单整体有效,可直接作为下一轮 backlog。**

## 3. 建议实施排序

按"外网零返工 × 机械可验收 × 债务腐蚀性"三维排序:

### 切片 1:P0-1 术语表 SSOT + P0-5 对抗性回归库

- 纯文档 + 合成 payload,不碰运行时语义,风险最低;
- 术语漂移被报告点名为"最具腐蚀性的本体债务",且无外网业务反馈期会自然累积;
- 对抗性 6 类 payload(公式注入/prompt 注入/越权 file_id/zip bomb/伪造 digest/非法状态跃迁)全部可合成构造,与涉密语料无关;
- 机械验收:专名全仓唯一指称(grep 可核);对抗用例按仓内 tamper 方法论做必红见证;ADR-0038 记 glossary-as-ssot。

### 切片 2:P0-2 状态机与跨字段不变量形式化

- 仓内已有 `asset_draft_bundle` 的 `allOf`+`if/then` 风格先例,照同风格施工;
- 范围:`failed ⟹ error_message≠null`、`completed ⟹ finished_at≠null`、`origin=eval ⟹ conversation_id=null` 等文档已承诺的联绑;`event.schema.json` 的 `payload` 收口、`mock` 强制 required;
- 验收:十态 × 不变量穷举 property-based 测试(全合成数据)+ 违例 JSON 必拒的 tamper 见证。

### 切片 3:P0-4 Event 上层本体

- 抽 `event_base.schema.json`(`$defs` 公共块),三 Event 子类 `$ref` 复用;消除三处 `skill` 定义的字段集漂移;`Task.id`/`Event.event_id`/`KnowledgeScope.scope_id` 补 UUID pattern;
- 牵三处契约,放在状态机之后;schema-diff 机械验收。

### 切片 4:P0-3 治理三块入 required(需治理确认,不能纯机械)

- 报告自身提醒:这是**治理决策不是技术操作**;13 个未声明包的回填须逐包与业务确认,不得把"诚实的未定义"伪装成"已定义";
- 建议两步:先改 schema 使缺省路径显式,再分批回填 Agent 包,每批附 changelog;
- 此切片需要用户/业务侧参与,不宜由维护者独立完成。

### 切片 5:P0-6 Agent 分类学双轴(paradigm)

- 有双写迁移成本(category 保留 + paradigm 新增 → 全量回填 → 下版移除 category),放最后;
- 验收:`cfd_evaluate / fea_evaluate / step_response_evaluate` 三者 paradigm 一致;`guide_agent.paradigm=orchestrate`。

## 4. 与既有工作的协调约束

1. **先读 ADR-0033 再碰 UI。** codex 的对话优先工作台(`f7b1f2f` + 821 行 `conversation_shell_contract.test.mjs`)与 K3 轮次的 UI 壳层存在域重叠。任何 UI 侧下一步必须先对齐 ADR-0033,避免按过期假设施工。
2. **切片 1–3 与 UI/后端运行时零耦合**,可在 GPT 5.6 sol 接手后与任何 UI 工作并行,冲突面仅在 `contracts/`、`docs/`、`evals/`。
3. **CI 已是必需门禁**(PR #18):所有切片提交前本地 `UV_OFFLINE=1 bash scripts/verify_all.sh` 必须 EXIT=0,否则 PR 无法合并。
4. **评测分级纪律(E0–E3)**:实施 P0-5 时按报告建议把 eval case 头部加 `classification: e0/e1/e2/e3` 标签,E3 在外网显式 `SKIPPED-classified`,不静默当通过——与平台诚实标记风格一致。
5. 报告基于"未部署内网 + 评测集涉密"前提;凡涉及真实语料、真实工具、真实组织授权的项(报告的 B/C 类),本轮只做 fail-closed 槽位与接入契约,不写依赖真实数据的实现。

## 5. 开工前需先澄清的两件事

1. **Agent 包计数**:报告"16/16"与当前 14 个 `agents/` 目录不符——确认是快照差还是口径差,再决定是否引用报告的覆盖结论。
2. **报告原文归属**:评测报告原文目前在本机 `~/Downloads`(qwenwork 渲染版),未入库。建议将其关键结论以本文件为准入库,原文不入库(含外部渲染痕迹);如需保留原文,另议存放位置。

## 6. 关联文件

- `docs/HANDOFF-K3.md` — K3 UI 深化轮次交接(环境重启命令、UI 侧 7 条待裁决项);
- `docs/adr/ADR-0033-conversation-first-auto-routing-agent-shell.md` — UI 侧施工前必读;
- `docs/07_Eval_Standard.md` — 评测分级(E0–E3)的落点;
- `contracts/asset_draft_bundle.schema.json` — `allOf`+`if/then` 形式化的仓内风格先例。

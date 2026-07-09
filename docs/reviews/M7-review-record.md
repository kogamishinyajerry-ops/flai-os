# M7 会话附件 审查记录（ADR-0014）

- 对象：commit `2924e19`（M7 主体）→ 反方处置 commit（本记录）
- 命中即审依据：LLM 边界（附件进模型上下文）+ 未受信外部输入解析（文件内容/文件名）

## 异源 Codex 治理审：环境悬置

本机 codex 原生二进制缺失（`@openai/codex/node_modules/@openai/codex-darwin-arm64/
vendor/aarch64-apple-darwin/codex/` 目录被清空，时间戳 2026-07-09 10:47，疑 npm
重装中途态）→ `codex review` 抛 ENOENT，整个 codex CLI 不可用（换 relay 配置无用，
二进制同一个）。**异源 Codex 治理审悬置待用户恢复 codex**（`npm i -g @openai/codex`
或重装），恢复后补跑 `CODEX_HOME=$HOME/.codex-relay codex review --commit <M7 SHA>`。

## 反方 fresh-context 审查（补偿，2026-07-09）

Codex 不可用期间以 general-purpose subagent 做敌意审查（fresh eyes，正交视角；
同家族非严格异源，故上面的 Codex 交叉仍需补）。判定 **CHANGES_REQUIRED**，
findings 全部本地最小复现坐实后修复：

| # | 级别 | Finding | 复现 | 处置 |
|---|------|---------|------|------|
| 1 | P1 | 附件正文/文件名逐字闭合 fence，注入文字被踢出块外、规则行管不到（红线#1 结构隔离可破） | ✅ 正文 payload 令 `<<END_ATTACHMENT>>` 出现 2 次；文件名换行断 header | `_neutralize_sentinels`（正文+文件名 `<<`→`< <`）+ `_safe_filename_for_header`（去控制字符/引号）+ 上传端根因去控制字符；3 条 fence 完整性回归，tamper 拆中和→2 红 |
| 2 | P2 | 文本 `read_bytes()` 全量载入，大文本每轮重渲染内存放大（与 xlsx 流式防御不对称） | ✅ 90MB txt × 5/条 × 每轮 | `_render_text_file` 只读 `limit*4+64` 字节；tamper 回全量读→红 |
| 3 | P3 | 预算 body-only 软顶：规则行/fence/横幅不计入，「硬顶」不实 | ✅ budget=5 实出 191 | 预算计入结构开销（近似上界，中和膨胀已注明）；措辞校准 |
| 4 | P3 | 失败轮已上传附件跨轮残留搭车 | ✅ chips 可见 | 保留为重试语义（可见可移除），如实标注已知行为 |

**诚实标注（反方原文认可）**：红线#2「人是唯一签发者」全程守住——推荐从 LLM
回复解析且 agent_id 必过确定性候选表，P1 的 fence 逃逸能操纵 LLM 对话/误导推荐，
但**不能凭空签发任务或造幻觉 agent_id**。P1 修的是「防注入双层」第一层（结构隔离）
的名实相符，不是签发防线（那一层 M6 已 tamper 自证）。

处置验证链：pytest 313 绿（+5）· M6 e2e 10/10 · M2 e2e 8/8 · 三处新 tamper 咬合
（拆 sentinel 中和 2 红 / 拆字节顶 1 红，还原复绿）。

## 待补
- codex 恢复后补异源 Codex 治理审（严格异源交叉），findings 若有再走处置。

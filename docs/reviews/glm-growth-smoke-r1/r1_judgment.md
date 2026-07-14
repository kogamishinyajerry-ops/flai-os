# GLM 生长烟测 R1 · 判分书

- **裁定：A 级（合格产出四条全达成）**，澄清 0/3 次，用时 13 分 48 秒（10:36:40→10:50:28）。
- 被试：GLM-5.1 · OpenCode 1.15.13 `--pure`（MCP 全禁）；沙箱=flai-os@15d747a 去 spec 单提交快照 `b0cce19`。
- 判分人：主控 Claude session（spec 作者）；全部证据独立复验，未采信被试自报告。

## 一、四条合格线（逐条证据）

| # | 合格线 | 结果 | 证据 |
|---|---|---|---|
| 1 | Agent 包八件套过契约 gate | ✅ | `agents/bench_summary_agent/` 齐全；判分人独立复跑全量 **797 passed**（含契约自动校验），见 r1_pytest_rerun.log |
| 2 | 工具落 tools_impl/ 零新依赖 | ✅ | `bench_channel_stats` 纯 stdlib csv；safety 三开关全 false |
| 3 | ≥1 eval case（draft） | ✅ | 4 case 含 3 条失败路径（缺限值/双限值歧义/无输入）——已合 M10 晋升门形状 |
| 4 | 起服全链跑通 | ✅ | 判分探针 **16/16 PASS**（r1_fullchain_probe.log）：登录→上传→建任务→worker 执行→waiting_review→**产物数值对 oracle 4 通道全中**（CH2=7/CH4=4/CH1=CH3=0）→人签 approve→completed |

## 二、加分面（超出合格线的观察）

- **零内核 diff**：git status 仅 4 项新增、0 项修改——「只加包不动底座」由被试自发做到（其引用 docs/02 §5）。
- **宪法内化**：requires_human_review=true 且人签闸实测停住；数值判定零 LLM（判分探针剥除 FLAI_LLM_* 环境跑通全链，实证零 LLM 依赖）；「结论与建议」栏留给工程师填写，模板拒绝代下结论。
- **诚实标注 DNA 完整吸收**：`out_of_limit_count=null` 语义=「未判定而非 0 次」；数据质量提示不静默（无限值通道/配错限值/行级脏值全部如实列出）；draft/L0/owner=TBD 的诚实起点 + changelog 记明晋升前置。
- **house 先例复用**：bool 拒收引 excel_case_parser 先例、utf-8-sig 防 BOM、ADR-0008 事件折叠、ADR-0024 污点声明、行级脏值不摧毁整表。

## 三、观察项（非死点，进后续队列）

1. `_md_escape` 只转义 `|` 未归一换行——control_logic 在 M5 R2 被咬过的同款坑（P3，若收编该包时修）。
2. CSV 仅支持 utf-8/utf-8-sig，GBK 编码（内网真实高频）会折叠为 failed——诚实但有真实摩擦（收编时议）。
3. task 详情 payload 的 reviewer 字段为空串，签发记名落点在审计层——平台侧口径事项，非被试责任。

## 四、死点报告（D1-D5）

**零条目。** 脚手架队列本轮无新增。

## 五、判据裁定与诚实边界

- **判据②（生长完成）：字面通过（A 级）。** 但判分人声明证据等级：本轮需求属 tool_automation + 文件上传 + 确定性计算——平台**先例最富**的沟槽（performance_disk 同形）。单轮 A 证明「有先例可循的需求 GLM 长得动」，尚不证明泛化生长力。**建议 R2 换无先例形态（reasoning_assist 或 knowledge 挂载类需求）确认后再宣判据②封板**；owner 亦可接受首轮即封（spec 字面允许）。
- **判据①（零内核 diff 计数）**：本次接入内核零改动，但 tool_automation 属已锻类，**不计入**「连续 2 个新模块类」计数；作为已锻类稳定性的旁证记录。
- 环境层未验证（外网 bigmodel ≠ 内网 GLM 部署形态）——归滩头侦察，本测不外推。

## 六、附带发现

被试产出的 `bench_summary_agent` 本身是一个可用性接近真实需求的交付物（台架试验后处理是 D 簇通用形态）。是否把它从沙箱收编入主仓（须按真实代码走治理审+修观察项 1/2），交 owner 裁决。

## 档案清单

gen_data.py（数据生成器+oracle）/ bench_points.csv+bench_limits.csv（冻结样例）/ r1_prompt.txt（冻结需求原文）/ r1_run_meta.txt / r1_seg1_transcript.log（被试全程 1034 行）/ r1_fullchain_probe.py+log（判分探针）/ r1_chain_backend.log+r1_chain_worker.log / r1_chain_task_detail.json / r1_pytest_rerun.log / 本判分书。沙箱保留于 `~/projects/aircraft-comac/_glm_smoke_sandbox/`（R2 可复用基线）。

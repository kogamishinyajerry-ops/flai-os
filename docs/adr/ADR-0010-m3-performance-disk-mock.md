# ADR-0010: M3 Mock 性能盘 Agent 四项裁决

- 状态：已接受（2026-07-09）
- 背景：M3 交付批量作业样板（任务书 §12.4/§11/§14.4）：performance_disk_agent
  + 三个 Tool Package。安全红线：一切用通用词，无任何厂商名/型号代号/专有
  工具名；mock 计算与任何真实性能盘无关。
- 决策：
  1. **三工具拆分**（excel_case_parser / performance_disk_mock /
     excel_summary_writer）而非单一大工具：M4 替换真实性能盘时只动中间的
     计算工具（新增 mock=false 包、切换 agent.yaml.tools id，docs/03 §3
     禁止原地翻牌 mock 字段），解析/汇总两端复用不动——调用链形状即
     "上传→解析→逐 case 计算→汇总"的长期契约。
  2. **mock 确定性公式与失败注入**：performance_disk_mock 输出 =
     纯虚构代数函数（常数随手虚构，同输入必同输出，adapter 内注释声明）；
     `altitude_m > 15000` 返回 status=failed「超出 mock 包线」——刻意内置的
     单 case 失败路径，供批量容错逻辑与测试使用（边界：>15000 失败，
     =15000 成功）。解析器合理范围（altitude≤30000 等）刻意比包线宽，
     不越权吞掉包线失败路径。
  3. **V0.1 无 LLM**：agent model.profile=none；task_report.md 为纯 Python
     模板字符串。§11.1 的 LLM 环节（失败归纳/修表建议/自然语言摘要）全部
     推 V0.2，prompt.md 作为标准包强制件占位并记录 V0.2 红线（LLM 只进
     叙事通道，绝不改写数值/判定结论）。
  4. **批量任务「有失败 case 仍 completed」**：解析成功且汇总写出 ⇒ 任务
     success——即使全部 case 计算失败（失败如实进 failed_count/汇总表/报告）；
     解析失败/零有效 case/汇总写不出才任务 failed。依据 docs/05 §5：单 case
     失败 ≠ 任务失败，任务的交付物是"批量结果账本"而非"全绿"。
- 补充口径：docs/03 对"解析类工具 output_schema 必含 raw_output_path"的条款
  按意图解读为"解析外部程序原生输出文件的工具"——excel_case_parser 解析的
  是 File Store 已登记（含 sha256）的用户上传文件，可追溯性已由平台保证，
  故未加该字段；save_raw_files 三工具均如实置 false（Registry 尚无该机制，
  不声明未实现的行为）。
- 影响与风险：mock 结果无工程意义已在 agent limitations/README/报告头/
  samples.jsonl 逐行标注（docs/03 §3 四落点）；requires_human_review=false
  仅限 mock 阶段，M4 必须转 true（宪法铁律六）。

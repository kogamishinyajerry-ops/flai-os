# performance_disk_agent 变更记录

## 0.1.0（M3，2026-07-09）

- 初版（Mock 阶段）：excel_case_parser → performance_disk_mock（mock=true，
  纯虚构公式）→ excel_summary_writer 批量作业链路；三产物
  （result_summary.xlsx / samples.jsonl / task_report.md）落盘。
- 批量语义：单 case 失败不摧毁任务；解析失败/零有效 case/汇总写出失败才任务失败
  （ADR-0010）。
- V0.1 无 LLM（model.profile=none）；LLM 摘要记 V0.2 债。
- requires_human_review=false（mock 产物无工程意义）；M4 真实工具接入时必须转 true。

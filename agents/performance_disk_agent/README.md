# performance_disk_agent（Mock 阶段）

批量 case 计算的平台样板 Agent（M3）：上传 case 表（.xlsx）→ 解析 → 逐 case
调用 mock 计算 → 三产物落盘。**当前一切计算来自纯虚构公式
（`performance_disk_mock`，mock=true），与任何真实性能盘无关，输出无任何
工程意义**——本 Agent 此阶段的价值是验证批量作业链路，不是算数。

## 使用

1. 准备 case 表：首行表头，必需列 `case_id` / `altitude_m` / `mach` /
   `power_kw`，可选列 `bleed_flow_kgps`（示例见 `eval_cases/case_table_50.xlsx`）。
2. 门户上传该文件创建任务（inputs 可为空，或 `{"sheet_name": "..."}` 指定 sheet）。
3. 任务完成后下载三产物：
   - `result_summary.xlsx`：逐 case 结果汇总（case_id/参数/输出/status/error_message）；
   - `samples.jsonl`：样本沉淀，每行一个 case（含 `mock: true` 标注）；
   - `task_report.md`：模板化报告（计数/失败清单/参数范围，V0.1 无 LLM）。

## 失败语义（两级，与 docs/05 §5 对齐）

- **单 case 失败**（mock 包线注入 `altitude_m > 15000`、单 case 异常）：
  折叠为该 case failed 记入汇总，任务继续——**有失败 case 任务仍 completed**
  （批量作业语义，ADR-0010）。
- **任务级失败**：无输入文件 / 解析失败（坏文件/缺必需列/零有效行）/
  汇总表写不出。

## requires_human_review 说明

Mock 阶段为 `false`（产物无工程意义，无需人工签发）。**M4 接入真实工具后
必须转 `true`**——真实工程结论必须停 `waiting_review` 由人放行（宪法铁律六）。

## 不适用范围（agent.yaml limitations 摘录）

- Mock 结果不得用于任何设计/校核/决策；
- 不做全性能分析（无包线扫描/插值/裕度）；
- 不替代专业判断；
- 仅支持 .xlsx 单 sheet case 表。

## eval_cases

- `case_001.json`：期望口径（50 行表 → 48 有效 case = 45 成功 + 3 包线失败，
  2 行解析错误）。
- `case_table_50.xlsx`：50 行示例表（含刻意的失败注入行与脏数据行）。
- `generate_case_table.py`：示例表再生脚本（防二进制文件腐化，可随时重建核对）。

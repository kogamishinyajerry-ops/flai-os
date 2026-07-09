# excel_summary_writer

批量 case 结果 → `result_summary.xlsx` 的写出工具（`mock: false`——写文件
是真实动作；数据本身是否 mock 由数据来源标注，本工具只忠实转写）。

## 契约

- 输入：`{cases:[{case_id, status, params?, outputs?, error_message?}], output_path}`。
- 列序固定：`case_id` → 参数列（altitude_m/mach/power_kw/bleed_flow_kgps，
  按实际出现）→ 输出列（shaft_power_kw/fuel_flow_kgps/egt_c，按实际出现）→
  `status` → `error_message`。
- 输出：`{status, file_path, ok_count, failed_count}`；计数用
  `status == "success"` 显式比较。

## 失败语义

写盘失败（目录不存在/无权限等）→ `status: failed` + `error_message`，
绝不抛裸异常。空 `cases` 列表合法：写出仅含表头的表，计数 0/0。

## 已知限制

- 不做任何计算/校验/排序：行序 = 调用方给的顺序。
- 单 sheet 输出；不支持样式/图表。
- 与任何真实性能盘程序无关。

测试：`python3 -m pytest tools_impl/excel_summary_writer/tests -q`

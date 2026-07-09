# excel_summary_writer

批量 case 结果 → `result_summary.xlsx` 的写出工具（`mock: false`——写文件
是真实动作；数据本身是否 mock 由数据来源标注，本工具只忠实转写）。

## 契约

- 输入：`{cases:[{case_id, status, params?, outputs?, error_message?, mock?}], output_path, notice?}`。
- 列序固定：`case_id` → 参数列（altitude_m/mach/power_kw/bleed_flow_kgps，
  按实际出现）→ 输出列（shaft_power_kw/fuel_flow_kgps/egt_c，按实际出现）→
  `status` → `error_message` → `mock`（逐行转写 case 的 mock 布尔，缺省 false）。
- `notice` 有值时：数据 sheet（保持第一）之后追加名为「声明」的 sheet 写入该
  文本——表格脱离任务上下文单独传播时声明随行（docs/03 §3 第五落点）。
- 输出：`{status, file_path, ok_count, failed_count}`；计数用
  `status == "success"` 显式比较。

## 安全：公式注入防护（CWE-1236）

**输出所有文本单元格强制惰性**（写入后 `cell.data_type = 's'`，白名单式，
不做 `=` 前缀黑名单）——case_id/error_message 等来自用户上传表的未受信
字符串**不会成为活公式**；`=HYPERLINK(...)` 之类内容原样以纯文本保留。

## 失败语义

写盘失败（目录不存在/无权限等）→ `status: failed` + `error_message`，
绝不抛裸异常。空 `cases` 列表合法：写出仅含表头的表，计数 0/0。

## 已知限制

- 不做任何计算/校验/排序：行序 = 调用方给的顺序。
- 单 sheet 输出；不支持样式/图表。
- 与任何真实性能盘程序无关。

测试：`python3 -m pytest tools_impl/excel_summary_writer/tests -q`

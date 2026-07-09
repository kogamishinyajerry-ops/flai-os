# excel_case_parser

批量计算 case 表（.xlsx）解析工具（`mock: false`——真实解析用户上传文件，
不生成任何数据）。Tool Package 标准见 `docs/03`。

## 契约

- 输入：`{file_path, sheet_name?}`；缺省解析首个 sheet。
- 表头（首行）：必需列 `case_id` / `altitude_m` / `mach` / `power_kw`，
  可选列 `bleed_flow_kgps`；未声明的多余列一律忽略。
- 输出：`{status, cases:[{case_id, params}], errors:[{row, case_id, error}]}`。

## 失败语义（两级，刻意区分）

1. **行级问题**（缺值/非数值/超合理范围/重复 case_id/case_id 缺失）：
   不抛异常，进 `errors` 并跳过该行——单行脏数据不摧毁整表。
2. **解析器自身失败**（文件不存在/非 xlsx/缺必需列/空表/零有效行）：
   `status: failed` + `error_message`。

## 合理范围（行级校验）

`altitude_m ∈ [-500, 30000]`、`mach ∈ [0, 3]`、`power_kw ∈ (0, 20000]`、
`bleed_flow_kgps ∈ [0, 50]`。**刻意比 mock 包线（altitude_m ≤ 15000）更宽**：
包线判定是 `performance_disk_mock` 的职责，解析器只拦物理上不可能/明显笔误的
值，不越权提前吞掉包线失败路径。

## 已知限制

- 只读首个（或指定）sheet；多 sheet 工作簿的其余 sheet 忽略。
- 数值一律按 float 解析；不支持公式单元格以外的富文本/合并单元格语义。
- 与任何真实性能盘程序无关；本工具只处理通用表格。

测试：`python3 -m pytest tools_impl/excel_case_parser/tests -q`

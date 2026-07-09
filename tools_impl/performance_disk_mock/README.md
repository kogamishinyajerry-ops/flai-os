# performance_disk_mock

单 case 性能计算的 **Mock 工具**（`mock: true`，诚实标注，宪法第五条）。

## 与真实世界的关系：没有关系

- 全部公式是**纯虚构的确定性代数函数**（见 `adapter.py` 注释块），常数随手
  虚构，不来自任何真实性能盘程序/手册/试验数据。
- 输出（`shaft_power_kw` / `fuel_flow_kgps` / `egt_c`）**无任何工程意义**，
  仅用于验证平台批量调用链路。
- 每次调用在 `tool_runs` 表（mock=1）、任务事件、`samples.jsonl`、
  `task_report.md` 中均如实携带 mock 标注，绝不冒充真实结果。

## 契约

- 输入：`{case_id?, params:{altitude_m, mach, power_kw, bleed_flow_kgps?}}`。
- 成功输出：`{status:"success", mock:true, outputs:{shaft_power_kw, fuel_flow_kgps, egt_c}}`。
- 确定性：同输入必同输出（纯代数，无随机/无时间依赖）。

## 内置失败注入（刻意设计）

`altitude_m > 15000` → `{status:"failed", mock:true, error_message:"超出 mock 包线…"}`。
15000 是虚构数字，不对应任何真实包线；用途是给批量 Agent 的单 case 容错
逻辑与测试提供可控的失败路径（docs/05 §5：单 case 失败 ≠ 任务失败）。
边界语义：`> 15000` 失败，`= 15000` 成功。

## M4 替换路径

真实工具落地时**新增** `mock: false` 的独立工具包并切换 Agent 白名单 id；
**绝不**原地把本包的 mock 字段翻成 false（docs/03 §3：那是切换实现，
不是翻牌一个字段）。

测试：`python3 -m pytest tools_impl/performance_disk_mock/tests -q`

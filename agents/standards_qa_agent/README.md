# standards_qa_agent（专业标准问答）

面向专业规范、条款号和已有机型实例的交互式问答。回答同步返回结构化 `findings` / `refusals`；命中时提供条款号线索，能找到实例索引时在同一 finding 中给出 `standard_clause + type_case` 双依据。

## 当前能力边界

- 交互运行时尚未注入知识源，`knowledge.enabled=false`，也不声明任何工具；
- 只使用 `prompt.md` 中的合成目录级条款和实例索引，不输出条款或实例正文；
- 条款冲突不裁决只并列，最终解释与签字归标准责任人和工程师；
- 未收录的标准、专业域或机型实例必须写入 `refusals`；
- 所有 evidence 均未回源，`resolved` 恒为 `false`。

> **合成声明：demo 语料全合成，真实性未核。**条款号、标准代号、机型、实例编号、问题与评测案例均为虚构结构演示，不对应任何真实标准、机型或工程记录。

## 使用

通过 conversation API 创建 `standards_qa_agent` 会话，再逐轮提交 `content`。例如可询问“XR-100 双通道传感差异检查有哪些条款与实例定位”。

## 输出与核验

`output_schema.json` 将依据种类限制为 `standard_clause` / `type_case`，并严格支持 `confidence.basis` 三种值：`双源(条款+机型实例)`、`单源`、`推断`。正式知识源接入后若能力边界变化，必须同步修改 charter、limitations、prompt 与 changelog。

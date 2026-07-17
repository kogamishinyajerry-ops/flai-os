# policy_qa_agent（制度政策问答）

面向质量、保密、人事、跨部门流程和负责人线索的交互式问答。回答同时返回面向用户的 `assistant_message` 与结构化 `recommendation`（`findings` / `refusals`），每条 finding 都带制度文号或目录出处、置信度和 `resolved: false`。

## 当前能力边界

- 交互运行时尚未注入知识源，`knowledge.enabled=false`，也不声明任何工具；
- 当前只使用 `prompt.md` 中四条合成目录级索引，返回“去哪里检索、按什么文号检索、向哪个职能窗口确认”的线索；
- 不输出条款原文、不编造负责人姓名、不替代正式审批流程；
- 未收录制度与所外法规必须写入 `refusals`，拒答按正常履约处理；
- 所有依据均未回源，`resolved` 恒为 `false`。

> **合成声明：demo 语料全合成，真实性未核。**目录文号、部门称谓、问题与评测案例均为虚构结构演示，不对应任何真实制度、机构或人员。

## 使用

通过 conversation API 创建 `policy_qa_agent` 会话，再逐轮提交 `content`。例如可询问“质量问题闭环应先检索哪个制度、去哪个入口确认”。若询问未收录领域，Agent 会返回非空 `refusals`。

## 输出与核验

`output_schema.json` 约束 recommendation：`findings[].evidence[].kind` 只能为 `knowledge_doc`，摘录不超过 300 字，且 `resolved` 只能为 `false`。正式知识源接入后才能新增真实回源能力；届时必须同步修改 charter、limitations、prompt 与 changelog。

# control_logic_agent

「纯结构化生成型」平台样板（M5 泛化验证）：**零 LLM、零工具**——把结构化
控制需求（状态列表 + 转移规则）确定性展开为规范化控制逻辑描述。

## 使用

inputs（无文件上传，纯 params）：

```json
{
  "system_name": "示例供电切换逻辑",
  "states": ["idle", "running", "stopped"],
  "transitions": [
    {"from": "idle", "to": "running", "condition": "start_cmd"},
    {"from": "running", "to": "stopped", "condition": "stop_cmd"}
  ]
}
```

约定 `states[0]` 为初始态。产物：

- `control_logic.json`：规范化状态机（states/transitions/initial_state/不可达态分析）；
- `control_logic.md`：人读版状态转移表 + 不可达态警告。

## 校验语义（两级）

- **形状**：Runtime 按 `input_schema.json` 校验（缺字段/空列表→任务 failed）。
- **语义**（workflow 负责）：状态不重名、transitions 的 from/to 必须在 states
  内——非法时诚实 failed 并**一次列出全部问题**。

## 不可达态分析

自初始态沿声明转移 BFS，纯图算法。**不理解转移条件的物理语义**：条件互斥性/
覆盖性、外部事件进入的状态等工程判断归控制工程师（见 limitations）。

## 不适用范围（agent.yaml limitations 摘录）

不做真实控制系统设计；生成物是结构骨架非可执行代码；不替代控制专业判断。

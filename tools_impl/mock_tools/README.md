# mock_tools / mock_echo

平台闭环验证用 Mock 工具包（Tool Package 的 Golden Sample，标准见 `docs/03`）。

- **mock=true 的语义**：本工具不触任何真实工程程序，输出只用于验证平台链路。
  一切经它产生的任务产物在事件与样本中携带 mock 标注，**绝不冒充真实结果**
  （宪法第五条）。
- 契约：见 `tool.yaml`（入参必含 `message` object；返回必含 `status`）。
- 失败语义：适配器绝不抛裸异常，失败折叠为 `{"status": "failed", "error_message": ...}`。
- 测试：`python3 -m pytest tools_impl/mock_tools/tests -q`

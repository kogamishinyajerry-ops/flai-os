# JerryAgent Research Agent

这是 FLAi-OS 的首个 Agent-layer sidecar 包。它验证一个明确的架构边界：JerryAgent
负责推理、并行专家和执行过程，FLAi-OS 继续负责治理与签发。

当前状态为 `disabled`，不是生产可用声明。启用所需环境变量：

- `FLAI_JERRYAGENT_ENABLED=1`
- `FLAI_JERRYAGENT_URL=http://127.0.0.1:<port>`
- `FLAI_JERRYAGENT_TOKEN=<32-256 visible ASCII chars>`
- JerryAgent 进程使用同一 token 的 `JERRYAGENT_FLAI_TOKEN`

适配器不读取代理环境变量、不跟随重定向，也不盲重试 POST。仅当回执处于不确定态时，
它才会先按 execution id 做精确 GET 对账；只有得到精确 404，才允许以同一 canonical body
重放一次，之后不再发出第三次 POST。health、execution identity、revision 和响应字节上限
均做精确校验；任一未闭合失败都会让 FLAi 任务真实失败，不回退 native。

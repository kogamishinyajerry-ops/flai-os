# ADR-0033：FLAi-OS 控制内核与可替换执行后端

- 状态：产品方向已接受（委托人在本次设计会话中确认，2026-07-23；不构成组织签发、试点或上线授权）
- 关联：ADR-0006、ADR-0007、ADR-0012、ADR-0029、ADR-0031

FLAi-OS 保持唯一控制内核，权威持有身份与资源授权、Canonical TaskGraph、队列与并发、任务状态、审计证据、产物和最终交付决定。执行平面不是一个把所有实现混在一起的万能 Adapter，而是由 Execution Broker 组合三类窄 Port：`AgentRuntimePort` 承载候选 Agent Loop，`SandboxProviderPort` 提供强制隔离，`ToolExecutionPort` 执行 Python/Office/CAE/HPC 动作。OpenClaw、OpenHands 只能实现 Agent Runtime 侧能力，macOS 隔离实现 Sandbox Provider，CAE/HPC 实现 Tool Execution；三者互不替代，也不得拥有第二套任务真相、绕过平台策略、直接写权威终态或产生真人签发。

该选择保留现有轻内核与 Agent Package/Model Gateway/SQLite Job Runner/人签链，避免直接引入第三方框架后形成双控制面、双恢复语义和双审计账本。替代方案是以 OpenClaw 或 OpenHands 替换本平台 Runtime；它能缩短局部 Agent Loop 建设时间，但其个人或软件工程 Agent 的信任边界、状态模型和产品范围不能直接成为国企多主体工程平台的权威边界，因此否决。

本 ADR 只确定所有权与适配边界，不授权导入 OpenClaw/OpenHands 依赖、复制源码、修改运行时代码或承诺任何 Adapter 进入生产。动态 Agent Loop 每提出一次 replan、Tool、Model、Knowledge 或 Connector 动作，都必须回到控制内核，由唯一 Authorization Module 针对 step digest、Grant、policy、credential/authorization/trust-policy epoch snapshot、lease id/generation、预算和有效期签发一次短时 `ExecutionTicket`；所有下游 Port 无票拒绝并返回可核验 receipt。各 Port 分别通过自己的 conformance suite，Execution Broker 再通过组合验收；移除任一 Adapter 不得改变 FLAi-OS 的权威任务语义。

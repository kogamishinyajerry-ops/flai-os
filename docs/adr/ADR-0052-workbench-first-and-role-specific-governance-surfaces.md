# ADR-0052：工程工作台优先与角色化治理界面

- 状态：产品方向已接受（委托人在本次设计会话中确认，2026-07-23；不构成组织签发、试点或上线授权）
- 关联：ADR-0001、ADR-0016、ADR-0029、ADR-0049、ADR-0050、ADR-0051

FLAi-OS 的首发主产品和默认首页是工程智能体工作台：普通工程师通过单一 Composer 提交目标，在同一任务上下文中查看自治执行、真实状态、产物与证据，并在末端处理 Delivery Bundle。Phase 0A 不以战略 Dashboard、地图或组织管理后台作为第一原型，也不要求用户先理解 Strategy、Opportunity、People、Risk 等管理分类才能开始工作。

平台另有两个角色化 Surface。治理与运行中心面向平台管理员、安全人员和 Agent Owner，呈现 Agent/Workflow 生命周期、策略与授权、Sandbox、队列预算、异常恢复和审计证据；智能化指挥中心面向领导和 AI 负责人，待真实运行数据形成后，只读聚合经验证的业务结果、机会组合与风险例外。三者都是同一控制内核的视图，不能各自建立用户库、任务状态机、审计账本、授权逻辑或指标事实源。

“FLAi-OS 智能化指挥中心”可以作为领导汇报名称或后期管理模块名称，但不替代 `FLAi-OS` 产品总名，也不成为工程师默认入口。产品日常界面使用“工程智能体工作台”，整体定位可表述为“航空工程智能体协作与治理平台”。Management Plane 仅保留为架构说明中的治理/控制视角，不能据此新建 Next.js/PostgreSQL 第二应用。

替代方案是按 V0.1 Management Plane 设计包先建设 Dashboard、Strategy、Opportunity、Agents、Knowledge、Experiments、People、Risk 等一级导航。该方案缺少真实任务与证据数据源，容易产生手填指标、人员监控和装饰性地图，并挤压核心自治工作体验，故否决。

本 ADR 不批准 08–10 文档的具体内容或任何 UI 实现。后续先定义 Core Workbench UX 与角色信息架构；Agent/Workflow 生命周期治理其次；AI 转型方法论作为组织手册；领导指挥中心必须等 Phase 0A 产生可信事实后另行设计。

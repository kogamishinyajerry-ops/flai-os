# WorkBuddy / WorkBuddy Enterprise 企业协作与治理参考

- 调研日期：2026-07-23（Asia/Shanghai）
- 研究对象：Tencent WorkBuddy、WorkBuddy Enterprise、WorkBuddy Managed Agents（WMA）
- 来源边界：仅采用腾讯云产品页、腾讯 / WorkBuddy 官方产品文档和官方更新记录；未采用腾讯云开发者社区个人文章、媒体评测或二手截图。
- 使用边界：本文是公开资料研究，不是产品采购背书、源代码审计、等保测评或私有化交付验收。

## 1. 结论摘要

WorkBuddy 最值得 FLAi-OS 吸收的不是某个像素或动画，而是它把普通中国职场用户能理解的对象放在前台：**任务、项目、专家、技能、资料、产物**。安全能力也不是只藏在管理后台，而是进入任务输入区、计划确认、风险确认卡、沙箱拦截原因、文件变更和运行状态等日常路径。

公开资料显示，WorkBuddy Enterprise 已把以下能力放进同一产品体系：统一身份、组织架构、成员与部门范围、企业专家和知识库、项目资产、公共/个人连接器、Agent/Runtime/Session 管理、版本与快照、沙箱、Trace、评测、用量和安全审计。它对国内企业用户的主要价值，是把“AI 会做什么”和“组织允许它做什么”放到同一个工作台里。

但不能把产品页中的“安全与审计”“数据不出域”直接当成可验收的安全合同。公开资料仍未给出完整 RBAC 矩阵、审计日志保留与防篡改机制、沙箱内核级隔离方案、并发和资源配额算法、离线私有化 BOM、HA/DR 指标、SBOM/补丁流程等。对国企内网部署，这些都必须转化为采购前问卷、架构证据和验收用例。

## 2. 最新版本与资料时点

| 结论 | 证据与边界 |
| --- | --- |
| 截至调研日，WorkBuddy 官方站公开更新记录的最新版本为 **5.2.6（2026-07-12）**。 | [WorkBuddy 官方更新日志](https://www.workbuddy.cn/docs/workbuddy/Changelog)（访问：2026-07-23）。腾讯云文档中心镜像当时只列到 5.2.3，说明两个官方入口存在同步时差；本文以 WorkBuddy 官方站为版本判断依据。 |
| 5.0.0 是团队协作能力的重要分界：新增 Teams 项目、计划看板、项目资产库、项目动态、项目级专家/Skill/连接器/指令、任务协作与流转、消息中心。 | [WorkBuddy 官方更新日志，5.0.0](https://www.workbuddy.cn/docs/workbuddy/Changelog)（访问：2026-07-23）。 |
| 5.1.0 把治理反馈进一步前置：沙箱拦截卡展示原因和黑白名单，新增安全中心系统级工具开关、沙箱总开关审计、目录写保护和工具循环黑名单。 | [WorkBuddy 官方更新日志，5.1.0](https://www.workbuddy.cn/docs/workbuddy/Changelog)（访问：2026-07-23）。公开更新记录证明功能存在，不等同于证明其策略算法、不可绕过性或审计完整性。 |

## 3. 工作台信息架构

### 3.1 核心对象不是同义词

| 对象 | 官方定义或行为 | 对 FLAi-OS 的启示 | 来源 |
| --- | --- | --- | --- |
| 本地任务 | 任务栏统一管理任务；每个对话是独立任务，任务之间维护独立工作空间与上下文，并可并行运行。 | 把“可切换、可停止、可追踪的任务”作为一级对象，不要让用户先理解 Agent runtime 术语。 | [新建任务栏（本地 AI 工作台）](https://cloud.tencent.com/document/product/1831/134391)（访问：2026-07-23） |
| 工作空间 | 当前任务主要读取和保存文件的文件夹，可由用户选择或由系统创建。 | 工作空间既是用户组织资料的对象，也是文件权限边界；UI 应始终显示当前边界。 | [默认权限与安全沙箱](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Permission-Modes)（访问：2026-07-23） |
| 项目 | 团队核心协作阵地，以“项目—任务”两层组织指令、连接器、专家、Skill 和资料；项目配置自动注入成员新建的任务。 | 项目应承载团队标准和共享资产；任务承载一次具体执行。不要把个人会话直接升级成组织共享空间。 | [项目](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)（访问：2026-07-23） |
| 专家 | “人设 + 方法论 + 工具链”的角色切换机制；专家团由团长拆解并行任务、整合交付。专家本身不主动获得系统权限，只有配备 Skill/MCP 后才在授权下访问文件或外部服务。 | “谁来做”与“能调用什么”必须分开建模和展示；专家身份不能暗含工具权限。 | [专家](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Expert-Center)（访问：2026-07-23） |
| Skill | 封装脚本与工作流的特定工具能力，可安装、启停、搜索和卸载；官方明确提醒第三方 Skill 可能外发数据或包含恶意提示词、越权和后门风险。 | Skill 是可执行供应链资产，不是普通提示词模板；必须有来源、版本、权限、扫描和启停状态。 | [技能](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)（访问：2026-07-23） |
| Agent | 声明模型、角色、技能和工具的完整 AI 助手配置。 | Agent 配置应可审阅、可版本化、可测试、可发布，不能只是聊天框里不可追溯的隐式状态。 | [企业智能体](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/CloudAgent)（访问：2026-07-23） |
| Runtime | Agent 的独立云端运行环境，包含完整 Linux 文件系统、终端、Manifest 和一个或多个 Session。 | 面向管理员显示真实运行资源；面向普通员工继续使用“任务/助理”语言，避免把基础设施概念推给所有人。 | [企业智能体](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/CloudAgent)（访问：2026-07-23） |
| Session | 单个用户与 Agent 的完整会话；每个 Session 维护独立对话历史和上下文。 | 共享 Agent 不等于共享会话；默认应为每位调用方建立隔离 Session。 | [企业智能体](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/CloudAgent)（访问：2026-07-23） |

### 3.2 一次任务的可见路径

官方任务栏把“工作模式、模型、工作目录、Skill、连接器、权限模式”放在发起任务附近；执行中的任务保留在左侧，右侧边栏集中展示产物、工作空间文件、文件变更和浏览器预览。这是一种适合非技术用户的渐进式披露：先下达任务，再按需展开能力、边界和证据。

来源：[新建任务栏](https://cloud.tencent.com/document/product/1831/134391)、[右侧边栏](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Right-Sidebar)（访问：2026-07-23）。

可借鉴的交互模式：

1. 左侧只回答“我有哪些任务、项目和状态”；中央回答“当前任务在发生什么”；右侧回答“产物和变更是什么”。
2. 产物、文件树、变更 diff、预览分栏，避免把所有工具日志永久堆在主对话里。
3. 每次新建任务都让用户看见工作目录和权限模式；若系统自动创建目录，也要提供清晰路径。
4. 专家和 Skill 分开入口、分开徽标；在输入框中只呈现本任务选中的能力。
5. 对执行过程做分段折叠，但保留可追溯的工具调用与关键原因。

### 3.3 项目协作不是“多人共用一个聊天”

官方项目文档公开了更完整的协作闭环：

- 项目配置包含指令、连接器、专家和 Skill，任务创建时自动注入项目指令、项目资料库和个人记忆。
- 项目动态包含定向分享/流转、成员上传或更新文件、邀请成员、公开任务、资产配置变化等事件。
- 任务支持分享、多人协作和流转。流转包包括产物、进度摘要、标题、描述、处理人、状态、截止日期及附件。
- 项目资产库集中保存文档和任务产物，并以 RAG 形式进入任务上下文；文件列表显示更新人和更新时间。
- 邀请可以由成员发起，但是否加入由项目管理员审批。

来源：[WorkBuddy 项目官方文档](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)（访问：2026-07-23）。

这里最值得吸收的不是“团队聊天”，而是**上下文随任务流转、责任字段随任务流转、资产留在项目中**。对于国企场景，FLAi-OS 还应在此基础上补上交接前数据分级检查和接收方权限再校验，不能只复制上下文。

## 4. 身份、权限与组织资产

### 4.1 身份与管理员

| 公开能力 | 事实边界 | 来源 |
| --- | --- | --- |
| 统一身份 / SSO | 旗舰版接入“腾讯统一身份”；企业文档也提供企微 SSO 认证源配置。管理员登录可使用手机、邮箱或 SSO。 | [企业管理员](https://cloud.tencent.com/document/product/1831/134412)、[企业微信集成](https://cloud.tencent.com/document/product/1831/134413)（访问：2026-07-23） |
| 管理员角色 | 公开文档中的 CodeBuddy 管理员可以获得企业后台管理权限；旗舰版若要完整管理通讯录，还需同时配置腾讯统一身份的账号超级管理员和 CodeBuddy 管理员。 | [企业管理员](https://cloud.tencent.com/document/product/1831/134412)（访问：2026-07-23） |
| 网络准入 | 企业后台公开 IP 白名单，可按 IP/CIDR 限制 CodeBuddy IDE/CLI/插件登录。该页没有证明 WorkBuddy 桌面端所有通道、WMA API 和私有化入口都继承同一策略。 | [IP 白名单](https://cloud.tencent.com/document/product/1831/134424)（访问：2026-07-23） |

对 FLAi-OS 的关键提醒：公开文档主要展示“管理员/超级管理员”，尚不足以证明存在安全管理员、业务管理员、审计员的职责分离。国企生产环境不应让一个平台超管同时拥有策略配置、执行授权、日志删除和审计导出全部权限。

### 4.2 企业专家权限

WorkBuddy Enterprise 官方文档给出的专家治理比普通市场列表更细：管理员可以上传企业专家包、分类、保存草稿或发布；可见范围可设为所有成员或指定成员/部门；下发策略支持白名单和黑名单，并规定黑名单优先；还提供对“某成员—某专家”的最终权限查询。

来源：[专家管理](https://cloud.tencent.com/document/product/1831/134421)（访问：2026-07-23）。

可借鉴模式：专家详情必须同时显示“来源、版本、状态、可见范围、能力描述”；敏感专家使用白名单，黑名单优先；草稿和启用是两个状态；发布后的唯一标识不应被悄然修改。

### 4.3 组织知识权限

公开资料至少展示了三种知识资产边界，不能混为一谈：

| 知识来源 | 已公开权限行为 | 来源 |
| --- | --- | --- |
| 企业自定义知识库 | 创建时“可见范围”必选，默认企业全员，也可指定部分成员。 | [知识库管理](https://cloud.tencent.com/document/product/1831/134417)（访问：2026-07-23） |
| 乐享知识库 | WorkBuddy 继承当前登录用户的乐享权限；授权项包含读取、搜索、创建和编辑，任务可引用团队空间、知识库或文件。 | [乐享知识库](https://cloud.tencent.com/document/product/1831/134398)（访问：2026-07-23） |
| 项目资产库 | 项目成员共享，内容以 RAG 或文件读取进入任务上下文；更新人和更新时间可见。 | [项目](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)（访问：2026-07-23） |

公开资料没有说明企业 RAG 在分片、缓存、向量索引、导出产物和任务流转的每一步如何重新执行源 ACL，也没有说明用户权限被撤销后已进入历史上下文的片段如何处置。因此 FLAi-OS 应把“检索时 ACL、引用时 ACL、流转时 ACL、导出时 ACL”作为四个独立控制点。

### 4.4 连接器和凭据

项目连接器区分两类：公共授权由管理员配置、团队共享统一票据；个人授权由成员各自授权、票据不共享。协作任务中个人连接器被禁用，仅允许公共授权连接器；公共连接器调用日志仅管理员可见。

企业连接器管理文档进一步公开了 OAuth 2.1、OAuth 2.0 和 API Key 方式、Gateway 工具过滤、独立授权、最小权限和禁用开关。企业智能体凭据以加密方式存储，只在 Agent 运行时由代理层解密注入请求头；Manifest 的 secrets 通过安全通道注入而不写进沙箱文件。

来源：[项目](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)、[Connector 管理](https://www.workbuddy.cn/docs/enterprise/adminguide/Connector%E7%AE%A1%E7%90%86)、[企业智能体](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/CloudAgent)（访问：2026-07-23）。

值得吸收的模式是“共享身份”和“个人身份”在 UI 上永久区分，并且协作场景默认禁用不可审计的个人票据。仍需补足：凭据轮换、吊销传播时间、HSM/KMS 边界、明文可见角色和密钥访问审计。

## 5. 风险确认与沙箱

### 5.1 用户侧风险确认

官方公开两种文件/工具权限模式：默认权限和完全访问权限。默认权限在敏感路径写入、重要或批量删除、执行脚本/命令/外部程序、网络访问或敏感能力时要求确认；取消后不执行。确认界面建议用户检查操作内容、影响范围和执行理由。沙箱还配合安全删除/回收站；修改已有文件前的自动备份目前公开说明为仅 Windows 支持。

“完全访问”会关闭上述逐步二次确认；切换时仍要勾选风险确认。腾讯官方明确不建议在生产资料、客户/财务资料、唯一副本、仓库根目录、批量删除或未知脚本场景开启。

来源：[默认权限与安全沙箱](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Permission-Modes)（访问：2026-07-23）。

可借鉴的确认卡至少应包含：

- 动作：具体工具和操作类别；
- 对象：规范化后的目标路径、系统或账号；
- 范围：单文件/批量、工作空间内/外、数据条数；
- 理由：为什么完成当前任务必须执行；
- 结果：成功、拒绝、超时、失败及错误码；
- 决策人：真实人类身份、时间、通道和策略版本；
- 恢复：预览、备份、回收站、回滚点或不可恢复警告。

对 FLAi-OS，不建议在正式内网提供一个可以绕过全部确认的普通“完全访问”开关。若确需无人值守，应改成管理员批准的、限时、限目录、限工具、限网络、限任务类型的策略包，并保留不可关闭的审计。

### 5.2 计划先行

WorkBuddy 公开 Ask/Plan/默认三类工作方式，其中 Ask 只问答不修改文件，Plan 先生成计划、确认后操作；这把风险控制放在意图层，而不仅是在命令执行前弹窗。

来源：[新建任务栏](https://cloud.tencent.com/document/product/1831/134391)（访问：2026-07-23）。

适合国内企业用户的借鉴是使用清晰中文：**只查看、先计划、执行任务**，并在每种模式旁显示可做/不可做，而不是只展示开发者术语。

### 5.3 云端运行沙箱

公开资料中的“沙箱”至少有两种形态，不应合并理解：

1. WorkBuddy 本地任务的命令沙箱和工作空间文件权限；
2. 企业智能体 / WMA 的独立云端 Runtime。

WMA 产品页声称云端沙箱支持 7×24 运行、自动休眠和恢复、独享沙箱暂停不丢盘、持久化、跨节点恢复、CoW Fork、端口转发和预热池。企业智能体文档公开了 Runtime 的运行中/休眠/失败状态、独立 Session、版本/Checkpoint、10 分钟无访问自动休眠及永久删除 Session 的警告。

来源：[WorkBuddy Managed Agents](https://cloud.tencent.com/product/workbuddy-managed-agents)、[企业智能体](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/CloudAgent)（访问：2026-07-23）。

这些页面证明产品表面和产品声明存在，但没有公开证明容器/虚机边界、内核隔离、seccomp/AppArmor、网络出口、挂载策略、root 权限、镜像签名、资源配额和逃逸测试。它们必须列入技术尽调，不能从“独立沙箱”四个字推导。

## 6. Agent 生命周期、可见性与管理

### 6.1 已公开能力

| 能力 | 官方公开事实 | 来源 |
| --- | --- | --- |
| 声明式 Agent 配置 | Manifest 1.0 可声明系统提示词、rules、skills、plugins、MCP、subagents、workspace、secrets 和 envs。 | [企业智能体](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/CloudAgent)（访问：2026-07-23） |
| 发布前测试 | 创建界面提供 Test Run；Agent 可关联企业知识库、Skill、专家和 MCP。 | [企业智能体](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/CloudAgent)（访问：2026-07-23） |
| 版本和恢复 | Agent 支持版本管理；Runtime 支持 Checkpoint/Version 和回滚。 | [企业智能体](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/CloudAgent)（访问：2026-07-23） |
| 运维状态 | Runtime 页面公开运行中、休眠、失败，并提示清理无 Session 的残留 Runtime。 | [企业智能体](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/CloudAgent)（访问：2026-07-23） |
| 可见/可管理范围 | WMA 产品页声称 Agent 下发到 WorkBuddy 后可管理可见范围和可管理权限。 | [WMA 产品页](https://cloud.tencent.com/product/workbuddy-managed-agents)（访问：2026-07-23）。公开页面未给出角色矩阵。 |
| 评测 | 企业智能体公开标准化评测任务、评测集和评分方式。 | [企业智能体](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/CloudAgent)（访问：2026-07-23） |
| Trace | WMA 产品页声称提供全链路 Trace、效果评测和持续优化。 | [WMA 产品页](https://cloud.tencent.com/product/workbuddy-managed-agents)（访问：2026-07-23）。Trace 字段、保留期和导出接口未公开。 |

### 6.2 对 FLAi-OS 的生命周期建议

建议采用：**草稿 → 测试 → 待审核 → 已发布 → 已暂停 → 已退役**。发布和恢复都必须生成新的不可变版本记录；“谁能看”和“谁能管理”必须拆成两个维度；调用 Agent 的每位用户默认得到隔离 Session；删除会话和删除 Agent 均使用强确认并标出保留/清除范围。

官方企业智能体还支持把沙箱产物发布到公网。这个能力对通用 SaaS 有价值，但对国企内网是危险默认值。FLAi-OS 应默认无公网发布路径；任何跨域发布必须走单独出口、内容检查和人工签发。

## 7. 审计、数据安全与可观测性

### 7.1 公开确认到的表面

| 能力 | 公开证据 | 来源 |
| --- | --- | --- |
| 项目操作留痕 | 项目动态记录成员上传/更新、邀请、公开任务和配置变化；项目资产显示更新人与时间。 | [项目](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)（访问：2026-07-23） |
| 连接器审计 | 公共授权连接器的调用日志仅管理员可见。 | [项目](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)（访问：2026-07-23） |
| 沙箱审计反馈 | 5.1.0 新增沙箱拦截原因/黑白名单可视化、沙箱总开关审计和目录写保护；5.2.0 提到安全中心审计日志搜索与总数展示。 | [WorkBuddy 官方更新日志](https://www.workbuddy.cn/docs/workbuddy/Changelog)（访问：2026-07-23） |
| 企业安全能力 | 产品页声称全流程加密、可追溯可审计、MCP 每次调用授权校验、租户数据隔离和 AIGC 内容安全。 | [WorkBuddy Enterprise 产品页](https://cloud.tencent.com/product/workbuddy-enterprise)（访问：2026-07-23）。属于厂商公开声明，需由合同与测试验证。 |
| 运行可观测 | WMA 声称 Trace、Eval、成本视图；企业智能体公开 Runtime 状态、Session 调用方和错误排查入口。 | [WMA 产品页](https://cloud.tencent.com/product/workbuddy-managed-agents)、[企业智能体](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/CloudAgent)（访问：2026-07-23） |
| 企业日志入口 | WorkBuddy Enterprise 文档目录提供独立“日志管理”页面。 | [日志管理](https://cloud.tencent.com/document/product/1831/134425)（访问：2026-07-23）。公开抓取未稳定呈现完整字段和保留规则，本文不据此臆测。 |

### 7.2 必须区分的数据流

| 执行形态 | 公开资料能确认的数据位置或行为 | 不能据此推出 |
| --- | --- | --- |
| 本地任务 | 可读取用户授权目录；默认权限保护工作空间边界。 | 不能推出模型请求、诊断日志、崩溃报告、遥测和连接器数据全部本地。 |
| 团队项目 | 项目配置保存在云端并由成员共享；个人连接器票据保存在成员本地；任务流转复制完整上下文、调用记录和中间产物。 | 不能推出项目数据天然符合某个内网分级要求。 |
| WMA / 企业智能体 | 配置和运行在云端，官方声称 Skill 配置、MCP 结果和敏感产物云端驻留；每位调用方有独立 Session。 | “云端驻留”不等于“企业自有域”，除非部署和租户边界被合同明确。 |
| 企业私有化版 | 产品页列出企业内网、自备算力与模型、数据不出域。 | 不能推出完全离线、无许可回连、无更新回连、无遥测或已支持特定信创软硬件。 |

来源：[项目](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)、[WMA 产品页](https://cloud.tencent.com/product/workbuddy-managed-agents)、[WorkBuddy Enterprise 产品页](https://cloud.tencent.com/product/workbuddy-enterprise)（访问：2026-07-23）。

因此，公开 FAQ 中类似“数据本地执行不上传”“服务端片段用后即弃”的概括，必须按具体功能和版本解释，不能覆盖项目云配置、任务流转和 WMA 云端驻留这些同样由官方公开的事实。

### 7.3 FLAi-OS 应增加的审计双账本

WorkBuddy 的公开资料同时出现“项目动态/文件更新”和“安全审计/Trace”。FLAi-OS 可以把它们明确拆成：

1. **业务时间线**：让项目成员看懂任务、交接、文件、责任人和状态变化；
2. **安全审计账本**：记录身份、策略版本、授权决策、工具参数摘要、输入/输出数据分类、网络目标、结果、错误、审批人和完整性证明。

两者都引用同一个不可变事件 ID，但访问范围不同。安全审计员不依赖业务管理员提供日志；业务成员也不应看见密钥和不属于自己的敏感调用明细。

## 8. 部署形态与内网能力

腾讯官方产品页公开三种交付形态：

| 形态 | 基础设施与网络 | 公开企业能力 | 来源 |
| --- | --- | --- | --- |
| 旗舰版 | 无需自建；共享网络、多租户逻辑隔离；1 席位起。 | 第三方认证、组织架构、用量控制、企业 Skill/专家/智能体/模型、安全审计和 OpenAPI。 | [版本对比](https://cloud.tencent.com/product/workbuddy-enterprise)（访问：2026-07-23） |
| 专享版 | 云端专属资源池、专属 VPC；100 席位起。 | 在旗舰能力上增加专属网络、插件、服务实例和数据租户隔离。 | [版本对比](https://cloud.tencent.com/product/workbuddy-enterprise)（访问：2026-07-23） |
| 企业私有化版 | 自备算力资源与模型服务；企业内网；300 席位起。 | 第三方认证、组织架构、企业 Skill/专家/智能体/模型、全平台安全与审计、OpenAPI、企业网络、专属插件/服务实例和“数据不出域”。 | [版本对比](https://cloud.tencent.com/product/workbuddy-enterprise)（访问：2026-07-23） |

这足以证明腾讯公开销售“企业内网私有化”形态，但不足以作为实施方案。FLAi-OS 采购/参考前必须索取：

- 完全离线安装与许可证激活方式；
- 服务、镜像、端口、域名、证书和中间件 BOM；
- Windows/国产操作系统、CPU/GPU、数据库和浏览器兼容矩阵；
- 安装包、镜像和 Skill 的签名、SBOM、漏洞通告与补丁 SLA；
- 模型网关、提示词、文件、向量库、日志、备份和遥测的逐跳数据流图；
- 单机/集群容量模型、租户/部门/用户/Agent 并发配额和降级策略；
- HA、备份恢复、RPO/RTO、升级回滚和灾备演练；
- 安全管理员、系统管理员、业务管理员、审计员的权限矩阵；
- 审计事件字段、保留期、防篡改、签名、导出和 SIEM 对接；
- 沙箱逃逸、提示词注入、凭据窃取、网络外传和恶意 Skill 的测试报告。

## 9. 建议 FLAi-OS 直接吸收的 UX / 治理模式

### P0：上线前应有

1. **任务输入区常驻边界摘要**：当前工作空间、执行模式、已选专家/Skill/连接器、网络状态和风险级别。
2. **只查看—先计划—执行任务三段式模式**：默认“先计划”用于高风险或首次任务；执行前展示将访问的目录、工具和外部系统。
3. **风险确认卡结构化**：动作、目标、范围、理由、数据等级、恢复手段、审批人、有效期；拒绝必须 fail-closed。
4. **个人与组织资产分栏**：个人 Skill/连接器/记忆不能无提示进入项目；项目公共连接器必须显示共享身份和责任人。
5. **项目—任务两层**：项目存团队规范、资料和可用能力；任务存一次具体执行、责任人、产物和状态。
6. **专家和 Skill 语义分离**：专家回答“以谁的方法工作”，Skill 回答“能调用什么”；权限绑定 Skill/MCP，而不是专家头像。
7. **Agent 草稿/测试/审批/发布/暂停/退役**：每次发布对应不可变版本，支持有审计的回滚。
8. **产物与变更证据面板**：产物、文件树、diff、预览、来源、生成者和时间戳，且 `completed` 不自动代表可信或已签发。
9. **Runtime 运维视图**：运行、排队、等待确认、休眠、失败、取消中、已终止；展示并发配额、资源使用、最后心跳和可安全终止入口。
10. **业务时间线 + 安全审计双视图**：普通用户看到协作，审计员看到完整授权和工具链；两者用事件 ID 关联。
11. **中国办公生态的一等入口**：企微/微信/腾讯文档/乐享式的扫码、部门、标签和消息中心交互可参考，但必须由组织身份与策略约束。
12. **私有化默认无公网发布**：联网、分享链接、外部 Connector 和公网部署均作为显式、可审计的管理员策略，不作为普通用户默认能力。

### P1：规模化运营时补齐

- 企业专家/Skill 的来源、版本、签名、扫描结果、可见范围、责任人、最后使用时间和退役状态；
- 项目公共连接器与个人连接器的清晰徽标、测试环境和一键停用；
- 用户/部门/项目/Agent 多层并发与用量配额，以及队列、公平性和预算预警；
- Trace 与业务产物关联，允许从失败产物回到具体模型、工具、策略和审批事件；
- 发布前评测集、红线用例和人工签发，评测通过也不得自动获得生产发布权。

## 10. 公开资料不能确认的部分

以下项目必须保持“未知/待证”，不能因产品宣传而写成既成事实：

1. WorkBuddy / WMA 是否开源，以及公开源代码是否与商业部署版本一致；本调研没有找到腾讯官方开源仓库可用于实现审计。
2. 本地沙箱和云端 Runtime 的具体隔离原语、内核共享方式、root/特权容器、系统调用和设备权限。
3. 网络默认策略是否拒绝全部未授权出口，DNS、代理、内网横向访问和端口转发如何管控。
4. 并发上限、调度公平、用户/部门/Agent 资源配额、任务取消、僵尸进程和超时强杀语义。
5. 企业管理员、项目管理员、发布者、安全管理员、审计员的完整 RBAC/ABAC 矩阵和职责分离。
6. Agent “可见范围”和“可管理权限”的具体角色、继承、冲突优先级和撤销传播时间。
7. 审计日志字段全集、保留期、不可变存储、哈希/签名、防删除、导出格式、API 和 SIEM 对接。
8. 企业知识库在分片、向量、缓存、引用、任务流转和导出阶段的逐文档 ACL 与撤权清理。
9. Prompt 注入检测策略、误报/漏报指标、策略更新、绕过测试和管理员可配置范围。
10. 私有化版完整离线能力、许可证回连、更新源、遥测开关、第三方依赖、国产化兼容矩阵和密码合规。
11. HA/DR、备份加密、RPO/RTO、跨节点恢复一致性和故障演练证据。
12. Skill/MCP/Connector 供应链的签名根、SBOM、恶意包处置、漏洞 SLA 和历史版本召回机制。
13. 厂商产品页提到的 ISO、SOC、等保等合规覆盖的具体产品、版本、部署形态、地域和证书有效期。
14. “数据不出域”“服务端用后即弃”等声明在本地任务、项目协作、WMA、专享 VPC 和私有化版之间的精确适用范围。

## 11. 主要官方来源清单

以下页面均于 2026-07-23 访问：

- [WorkBuddy 官方更新日志](https://www.workbuddy.cn/docs/workbuddy/Changelog)
- [WorkBuddy Enterprise 产品页与版本对比](https://cloud.tencent.com/product/workbuddy-enterprise)
- [WorkBuddy 产品页](https://cloud.tencent.com/product/workbuddy)
- [WorkBuddy Managed Agents 产品页](https://cloud.tencent.com/product/workbuddy-managed-agents)
- [新建任务栏（本地 AI 工作台）](https://cloud.tencent.com/document/product/1831/134391)
- [默认权限与安全沙箱](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Permission-Modes)
- [项目](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)
- [专家](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Expert-Center)
- [技能](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)
- [右侧边栏](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Right-Sidebar)
- [企业智能体](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/CloudAgent)
- [企业管理员](https://cloud.tencent.com/document/product/1831/134412)
- [企业微信集成](https://cloud.tencent.com/document/product/1831/134413)
- [知识库管理](https://cloud.tencent.com/document/product/1831/134417)
- [专家管理](https://cloud.tencent.com/document/product/1831/134421)
- [IP 白名单](https://cloud.tencent.com/document/product/1831/134424)
- [日志管理](https://cloud.tencent.com/document/product/1831/134425)
- [乐享知识库](https://cloud.tencent.com/document/product/1831/134398)
- [Connector 管理](https://www.workbuddy.cn/docs/enterprise/adminguide/Connector%E7%AE%A1%E7%90%86)


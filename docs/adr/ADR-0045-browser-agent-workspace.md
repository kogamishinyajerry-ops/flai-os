# ADR-0045：浏览器是 Agent 控制面，不是运行边界

- 状态：Accepted
- 日期：2026-07-20
- 关联：ADR-0029（提议约束，非实施授权）、ADR-0039、ADR-0043、ADR-0044

## 背景

Claude Code、OpenCode 与 Pi CLI 证明了终端内 Agent 的执行能力，但终端、命令、上下文维护和
本地工作区不是企业工程师的合理默认入口。PI WEB 展示了另一种产品心智：Agent 会话与真实工作区
驻留在持续运行的机器上，浏览器只是跨设备监督、重定向和复核工作的控制面；关闭浏览器不等于取消
服务端会话，多项目、worktree 与会话可以并行存在。

这一心智与 FLAi-OS 的 SQLite 任务、后台 Job Runner、持久会话和 JerryAgent 运行层相容，但 PI WEB
本身明确假设可信用户、可信仓库与可信服务器路径，不提供沙箱、权限系统或多租户安全。因此它可以
作为工作台产品参考，不能替代 FLAi 的身份、分级、证据、人签、审计和发布治理。

参考：

- <https://pi-web.dev/>
- <https://pi.dev/packages/%40jmfederico/pi-web?name=web>

## 决策

### 1. FLAi Portal 采用“任务工作台”心智

普通员工的默认入口是浏览器中的工程任务与专业 Agent，而不是模型、prompt 或终端：

1. 从专业 Agent 或工程任务模板进入；
2. 提交文件、工况、约束和预期交付物；
3. 由服务端会话持续执行；
4. 用户离开页面后，任务只受服务端生命周期和显式治理动作影响；
5. 用户返回后，从持久会话与完整事实快照恢复监督。

CLI/TUI 继续服务开发者与高级诊断，不成为 CFD、结构、控制、适航或管理人员的必经路径。

### 2. 运行时隐藏，但运行事实不隐藏

界面不要求员工理解 Pi、JerryAgent、模型家族或命令行。运行时可替换性停在 Agent-layer adapter
边界；进入浏览器合同的只有任务依赖、当前阶段、匿名子智能体、等待原因、继续条件、接力和人签。

隐藏实现不等于制造轻松感。断连、gap、runtime unavailable、候选完成、等待人签和真实失败必须
使用各自的闭合状态与信任色，不能用“正在思考”遮蔽未知，也不能把 Agent `completed` 冒充发布。

### 3. 单焦点会话与按需工作流监控并存

当前批次把该心智落实为双投影：

- 会话主轴只显示一张紧凑事实卡和一个低频运行 glyph；
- 右侧监控栏默认关闭，按需展开 dependency、wait、handoff、subagent 与 signoff；
- 主轴与监控栏复用同一 conversation snapshot 和轮询权威，不增加第二 poller；
- 关闭监控栏不触发 cancel；返回会话后用完整快照恢复事实；
- epoch 变化、revision 回退或同 revision 内容漂移强制 resnapshot，失败时保留旧快照并明确 stale。
- unavailable 全量快照不会清除每个 task 的 bounded runtime revision 高水位；因此
  `epoch A/rev 7 → unavailable → epoch A/rev 6` 仍会强制 resnapshot，而一个经二次完整快照确认的
  新 epoch 可以建立新的高水位。

这保留了 ChatGPT.app 式按需侧栏的低密度、Claude Desktop 式 workflow/subagent 监督，以及
Claude Code/OpenCode 的低焦虑运行提示，同时避免永久第三栏和多行无限脉动。

### 4. JerryAgent 是执行底座，FLAi 是企业控制面

不采用“先接 PI WEB、以后再替换 runtime”的迁移路线，也不引入 LangGraph、Semantic Kernel 或
第二套编排状态机。JerryAgent 继续提供持久 Agent 执行、子智能体和等待事实；FLAi 继续拥有会话、
任务、专业 Agent manifest、权限、密级、依赖 gate、人签、产物与发布。

跨层只允许版本化、默认关闭、Bearer 保护、exact-schema、fail-closed 的 adapter 合同。浏览器从不
直连 JerryAgent，也不读取 prompt、工具参数、Jerry 内部 ID 或自由文本 runtime payload。owner-scoped
FLAi task handle 仅保留在快照数据模型中用于精确 inspect 路由，不进入可见文案、ARIA 描述或诊断型
DOM attribute；用户看到的是 Agent 名称与匿名 ordinal。

### 5. 门户扩展按真实使用复利排序

本 ADR 不授权新框架或门户重写。后续按以下窄切片推进：

1. **任务入口**：从冻结 Agent manifest 生成专业任务模板、输入 schema 与预期交付物；
2. **持久恢复**：明确“离开页面后仍在服务端运行”，并提供重连、gap resnapshot 与会话生命周期；
3. **工作区合同**：为服务器项目、文件、工具和计算环境定义受控 workspace profile，而非暴露任意路径；
4. **员工视图**：按角色呈现 Agent 目录、最近任务、签收件箱和课题连续性；
5. **高级视图**：将终端、原始日志和 runtime 诊断保留为受权渐进披露能力。

每一步都必须复用既有审计、人签、分级与来源见证，不以“更像工作台”为由绕过治理。

### 6. ADR-0029 owner 决策边界保持未越权

本批只把浏览器工作台接到现有认证 owner scope、任务、事件、模型/工具留痕与人签 SSOT；不新增
KPI route、治理自评分、自由文本 rationale/chain-of-thought、角色枚举或第二套 workflow trace。
ADR-0029 中的运行时授权轴仍是 sensitive 真实数据进场前的独立 owner 决策项；当前界面不得把
“已认证 username”表述成“已具备角色授权”，也不得用右栏监控完成度暗示治理控制已 verified。

## 被拒绝的方案

- 直接部署 PI WEB 作为 FLAi 企业门户：其安全模型不覆盖权限、分级、多租户、人签与发布。
- 给每位工程师安装 TUI：把终端运维和 prompt 工程转嫁给业务用户。
- 重写 JerryAgent 为另一套通用 Agent 框架：增加第二套运行真相且没有当前产品收益。
- 在首页常驻所有 Agent 流程：制造监控墙和焦虑，破坏单焦点会话。
- 用“数字员工仍在工作”掩盖失联或未知：运行源不可用必须明确披露。

## 验证

- 关闭/打开监控栏不触发任务取消或新轮询；
- 路由离开后服务端任务事实可由完整快照恢复；
- 普通路径不暴露 runtime 品牌、终端或内部标识；
- unavailable gap 之后的同 epoch revision 回退仍触发强制 resnapshot；
- native `not_applicable` 不显示成 runtime 故障；
- 截断快照披露“最近 N / 共 M”，不作全会话终态断言；
- 人签与 Agent 完成在文字、图形和信任色上均不混同。

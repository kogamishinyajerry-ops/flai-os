# FLAi-OS 深度接手与后续开发路线图

> 状态：DRAFT，规划已落盘，尚未发布到 GitHub issue tracker。
>
> 事实基线：main@fef203d，核对日期 2026-07-16。
>
> 当前 checkout：feat/eval-async-queue@e504595。该提交已经被 main 完整包含，
> 相对 main 落后 36 个提交、领先 0 个提交，不能作为后续开发基线。
>
> 工作区保护：当前有 68 个已跟踪截图类文件被修改，均视为用户资产。本计划不覆盖、
> 不暂存、不还原这些文件。
>
> Tracker 边界：GitHub CLI 当前返回 HTTP 401，未能刷新 issue/PR 状态；任何 issue
> 创建、评论、关闭或状态变更都需要凭据恢复后再显式执行。

## 1. Destination

把 FLAi-OS 从“V0.1 结构与生长能力已封板”推进到以下可证伪终态：

1. 主线、文档、验证脚本与实际能力重新对齐，不再由旧分支或旧状态文档误导开发。
2. Gate 1 的目标机证据全绿并由具名 owner 签发，才允许不可逆内网导入。
3. M4 真实性能盘以独立 real Tool Package 接入，mock 保留且如实标注。
4. 导入后再按 owner 裁决推进 Gate 2 运维韧性、交互结构补证与 UI 收口。
5. 每个阶段都有机械验收、tamper 咬合、诚实边界和可回退点。

本路线图是“如何抵达”的决策地图，不代表任何尚未执行的功能已经完成。

## 2. 不可破坏的边界

- 人是唯一签发者；LLM 不进入审核、晋升、导入授权或工程判决链。
- 假绿死罪；所有安全 gate 使用显式 is True / is False 语义。
- fail-closed；缺配置、缺证据、缺签发或状态不明时拒绝，不猜测。
- completed 不染绿；绿只给可核 REAL，teal 只给人签，amber 表示未核。
- 不引入 Redis、Celery、ORM、新数据库或新编排框架。
- 后台任务继续使用 SQLite 任务表与轮询 Job Runner。
- 不在未确认真实调用形态前实现 performance_disk_real。
- 不直接合并落后主线且含治理放松的候选分支。
- 不修改当前 68 个截图改动。
- 外部写操作默认 dry-run；GitHub 写入、owner 裁决和导入动作单独授权。

## 3. 当前事实基线

| 事实 | 当前证据 | 规划含义 |
|---|---|---|
| V0.1 已封板 | tag v0.1.0-sealed；README 与封板记录 | 结构层和生长层不重开；不外推内网生产就绪 |
| 最新主线 | main@fef203d | 后续实现只能从干净 main 新分支开始 |
| 当前 checkout | feat/eval-async-queue@e504595，behind 36 / ahead 0 | 只作历史工作区，不继续堆功能 |
| 最新主线代码图 | 6718 nodes / 21233 edges / 118 routes | FastAPI、Runtime、Job Runner、治理、Vue 已形成较完整内核 |
| 最近全量验证记录 | 2026-07-15 记录 20 步、227 PASS、0 FAIL | 是历史证据，本轮未在 main 上复跑，不能冒充当前实测 |
| Gate 1 本机代码项 | N1、N2、B2、M2† 已绿；B3 代码绿但缺内网 p99 | Gate 1 仍未闭合 |
| Gate 1 外部项 | B1 缺目标机调度和真 drill；B3 缺内网延迟；缺 owner 终裁 | 不可逆导入继续 fail-closed |
| M4 解锁物 | 缺脱敏样例、入参/出参清单、调用形态、目标 OS/Python/pip 现实 | 不能开始真实 Adapter 实现 |
| Agent 成熟度 | main 中 13/13 Agent 均 status=draft、maturity=L0 | “平台有治理闭环”尚未转化成首个真实 L1 |
| 离线发布 | package_release.sh/.ps1 均 NOT-IMPLEMENTED | 目前没有可交付离线包 |
| Windows 证明 | PowerShell、NSSM、msvcrt、NTFS 完整性门均未在目标机实测 | 只能声明已设计，不能声明已验证 |
| GitHub tracker | gh 读取返回 HTTP 401 | issue 真相未刷新，地图暂不发布 |

## 4. 已锁定的决策

1. 当前主线 main@fef203d 是代码事实源；当前 checkout 不是。
2. Gate 1 是不可逆导入前唯一硬门；Gate 2 不反向无限阻塞廉价导入。
3. Gate 1 收口必须同时满足：
   - 六项 P0 判据全绿；
   - 证据可复算且有负例或 tamper 咬合；
   - 具名 owner 带日期终裁。
4. M4 真实 Adapter 新建 tools_impl/performance_disk_real；不把 mock 原地改名冒充真实。
5. excel_case_parser 与 excel_summary_writer 维持既有平台契约；真实 Adapter 只替换中间计算件。
6. Gate 2 三轨必须拆开审理，不把 T1、T2、T3 当一个大提交整体硬合。
7. T3 会退休 P0-N2 的临时拒载护栏，属于治理级放松，必须由 owner 具名签发。
8. 下一个非纯加列 schema 变更前建立轻量迁移纪律，但不上 ORM/Alembic。
9. 需求接件 Agent 是独立候选，不属于 Gate 1，也不应抢在可信基线和首个 L1 之前。

## 5. 分支处置地图

| 分支 | 相对 main | 处置 |
|---|---:|---|
| feat/eval-async-queue | behind 36 / ahead 0 | 已并入 main。保护截图后停止在此开发；后续可归档，不做 reset |
| feat/gate2-wave1 | behind 32 / ahead 3 | 不整体合并。分别审理 T1 c65a745、T2 967e3e8、T3 8827c3a |
| backup-pre-r3-recommit | Gate2 旧备份 | 仅作取证，不参与合并 |
| backup-pre-r3v-recommit | Gate2 旧备份 | 仅作取证，不参与合并 |
| feat/requirement-intake-agent | behind 18 / ahead 4 | 可复用候选；先 rebase/移植、解除 ADR-0028 冲突、再全量验收 |
| main / origin/main | fef203d | 新开发基线 |

### Gate2 三提交的推荐处置

- T1 运维韧性 c65a745：
  - 保留设计与测试资产；
  - 从最新 main 建新分支重放，不直接合旧树；
  - 重点复核宽墙钟、泄漏执行线程、外部副作用、eval worker 监督与主线新迁移的交叉影响。
- T2 UI 967e3e8：
  - main 随后又合入 32 个提交，其中大量是 UI/UX 深化；
  - 不移植整批截图和样式；
  - 只核对 SignPanel 双签发面共用、amber 未核预填提示、焦点环等尚未被主线覆盖的语义。
- T3 交互 tools/knowledge 8827c3a：
  - 保持 HELD；
  - 独立 rebase、独立安全审、独立 owner 终裁；
  - 验证 interactive_safe、shell/write/workspace 跨字段拒载、引用覆盖与历史 fence 中和；
  - 未签发前 P0-N2 继续有效。

### ADR 编号冲突

Gate2 T3 与需求接件 Agent 都使用 ADR-0028，而 main 已有 ADR-0029。推荐：

- 为 Gate2 T3 保留 ADR-0028，因生产纲领已按该语义引用且候选提交明确 HELD；
- 需求接件 Agent 在接纳时改为 ADR-0030；
- 更新文件名、正文、自述、测试和提交说明中的全部引用；
- 不用“哪个先合哪个占号”的偶然顺序决定架构记录身份。

## 6. 分阶段开发路线

## Phase 0：恢复可信主线与验证门

优先级：P0，本地可立即执行。

预计：0.5 至 1.5 天，拆成两个可独立验收的窄切片。

### Ticket：恢复 main 可信基线

目标：

- 从 main@fef203d 创建干净、独立工作树或新分支；
- 当前 68 个截图改动原地保留；
- 在一次性验证环境复跑主线全门，不让验证覆盖用户截图。

实施：

1. 记录当前分支、HEAD、68 个修改文件清单及内容 hash。
2. 从 main 创建新的 codex 前缀开发分支；不得 checkout 覆盖当前工作树。
3. 首次全量验证在一次性 worktree 或临时副本运行。
4. 记录 frontend build、pytest、node 核与每套 E2E 的独立结果。

Done when：

- 新工作树 HEAD 等于 main@fef203d 或当时刷新后的 origin/main；
- 当前旧工作树的 68 个文件 hash 未变化；
- bash scripts/verify_all.sh exit 0；
- 结果记录包含每一步的命令、exit code、数量和时间；
- 未把历史 review 文档中的绿灯冒充为本轮执行结果。

Stop if：

- origin/main 与本地 main 出现未经核对的新差异；
- 新工作树无法建立且唯一替代方案会覆盖当前截图；
- 全量门失败但失败原因尚未定位。

### Ticket：修复跨平台验证门与证据污染

目标：

- macOS/Linux 与 Windows 开发验证覆盖等价；
- 日常 E2E 默认不改仓内金图；
- 部署验收与开发全量验收职责分离。

当前 main 的明确漂移：

- verify_all.sh：17 套 E2E，并执行 node --test；
- verify_all.ps1：9 套 E2E，不执行 node --test；
- Windows 漏 8 套：m9、m10、m11_auth、cfd_flow、batch_a、batch_b、
  eval_queue、eval_snapshot；
- README 与两脚本注释仍写 5 套；
- PowerShell 全量门依赖 Node、Playwright 浏览器和 uv 在线/缓存能力，
  与目标机免 Node 的离线部署口径不是同一个门。

实施：

1. 对齐 verify_all.sh 与 verify_all.ps1 的步骤和 E2E 清单。
2. 扩 backend/tests/test_scripts_parity.py：
   - 两边 E2E 集合完全相等；
   - 两边都包含 frontend build、全量 pytest、node 核；
   - 缺一项时测试变红。
3. 给 E2E 统一增加临时 artifact 输出目录：
   - 默认写临时目录；
   - 只有显式 UPDATE_GOLDENS=1 才更新 docs/reviews 下的证据图。
4. 文档明确两个门：
   - 开发/CI 全量门：build + pytest + node + 浏览器 E2E；
   - 目标机部署门：预构建 dist + API/worker + deploy_selfcheck，不要求 Node/Playwright。
5. 更新 README 和脚本注释中的数量与边界。

Done when：

- parity 测试可机械证明 sh/ps1 等价；
- 默认跑全量验证前后 git status 不新增或改写证据图；
- 显式 UPDATE_GOLDENS=1 仍可生成审查截图；
- Windows 脚本至少通过静态解析，并在目标机阶段补真运行证据；
- deploy_selfcheck 与 verify_all 的职责在 README 中不再混淆。

### Ticket：恢复文档 SSOT

目标：把“历史设计”“当前事实”“候选 HELD”“未来计划”四类文档状态分开。

最低修复集：

- README：
  - “唯一悬置 M4”改为 M4 + Gate1 目标机证据；
  - 删除“零前端单测”“全局无鉴权”等过时断言；
  - 校准 polling、RAG、超时变量和验证套件数量；
- .env.example：
  - 增 FLAI_LLM_TIMEOUT_S；
  - 删除仍按硬编码 60s 描述的旧说明；
- docs/M4_intranet_day1_recon_checklist.md：
  - 1-5 从“60s 是否够用”改为“采样 p99 并配置 timeout 大于 p99”；
- docs/01_Overall_Architecture.md：
  - BM25 Knowledge 已实现，向量/Obsidian/MCP 仍未实现；
- 旧 plans/specs/ADR：
  - 只加 status 头，不重写历史内容；
  - 标 completed、superseded 或 held 及其替代证据。

Done when：

- git grep 不再在当前态文档中命中过时的“全局无鉴权”；
- README、生产纲领、架构文档、环境样板无相互冲突的当前态断言；
- 历史文档保留原始决策，不把历史基线伪装成当前事实。

### Ticket：恢复 tracker 只读对账

实施：

1. 由用户恢复 gh 认证；本任务不代填或输出凭据。
2. 只读列出 open/closed issues 与 PR。
3. 把本路线图中的票名与现有 issue 去重。
4. 获得显式授权后，才发布 wayfinder map 与子 issue。

Done when：

- gh auth status 成功；
- issue/PR 清单可读取；
- 本地路线图记录与 tracker 无重复或相互冲突的活任务；
- 未经授权没有任何 GitHub 写入。

## Phase 1：等待内网输入期间的本地价值切片

优先级：P0/P1；不得延误 Gate1 外部协调。

### Ticket：完成首个真实 L1 晋升

目标：把“治理设施已建”变成第一条真实、可复算、由人签的成熟度记录。

推荐对象：control_logic_agent 或另一个 profile=none、mock=false、输入输出可本地复算的
确定性 Agent；不以 performance_disk_mock 冒充真实。

Done when：

- 至少 3 个 approved eval case，含明确失败路径；
- 异步评测从冻结快照执行，failed=0、skipped=0；
- case digest 与当前 Agent 版本匹配；
- 具名人确认 exception_paths_handled is True；
- promotion 表、agent.yaml、changelog 三方一致；
- deploy selfcheck 或启动 reconciliation 能发现并拒绝磁盘/DB 晋升漂移；
- L1 只证明该 Agent 的已测边界，不外推平台全部 Agent。

### Ticket：裁决需求接件 Agent 是否接纳

候选：feat/requirement-intake-agent，behind 18 / ahead 4。

已有价值：

- Agent 包、资产目录 Tool、16 条资产清单、append-only backlog CLI；
- 37 项新增测试；
- backend/app 零 diff。

接纳前必须：

1. 从最新 main 重放而非整体 merge 旧树。
2. ADR 改为 ADR-0030。
3. 复核资产清单的 status、honest_note、数据分级和 owner。
4. 复核 backlog ledger 的权威路径、锁、坏行 fail-closed、备份/恢复和 Windows 行为。
5. 明确机器评估只产候选，人签才允许状态推进。
6. 全量 verify_all 通过。

该票不属于 Gate1；若 M4 目标机窗口已到，立即让位给 Gate1/M4。

### Ticket：裁决 Gate2 三轨候选的去留与顺序

这是 HITL 决策票，不自动执行。

推荐默认：

1. T1 运维韧性：保留，导入后优先；可在等待期做最新主线重放与审查，但不抢 Gate1。
2. T2 UI：只抽尚未覆盖的签发语义，不移植旧截图和大面积样式。
3. T3 交互结构：继续 HELD，具名 owner 终裁后才退休 N2。

## Phase 2：Gate 1 目标机证据与离线交付

优先级：P0，阻塞不可逆内网导入。

外部前置：

- 目标 OS、版本、位数；
- Python 精确版本；
- 是否有内网 pip 镜像及覆盖版本；
- 模型端点、鉴权、模型名、并发/限流；
- 至少一次目标机窗口和具名 owner。

### Ticket：闭合 Gate1 目标机证据

实施：

1. P0-B1：
   - 接计划任务或等价调度；
   - 真跑 backup；
   - 真跑 drill；
   - 截断一份副本，证明 drill 会失败。
2. P0-B3：
   - scripts/measure_llm_latency.py 采样多次；
   - 原始逐请求时延落盘；
   - 第三方可复算 p50/p99；
   - FLAI_LLM_TIMEOUT_S 大于目标模型实测 p99。
3. Windows 核验：
   - init_db、API、worker PowerShell；
   - msvcrt 单 worker 锁；
   - NTFS symlink/junction 完整性门；
   - NSSM 启动、崩溃重启、环境加载、关停；
   - API/worker 代际一致。
4. 具名 owner 审阅全部证据并签发。

Done when：

- B1、B2、B3、N1、N2、M2† 全绿；
- tamper 证据全部咬合；
- 目标机 deploy_selfcheck 12/12 PASS；
- owner 签发记录有姓名、日期、证据索引和诚实边界；
- 未签发时导入脚本或流程继续拒绝。

### Ticket：构建并验证离线发布包

决策：

- 有合格内网 pip 镜像：requirements.lock + hash + 预构建 dist；
- 无镜像：匹配目标 OS/Python ABI 的 wheelhouse；
- 信息不足：package_release 继续 NOT-IMPLEMENTED，禁止抽奖式打包。

发布物至少包含：

- 源码与预构建 frontend/dist；
- 精确依赖锁和 hash；
- 选定分支的 wheels 或镜像安装说明；
- 配置样板，不含 secret；
- SHA256 manifest；
- 初始化、首账户、API、worker、selfcheck、backup/drill 操作说明。

Done when：

- package_release.sh 与 package_release.ps1 行为等价；
- 干净目标机在断网条件下完成安装；
- 不需要 Node；
- 建首账户后 API/worker 启动；
- 静态资产闭包完整，根页、深链和首个 JS/CSS 可访问；
- deploy_selfcheck 12/12 PASS；
- worker 重启演练与 backup drill 通过。

## Phase 3：M4 真实性能盘 Adapter

优先级：Gate1 签发后最高。

### Ticket：冻结真实性能盘调用契约

阻塞前置：

- 一份结构保真的脱敏输入；
- 完整入参/出参、单位、范围、默认值；
- 一次真实操作观测；
- CLI、COM/DLL、Excel 宏或 HTTP 的真实调用形态；
- 典型与最坏耗时、许可证和并发限制。

决策产物：

- ADR：调用形态、失败分类、超时、工作目录、编码、并发、许可证、清理；
- tool.yaml：mock=false、真实 output_classification、安全声明；
- input/output schema：与真实字段逐项对齐；
- 明确哪些原始 stdout/stderr/文件保留为审计证据。

Stop if：

- 只有字段名猜测，没有结构保真样例；
- 调用只能靠人工 GUI 且无法稳定自动化；
- 真实工具许可或数据边界不允许自动接入。

若自动化不可行，诚实降级为“生成输入册 → 人工运行 → 回传结果册”的半自动流程，
不伪装全自动。

### Ticket：实现 performance_disk_real 并完成 canary

实施边界：

- 新增 tools_impl/performance_disk_real；
- 保留 performance_disk_mock；
- Runtime、Registry、Task 状态机不因接入真实工具而改；
- performance_disk_agent 仅在签发后切换白名单；
- 每个真实结果仍进入 waiting_review，人签后才 completed；
- 敏感数据传播、完整性闸、tool_runs、samples、eval snapshot 全链保留。

最小测试：

- 正常 case；
- 超包线 case；
- 工具不可用；
- 超时；
- 畸形输出；
- 部分批次失败；
- 中文路径/编码；
- 重启后不自动重放有外部副作用的任务。

Done when：

- 真实工具执行 mock=false；
- 正常、失败、超时均有原始可审计证据；
- 不发生数值“合理化修正”；
- mock 与 real 的契约差异有明确版本记录；
- canary 由具名工程师审核；
- 评测与晋升只覆盖已观测工况，不外推全包线。

## Phase 4：导入后的 Gate2 与成熟度后锻

顺序建议：

1. 运维韧性；
2. 授权与职责分离；
3. 评测与晋升证据加固；
4. 交互 tools/RAG；
5. UI 与前端韧性；
6. 低危 backlog。

### Track T1：运维韧性

- 任务宽墙钟与安全终止策略；
- 主 worker 与 eval worker 分轴 heartbeat、last-loop-error、监督；
- queued/running/waiting_review 数量与最老龄期；
- 规模 benchmark 与复跑数量级一致性；
- finish_eval_run 终态 CAS，禁止无条件覆盖 terminal；
- deploy selfcheck 静态资产闭包和深链探针。

注意：仅把任务标 failed 而泄漏执行线程仍继续产生外部副作用，不算真正收口。

### Track T2：授权与职责分离

先微决策，再改 schema：

- operator：创建和查看任务；
- reviewer：审核，但默认不得审核自己创建的任务；
- admin：评测、样本固化、晋升、admin-only Tool；
- 若现场仍采用单人封闭运维，明确记录为过渡风险，不虚构 RBAC 已存在。

### Track T3：评测与晋升证据

- eval 结果 detail 的敏感信息门；
- provenance envelope：Agent、case、模型 profile、Tool 版本/配置、Knowledge scope、
  外部文件 hash；
- CFD 等外部活状态转为冻结、带 hash 的输入资产；
- promotion 的磁盘写与 DB 审计 crash reconciliation；
- 首个 L1 后再规划 L1→L2/L3，不提前扩状态机。

### Track T4：交互 tools/RAG

- 以 Gate2 T3 候选为参考，重新基于最新 main 实现；
- default-deny；
- tool 必须 interactive_safe is True；
- shell、raw file、workspace isolation 等声明与交互运行时能力一致；
- RAG 引用按结论单元覆盖，不用“附了出处表”冒充 grounded；
- 先做第二个 interactive Agent 的零内核 diff 验证弹；
- 流式 token、WebSocket、多模态不夹带进入本 track。

### Track T5：前端诚实韧性

- 异步评测轮询瞬断后保留 active run id，未确认无在途 run 前不解锁重复提交；
- 未知路由提供诚实 404 与返回路径；
- 未登录时不挂 QuickSwitcher、SimMonitorFloat 等业务请求/iframe；
- 登录表单补 label、autocomplete、375px、键盘焦点验收；
- 信任色补 clay/green/teal/red/amber 亮暗矩阵；
- REAL 绿首次消费必须绑定可核 provenance；
- Element Plus 体积和首屏图片列 P2 预算，不阻塞 Gate1。

### Track T6：低危 backlog

- 孤儿文件、任务产物和会话 GC；
- feedback.message 长度上限；
- PDF/docx/图片解析；
- Engineering Memory；
- source=obsidian/mcp、向量检索；
- 前端组件级测试扩充；
- schema_migrations 表；
- 数据导出/迁出包。

## 7. Wayfinder frontier

可立即执行且未被外部事实阻塞：

1. 恢复 main 可信基线
2. 修复跨平台验证门与证据污染
3. 恢复文档 SSOT
4. 完成首个真实 L1 晋升
5. 裁决需求接件 Agent 是否接纳
6. 裁决 Gate2 三轨候选的去留与顺序

被外部事实阻塞：

1. 闭合 Gate1 目标机证据
2. 构建并验证离线发布包
3. 冻结真实性能盘调用契约
4. 实现 performance_disk_real 并完成 canary

## 8. Fog of war

以下在范围内，但当前事实不足，暂不伪切成实现票：

- 性能盘究竟是 CLI、COM/DLL、宏还是 HTTP；
- Windows 版本、Python ABI、内网镜像覆盖；
- 内网模型协议、鉴权、模型名、限流和 p99；
- SSO 与组织角色映射；
- 真实知识语料格式、密级分布和 PDF 占比；
- L2 专家签字在组织中的权威记录方式；
- 真实工具许可证、单实例和并发约束。

当对应侦察票有原始证据后，再把这些 fog 毕业为精确实现票。

## 9. Out of scope

- Redis、Celery、消息队列平台化；
- ORM 或数据库替换；
- 自动合并、自我批准、LLM 签发；
- 在 M4 前承诺全部 Agent 生产可用；
- 流式 token、WebSocket、多模态 V0.3；
- 一键自动起 N 个需要人补工程输入的任务；
- 把历史 mock 或合成语料包装成真实工程结论；
- 未经授权发布 GitHub issue 或改动外部状态。

## 10. 推荐的首个执行切片

名称：恢复 main 可信基线与跨平台验证门。

范围：

- 新建干净 main 分支/工作树；
- 保护当前 68 个截图；
- 修 sh/ps1 parity；
- 日常 E2E 默认写临时 artifact；
- 修 README、.env.example、M4 checklist 的当前态漂移；
- 在一次性工作树跑全量门。

验收：

- parity 负例先红、修复后绿；
- verify_all exit 0；
- 默认验证前后工作树无截图改动；
- 当前旧工作树 hash 不变；
- GitHub 不写入；
- 提交可独立回退，不夹带 Gate2/M4/需求接件功能。

这是当前风险最低、复利最高、且不依赖内网事实的下一步。

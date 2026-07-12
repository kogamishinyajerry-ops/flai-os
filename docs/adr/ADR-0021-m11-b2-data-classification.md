# ADR-0021：M11-B2 数据分级标记轴（files/samples classification）

- 状态：R5（审查史：R0 loop-auditor 设计审 BLOCK（F1-F7）→ R1 修订
  APPROVE → R2 实现期强化 D5 门序、单点复核 APPROVE 维持 → Codex R0：
  知识轴入派生、运行进程代际标记、ps1 fail-open → Codex R1：worker 代际
  心跳（迁移 #7）、scope_registry 全构造点接线、库身份指纹、IN 分批 →
  Codex R2（round cap 第 3 轮）：beat() guard 回归修复、探针 stdlib-only
  常量下沉；工具读文件系统的 taint 缺口 declare-and-defer（触发器
  shipped 不可达，硬前置递延，见 D6/递延）。round cap 交代见
  docs/reviews/M11-B2-C2C3-review-record.md）
- 日期：2026-07-12
- 关联：ADR-0019（真鉴权，D4 default-deny 是本轴的前置——分级门只对已认证
  用户有意义）、ADR-0018（固化通道是分级门控的出口之一）、PM-M11-DIRECTION B2。

## 背景

平台将承载出口管制敏感（EAR 红线口径）与部门内部两类数据。M4 解锁后真实
工程数据进场，**届时再补分级轴 = 存量数据无标可考，只能全量人工重审**。
mock 期把轴立起来（全量缺省 internal，成本≈0），真实数据进场时按入库口径
标注即可——这是「机制化前置」的全部含义：先有轴，再有数据。

**V0.1 分级只有两级**：`internal`（部门内部，登录用户可用）/
`sensitive`（敏感，出场通道 fail-closed）。不做多级密级体系——两级已覆盖
「能不能离场」这一个当前唯一需要机器裁决的判定。

## 决策

### D1 存储轴：files/samples 各加 classification 列 + 标注人追溯

- 迁移 #6：`files.classification TEXT NOT NULL DEFAULT 'internal'`、
  `samples.classification TEXT NOT NULL DEFAULT 'internal'`、
  `files.uploaded_by TEXT`（可空，设计审 F2：分级标错时必须查得出谁标的）。
- 存量行由 DEFAULT 回填 `internal`——**mock 期数据全部是演示产物，internal
  是如实标注不是宽松兜底**（与迁移 #4 tasks.origin 同一裁决口径）；存量
  `uploaded_by` 留 NULL 如实（自报时代数据，同 ADR-0019 F7 对账口径）。
- 新库 DDL 与存量 ALTER 双轨（同迁移 #1-#4 的写锁内探测模式）。
- **repos 层 `classification` 是无默认值的必填 kwarg**（设计审 F4）：
  `create_file`/`record_sample` 全部调用点显式传值，漏传=TypeError 当场炸，
  绝不静默吃 DB DEFAULT 洗白。DDL DEFAULT 只服务存量迁移回填，不服务新写入。

### D2 标注入口：上传契约声明，缺省 internal

`POST /api/files/upload` 增可选 form 字段 `classification`，合法值仅
`internal | sensitive`，非法值 422 拒绝（不静默降级为 internal——错误方向
必须是「拒收」而非「洗白入库」）。缺省 `internal`。

- **合法性校验先于任何磁盘 I/O**（设计审 F7）：非法值在写盘循环开始前
  拒绝，不产生孤儿 blob。
- `uploaded_by` 记登录会话身份（`request.state.user["display_name"]`，
  复用 ADR-0019 D5 模式）。仅上传端点填人；runtime 产物与 eval runner
  复制件非人工标注场景，留 NULL 如实。
- **自报信任根（设计审 F2，如实声明）**：分级值由上传者自报，无内容核验、
  无第二人复核——本轴保证的是「标了 sensitive 的数据出不去」，不保证
  「该标 sensitive 的数据一定被标了」。后者靠 uploaded_by 追责 + 人工
  审核纪律 + 词面纪律兜底，见 D6。

V0.1 **不做 UI 标注入口**：mock 期无 sensitive 数据可标，入口=API 契约。
UI 表面（标注/标签展示/改级审批）随角色轴一起做，已声明限制。

### D3 污点传播：派生数据不因流转而洗白

这是本轴的承重墙。没有传播，下载门形同虚设——把 sensitive 文件作为输入
跑一次任务，产物就是「新的 internal 文件」，一键洗白。

- 任务级派生口径：`task_input_classification = 全部输入文件记录均为
  internal → internal；否则 sensitive`。**三个 fail-closed 分支**：
  1. 输入文件记录缺失（id 查无此行）→ sensitive（出处不可考，宁严勿洗白）；
  2. 未知分级值（既非 internal 也非 sensitive，如坏数据/未来新级）→
     sensitive（allowlist internal，不 blocklist sensitive）;
  3. 无输入文件 → internal（无污点源）。
- **派生无条件基于 `task.input_file_ids` 现查 DB**（设计审 F6）：不依赖
  `_open_input_files` 的副作用——schema 校验先失败时 verified_files 恒空，
  若据此推导会把带 sensitive 输入的失败样本误判成分支③ internal。
- 传播落点：任务**产物文件**（`_register_outputs`）与**样本**（成功/失败
  两条 `record_sample` 路径）继承任务级派生值。
- eval runner 注册的 case 输入文件显式 `internal`：eval case 内容经
  人工放行+策展双关（ADR-0018），且 D5 分级固化门拦住 sensitive 入包——
  包内数据 internal 是构造性保证。
- **知识轴（Codex 治理审 R0-P1，R3 补）**：绑 `restricted` 密级知识库的
  job Agent 能把检索文本写进产物——**零输入文件也携带受限内容**，文件
  污点轴测不到。任务级派生 = 文件污点轴 ∨ 知识轴：Agent 声明
  `knowledge.enabled is True` 时逐 scope 查密级，`public_internal/
  department` → internal（department 语义=部门内部，与 internal 定义
  重合）；`restricted`/未知密级/未注册 scope/registry 缺失 → sensitive
  （fail-closed，与 ADR-0015 静态门兜底拒绝同向）。判定看**声明**不看
  「这次真的检索了没有」——能接触受限语料的 Agent，其一切产物按可能
  携带受限内容处理。

### D4 下载门：sensitive fail-closed 待角色轴

`GET /api/files/{id}/download`：`classification == 'internal'` 才放行，
其余（sensitive 与任何未知值）一律 403，detail 如实说明「角色授权体系
未建立，fail-closed 拒绝」。判定是 **internal-allowlist**，不是
sensitive-blocklist——DB 里出现坏值时错误方向是拒下载。

**不做假授权**：V0.1 用户无角色列，「谁可以下载 sensitive」无裁决依据，
诚实答案就是「暂时没有人可以」。加白名单/口令旁路=伪造一个未经设计的
授权体系（fail-open 大忌，同 ADR-0019 D9 不设 AUTH_OFF 的裁决）。

### D5 固化门：sensitive 样本拒绝入包（门序保证自然链路可达）

`fix_sample_as_eval_case` 增前置：`sample.classification != 'internal'`
→ CurationError（422）。eval_cases 是**版本化 agent 包目录**——打包、
拷贝、发布都以包为单位，sensitive 数据固化入包=脱离 DB 门控的静默离场
通道。

**门序即有效性（设计审 F1 的解法，R2 修订）**：设计审曾指出若分级判定
排在既有「源任务含输入文件拒绝固化」门**之后**，则自然链路恒不可达
（能产出 sensitive 的 D3 分支①②都要求有输入文件，会先被旧门拦；分支③
恒 internal）——判定沦为死代码。解法是**分级门排在旧门之前**（安全语义
门优先于技术限制门）：污点传播来的 sensitive 样本先撞分级门、被以分级
语义拒绝，判定在自然链路上真实可达，验收以端到端链路作证（另保留 DB
直插 witness 覆盖「无输入文件却 sensitive」的未来改级态）。两门语义
并立：旧门防「搬运用户上传物」，本门防「敏感内容入包」；V0.2 若放开
旧门（人工落文件固化），本门即唯一 sensitive 屏障，实现处已留耦合注释。

### D6 门控边界的诚实声明

分级门控的是**离场通道**（下载、固化入包），不是登录用户的界面可见性。
产物内联查看（前端 `fetchOutputFile`）与下载共用 `/download` 通道，故
sensitive 产物的 UI 内联视图**同样被 D4 挡住**——比最小必要更严，方向
是多限制，如实接受。

| 管 | 不管（如实声明） |
|---|---|
| 下载出场（D4，含内联查看） | 已认证用户在 UI 内**查看** sensitive 样本/任务详情文本（V0.1 全体登录用户同权，角色轴递延） |
| 固化入包（D5，门序保证可达） | 会话附件被送入模型网关（网关指向内网 GLM 是部署层配置承担的边界，非本轴门控） |
| 派生洗白（D3，文件污点轴 ∨ 知识轴） | 能读服务器文件系统者直接拷 uploads/（同 ADR-0018 P1-1/ADR-0019 边界裁决） |
| restricted 知识库派生产物（知识轴恒 sensitive） | Agent 未声明 knowledge 却由 workflow 代码自行读磁盘敏感文件（能改包代码者即 ADR-0018 P1-1 边界外） |
| 坏分级值静默放行（allowlist 拒绝） | 备份文件本身的分级（backup 整库含 sensitive 行，备份介质管控是运维纪律，见 backup_restore 文档） |
| 标注人追溯（D1 uploaded_by） | **分级值源头真实性**（设计审 F2）：自报无核验，「该标未标」本轴测不出——靠追责可查+人工审核+词面纪律兜底 |
| 文件实体的离场 | **自由文本旁路**（设计审 F3）：`tasks.inputs_json`/`samples.input_json` 内嵌粘贴文本不受本轴覆盖——无输入文件的任务恒落分支③ internal，敏感文本可经样本→固化入包。残余风险由固化前置的人工 `accepted_by_engineer` 审核（放行人对内容负责）+ EAR 词面纪律兜底；是否限制高风险 Agent 的自由文本输入 schema，留 owner 裁决 |
| 输入文件轴 ∨ 知识轴 | **工具读取的外部数据源**（Codex R2 审 P1）：workflow 里工具直读服务器文件系统（如 `monitor_adapter_recon` 读 run 目录并把证据拷进产物/tool_runs），既无输入文件也无 knowledge scope → 派生落分支③ internal。当前唯一此类 Agent（`monitor_adapter_gen_agent`）是 `status: draft` + `knowledge.enabled: false` + `visibility: admin_only`、**未激活**，故 shipped 态不可达；机制化（工具级 taint 声明 / agent 显式 `output_classification: sensitive`）随该 Agent 激活前置立项，见递延。**该 Agent 激活前必须先补此机制**——这是硬前置，非可选优化 |

**反激励缺陷（设计审 F2，如实声明）**：V0.1 无人可下载 sensitive——
诚实标注者标完自己也用不了（黑洞效应），而缺省 internal 零摩擦，激励
方向与轴的目标相反。mock 期无真实数据，此缺陷无实际暴露面；**真实
EAR 敏感数据进场的硬前置=角色轴先落地**（见递延），届时 sensitive 是
「受控可用」而非「黑洞」，激励才对齐。

EAR 红线的**词面纪律**（敏感型号名不入仓不上屏）继续由人工+审查把守，
本轴管的是**数据实体**的离场，两者互补不互替。

## 验收标准（R1 按设计审 F1/F5 修订）

1. 上传缺省 internal，下载放行；上传声明 sensitive，下载 403；
   `uploaded_by` 记登录身份。
2. 上传非法 classification 值 → 422 拒收（不入库**不落盘**，F7）。
3. DB 内坏分级值（直插 'weird'）→ 下载 403（allowlist witness）。
4. 存量库（无新列）经 init_db 迁移后列存在、classification 全 internal、
   uploaded_by 全 NULL，幂等可重跑。
5. 传播 witness 分支①（真跑链路，非单测桩）：sensitive 输入文件 →
   任务产物文件与样本全部 sensitive，产物下载 403。
6. 传播 witness 缺失记录：input_file_ids 指向不存在记录 → 派生
   sensitive（fail-closed）。
7. 传播 witness 分支②（F5 补）：输入文件 DB 直插坏分级值 → 派生
   sensitive 传播到产物/样本。
8. 传播 witness 分支③正向（F5 补）：无输入文件任务 → 产物/样本显式
   断言 internal（不只靠回归兜底）。
9. 固化门双 witness（R2 门序修订后）：(a) **端到端自然链路**——sensitive
   输入文件→任务→样本→approve→固化尝试→422 且拒绝理由是分级语义（非
   「含输入文件」技术门文案）、包目录无新文件落盘；(b) DB 直插构造
   「无输入文件的 sensitive 样本」（模拟未来改级态）→ 同样 422。
10. 失败样本传播（F6）：schema 校验失败的任务带 sensitive 输入 →
    失败样本仍 sensitive（派生不依赖 verified_files）。
11. internal 全链路回归不变（既有测试全绿=internal 语义零扰动）。
12. 知识轴 witness（R3 补，真跑链路）：绑 restricted scope 的 job Agent
    （零输入文件）→ 产物/样本 sensitive、产物下载 403；密级判定矩阵
    （restricted/department/public_internal/未知/未注册/registry 缺失/
    enabled 非 True）单测穷尽。
13. 运行进程代际（R3 补，C2 配套）：/api/health 自报 `classification_axis`
    布尔位；部署自检门以「库已迁移+旧进程」场景实机复现单点咬合。
14. worker 代际（R4 补，Codex R1-P1）：Job Runner 独立进程写心跳+代际
    （迁移 #7 worker_heartbeats 单行 upsert）；自检门要求 60s 内新鲜且
    代际匹配——「API 已升级而 worker 未重启」的洗白窗口被单点咬住；
    `_build_default_runner`/`promote_agent_l1.py` 两处生产构造点
    scope_registry 接线有 witness 钉住（漏接线=public_internal 知识
    Agent 产物 403 的过度限制回归，反向 witness 同咬）。
15. 库身份一致（R4 补，Codex R1-P2）：health 自报库路径 sha256 指纹
    （opaque），自检门与探针侧比对——两侧 FLAI_DB_PATH 不一致的假绿
    实机复现单点咬合。IN 子句分批（33000 id 不炸）witness 咬合。

## 已声明限制（递延）

- **角色轴（谁可下载 sensitive）→ 真实 EAR 敏感数据进场的硬前置**，
  随真实用户体系需求设计；届时同步解反激励缺陷（D6）。
- UI 标注/展示/改级流程 → 随角色轴。
- 会话附件/知识库摄取的分级过滤 → 随角色轴。
- 改级审计（classification 变更历史）→ V0.1 列不可变（无改级 API），
  出现改级需求时先补审计表再开口子；「无输入文件却 sensitive」的改级态
  已由 D5 的 DB 直插 witness 预先覆盖（验收 #9b）。
- 自由文本旁路的机制化（限制高风险 Agent 输入 schema）→ owner 裁决
  后立项，本批只如实声明（D6）。
- **工具级 taint / agent 显式 output_classification**（Codex R2 审 P1）→
  `monitor_adapter_gen_agent`（读文件系统的工具类 Agent）激活的**硬前置**：
  它现为 draft/禁知识/admin-only/未启用，taint 缺口 shipped 态不可达；
  谁激活它谁必须先落地本机制，否则其产物会带外部文件系统内容却判 internal
  过下载/固化门。已在 D6 边界表如实声明。
- **worker 长任务心跳**（Codex R2 审 P2）→ 心跳当前只在 run_once 前发；
  单任务 wall-clock 超 60s（如 monitor 工具，属上条同一 draft Agent）时
  自检门可能误报 worker 死。触发器与上条同源（未激活的长任务 Agent），
  shipped 的 B2 相关 Agent 全是快任务、部署期 worker 空闲即时心跳，故
  暂列递延；随该 Agent 激活改异步心跳/租约。

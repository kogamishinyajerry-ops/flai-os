# 批八设计契约：专家团队实体（teams）+ 密级遮蔽渲染面（AGENT-TEAM-B8）

> 状态：DESIGN-FINAL（loop-auditor Mode B 实现前审 FLAG，F1-F3 修订已并入本文，
> F4/F5 留痕处置见 §六；auditor 自报 Mode B 试用期未转正，其结论作参考输入、
> 由主 session grounded 复核后采纳——F1 经实读 runtime.py 证实为真缺口）。承接批七 §2.6 DDL 级
> spec 与 N5 后移决议；批七已合并 origin/main 2a507f6（专家语义层+编队投影+
> retro 全清），本批把「一次性召集的编队」升格为「可保存、可复用、召集前
> 对账的团队模板」。源料同批七：owner 两份策划（AI 平台运作策划 / 航空摄影
> 场景应用设计）中的「定制化专家团队」诉求。

## 〇、范围与非目标

**实施**：
- S1 存储：teams / team_members 两表（迁移 #13，新表 CREATE IF NOT EXISTS 即幂等）+ repos 层。
- S2 API 三端点 + summon 对账 gate（本批唯一新 fail-closed gate）。
- S3 前端：方案卡「存为团队模板」入口 + 门户「专家团队」区块 + summon 填参面板 + **EvidenceList.withheld 密级遮蔽渲染面接线**（批七 3-lens 留存项）。
- S4 oracle O1-O8 + tamper 四咬 + craft 基线重录 + Codex cap=3 治理链（同批七全套）。

**非目标（显式挂账）**：
- 跨会话/跨批 task_id 依赖引用（批七 L1-3 挂账）——teams 只表达**团队内** seq/after 拓扑，不做跨单引用。
- 二阶段垂类包（sys_calc/cfd_assistant/test_data）——按运营节奏另批。
- SSE/流式通道（批七已钉非目标）。
- 运营面四条（授权名额/激励/看板）——移交 owner，非本仓代码。

## 一、存储契约（S1）

```sql
CREATE TABLE IF NOT EXISTS teams (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, goal_template TEXT,
  owner_user TEXT NOT NULL,              -- username（唯一键，同 created_by_username 口径）
  created_from_conversation_id TEXT,     -- 血缘：从哪个导引会话方案存出（可 NULL）
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS team_members (
  team_id TEXT NOT NULL REFERENCES teams(id), agent_id TEXT NOT NULL,
  agent_version_at_save TEXT NOT NULL,   -- 保存时点版本快照（对账基准，防漂移伪史）
  role TEXT, seq INTEGER NOT NULL,
  after_json TEXT,                       -- 同团队内前序 seq 列表（JSON int[]；按构造 DAG：仅可引用更小 seq）
  PRIMARY KEY (team_id, seq));
```

- after 语义与 batch 端点同族：**下标（seq）不是 agent_id**——同 agent 可多席位。
- 存入时校验：agent 在场、非 interactive（job 型才可入团队）、after 仅引用更小 seq、成员数 ≤5（同 guide _MAX_AGENTS 口径）。
- 删除：本批只做软语义（无删除端点；退路=owner 直接 DB 操作），不扩面。

## 二、API 契约（S2，三端点）

1. `POST /api/teams` — 从会话方案存团板：入参 `{name, conversation_id}`；后端读该会话
   recommendation 快照（decision=orchestrate）抽 agents[]（agent_id/role/after）落两表，
   `agent_version_at_save` 取 registry 当前版本。会话不存在/无 orchestrate 方案/成员越界 → 422。
   **不接受前端直传成员列表**——团队蓝本必须源自导引方案快照（防手搓越过 guide 校验层）。
2. `GET /api/teams` + `GET /api/teams/{id}` — 列表/详情投影：成员按 seq、人话名走前端
   agentNames、**团队密级展示口径 = min(成员 clearance)**（仅展示；召集判定仍按成员各自 clearance）。
3. `POST /api/teams/{id}/summon` — 召集：入参 `{items: [{seq, inputs, input_file_ids}], conversation_id?}`。
   流程 = **对账 gate（下述）→ 映射为 batch items（after_json→after 下标）→ 复用
   POST /api/tasks/batch 同一内部创建函数**（全有全无单事务 / 密级 gate 四路复用第四路 /
   task_created+charter 事件在事务内——批七 S4e 语义全继承，零平行实现）。
   **seq→下标转换契约（auditor F3）**：端点内部**按 seq 升序重排**后构造 batch 数组，
   **绝不信任客户端提交顺序**——after_json 存 seq 值、batch after 是数组位置下标，
   乱序提交若直译会把合法 DAG 误判非法或静默建错依赖边；O3 含乱序提交 case。

### summon 对账 gate（本批唯一新 fail-closed gate，loop-auditor 审点）

拒发整单（422 + 逐席位错误清单，零写入）当任一成员：
- G1 agent 不在 registry（已下架/拒载隔离）；
- G2 agent status == "disabled"（`is True`/字面比较，绝不 truthiness）；
- G3 agent 现为 interactive（保存后包形态变更）；
- G4 版本漂移：现版本与 `agent_version_at_save` 比对——major 变化，或 0.x 期 minor 变化 → 拒
  （0.x 期 minor≈breaking，semver 惯例）；patch 变化**不拒**但在响应 `warnings[]` 如实列名。
  解析失败路径（auditor F5）：version 经 agent.schema.json pattern 强制 `\d+\.\d+\.\d+`
  结构上不可达畸形，但比较代码仍 fail-closed——任一侧解析失败按 major 变化处理（拒）。
- G5 items 席位与 team_members 不对齐（缺席/多席/重复 seq）→ 422。
- 材料密级：不设团队级新判定——batch 内部创建函数的 ADR-0030 成员级 gate 原样生效
  （min 口径只是展示，**绝不**替代成员级判定，防「团队均值」稀释语义）。

时点语义：对账在创建事务**之前**（读 registry 内存态），创建仍在 BEGIN IMMEDIATE 单事务；
对账通过与事务提交之间的 registry 变更窗口不设锁（诚实边界：与 create_task 单建同宽）。
**执行期兜底补强（auditor F1，本批真修）**：runtime `_execute` 现只重查「仍注册 +
版本漂移」，**不查 disabled**——滞留 created 的依赖任务在等待窗口内成员被禁用仍会
执行（B7 继承缺口，本批既引它作兜底就必须补齐）：`_execute` 增 disabled 检查
（镜像 conversation.py 既有模式，`== "disabled"` 字面比较），禁用成员的任务诚实
failed 不硬跑；+回归测试。补后 R1 的兜底声明才成立。

## 三、前端投影（S3）

- GuidePage 方案卡 plan-foot 增 secondary 动作「存为团队模板」（仅 orchestrate 且会话
  active；成功 toast + 门户入口提示；命名走轻量 prompt 输入）。主动作序不变（一屏一主动作）。
- AgentPortal 增「专家团队」区块：团队卡（名/成员链 seq 顺序/密级 min pill/来源会话深链）
  + 「召集」按钮 → summon 填参面板（逐席位复用既有 agent schema 预取与就绪判据；参数
  未齐禁提交）。对账失败的逐席位清单如实渲染（中性策略拒绝文案，非报警红）。
- **EvidenceList.withheld 接线**：taskEvidence 对非 internal JSON 产物已零下载（批七 S4h）
  ——本批补渲染面：store 记 `withheld: true`（有 JSON 产物但密级受限），消费面
  （GuidePage T5 chip / Workbench 收纳行 / TaskDetail 依据段）渲染静态「依据清单〔按密级
  隐藏〕」标记，**绝不编造计数**（无内容即无 N）；EvidenceList `withheld` prop 用于
  TaskDetail 有行骨架但引文受限的形态。
- 信任色五槽不动：teams 卡无新色轴；对账失败=中性；「召集」CTA 走 cta-clay。

## 四、oracle（S4，O1-O8）

| # | 断言 | tamper 咬点 |
|---|---|---|
| O1 | 存团队：orchestrate 方案→POST /api/teams→GET 回读成员/seq/after/版本快照保真 | 存储层丢 after_json → O1 红 |
| O2 | 对账 fail-closed（G2）：成员 disable 后 summon → 422 整单 + 席位清单 + 零任务写入 | **TB1：对账 gate 判定短路 `ok=True`** → O2 红 |
| O2b | 对账 G1/G3/G5 逐条（auditor F2）：①成员从 registry 卸载 → 422 指名；②包翻 interactive → 422 指名；③items 缺席/重复 seq → 422——三判据各有专属正路径证明，缺一即 TB1 咬不住的漏写面 | 各判据单独注释掉 → 对应子探针红 |
| O3 | summon 成功链：after→depends_on 真 task_id、下游滞留 created、resolver 接力完成（复用 batch_g 判据缩编）；**含乱序提交 case（auditor F3）**：items 逆 seq 序提交 → 依赖边仍正确 | TB2：summon→batch 映射丢 after → O3 红 |
| O4 | 版本漂移：bump 成员 minor → summon 拒且清单指名；patch → 放行 + warnings 列名 | 对账版本比较砍掉 → O4 红 |
| O5 | 密级不稀释：sensitive 材料配 internal 上限成员 → 整单 422（batch gate 第四路复用实证） | **TB3：summon 绕过内部 batch 函数直建** → O5 红 |
| O6 | withheld 诚实：sensitive JSON 产物 → 零 /download 请求（网络断言）+ 遮蔽标记在场 + 无编造计数 | **TB4：强渲计数「依据 N 条」** → O6 红 |
| O7 | 存团队入口纪律：非 orchestrate/已归档会话 → 入口不在场或禁用（假入口=假承诺） | — |
| O8 | craft 基线：teams 卡过批五 craft 焦点/信任色断言（craft 套件重录基线先行全绿） | 既有 craft replay 咬 |
| O9 | 执行期 disabled 兜底（auditor F1 真修的回归面）：滞留 created 的依赖任务，其 agent 被禁用后上游完成 → 该任务诚实 failed 不执行 | `_execute` disabled 检查注释掉 → O9 红 |

tamper 登记 `scripts/tamper_replay.sh` b8-* 四 case（TB1 gate 短路 / TB2 after 丢失 /
TB3 绕道直建 / TB4 计数编造），三条件干净咬合契约同批六/七。

## 五、外科改动清单

- `backend/app/storage/db.py` — 迁移 #13 两表。
- `backend/app/storage/repos.py` — create_team / get_team / list_teams / list_team_members。
- `backend/app/api/teams.py`（新）— 三端点 + 对账 gate；batch 内部创建函数从 tasks.py
  提为可复用函数（**同文件内提取，不迁移不改语义**，tasks.py 的 batch 端点与 teams
  summon 共调）。
- `backend/app/api/__init__/main` 路由注册（同既有 router 挂载惯例）。
- `frontend/src/api/teams.js`（新）+ `AgentPortal.vue`（teams 区块+summon 面板）+
  `GuidePage.vue`（存团队入口）+ `stores/taskEvidence.js`（withheld 标记）+
  `EvidenceList.vue` 消费面三处 + `TaskDetail.vue` 依据段 withheld 形态。
- `frontend/e2e/batch_h_teams_acceptance.py`（新，O1-O8）+ `scripts/tamper_replay.sh`
  b8-* 四 case + `scripts/verify_all.sh` 登记。
- `docs/adr/ADR-0031-team-template-entity.md`（新）：团队蓝本必须源自导引方案快照 /
  对账 fail-closed 五判据 / min 密级仅展示 / 版本漂移语义。

## 六、风险

- R1 对账 gate 与执行期 registry 窗口：诚实声明不加锁（同 create_task 宽度），执行期
  兜底已有——ADR 里写明，不假称原子。
- R2 版本快照可能长期漂移致团队「存了就废」：patch 放行 + warnings 缓解；拒发文案给
  「重新从导引方案另存新团队」出路。
- R3 summon 填参面板是本批最大新 UI 面：复用既有内联召集就绪判据（agentBatchable 族），
  不造第二套参数校验。
- R4 withheld 标记若消费面漏接（三处），密级遮蔽体感不一致——O6 对三视图逐一断言。
- R5 「存为团队模板」按会话快照抽取：会话 recommendation 可能含 dropped/越界成员——
  存入时按 §一 校验重跑（guide 校验层不被信任为唯一防线，纵深）。

**loop-auditor 审后留痕**（Mode B FLAG → 修订并入）：F1 执行期 disabled 兜底真修
（§二时点语义 + O9）；F2 补 O2b 三判据专属探针；F3 seq 升序重排契约 + 乱序 case；
F5 版本解析失败 fail-closed 一句话。F4（「零平行实现」架构承诺行为等价不可机器判定）
接受为 code-review 残差——Codex 治理审抽查 summon handler 是否真调共享创建函数，
不另设静态断言。

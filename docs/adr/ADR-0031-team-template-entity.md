# ADR-0031：专家团队模板实体与召集对账门

- 状态：Accepted（补录既有实现的 SSOT，不新增 owner 签发）
- 日期：2026-07-18
- 关联：`docs/design/AGENT-TEAM-B8-DESIGN.md`、`docs/reviews/AGENT-TEAM-B8-review-record.md`

## 背景

导引会话已经能产生结构化多 Agent 方案，但若由前端重新拼装成员、依赖和版本，保存的
“团队”会丢失方案血缘，也可能绕过注册、密级和批量创建的不变量。平台需要一个可复用
的团队蓝本实体，同时必须保证它不是新的自动签发者，也不是绕过 Task Runtime 的执行器。

本 ADR 补录已合入主线的批八决策。补录文件只恢复文档单一事实源，不改变既有代码、
review 结论或人签授权状态。

## 决策

1. `teams` 保存蓝本头、owner username、目标模板和来源会话；`team_members` 以
   `(team_id, seq)` 保存席位、Agent 版本快照、角色及前序 seq。迁移号为 #13。
2. 团队只能由服务端读取 `decision=orchestrate` 的会话 recommendation 创建；接口不
   接受客户端自报成员列表。保存前重新验证 Agent 在场、未禁用、job 模式、成员数不
   超过 5，且 `after` 只引用更早席位；任一失败则 422、零写入。
3. 召集是整团动作。服务端先执行 G1–G5 对账：注册状态、disabled、workflow 模式、
   版本漂移和席位集合；失败返回逐席位清单，整单零写入。0.x minor 或 major 漂移拒绝，
   patch 漂移只警告；版本解析失败按不兼容处理。
4. 客户端顺序不可信。服务端按 seq 升序重排，把持久化的前序 seq 映射为 batch 数组
   下标，并调用既有 `run_batch_creation`；不得另造任务创建路径。
5. 对账时观察到的 Agent 版本通过 `pinned_versions` 传入批量创建，关闭对账后热切换
   版本的 TOCTOU 旁路。Runtime 继续在执行期复查注册、版本和 disabled 状态。
6. 团队 `clearance_display` 仅用于展示成员密级最小值；缺位成员按最保守 internal
   参与计算。真正的材料密级判定仍逐成员复用批量创建门，展示值没有授权效力。
7. 团队模板不签发、不评审、不提升成熟度。LLM 只提供候选方案；任务创建、人工复核和
   最终签发仍沿用既有状态机，人始终是唯一签发者。

## 接口与持久化约束

- `POST /api/teams`：从会话方案原子保存团队蓝本。
- `GET /api/teams`、`GET /api/teams/{id}`：分页列表与现势投影。
- `POST /api/teams/{id}/summon`：对账后复用批量任务创建。
- `agent_version_at_save` 是兼容性对账基准，不冒充当前版本。
- `after_json` 存前序 seq，不存 Agent id；同一 Agent 可以占多个席位。
- 本批没有删除接口；来源会话只作血缘记录，不设置会因历史清理而破坏蓝本的外键。

## 后果与诚实边界

- 获得了可审计、可复用、能检测版本漂移的团队蓝本，复杂性集中在 teams 模块和既有
  batch 创建接口之后。
- 对账与事务提交之间不锁 registry；`pinned_versions` 和 Runtime 复查把已知旁路
  fail-closed，但不宣称 registry 热更新与事务原子。
- file_upload 席位的 API 材料路径有覆盖；前端上传交互尚缺独立端到端样本，继续作为
  review record 中的诚实残差。
- 团队列表接口支持分页；门户当前只消费首页，规模化翻页 UI 按真实需求再增加。

## 验证

- 后端：`backend/tests/test_b8_teams.py` 覆盖创建、G1–G5、乱序依赖、版本钉死、材料
  422、分页及密级展示。
- 浏览器：`frontend/e2e/batch_h_teams_acceptance.py` 覆盖保存、拒发、召集与 withheld。
- 敌意复放：`scripts/tamper_replay.sh` 的 b8-* 用例。
- 全量门：`bash scripts/verify_all.sh` 与 `pwsh -File scripts/verify_all.ps1` 均必须登记
  batch H；普通运行不得覆盖 `docs/reviews`。

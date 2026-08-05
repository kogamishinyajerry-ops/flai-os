# ADR-0040：生活场景教学 demo 边界章程

- 状态：Accepted（2026-08-05）
- 关联：ADR-0032（受治理的资产草稿预览）· ADR-0033（会话优先自动路由）· ADR-0034（任务证据绑定的资产候选账本）· ADR-0035（隔离 Skill Package 材化与受控复用）· ADR-0037（V1 owner 对象授权）· `docs/reviews/ONTOLOGY-ASSET-REUSABILITY-AUDIT.md`
- 授权边界：本 ADR 只声明教学 demo 的性质、隔离边界与未来扩展约束；不授权任何新的写入路径、账本接入、材化行为或复用池变更。

## 背景

L1 教学 demo（`agents/life_guide_agent`、`/demo` 页面、`data/demo_scenarios/` 场景种子）
的目标受众是 FDE 团队——纯动力工程师，基本不写代码。demo 用做饭、旅行、装修三个
生活场景，让他们看懂"一段真实经历怎么变成可复用、可治理、可追责的资产"。

demo 与生产共用同一套后端与治理链：同一个 `AssetDraftBuilder`、同一组契约、同一套
登录与 owner 授权。这带来两个已被审计（`ONTOLOGY-ASSET-REUSABILITY-AUDIT.md`）点名
的风险：

- R3：`candidate_materializer.py` 的 `reuse_eligible` 在包 `approved` 时翻为 true
  （`list_reuse_eligible` 据此进入全局复用匹配）。若 demo 路径将来接入材化并产生
  已批准包，"家常红烧肉"可能被生产任务的复用匹配命中，污染生产复用池。
- R2：demo 若使用真实账号，demo 产生的候选会与工程师真业务候选共享同一 owner
  命名空间，混入生产治理面。

## 决策

### 性质声明

`/demo` 与 `life_guide_agent` 是教学工具，不是生产 Agent；其输出是教学投影，不是
工程资产。`data/demo_scenarios/*.json` 是教学脚本（预设的对话与期望投影），不构成
真实工作证据，不进入任何证据计数。

### 当前形态（诚实声明）

demo 目前止步于草稿预览投影：候选只在 `/messages` 响应级透传并由前端
`LifeDraftCard` 调既有 `asset-draft-preview` 端点算 digest，不写库、不进候选账本、
不材化、不产生 Skill Package。因此当前**不存在**复用池污染的真实路径；本章程的
扩展约束针对的是未来可能的接线。

### 未来扩展约束

若后续把 demo 接入候选账本或 Materializer，必须先落实现再放行，且满足：

- demo 来源的 Skill Package 强制 `reuse_eligible=false`，且该标记不因 `approved`
  翻转；`list_reuse_eligible` 必须排除 demo 来源包。
- demo 包在来源与 provenance 中携带可判定的教学标记（teaching-demo origin），
  使任何审计都能区分教学包与生产包。
- demo 会话使用独立 demo 账号（如 `demo_yandongjie`），靠 ADR-0037 的 exact-owner
  授权与生产候选隔离；禁止用生产账号把 demo 链路跑进生产 owner 空间。
- demo 包只存在于隔离区，永不进 `agents/` 目录或 Registry。

### 教学边界

- `life_guide_agent` 不做工程判断：工程问题（振动、性能盘、FTA）走 `guide_agent`，
  主持人按 prompt 铁律诚实拒绝并指路。
- demo 不证明本体论对 FDE 有用，只证明"闭环可跑、工程师能看懂"；FDE 领域价值
  由后续 L3 领域本体层论证。

### 退场

教学结束或 owner 决定清理时，demo 会话与隔离区教学包可整体清退。清退是需要 owner
确认的运维动作，系统不自动退场、不自动删除。

## 不可变量

- demo 内容永不进入 `reuse_eligible=true` 的全局复用池。
- demo 产出永不进 Registry、永不进 `agents/` 目录。
- 候选投影的 effects 四项（不写库/不执行/不注册/不晋级）在 demo 路径全程保持 False。
- demo 账号与生产 owner 命名空间隔离；签发权始终在人手里，demo 不新增任何自动
  签发、自动晋级或自动注册路径。
- 本章程不放宽 ADR-0033/0034/0035 对生产路径的任何铁律。

## 后果

FDE workshop 得到一条零风险教学通道：工程师可以亲手走完本体论建模闭环，生产复用
池、Registry 与候选账本不受任何影响。代价是未来若给 demo 接账本或材化，必须先实现
教学标记与排除逻辑并经 owner 审查——本 ADR 不授权该实现，届时另起方案。

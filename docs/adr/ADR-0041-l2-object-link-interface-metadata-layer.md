# ADR-0041：L2 Object/Link/Interface 元数据层（设计章程）

- 状态：Proposed（2026-08-05，待 owner 审）
- 关联：ADR-0031（Agent Shell 只读本体投影；对 RDF/图数据库的拒绝）· ADR-0032（受治理的资产草稿预览）· ADR-0034（任务证据绑定的资产候选账本）· ADR-0035（隔离 Skill Package 材化与受控复用）· `docs/design/ONTOLOGY-MODELING-MULTI-AGENT.md` §2.2
- 编号说明：多 agent 设计文档把本层写作"ADR-0036"，该编号已被 owner-scoped feature-asset map 占用；L2 元数据层取本编号 0041。

## 背景

L1 已经走通资产治理闭环：Work Case → Generalization → Asset Candidate → 草稿预览
/材化 → 复用证据。但这条链只有**线性血缘**——Candidate 指向 Bundle，Bundle 指向
Lineage，都是单链引用。跨候选的关系查不出来：两个 Skill 是否解决同一类问题、多个
Task Pattern 是否引用同一份依据、某个方法在哪些独立 Work Case 里被验证过——这些
问题在现有结构里没有投影面。

Palantir Foundry 的核心洞察是：ontology 是 agent 的 ground truth，不是给人类看的
治理摆设。FLAi-OS 若停在单链血缘，资产越多越成孤岛。

ADR-0031 已明确拒绝 RDF、Neo4j 与通用 nodes/edges API，但没有拒绝"在现有 JSON
Schema 之上加一层关系元数据投影"。本章程就是给这一层定边界。

## 决策（章程级：授权方向，不授权实现）

### 三件套定义

- **Object Type**：既有资产对象的类型边界——Task Pattern、Skill（含 Skill Package
  修订）、Work Case 来源会话、Agent Package。Object Type 只描述既有对象，不新增
  资产实体，不改变任何既有 digest。
- **Link Type**：对象之间的显式类型化关系。原则：关系必须**已经以 digest 引用的
  形式隐含存在**（如 `skill.operationalizes_task_pattern_digest`），L2 只是把它们
  显式化、可查询，不发明新关系。
- **Interface**：跨类型共享的属性/能力契约面，例如"含人工判断点""声明不适用边界"。
  Interface 是只读投影的分类维度，不是可执行接口。

三件套均以 JSON Schema 定义，放 `contracts/ontology/`（object_type.schema.json /
link_type.schema.json / interface.schema.json），版本演进走既有契约通道。

### 实现边界

- 新增 `backend/app/ontology/graph.py`：**只读投影模块**。从既有账本与 digest 引用
  推导对象与关系，无新写入路径，无时钟/随机数/LLM，投影结果确定性、内容可寻址。
- 不改 ADR-0034/0035 的任何 digest 计算与状态机。
- 不引入图数据库、不引入 RDF、不提供通用查询语言；跨 case 查询只开放**预先定义的
  具名投影**（某对象的一跳关系、某 Link Type 的成员列表这类），查询面 fail-closed。
- 工程师侧只读：可视化组件（`frontend/src/components/OntologyGraph.vue` 一类）展示
  投影结果；工程师不建对象、不拉关系线、不填元数据表单（ADR-0033）。

### 首个切片（提议）

最小可验证切片：投影"Task Pattern ↔ Skill ↔ 来源会话"三角关系，在治理页或 /demo
做只读渲染。用最小链路面验证三件套契约的形状，再谈扩展。切片实施前须 owner 另行
拍板，本章程不构成开工授权。

### L3 关系

L3 领域本体（engine_model / fault_mode / airworthiness_clause 等 Object Type）在本层
之上生长，依赖本层的 Link Type 与 Interface 机制；本章程不预支 L3 的任何决策。

## 不可变量

- L2 层是只读投影：不写对象、不写关系、不进任何治理链，不改变既有 digest。
- 关系只从既有 digest 引用与平台可解析来源推导；LLM 不猜关系线，推导不出的关系
  不表达（fail-closed，绝不伪造连接）。
- 继承 ADR-0031 的拒绝面：无 RDF、无图数据库、无通用 nodes/edges。
- 工程师交互面不新增表单、选择器或关系编辑器。

## 后果

章程定稿后，L2 有了明确编号与边界，实施切片可以逐片立项、逐片审查，跨候选关系从
"查不出"变成"按具名投影可查"，并为 L3 领域本体铺路。代价是平台要维护三份新契约
与一个投影模块，其演进同样受契约版本纪律约束。在 owner 接受本章程之前，任何 L2
实现代码都不应开工。

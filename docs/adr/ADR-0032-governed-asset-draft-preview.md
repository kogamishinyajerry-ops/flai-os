# ADR-0032：受治理的资产草稿预览

- 状态：Accepted（2026-08-01）
- 关联：ADR-0012（导引草案与人工提交分离）· ADR-0018（评测策展）· ADR-0030（人工门与依据纪律）· ADR-0031（Agent Shell 只读本体投影）

## 背景

FLAi-OS 已能带领工程师完成对话、创建任务、观察证据并由人签发，但真实工作结束
后，尚无一致方式把其中可复用的方法沉淀为 Task Pattern 与 Skill。若直接从 CFD、
CAD 等具体工作流扩张，会继续增加功能数量，却不会形成跨领域可积累的资产骨架。

## 决策

Asset Builder v0 只建立一条受治理的草稿链：

```text
平台内 Work Case
  -> 工程师填写 Generalization
  -> Task Pattern Draft
  -> Skill Draft
  -> Deterministic Validation
  -> Review Readiness
```

核心只有一个深接口：

```python
AssetDraftBuilder.preview(conversation=..., generalization=...)
```

它是无状态、无时钟、无随机数、无 LLM、无数据库、无 Registry、无执行器的纯投影。
薄路由只解析既有 Guide conversation，再调用 Builder 返回版本化、内容寻址的
`asset_draft_bundle.v1`。来源摘要、Task Pattern、Skill 和整个草稿包分别带摘要，
并以显式字段表达 `derived_from` 与 `operationalizes` 关系；不建立通用 nodes/edges。

语义缺口返回 `200 + needs_revision + blocking issues`，让工程师继续修改；结构、
类型、长度或未知字段错误返回 422。找不到来源返回 404；来源没有已保存的用户工作
返回 409；畸形平台来源 fail-closed 为通用 503。响应不回传整段会话原文。

`ready_for_human_review` 只表示结构足够交人审。v0 的审核决定恒为
`not_recorded`，且响应通过常量字段声明不会写库、执行工作、注册资产或晋级资产。
UI 只允许下载待审 JSON 或返回修改；下载后仍是草稿。

## 不变量

- 同一来源代际与同一规范化 Generalization 必须产生逐字节稳定的摘要与关系。
- 任何 blocking issue 都必须得到 `review.state=not_ready`。
- Task Pattern 与 Skill 始终是 `draft`；v0 不出现 approved、registered、released、
  promoted、completed 或 waiting_review。
- 人工判断点、证据要求与不适用边界缺失时不得进入 Review Readiness。
- 客户端不能提交审核人、审核状态、ID、摘要、权限或晋级字段。
- 来源在平台内可解析，只证明记录存在；现阶段不把它描述成 user-verified 或已审核。

## 后续扩展

未来扩展通过新的、显式引用摘要的对象完成，而不修改 Draft Bundle：

- Matt 风格 `SKILL.md` 由独立 Materializer 从已审核 Skill Revision 渲染；文件格式是
  adapter，不是本体。
- Workflow Draft 引用一个或多个已审核 Skill Revision；当前线性步骤不冒充工作流 DSL。
- Agent Package Draft 继续走既有 Package Schema、Eval 与人工晋级门，Builder 不能
  调用 Agent Registry 注册。
- Review Decision 以追加式记录引用精确 bundle digest；Registry 只接受经批准的决定
  与对应摘要，不直接接受 Builder 输出。
- CFD、CAD 等 Domain Pack 在出现第二个真实实现后再提炼显式 validator seam。

## 后果

平台获得一条跨领域、可累积且不绕过治理的资产起点，也为未来功能地图与架构地图
提供稳定对象和血缘。代价是新增两份严格 JSON Schema 公共契约，并要求任何规则、
规范化或结构变化分别通过 builder、validation policy 或 schema 版本演进。

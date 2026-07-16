# ADR-0029：知识引用回源只读通道（签发人核对出处）

- 状态：Accepted（评审 N7 落地，2026-07-15）
- 关联：ADR-0015（knowledge 轴装配）· ADR-0021（数据分级轴）· docs/06 §4（无出处禁止进入上下文）
- 来源：《FLAi-OS Agent 原生高维评审 2026-07-15》N7——knowledge_qa 草案带
  [source · chunk] 引用，但签发人**点不开原文**，只能凭引用标签橡皮图章；
  引用体系的信任价值折半。签发是本平台唯一人类判决点，判决点上的信息必须可核。

## 一、问题

1. 检索事件（`knowledge_search` info event）与草案产物里已有出处四钥
   （scope_id/chunk_id/source/fingerprint），但全平台没有任何「按钥取原文」的通道；
2. KnowledgeService 信任边界（service.py docstring，loop-auditor T5 被证对象）规定
   服务层零授权判定、除 Runtime 装配外不得直接持有——朴素地让 API 层直调服务
   会绕过密级门，restricted 语料原文直接外泄给任意登录用户；
3. `chunk_id = f"{doc_id}#{i}"` 且 doc_id 取文件 stem——同 stem 不同路径必然同 id
   （既有已知限制），回源通道必须直面碰撞而不是首个命中当唯一真相。

## 二、决策

### D1 信任边界修订：新增第二个合法持有者
`knowledge/provenance.py` 的 `ChunkProvenanceReader` 成为 KnowledgeService 的
**第二个合法持有者**（第一个仍是 Runtime 装配）。它自带密级门，是
`GET /api/knowledge/chunk` 的唯一入口。除此二者外，直接持有服务实例的禁令不变
（service.py docstring 同步修订）。

### D2 密级门（fail-closed，显式比较，兜底拒绝）
- scope 未注册 → 404（default-deny：未注册即不存在）；
- `confidentiality == "restricted"` → 403——V0.1 无角色轴，登录态区分不了 admin，
  **宁拒不泄**；角色轴（gh#7）落地后另议放行；
- 枚举外/缺失密级 → 同拒（无法验证 = 拒绝；防未来 schema 枚举扩张而门未同步的
  静默放行，tamper T2 + 单测「门先于读」哨兵双保）；
- `public_internal` / `department` → 放行给登录用户（M11 全站登录已强制）。

### D3 诚实边界（记录在案，不静默）
- **department 放行口径 = 任何登录用户**：V0.1 无部门轴，做不出「本部门人员」
  判定。与现状一致——knowledge_qa 草案产物本就对登录用户可见且已含语料摘录，
  本端点没有扩大暴露面，只是把「摘录」升级为「可核对的原文」；
- **回源读的是当前语料，非检索时点快照**：检索后语料若更新，内容可能与草案
  引用时不同；fingerprint 供上层比对漂移，本层不伪装时间机器。chunk 不存在时
  404 detail 如实说明「语料可能在检索后被更新/删除」；
- **密级快照 vs 语料自刷新（Codex 治理审 R0 P1-2）**：confidentiality 取自
  scope_registry 启动期快照（不重扫），语料却按指纹自刷新——运行中把某 scope
  由 public_internal 改成 restricted 且不重启，则密级门读旧快照、语料已刷新，
  构成潜在越密级泄漏。这是**平台级既有属性**（`_KnowledgeContext.search` 的密级/
  白名单判定同源自该启动快照），非本通道独有。V0.1 运维口径=**收紧密级必须
  重启服务才生效**，与白名单同纪律；本通道忠实沿用平台唯一密级真源，不分叉。

### D6 排 V0.2 的平台级加固（不在本 ADR 修）
把密级策略摘要与语料 generation **原子绑定**——回源（及检索）时校验「策略快照
与语料代际同源」，策略漂移/缺失/并发重扫一律 fail-closed 拒绝。此为知识轴整体
加固（同时收口 D3 密级快照与「每次 GET 全量哈希语料」的 DoS 放大面，Codex 治理
审 R0 P2-service），非单端点可闭合，故显式排 V0.2 队列并在此记录，不静默。

### D7 与 docs/06 的关系（Codex 治理审 R0 P2）
`docs/06_Knowledge_Memory_Standard.md` 原文规定「Runtime 是知识服务唯一通道，
拒绝任何直接持有 Service」。本 ADR 是对该规定的**窄例外授权**：新增
ChunkProvenanceReader 为第二合法持有者，且自带密级门（D2）。docs/06 已同批补注
指向本 ADR，两文档不再冲突。

### D4 歧义如实报（stem 碰撞）
同 chunk_id 命中多个源文件且未带 `source` 消歧 → 409，detail 列出全部候选
source；带 `source` 精确匹配到单条才 200。绝不猜首个。

### D5 传参与暴露面
- chunk_id 含 `#`，一律走 **query 参数**（路径参数会被当 URL fragment 截断）；
- 端点自动落在 M11 auth 中间件保护面内（allowlist 之外一律 401）；
- 只读 GET，无任何写路径；入参长度全部设上限（DoS-echo 同口径）。

## 三、验证

`backend/tests/test_knowledge_provenance.py`（单元 9 + API 8）：密级门四态、
门先于读哨兵、歧义/消歧/miss、401/403/404/409/422 映射、七字段形状。
tamper T2（放宽门准 restricted）单元+API 双层 RED 实证必咬。

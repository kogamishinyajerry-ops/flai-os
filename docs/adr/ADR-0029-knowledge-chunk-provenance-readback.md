# ADR-0029：知识引用回源只读通道（签发人核对出处）

- 状态：Accepted（评审 N7 落地，2026-07-15）
- 关联：ADR-0015（knowledge 轴装配）· ADR-0021（数据分级轴）· docs/06 §4（无出处禁止进入上下文）
- 来源：《FLAi-OS Agent 原生高维评审 2026-07-15》N7——knowledge_qa 草案带
  [source · chunk] 引用，但签发人**点不开原文**，只能凭引用标签橡皮图章；
  引用体系的信任价值折半。签发是本平台唯一人类判决点，判决点上的信息必须可核。

## 一、问题

1. 检索命中在草案产物里带出处四钥（scope_id/chunk_id/source/fingerprint），
   但全平台没有任何「按钥取原文」的通道；`knowledge_search` 事件原先只落
   scope_id + chunk_id 两钥（R1 P2 修正：现逐命中加落 `hit_citations` 携
   source/fingerprint，签发面据此对同 stem 碰撞带 source 消歧、比对 fingerprint
   漂移）；
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
- **密级快照 vs 语料自刷新（Codex 治理审 R0 P1-2 → R1 P1 强化为真门）**：
  confidentiality 取自 scope_registry 启动期快照（不重扫），语料却按指纹自刷新——
  运行中把某 scope 由 public_internal 改成 restricted 且不重启，则快照读旧宽松值、
  语料已刷新，构成潜在越密级泄漏。R0 曾按「运维需重启」文档化，R1 指出**文档约定
  不是安全 gate**、不能闭合泄漏——故本回源通道（新暴露面、调用面最广）在 read 时
  **额外从盘上现读** scope.yaml 密级，取「快照 ∩ 盘上」交集：任一为受限/漂移/
  不可验证即 fail-closed 拒（`provenance._read_disk_confidentiality`）。这**真正闭合**
  了收紧方向的泄漏，不依赖运维纪律。平台级 `_KnowledgeContext.search` 的同源快照
  属性仍在（本次不改 search），排 §D6 的 V0.2 平台加固。

### D6 排 V0.2 的平台级加固（不在本 ADR 修）
把密级策略摘要与语料 generation **原子绑定**——回源（及检索）时校验「策略快照
与语料代际同源」，策略/索引 generation 缓存 + 并发锁 + 请求限流一并落地。此为
知识轴整体加固（收口「每次 GET 全量哈希语料」的 DoS 放大面，Codex 治理审 R0/R1
P2-service），非单端点可闭合，故排 V0.2。
**诚实记录增量风险（R1→R2 P2）**：`get_chunks_by_id` 每次调用都对 scope 全部文件
`read_bytes()`+SHA-256 建/校验 manifest（与 search 同源，非本端点新引入），但本
GET 端点确实提供了**更廉价、可重复直接触发**的放大入口——「排 V0.2」不等于本端点
当前零新增风险。**当前无请求级限流**：仓内 M11 只有登录 PBKDF2 节流，**没有**全站
请求限速位，语料规模也无强制上限——故 V0.2 加固前，缓释只靠「knowledge scope 语料
现状规模有限 + 内网已登录员工受众」这一**运营现状**，不谎称已有技术门。scope.yaml
现读侧已加 64KiB 字节上限（provenance），语料侧规模门排 V0.2。

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
- 端点落在 M11 auth 中间件保护面内（allowlist 之外一律 401）。**R1 P1 强化**：
  中间件按 root_path 归一化应用内路径，ASGI 子挂载（`Mount("/prefix", app)`）下
  `/prefix/api/*` 仍稳定落门内，path-based 门不再因挂载前缀被绕（实测咬合，
  `test_m11_auth.test_prefix_mount_does_not_bypass_auth_gate`）；
- 只读 GET，无任何写路径；入参长度全部设上限（DoS-echo 同口径）；
- **异常映射覆盖已知损坏族**（R0→R1→R2 P2，不声称"全覆盖"）：
  ScopeNotRegistered→404 / AccessDenied→403 / Ambiguous→409 / Ingest（空语料）→409 /
  InvalidScopePackage→409 / SourceUnavailable→503（含语料 OSError/UnicodeError/
  ValueError/坏 Office 包 zipfile.BadZipFile）。解析器专属异常的彻底统一收容排 V0.2
  摄取层加固；当前对已知损坏族 fail-closed 映射，不裸抛 500 泄栈/路径。

### D5′ 存在性可见的诚实边界（Codex 治理审 R1 P2）
拒绝文案已泛化（不回显 scope_id/密级 repr），但**未消除存在性枚举**：未注册
scope 返 404、restricted 返 403、已注册但 chunk 缺失返另一种 404——登录用户仍可
借状态码区分 scope 状态。这是**刻意接受的边界**：受众是内网已登录员工，且合法
引用持有者应看到「受限不放行」而非「不存在」（诚实透明高于对内网员工的存在性
隐藏）。故不追求不可区分响应；本节如实记录「降低泄漏面，非消除枚举」，代码注释
同口径，不 over-claim。

## 三、验证

`backend/tests/test_knowledge_provenance.py`（单元含密级门四态+盘上漂移拒+门先于
读哨兵；API 含 401/403/404/409/422/503 映射+泛化文案+长 id+七字段）。tamper：放宽
门准 restricted（单元+API 双 RED）、拆 503 映射（→500 RED），先红后绿零残留。
子挂载绕过 fail-closed 见 `test_m11_auth`；四钥事件见 runtime 检索事件测试。

# ADR-0015: Knowledge 内核检索服务（收编 COMAC_FDE ingest/retrieve）

- 状态：已采纳（2026-07-09，owner 批准 Wave 1 开工；Wave 2 knowledge_qa Agent 待 Wave 1 收口后批准）
- 关联：ADR-0007（governance 槽位预留）/ ADR-0013（假绿清除时补的 knowledge 空桩）/ docs/06（知识与记忆标准）

## 背景

`backend/app/knowledge/` 自 ADR-0013 起是诚实空桩（仅 .gitkeep）；docs/06 §1 明言
V0.1「只立契约与目录，不做检索引擎」。COMAC_FDE 孵化仓第一批（K 工作流）已在外网
用合成语料验证了「ingest→BM25→归纳→DRAFT」链路，其中 `core/ingest.py`（多格式文档
→Chunk）与 `core/retrieve.py`（jieba+BM25 离线检索）正是本内核空洞的填充物。
跨仓裁决（2026-07-09，12 候选 31-agent 对抗复核）判定：二者目标形态 = kernel_service，
且是 Wave 2 首个 knowledge_qa Agent（四类别中唯一空缺）的硬前置。

## 决策

1. **收编而非依赖**：复制适配进 `backend/app/knowledge/{chunking,bm25,scopes,service}.py`，
   不 import COMAC_FDE 仓（孵化仓生命周期独立）。上游出处在各模块 docstring 注明。
2. **BM25 纯 Python 自实现，不引 rank-bm25**：rank-bm25 传递依赖 numpy，会把离线
   Windows 打包拖进 cp310/311/312 三平台二进制轮子链（FDE 侧已实证 numpy<2.5 约束
   之痛）。自实现 ~60 行复刻 rank_bm25.BM25Okapi 算法（含小语料负 idf 的
   epsilon 地板行为——复刻而非"修复"，保持与 FDE 已验证行为一致），以三组冻结
   golden 差分测试钉数值等价。**新硬依赖仅 jieba（纯 Python）**；python-docx 为
   可选依赖，缺失时 docx 解析诚实报错不静默跳过。
3. **scope 注册表落地 `data/knowledge/<scope_id>/scope.yaml`**：契约即既有
   `contracts/knowledge_scope.schema.json`（零改动）。`data/vector_store/` 保持
   占位（留给未来向量检索），BM25 file_dir scope 不占用该目录。
   V0.1.x 实现面 = `source: file_dir` × `kind: document`；obsidian_vault/mcp、
   engineering_experience/run_memory 检索一律 KnowledgeSourceUnavailableError
   显式"未接入"（docs/06 §6 纪律：侦察未回不实现、不静默 mock）。
4. **default-deny 三层门**：
   - 启动对账（reconcile）：`knowledge.enabled is True` 的 Agent，其 scopes 有任一
     未注册 → 整个 Agent 拒绝注册（docs/06 §3「scope_id 不存在 → 拒绝注册」从
     文档承诺变成代码强制）；
   - 运行时白名单：`context["knowledge"].search` 第一步查 agent.yaml scopes
     frozenset，不在即 KnowledgeScopeDeniedError + 事件留痕（与工具白名单同构）；
   - **密级静态门**（V0.1 无用户鉴权下的诚实近似）：restricted scope 仅
     visibility=admin_only 的 Agent 可挂；department 需 admin_only/department_trial；
     public_internal 不限。真正的按人角色核对密级，待用户鉴权体系（V0.2 债，
     本 ADR 显式承认这是 agent 级近似而非 user 级判定）。
     **边界精确声明（loop-auditor Mode A Finding 4）**：`permissions.visibility`
     在 V0.1 运行时未被任何 API 端点强制（create_task/会话入口均无鉴权检查，
     created_by 是自由文本）——本门只约束**注册期** scope↔agent 声明一致性，
     不约束**调用期**主体身份。读者不得将其理解为"agent 级访问控制在调用时
     生效"；涉真实 restricted 语料上内网前，鉴权层是硬前置。
5. **事件枚举扩 `knowledge_search`**（contracts/event.schema.json + runtime._EVENT_ENUM
   同步）：docs/06 §7 要求知识调用事件必须走 task_events；命中/未命中/拒绝均留痕。
   前端时间轴对 event_type 原样渲染，无枚举映射面需要同步。
6. **出处由构造保证**：检索命中 KnowledgeHit 的 source（相对路径）+ fingerprint
   （内容 sha256[:12]）为必填字段——docs/06 §4「无出处禁止进入 Agent 上下文」
   由类型构造实现，不靠调用方自觉。
7. **检索文本是数据不是指令**（docs/06 §5）：Wave 1 内核只返回结构化命中，不进
   prompt；Wave 2 任何将命中文本注入 LLM prompt 的消费方，必须走 M7
   attachments.py 同款 sentinel 中和 + 规则行注入（此为 Wave 2 合并门槛，先记在案）。
8. **索引进程内惰性缓存**：per-scope manifest（文件相对路径+sha256[:12] 清单）
   变化即重建；不落派生盘缓存（语料量级小，YAGNI；语料增长后的持久化索引为已知债）。

## 修订：codex 治理审 R1（2026-07-09，1 P1 + 3 P2 + 1 P3 全采纳）

885d92f 收口后的 codex 补跑审（gpt-5.6-sol ultra）CHANGES_REQUIRED，五条
finding 逐条 grounded 复核成立，全部落地（tamper T6-T9 咬合入测）：

- **R1-P1 逐文件 symlink 收容**：`ingest_dir` 对每个候选文件 resolve 后要求
  仍在源根之内，越界即 KnowledgeIngestError 硬拒整次摄取——此前
  `resolve_source_dir` 只验根目录，scope 内一个 `leak.md -> 仓外文件` 的
  symlink 即可整体绕过路径逃逸门（决策 4 的收口）。域内 symlink 不误伤。
- **R1-P2 单包读取失败收容**：scope.yaml 的 `OSError`/`UnicodeError` 同
  YAML 解析失败一样转 `InvalidScopePackageError` 软记录——此前一个非
  UTF-8 的 scope.yaml 会炸穿 scan() 拖死整个 assemble()（API 与 worker
  双双起不来），违背"单包不合格软记录继续"的自我承诺。
- **R1-P2 指纹绑定字节快照**：文件只读一次，指纹与解析共用同一份字节——
  此前指纹读一次、parser 再开一次文件，间隙内源文件被替换会产生「正文 A +
  指纹 B」的出处脱钩（决策 6 出处双钥的完整性漏洞；活文件源是声明支持的场景）。
- **R1-P2 超长单段硬切**：`_merge` 对单段超 MAX_CHARS 者先按 800 硬切再
  合并——此前超长段（超长 CSV 行/无空行长文）整段成 chunk，击穿宣称的
  chunk 上界并放大检索命中与模型上下文。硬切可能断词，检索按 jieba 分词
  计分，边界词项损失可接受。
- **R1-P3 pip fallback 配方补 jieba**：四个 dev 脚本的"依赖缺失？先装"
  提示补上 jieba（uv 路径此前已同步，echo 的 pip 配方漏了——按提示装完
  照样 ModuleNotFoundError）。

## 后果

- **范围**：knowledge 挂载仅覆盖 job 模式（AgentRuntime._build_context）；
  interactive（ConversationService）不挂——该运行时自 M6 起也不挂 tool_registry，
  属既有架构态。Wave 2 knowledge_qa 若选 interactive 型需先补挂载点并另立 ADR。
- 现役五 Agent 全部 `knowledge.enabled: false`，行为零变化；reconcile 对其不咬合
  （边界 witness 入测）。
- Wave 2 knowledge_qa Agent 解锁；其「语料+问题」双输入天然拆解为
  scope（语料）× input_schema（问题），规避 input.type 单枚举装不下的问题。
- 离线打包新增 jieba 纯 Python wheel 一枚；scripts/6 脚本与 README 跑测命令
  同步 `--with jieba`（M3 教训：依赖改动必同步脚本，测试绿≠脚本对）。
- 真实语料价值仍卡 EAR/M4 内网闸门：本地只能合成语料验证机制正确性，
  不能宣称业务价值（DECLARED-NOT-VERIFIED 纪律不变）。

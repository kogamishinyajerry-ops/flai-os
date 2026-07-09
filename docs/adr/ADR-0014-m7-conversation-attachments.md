# ADR-0014: M7 导引会话附件（内核渲染 + 防注入 + 随草案带入）

- 状态：已采纳（2026-07-09，owner 拍板立项——0.1.1 诚实降级的正式补实）
- 关联：ADR-0012（interactive 运行时）/ ADR-0013（事务性单轮、迁移模式）

## 背景

任务书对导引的原始愿景是「接手用户需求+上传附件」。M6 交付时全链路不支持
会话附件，按诚实纪律降级为显式 limitation；owner 于 2026-07-09 拍板补实，
立 M7（同时拍板建 GitHub 私库）。

## 决策

1. **附件引用而非内嵌**：消息体只存 `file_ids`（复用 File Service，先经
   `/api/files/upload`），`conversation_messages.file_ids`（JSON 数组，默认
   `'[]'`）；存量库走迁移 #2（与迁移 #1 同一 BEGIN IMMEDIATE 写锁块，Codex
   R1-P1 的并发启动安全模式直接继承）。消息**原文永不改写**——渲染只发生在
   喂模型的内存副本上。
2. **渲染是内核职责，不下放 Agent**：`backend/app/runtime/attachments.py`
   确定性渲染；「附件是数据不是指令」规则行随**每个渲染批次**由内核注入
   （tamper 实证：拆掉规则行注入，渲染器单测+全链服务测齐红）。Agent 侧
   prompt.md 铁律第 5 条同义强化，构成双层。纵深的最后一层是 M6 已有的
   推荐块确定性 schema 对账——注入内容永远无法直接触达签发（人是唯一签发者）。
3. **类型策略（V0.2 能力面）**：文本类（txt/md/csv/json/yaml/log/xml/ini/py）
   直读 UTF-8（errors=replace）；`.xlsx` 用 openpyxl `read_only` 预览活动
   sheet 前 30 行×16 列（防炸弹表；完整解析是目标 specialist Agent 用注册
   工具做的事）；其余类型（docx/pdf…）只列文件名不解析，块内如实标注 V0.3
   规划。缺文件/读取失败渲染为显式失败行，单文件失败不崩整轮。
4. **预算硬顶，新消息优先**：单文件 16K 字符、单轮全窗口共享 24K 字符，
   在窗历史**从最新往旧**分配（与截窗同哲学：诚实降级）；预算耗尽的附件
   渲染为显式占位（tamper 实证：拆掉跨轮预算分配，预算测试咬红）。附件
   预算叠加在历史截窗（40 条/60K）之外，总上下文有界。
5. **校验先于一切副作用**：`file_ids` 去重保序、≤5 个/条（API pydantic 422
   + 运行时防御纵深双层）；引用不存在的文件 → 404 且**零落库**（先于 LLM
   调用），与 ADR-0013 事务性单轮口径一致。
6. **附件随草案带入创建任务页**：确认草案时前端把会话内发送成功的附件
   （id+文件名，去重）经 sessionStorage `flai_prefill.files` 交创建页，以
   「已上传」状态入附件列表（`status:done`+fileId），提交时自然并入
   `input_file_ids`——**是否随任务提交由人决定（可移除）**，一次上传直达
   任务签发，不改变「人是唯一签发者」。
7. **GET 会话消息带 attachments 元数据**（filename/size_bytes）；文件行已被
   清理的 id 给显式占位名，不隐藏「曾传过附件」的事实。

## 影响与风险

- 上下文成本：最坏 60K（历史）+24K（附件）字符 ≈ 25K token 级/轮，reasoning
  画像可承受；预算常量集中在 conversation.py/attachments.py 顶部，内网实测
  后可调。
- 附件孤儿：会话上传后未发送成功/会话弃置的文件与 README 限制 #5 同口径
  （无主文件 GC 是 V0.2 项）；重试不重复上传（前端记 fileId）。
- xlsx 仅预览首 sheet 前若干行——工程师若把关键工况放后排 sheet，导引看不到
  （limitation 已声明，块内亦列出全部 sheet 名供导引追问）。

## 修订：反方 fresh-context 审查处置（2026-07-09，commit 待提交）

异源 Codex 治理审因本机 codex 原生二进制缺失（`@openai/codex-darwin-arm64`
vendor 目录被清空，ENOENT）暂不可用——**异源交叉审查悬置待 codex 恢复**；
先以反方 fresh-context subagent 审查补偿（同家族，非严格异源，恢复后补跑
`codex review --commit`）。反方判定 CHANGES_REQUIRED，1 P1 + 1 P2 + 2 P3，
全部本地最小复现坐实后修复：

1. **[P1] fence 逃逸（红线#1 结构隔离可破）**：附件正文含 `<<END_ATTACHMENT>>`
   会提前闭合 fence，把注入文字踢出块外、规则行管不到；文件名含换行/引号能
   断 header。**复现确认**（正文 payload 令 `<<END_ATTACHMENT>>` 出现 2 次）。
   注：红线#2（人是唯一签发者）仍守住（推荐块 schema 对账），故非「注入直达
   签发」，但「防注入双层」的第一层名不副实。修复：`_neutralize_sentinels`
   把正文/文件名的 `<<`→`< <`、`>>`→`> >`（LLM 语义无损、人类可读，字面再
   拼不出定界符）+ `_safe_filename_for_header` 去控制字符/引号 + 上传端
   `_sanitize_filename` 根因去控制字符（连带消 Content-Disposition 换行隐患）。
   补 3 条真咬合 fence 完整性的回归（tamper 拆中和→2 红实证）。
2. **[P2] 文本全量 read_bytes() 内存放大**：大文本每轮重渲染全量载入，与
   xlsx 的 read_only 流式防御不对称。修复：`_render_text_file` 只读
   `limit*4+64` 字节（够 limit 字符可切）。tamper（回全量读）咬红。
3. **[P3] 预算 body-only 软顶**：规则行/header/footer/横幅不计入 budget，
   「硬顶」措辞不实。修复：预算计入结构开销（近似上界，中和引入个位数膨胀
   已如实注明）；本决策第 4 条措辞校准。
4. **[P3] 失败轮已上传附件跨轮残留**：保留为重试语义、chips 可见可移除——
   如实标注为已知行为（GuidePage `uploadPendingFiles` 注释），不改行为。

处置验证：pytest 313 绿（+5）· M6 e2e 10/10 · M2 e2e 8/8 · 三处新 tamper 咬合。

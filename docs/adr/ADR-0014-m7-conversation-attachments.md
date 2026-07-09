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

## 修订二：第二轮独立敌意审查处置（2026-07-09，另一 session 的深度审）

另一独立 session 用真实 PoC（直接调 workflow/渲染器真实函数）做了更深一轮审，
抓到上一轮反方审**漏掉**的三个真问题（均本地复现坐实后处置）：

1. **[P1] xlsx 资源攻击**：openpyxl(read_only) 对 sharedStrings.xml 是一次性整表
   解析，30×16 行列硬顶只压展示量、不压解析成本。实测：438KB 上传（高压缩比）
   → 9.5MB 字符串 → 0.378s/4.1MB，线性外推可到分钟级/GB 级；5 个/条放大 5 倍，
   `except` 兜底捕不住进程级 OOM-kill。修复：`_xlsx_parse_budget_ok` 在开 openpyxl
   前用 stdlib zipfile 探测解压总量（>8MB 拒）+ 压缩比（>200x 拒），超预算走
   「未解析」显式路径。tamper（拆探测）咬红。
2. **[P1 诚实性] echo/quote 注入 + 假绿测试**：`_split_recommendation` 只看第一个
   `<<RECOMMEND>>` 块的位置、不问意图——LLM 若因被说服（场景A）或引用/复述攻击块
   警告用户（场景B）输出 agent_id 真实、字段 schema-valid 的推荐块，校验层照单
   全收产出卡片；场景B 尤其展示文字说「我不会照做」而 UI 弹合法卡片，矛盾且用户
   无信号。且原测试 `test_injection_..._does_not_reach_recommendation` 用**不存在**
   的 agent_id（最易防），docstring 却承诺「附件内容永远无法触达签发」——是假绿。
   **本决策的处置遵循「不假装修好」**：不在本轮重设计 prompt 协议（防不住场景A、
   且需模型侧显式约定），而是①改假绿测试为诚实固化残余风险（真实 agent_id echo
   → 断言确实产出卡片=已知风险，非防住）②把残余风险与缓解写进 README 限制 #11。
   **边界诚实（审查方亦确认）**：红线#2「人是唯一签发者」全程守住——推荐过 schema
   对账、agent_id 必真实、人工创建页复核+提交是最终防线，echo 攻击操纵得了对话/
   误导推荐，**造不出任务、造不出幻觉 agent_id**。修的是「防注入」表述的名实相符，
   不是签发防线。
3. **[P2] 跨会话/跨任务 file_id 无归属校验**：M7 新增「引用任意已存在 file_id →
   文件全文渲染进模型上下文」的通路，触发只需知道 file_id。与「V0.1 无鉴权」同源，
   但若模型后端是外部厂商 API，即「平台内任意文件→第三方」的新通路，EAR/商密敏感。
   处置：README 限制 #12 显式点出（此前被「V0.1 无鉴权」一句带过）；会话级 file
   归属校验列 V0.2。

精度校准（审查指出的用词不实，非安全问题）：
- 「file_ids ≤5 的 422+运行时双层」此前是**死代码**（pydantic 查去重前、运行时查
  去重后，去重只减不增 → HTTP 入口下运行时层永不触发）。已把运行时检查移到**去重
  前**，纵深名副其实；补测试用「去重后 5、去重前 7」的含重复输入真咬合（tamper
  移回去重后即红）。
- 「24K 硬顶」在修订一已改为含结构开销的近似上界（非仅正文软顶）。

处置验证：pytest 317 绿（+4）· M6 e2e 10/10 · M2 e2e 8/8 · xlsx 预算 + file_ids
去重前两处新 tamper 咬合。

## 修订三：异源 Codex 治理审处置（2026-07-09，codex 0.144.0 恢复后补跑）

codex 二进制此前被清空，重装 0.144.0 恢复后对整个 M7 面（07d61ff..HEAD）跑
`codex review --base`。**P1 零**；2 P2 + 1 P3，全 grounded 复核坐实后处置：

1. **[P2] 预算耗尽仍逐文件吐 fence 占位块**：`budget_chars=10` + 5 文件吐出几百
   字符（codex 实跑复现），24K 硬顶失效。修复：预算耗尽改**一行汇总剩余文件名
   后 break**，总量有界；补 `test_tiny_budget_many_files_stays_bounded` 复现 codex
   场景，tamper 咬红。
2. **[P2] `_sanitize_filename` 未去引号 + 我的测试假绿**：`isprintable()` 留 `"`，
   字面引号原样落库。**且原上传级测试假绿**——httpx multipart 客户端预编码
   `"`→`%22`，断言 `'"' not in fn` 根本没执行到引号分支就通过了。修复：sanitizer
   加 `ch != '"'`；测试改为**直接单测 `_sanitize_filename`**（字面引号），tamper
   去引号即红（不再假绿）。
3. **[P3] 导引先传附件再落轮次 → 弃置即孤儿**：与 README 限制 #5 同类（上传-引用
   无 GC）；已把导引流并入 #5 显式记录，会话级附件 GC 随 V0.2 孤儿回收统一做。

处置验证：pytest 318 绿（+1）· 两处新 tamper 咬合（含修正的假绿测试）。至此 M7
异源 Codex 审 P1 零、P2/P3 全处置，审查环收口。

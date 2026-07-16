# 批次二·细粒度还原（F1-F6）评审记录

> 契约：docs/design/UI-DESKTOP-CRAFT.md「批次二：细粒度还原」。
> 分支 feat/uiux-craft-fine-grain（基线 main 7a351a9）。
> 治理链：craft 套件扩针（36→51）→ 5 处 tamper 自证 → 3-lens 对抗审 →
> Codex 治理审（native Pro，gpt-5.6-sol ultra——owner 2026-07-15 指定走
> Pro 订阅池）→ verify_all 18 套 → 合并 push。

## 一、改动面

| 文件 | 改动 | 工作项 |
|---|---|---|
| frontend/src/utils/format.js | formatDuration ≥60s 秒补零；新增 formatTokens（千位压缩 1 位小数，整值去尾零） | F1 |
| frontend/src/views/TaskDetail.vue | rail tokens 走 formatTokens；产物 >3 件尾部折叠（visibleArtifacts/artifact-more）；产物类型标签「文档 · MD」；接入 VerificationCard（产物后、动作前，class="section"） | F1/F5/F6/F3 |
| frontend/src/components/DeliveryCard.vue | 尾行 tokens 走 formatTokens | F1 |
| frontend/src/components/StatusCenter.vue | 速览 tokens 走 formatTokens | F1 |
| frontend/src/components/WorkLog.vue | 工作态 1s ticker（nowTick），elapsed 与轮询解耦，纯离散文本替换 | F2 |
| frontend/src/components/VerificationCard.vue | **新组件**：核验自证段（工具真实性/人工签发/批量结果三行，全落库数据投影） | F3 |
| frontend/src/components/CompletionSeal.vue | 尾部落定时刻（同日 HH:MM／跨日 MM-DD HH:MM；cancelled 报时刻不报时长） | F4 |
| frontend/e2e/craft_desktop_acceptance.py | 夹具增强（签发链/tool_runs/model_calls/5 真产物/running 任务/internal 分级戳）+ ⑨ 探针 15 支 | 验收 |

## 二、验证证据

- craft 套件：3-lens 收口后 **56/56 全绿**（36 既有 + ⑨ 新针 20 支，EXIT=0
  直读非 tail；3-lens 前首轮为 51/51）。
- **tamper 自证 5 处 6 咬**（变异→套件→恢复，恢复后 cmp 逐字节一致）：

| # | 变异 | 咬合探针 | 结果 |
|---|---|---|---|
| T1 | formatDuration 秒补零回退（`2 分 5 秒`） | ⑨F1 盖章时长秒补零 | BITE（50/51，恰失血一针） |
| T2 | 核验段 amber「未经真实核验」pill 拆除 | ⑨F3 mock 如实披露 | BITE（50/51） |
| T3 | 产物折叠 slice(0,3) 拆除（全量平铺） | ⑨F5 默认渲染前 3 | BITE（cards=5 被抓） |
| T4 | sealClock 强制 null（时刻拆除） | ⑨F4 盖章落定时刻 regex | BITE；3-lens 补针后**复跑双咬**（⑨F4 completed + ⑨F4' cancelled，54/56 恰失两针） |
| T5 | ticker 拆除回退 Date.now()（轮询驱动） | ⑨F2 断轮询后仍逐秒递增 | BITE——验证 route-abort 探针设计成立：无 ticker 时断轮询窗口文本真冻结 |

- **分级门咬合实证（意外收获）**：首跑夹具种 tool_runs/model_calls 未落
  data_classification 戳 → ADR-0025 fail-closed 兜底把任务判 sensitive、
  events payload/message 全遮蔽（签发行/工具 chip 消失）——门在正确工作；
  修复=夹具补 runner 同款 internal 戳并注释教训。遮蔽路径由此获得一次
  免费的真实咬合证据。

## 三、3-lens 对抗审（trust / regression / paradigm，Sonnet 5 并行三镜头）

8 条 findings 收敛为 6 个独立问题（formatTokens 边界三镜头齐咬）。逐条 grounded
复核（亲读 classification_gate.redact_rows / StatusCenter:130 / e2e 文案锚扫描）
后处置：

| # | 镜头/级别 | 问题 | 复核 | 处置 |
|---|---|---|---|---|
| 1 | trust P1 | 签发行把「已签发但 payload 被分级门遮蔽」谎报成「未经人工签发流程」（对已发生事实的确信性否定） | ✅ 坐实：redact_rows 置 payload=null 保 event_type | **修**：deriveSignoff 三态 SSOT（null/redacted/完整）下沉 utils/format，WorkLog+VerificationCard 共用；redacted→中性「签发记录不可用（内容受限）」；新增 task F（真实 sensitive 分级）e2e 探针走真遮蔽链路 |
| 2 | trust P2 | 页头批量 el-tag type="success" 真绿 vs 核验段同数据中性——同屏两种信任信号 | ✅ 坐实；e2e 无 success-tag 锚 | **修**：success→info + 信任色锁注释；task E 补批量摘要事件，新增「页头无绿 tag+核验失败计数染红」双探针 |
| 3 | trust P2 | F4「cancelled 报中断时刻」零探针覆盖，且 task_c 夹具无 finished_at（真实后端对任意终态必写）——声明等级高于证据等级 | ✅ 坐实 | **修**：task_c 补 finished_at（无 started_at=从队列直接取消的合法路径）；新增「已取消 · HH:MM 且无时长词」探针；T4 tamper 复跑证双针齐咬 |
| 4 | trust P3 + regression P2 + paradigm P2（三镜头齐咬） | formatTokens n∈[999950,999999] 输出「1000k」（四位假 k 值，不在格式表合法形态） | ✅ 执行验证坐实 | **修**：以渲染结果本身为判据（kStr==="1000" 升 M 档），同一套 toFixed 舍入不再打架 |
| 5 | paradigm P2 | F6 类型标签只落 TaskDetail，StatusCenter 速览孪生徽章仍裸后缀「.md」 | ✅ 坐实（StatusCenter:130） | **修**：artifactTypeLabel 下沉 utils/format SSOT，两处共用 |
| 6 | paradigm P3 | 批准口播两处措辞漂移（「依据 X 的批准放行」vs「已由 X 批准放行」）与「同源同谓词」注释自相矛盾 | ✅ 坐实；e2e 无「依据」文案锚 | **修**：signoffText 对称句式「✓ 由 X 批准放行／✕ 由 X 驳回」统一两处；新增逐字同串探针 |
| 7 | regression P3(low) | WorkLog 与 VerificationCard 各自拉一次 tool_runs（无共享缓存） | ✅ 属实但有界（每状态至多一次+展开一次），两组件注释已声明 | **不改（accepted-by-design）**：下沉 channel 的收益不抵复杂度；若后续 tool_runs 进 liveFeed channel 一并收编 |

## 四、Codex 治理审（native Pro · gpt-5.6-sol ultra，owner 指定 Pro 池）

### R0（--uncommitted，2026-07-15）

审查者自行复跑 craft 套件（其独立环境 56/56 绿）后给出 **0×P1 + 2×P2**：

| # | 级别 | 问题 | 处置 |
|---|---|---|---|
| 1 | P2 | VerificationCard 贪拉全量 tool_runs（`SELECT *` 带回解码 input/output/raw_path，卡片只要 total/mock 两个数；批量任务开详情=搬运整条执行轨迹，WorkLog 展开再来一次） | **修**：新增有界聚合端点 `GET /tasks/{id}/tool_runs/summary`（单条 COUNT SQL，只回 total/mock_count——纯计数元数据，严格少于遮蔽后 tool_runs 行，无需分级门分支；与 delivery_summary 同先例）；前端 getToolRunsSummary + 形状校验（畸形→「不可用」绝不冒充 0 计数）；pytest 新用例（键集恰 {total,mock_count}/与明细对账/零 run 0 值/未知 404） |
| 2 | P2 | deriveSignoff 把「无遮蔽标记但缺 reviewer」（畸形/存量数据）也报「内容受限」——虚构一个没发生的限制；后端遮蔽路径显式打 `content_withheld=true` | **修**：受限判定只认后端真标记（content_withheld is true→redacted），缺标记=`{unknown}`→「签发记录不完整」不编因；两组件模板补 unknown 态；单测按新契约改写+补 unknown 用例 |

R0 修复后三层复验：node --test **16/16** · pytest summary 用例 **6 passed** ·
craft **56/56**（⑨F3'' 真遮蔽探针继续咬合——分级门路径带真标记）。

### R1（--uncommitted，R0 修复后）

**1×P2 + 1×P3**（两条均打在 R0 轮新代码上——审得准）：

| # | 级别 | 问题 | 处置 |
|---|---|---|---|
| 1 | P2 | VerificationCard summary 请求竞态：waiting→completed 迁移在首请求在途时发起第二请求，无世代守卫——旧失败可抹新成功（永久「不可用」），反序装 stale 计数 | **修**：fetchSeq 世代守卫（house pattern=TaskDetail feedbackSeq），then/catch 双侧 stale 作废；畸形形状同守卫内联处理 |
| 2 | P3 | 盖章跨午夜：终态停轮询后 computed 裸读 new Date() 永不重算，昨日完成滞留裸 HH:MM | **修**：todayKey 响应式日界+单发 setTimeout 对准下一本地午夜+1s 翻页再武装（零轮询，卸载即清）；sameDay 判据改 toDateString 对比 |

R1 修复后复验：craft **56/56** · node --test **16/16**。

### R2（--uncommitted，R1 修复后·cap 末轮）

**Clean**：「No actionable correctness defects were found. Frontend build, Node
tests, full pytest suite, and the targeted craft acceptance suite all passed.」
——审查者在其独立环境自跑四层验证全绿后给出零 actionable。

**收敛判定**：R0（2×P2 全修）→ R1（1×P2+1×P2 全修，均为对 R0 轮新代码的
精准复审）→ R2 clean。cap=3 内收敛，无 P1 残留，无裁决升级项。3-lens 侧
1 条 P3(low)（tool_runs 双源拉取）accepted-by-design 已在 §三记录——且 R0
的 summary 端点落地后，核验段已不再拉全量明细，该 P3 的实际重叠面进一步
缩小。

## 五、Codex 协作（执行主力 dispatch，owner 指定走 Pro 订阅池）

- format.js 纯函数单测（frontend/tests/format_display.test.mjs）dispatch 给
  native codex exec——契约清晰的测试编写，「谁写另一方审」：format.js 我写、
  单测 Codex 出、主控亲核+亲跑仲裁。
- 实况：首派 gpt-5.6-sol ultra **网络悬死**（>1h 进程 CPU 累计 0.1s，非推理
  慢）→ 砍掉重派 native gpt-5.5 medium（同 Pro 池，路由表「简单直白单文件」
  档）→ 4 分钟交货 8 test/15 断言，含 999950→"1M" 进位穿透边界针与
  deriveSignoff 三态（null/redacted/完整）。
- 收货核验：主控亲读全文（契约忠实，无 tamper 窗口污染痕迹）+ 亲跑
  `node --test` **15/15 pass**（恢复树上仲裁）。边界断言本身构成 formatTokens
  修复的变异敏感网（回退即红）。

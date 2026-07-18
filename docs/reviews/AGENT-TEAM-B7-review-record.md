# 批七「专家团队语义层 + 编队投影」评审记录（AGENT-TEAM-B7）

> 契约=docs/design/AGENT-TEAM-B7-DESIGN.md（DESIGN-FINAL）。范围=96b7e10..HEAD
> （S1 契约层 e4e80fd / S2a 后端 54719f3 / S2b 三垂类包 b3fccd0 / S3 前端投影
> 6262d73 / S4a-S4b 验证链与 3-lens 收口）。本文件=治理链存档；tamper 明细见
> 同目录 AGENT-TEAM-B7-tamper-log.md。

## 一、验证链总账

| 环节 | 结果 |
|---|---|
| 后端 pytest 全量 | 913 passed（含批七新增 24：契约 8+批量/密级 17+三包行为 7，扣重叠计） |
| 前端纯函数核 node --test | 绿 |
| batch_g_squad_acceptance（O1-O11，42 探针） | 42/42 绿（真 JobRunner+真 resolver 全链） |
| craft_desktop_acceptance（批五基线） | 110/110 绿（S3 新渲染下重录，O12 前提） |
| 批五/六 tamper replay 8 case | 8/8 BITE-OK（S3 基线 6262d73 worktree，基线先行全绿） |
| 批七 tamper TB1-TB4 | 会话内四咬 + 登记 replay（b7-* 四 case）；TB1 首轮 crash-type 如实修正（见 tamper-log） |
| 受影响存量 e2e 冒烟 | m8_workbench 11/11 · m8_collab_chain 9/9 · orchestrator 4/4 · inline_summon 14/14 |
| verify_all 全量 | 见 §四 收口更新 |

## 二、3-lens fresh-context 审（sonnet 异脑，1P1+4P2+2P3）

| # | 级 | 裁决 | 处置 |
|---|---|---|---|
| L1-1 | **P1** | resolver 管道注入绕过 ADR-0030 创建门：下游创建时零文件（材料级 public 恒过门），事后被注入 sensitive 上游产物无人复核 | **真修**：`_open_input_files` 消费点对 kind=output 管道产物重跑 `agent_clearance_allows`（K1/K2/provenance 同款双端强制）。边界如实声明：直提交输入由创建门全 API 路径判定不重判（护 ADR-0025 存量派生语义）。+2 测试（拒执行/对照放行） |
| L1-2 | P2 | guide 显式 `after: []` 被误当剥离记名（虚假降级告警上屏） | 真修：合法空值不记 stripped；+回归测试 |
| L1-3 | P2 | openPlan 跨轮依赖静默降级为并行（前后端诚实记名标准不一致） | 真修：剥离计数经 warning 显式披露「N 条依赖…改为并行——需要严格接力请一次性召集」。batch 契约本身只表达同批下标（跨批引用 task_id 排批八 teams 语义） |
| L1-4 | P3 | material level 的 public 分支现实不可达（files 只收 internal/sensitive） | 接受留存：为未来文件分级扩展预留，fail-closed 方向无害；ADR-0030 已述三级语义 |
| L2-1 | P2 | L3+interactive 组合不受装载不变量约束（interactive 无人签闸可兑现） | 真修：L3 ⟹ mode=job 且 rhr=True，其余姿势全拒载；+测试 |
| L2-2 | P2 | findings 装载校验仅查顶层键，空 schema `{}` 可骗门 | 真修：须 array 且含 evidence+resolved 结构；正控升级+三弱形反例测试 |
| L3-1 | P3 | O11 探针 6s 观察窗在高负载 CI 是 flake 面 | 真修：排序 stub 窗放宽 8s |
| — | — | `EvidenceList.withheld` prop 未接线（冗余非泄漏，下载 403 独立在场） | 接受留存：预留给密级遮蔽渲染面，batch 八接线 |

审查方无发现面（如实记录）：`is True/False` 纪律全新增判定点合规；EvidenceList
全链无绿；resolved 三包 schema 层 `const: false` 硬锁无绕过；batch 失败清单
可读性、O 探针无 vacuous 写法；「等待接力」文案忠实无编造。

## 三、S2b 三垂类包异源关系

Codex（native 20x Pro gpt-5.6-sol ultra）落地三包 → Claude 逐文件亲核（manifest
三 block/装载不变量/EAR 扫描零命中/语料 12 条全合成 SYN-FH-*）+ 7 条持久化
异源行为测试（Codex 自报自测不算证据）：拒答不调模型/resolved 自报 true 必
降级/白名单外编造诚实 failed 不落盘/双依据保留。Codex 报的 6 条并发失败
（5 m11 分类 + 1 guide schema）由 Claude 修复（夹具合法授 sensitive + output
schema 补 after，语义均忠实非放水）。

## 四、收口更新（按发生顺序追记）

- [x] **verify_all 全量 EXIT=0**（2026-07-17）：20 步全过——build + 913 pytest +
  node --test + 18 套 e2e 全 ALL GREEN（含 craft 110/110、batch_g 42/42 收官），
  失败=无。
- [x] **b7-* replay 四 case 独立重放 EXIT=0**：基线先行全绿 → b7-after-cut
  （FAIL O1c）/ b7-hollow-pulse（FAIL O2a）/ b7-fake-settle（FAIL O7e）/
  b7-gate-cut（FAIL O4a）四处全部三条件干净咬合（非零 RC + 精确 FAIL 行 +
  FAILED 汇总必达）。
- [x] **Codex 治理审 R0**（86gs gpt-5.6-sol ultra）：CHANGES_REQUIRED，6P1+4P2
  全部 grounded 证实并修复（S4e af146e5）——batch 事务原子性/registry 隔离不崩/
  门户直达垂类交互包/QA 双空拒收/工作台全任务分组/编队全任务收束判据 +
  结构化路径校验/charter 持久化事件/空心灯/空白输入归一。修后 verify_all
  全量 EXIT=0。
- [x] **Codex 治理审 R1**：CHANGES_REQUIRED，1P1+5P2 全落（S4f 8d3ad98）——
  未召集块 v-else 劫持（真回归）+ QA 目录白名单/StrictInt 下标/charter 上屏
  优先级/finish_reason 白名单/UnicodeError 隔离。修后 verify_all 全量
  EXIT=0（1034 pytest + 18 套 e2e）。（首次 R1 因 codex 侧 context 压缩中断，
  重跑出裁决；两轮共新增 10 条回归测试。）
- [x] **Codex 治理审 R2（cap=3 终轮）**：仍报 2P1+5P2，两 P1 grounded 证实：
  ①交互附件不过密级 gate（post_message 只查存在性，clearance 仅任务路径
  强制——internal 上限交互 agent 可被喂 sensitive 附件进模型上下文）；
  ②taskEvidence 被动依据水合对 sensitive 产物盲调下载 → 伪造
  sensitive_download_denied 审计事件（listOutputFiles 已回传
  data_classification 可跳过，仓内 tasks.py:893 有同款先例修法）。
- [ ] **cap 用尽仍有 P1 → owner 裁决**（本行代填裁决结果）：修复后合并 /
  带已知问题合并+快跟 / 其它。R2 的 5 条 P2（目录白名单子串匹配收严 /
  evidence_policy.kinds 装载期未强制 / 拒答 reason 越长度上限 / QA
  finish_reason / RecursionError 隔离）进 retro 队列。

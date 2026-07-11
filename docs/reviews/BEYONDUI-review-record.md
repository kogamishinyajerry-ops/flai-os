# Beyond-UI 深度优化批（2026-07-11）审查记录

> 批次来源：owner「除了UI，深度思考优化方向，配合 5.6 Sol 联合开发优化」。
> 双路提案（Claude 六镜头 Workflow + Codex 5.6 Sol 独立异源提案）→ 主控裁决 →
> 三 lane 联合开发（Codex Lane A/B + Claude Lane C）→ 互审 → 全量验证。

## 提案与裁决

- Claude 六镜头（BE 后端健壮性 / FE 前端工程 / GOV 诚实治理 / M4 内网准备 /
  AST 资产槽位 / TST 测试基建）：FE 镜头返回退化占位数据判失效，其覆盖面由主控
  亲查补位（Element Plus 全量引入=代码内注释明示的刻意决策，不动）。
- Codex 8 条（CDX-1~8）：主控逐条 grounded 复核。**CDX-1（Runner 可自动把
  waiting_review 转 failed 的违宪旁路）复核坐实为真 P1**——waiting_review→failed
  是合法转移（预留人工驳回），runtime 状态提交与事件写入非原子，事件写入异常冒泡
  即触发 Runner 兜底自动置 failed。CDX-5 的 .env.example 键名漂移
  （DATABASE_URL vs 代码实际读 FLAI_DB_PATH）亦坐实。
- 判缓/判否：CDX-2 真工具执行边界（L，M4 侦察后设计）、CDX-4 sha256 消费前
  完整性闸（M，独立批次专审）、CDX-6 离线发布包（L，依赖内网平台侦察）、
  CDX-7 单 worker OS 锁+崩溃恢复（M，与 README #15 reaper 合并为 V0.2 项）、
  CDX-8 完整 readiness（部分采纳为 health 布尔位）、GOV-1 model_calls 聚合
  （端点已存在，UI 接线归下一 UI 批）。

## 落地清单

**Lane A（Codex 实现，Claude 审=APPROVE）**：
- A1 宪法修复：`repos.fail_task_from_execution`（BEGIN IMMEDIATE 锁内执行态
  白名单，非执行态零写入返回 None）+ Runner 拒绝口径留痕 + runtime
  review_requested 事件写失败降级不冒泡。回归测试 3 组。
- A2 十个幂等索引（存量列迁移后同锁内建，sqlite_master 对账测试）。
- A3 claim_next_queued 无锁预检（探测不参与裁决，锁内逻辑逐字保留；空队列
  不再每秒抢 BEGIN IMMEDIATE 写锁）。
- A4 gateway _post 有限重试（仅 TransportError/502/503/504，共 2 次尝试；
  「一次逻辑调用恰一条 model_calls」不变量保持，401 不重试有测试咬合）。

**Lane B（Codex 实现，Claude 审=APPROVE）**：
- 状态机非法转移矩阵程序化补集（100 个有序对全覆盖，原 26 个盲区清零）；
- 契约 parity gate 扩展到 list_tasks 逐元素 + review approve/reject 响应；
- backend/tests/conftest.py 收敛 10 处逐字重复 app_env（定制 fixture 保留）；
- scripts parity 静态门（.sh/.ps1 --with 集合相等）；
- health 端点 llm_*_set 只读布尔位（不回显值）；
- scripts/verify_all.sh(+.ps1) 一键全量验证（fail-fast+清单汇总）；
- scripts/probe_llm_gateway.py（只出原始观测，无整体 PASS 裁决）；
- scripts/diagnose_gc_debt.py（只读，注释焊死「禁用 files.task_id 判孤儿」）。

**Lane C（Claude 实现，Codex 审见下）**：
- README 诚实清单修订（#1 结构化表单已交、#5 files.task_id 地雷警示、
  #19 弃置会话具体触发路径）+ FLAI_* 环境变量表 + verify_all/xdist 接线；
- .env.example 键名修正 + 「不自动加载」诚实标注 + WAL 本地盘约束；
- docs/M4_intranet_day1_recon_checklist.md（全仓「待内网侦察」标记（grep 18 处
  精确命中，不含本 checklist 自引用）归组为四类逐项核对表，含 30 分钟最短路径）；
- favicon.svg（与 brand-mark 同源手写 SVG）+ index.html link；
- EmptyState.vue 收敛 8 处裸 el-empty 为三语义变体 + AI 生成插画
  （chatgpt.app gpt-image-1，漫画墨线+暖白+clay 单强调+透明底，
  description 文案逐字不变）。

## Lane C 互审（Codex read-only 审 Claude，1P1+6P2+6P3，全部处置）

- **P1** GC 孤儿口径漏 `conversation_messages.file_ids`（会话附件会被误判孤儿）
  → 脚本三源并集 + 表缺失如实标注 + 新回归断言（conv_ref 绝不判孤儿）+ README #5 改口径；
- **P2×6** 全修：README #19 限定「从未召集任务」/ 上传默认 20→100 更正 /
  verify_all 改跑满三个 testpaths（.sh 与 .ps1 同步）/ EmptyState 去 slot 透传
  （消空 .el-empty__bottom 20px）/ checklist 401/403 降级为观测 /
  README xdist 声明补具体证据（2026-07-11 本机 514 例 串行~25s→~7s）；
- **P3×6**：MODEL_FAST 改按需 / .env.example 补 PORT+UPLOAD 可选键 /
  「17 处」更正为 18 处精确命中 / EmptyState 注释披露尺寸变化（80→96、60→76
  为刻意设计）/ checklist 1-3 拆 content 必需与 usage 可选 /
  **e2e 对空态与 favicon 零断言=接受为残余**（插画为装饰性资产，截图 archival
  非 diff gate；若日后升格为契约再补断言）。

主控对 Lane A 附加 tamper 自证：拆 fail_task_from_execution 白名单
（waiting_review 加入执行态集合）→ test_mark_failed_best_effort_refuses_waiting_review
必红；还原→全绿。

## 验证

见收尾报告与 verify_all 输出（本文件提交时以 git 历史中的实际运行为准）：
全量 pytest（三个 testpaths，514 例）+ 5 套 Playwright e2e + 前端构建。

## 残余风险 / 递延

- CDX-4/CDX-7/CDX-2/CDX-6 见上判缓条目；
- verify_all.ps1 DECLARED-NOT-VERIFIED（本机无 Windows）；
- gateway 重试上限 2 次尝试（交互式会话最坏等待 ~120s+0.5s，可接受；
  若内网抖动频繁再议退避参数）；
- 空态插画为装饰性资产，e2e 对其零断言（截图为 archival 非 diff gate）。

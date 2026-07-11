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

---

# R4 批（2026-07-11 第二批）审查记录

> 批次来源：owner「R4已经完成，进一步优化 ultracode」。上一批判缓的 CDX-4/CDX-7
> 升格落地（Codex K lane），R4 实机拉片对应的三个前端件（Claude Workflow B lane），
> 双镜头（信任色/诚实 + 回归风险）对抗审 → 主控裁决落修。

## 落地清单

**K lane（Codex 实现，Claude 亲核=APPROVE+1 项补强）**：
- K1（原 CDX-7）：worker 跨平台单实例文件锁（fcntl/msvcrt，锁文件不删避免竞态、
  锁先于装配）+ 启动恢复中断执行态任务置 failed（走 `fail_task_from_execution`
  锁内白名单，waiting_review 天然免疫；`worker_interrupted` 事件留痕，绝不自动
  重放）。README #15 由「无卡死任务回收」收窄为「仅覆盖进程重启时点」。
- K2（原 CDX-4）：File Store 消费前完整性闸（`storage/file_integrity.py`：
  O_NOFOLLOW→fstat size→流式 sha256→seek(0) 同句柄消费，权威根限定）。三个消费
  口接线：下载 409 / 导引附件「已拒绝注入」/ 任务输入 validation_failed
  （**行为翻转**：缺失输入从 warning 跳过改为整任务拒绝执行）。fd 生命周期三条
  失败路径（knowledge 装配失败/置 running 失败/workflow 结束）全兜。
- 主控补强：`api/files.py` 覆写 Starlette FileResponse 三个私有挂点实现已验
  句柄的 Range 语义——升级改名会**静默绕过**覆写、基类重开 path 直出未验内容，
  故加导入期哨兵（挂点缺失即 RuntimeError 拒绝启动，fail-loud）。

**B lane（Claude Workflow 三 builder 并行 + 构建门 + 双镜头审）**：
- B1 TaskDetail 模型调用消耗诚实披露（次数/成败/模型名/token 合计——只对可折算
  行求和，凑不出即「未知」绝不记 0；失败数>0 才标 trust-fail 红，成功数中性）；
- B2 工作台轻量轮询（首页+会话视图 5s）+ 会话卡未读 clay 圆点（行动召唤语义，
  不占信任色四槽；窗口外任务诚实不亮）+ 成员任务「最近动态」行（最后一条事件
  message 原文，不承诺第一人称叙事）；
- B3 ⌘K QuickSwitcher（三源客户端过滤，键盘环绕导航）。**B3 自报告退化为占位
  数据（"test"），按纪律判自报告作废，主控逐行亲读其 diff**——实现质量实际过关
  （convoTitle 口径与 App.vue 一致、statusLabel/taskLampColor 复用、挂载零外溢），
  仅缺 IME 守卫（见下）。

## 双镜头审 findings 处置（全部落修）

- 信任 P2：chip-lastword 按「状态未变跳过」节流，长任务同状态下动态冻结在第一条
  → 去节流改每 tick 无条件重取（≤5 请求/5s，task_events 有索引）+ 请求序号守卫；
- 信任 P3：「第一人称汇报」措辞过度承诺（实际多为机械上报文案）→ 注释/文档
  统一改口径为「最近动态=最后一条事件 message 原文」；
- 回归 P2：QuickSwitcher 缺 `e.isComposing` 守卫（中文 IME 选词 Enter 误触跳转）
  → 补守卫；
- 回归 P2：两工作台页用 setInterval（慢网堆积并发）→ 改 TaskDetail 同款链式
  setTimeout（上一轮落地才排下一轮，document.hidden 跳过仍续轮）；
- 回归 P3×2：fetchLastWord 乱序竞态 / syncModelCalls 游离于 baseline 守卫外
  （stale 覆盖含旧错误横幅）→ 均加请求序号「最新发起者胜」守卫；
- 确认性 P3×3（e2e 锚点含 m2 `a[href*='/download']` DOM 序、localStorage
  降级、异步全兜错）复核通过，零改动。

## 判否 / 残余

- **BE-4（知识索引指纹 (mtime,size) 键复用）判否不落地**：knowledge 服务 docstring
  已把「绝不基于 mtime 猜新鲜度」立为设计约束（Windows 复制保留 mtime 正是其
  对抗场景），指纹复用恰在该场景失效——与既有设计承诺冲突，递延 owner 裁决；
- path 型工具契约以路径二次打开输入文件的 TOCTOU 窗口（句柄化契约待后续升级，
  README #20①）；
- K1 msvcrt 锁 / O_NOFOLLOW 的 Windows 分支本机未实测（M4 侦察清单 2-5/2-6）；
- 下载 Range 覆写依赖 Starlette 私有挂点（导入期哨兵兜底，README #20②）。

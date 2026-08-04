# FLAi-OS 批 0 体验审计 + 切片 1 实施记录

> 基线：`origin/main` @ `d5a52aa`（含 PR #23）· 分支 `qw/agent-shell-audit-v1`
> 作者：千问办公 · 日期：2026-08-04
> 证据：本目录 `craft-shots/s1-*.png`（选集入库）；全量 25+5 张在 `/tmp/flai-audit-stack/shots{,-after}/`（重启即失）。
> 诚实口径：全部流式证据为 stub 网关驱动（链路真、内容假），如实标注。
> owner 裁决留痕（2026-08-04 逐条）：PR#23 合并✓；今日/任务台合并=批 0 后裁；
> 会话隔离=先出方案✓（草案见 §四）；LLM 复验=挂起等窗口；WorkLog 零值段=并入首批✓；
> IntentGlyph/empty-log=退役✓（排队列）；离线打包=挂起 M4；密级 pill=收进 title✓（排队列）；
> P1-2 失败痕迹=维持现状✓；切片 1 构成=按提案✓；本报告随切片 1 入库✓。

## 一、基线实测（隔离副本）

| 项 | 实测 | 备注 |
|---|---|---|
| pytest（三 testpaths） | 1785 passed, 2 skipped | HANDOFF-K3 旧值 1201，已同批更新 |
| node --test | 231 | 旧值 126 |
| E2E | 21 套 | 旧值 20 |
| Craft / Batch-G / Batch-H | 121 / 46 / 26 | 含本批新针 |
| bundle 主入口 JS gzip | 135,106 B（≈132KB） | 预算不放宽 |
| 动态入口 / 最大路由闭包 | 7 / GuidePage ≈202KB | 旧值 8 / AgentPortal≈204KB |

NEXT-STEPS 六项 P0 独立复核：全部「未做」，与 NEXT-STEPS 自审一致。
probe_llm_gateway.py 离线自检：缺配置 fail-closed 明示；不可达 URL 输出原始观测+「是否符合协议由人判断」。

## 二、P0/P1/P2 清单

### P0-1 方案卡开工后活状态不在可见面（已修，见 §三）
成员任务状态灯/状态词/秒表/「审阅签发 →」/产物锚点/L1 编队行全部位于默认收起的
`route-disclosure` 内；可见面仅「执行已接入，关键状态会在这里更新」一行指向隐藏内容。
冲突 UI-PARADIGM #1/#2；ADR-0033 只要求路由依据进披露，活状态不是路由依据。
证据：`s1-before_plan-card_light_1440.png`。

### P1-1 会话内活跃会话侧栏标题停在兜底（排队列，切片 2）
`recordConversationFirstUserContent` 仅在全量拉取时记录；就地建会话+发送后不补记。
reload 后正确（first_user_message 投影）。修法：发送/stream done 补记一层+node 单测。

### P1-2 失败轮对话轴无持久痕迹（owner 裁：维持现状）
回滚+草稿还原契约正确；失败仅瞬时 toast。留观察。

### P1-3 长会话阅读节奏装置缺失（切片 3，主场入口）
无日期/工作段分隔；每泡全精度时间戳；助手回复视觉同构。证据：`s1-before_long-session_light_1440.png`。

### P2
- P2-1 收起披露与 plan-foot 双发丝线死空间（已修）。
- P2-2 今日页待签空态插画 vs 进行中 line 态同屏双语法（存疑不动手）。
- P2-3 失败卡「进行了 0 秒」零值噪点（观察项）。
- P2-4 craft ⑭C1/C2 并发负载 flaky，单跑全绿（retro 队列）。
- P2-5 文档基线数字过期（已修）。

## 三、切片 1 实施记录（本 PR）

改动面（纯前端+测试+文档，零后端/零契约/零新依赖）：

1. `GuidePage.vue`：编队总览行（sa-squad-line）自披露内**移动**至可见面（sa-squad-face，
   非复制——避免 e2e strict-mode 双匹配）；waiting_review 时可见面长 amber
   「审阅签发 →」CTA（`squadReviewTarget`，无待签返回 null 不渲染）；承诺行改「执行已接入」
   （元素与 aria-live 保留，ui_lab stateLiveRegions 锚不动）；roster 明细留披露（ADR-0033）。
2. `GuidePage.vue` CSS：`.sa-squad-face`/`.squad-review-cta`（amber=待签槽，hover 回墨，
   focus-visible 走全局 clay ring）；`.route-disclosure:not([open]) + .plan-foot` 收双发丝线。
3. `WorkLog.vue`：时长段零值豁口——<1s「已 X」整段不出现，工作/完成态同一规（owner 裁 #4）。
4. 探针：batch_g S1a–S1e（可见面在场/相段词到账/无待签不长 CTA/待签 CTA 直开速览）；
   craft ⑰S1（零时长完成态无「0 秒」）。tamper 登记：`s1-face-cut`（batch_g）/`s1-zero-cut`（craft），
   提交后 `bash scripts/tamper_replay.sh s1-face-cut s1-zero-cut` 验咬合。
5. 文档：HANDOFF-K3 基线数字更新；本报告与 s1-* 截图入库。

验收实测：batch_g 46/46、craft 121/121（隔离副本）；build/check:bundle/node 231 本地绿；
after 截图 `s1-after_plan_{light,dark,reduce}_1440.png`、`s1-after_session_light_375.png`——
可见面编队行「协作已收束 · 1 失败」rose 段不展开披露即在场，暗色/reduced-motion 无漂移。

## 四、会话隔离立项方案（草案，待审；实施在切片 1 之后）

- 面：8 个会话端点（POST/GET /conversations、GET/{id}、POST/{id}/messages、/messages/stream、
  /conclude、GET/{id}/model_calls、GET/{id}/tasks）统一 exact-owner 校验。
- 模式：复用 `object_authorization.py`（ADR-0037）；missing/legacy/跨 owner 同塌 404
  「资源不存在或不可访问」，不构成存在性 oracle。
- 数据面：conversations 表已有不可变 `created_by_username`（迁移 #9），零迁移；
  `created_by` 仅展示名不判权。列表过滤只是投影，隔离以端点级校验为准（codex 意见落地）。
- 负向见证：用户 A 持 B 的会话 ID 对 8 端点逐一读/写/stream/conclude 全 404；pytest+e2e 原子同批。
- 非目标：不改持久化/状态机/权限模型新增；跨用户共享=显式不支持（需 owner 确认内网无此场景）。
- 估时：后端 ≈200–400 行+测试；前端零改动。

## 五、记录

- flaky：craft ⑭C1/C2 并行负载红、单跑绿——retro 队列（余量再提或串行化声明）。
- 环境：审计栈 launcher 重建于 `/tmp/flai-audit-stack/launch.py`（create_app+stub 注入
  `app.state.conversation_service.model_gateway`；worker 以 `FLAI_DB_PATH` 同库起）。
- retro 队列追加：P1-1、P1-3、P2-2、P2-3、P2-4、IntentGlyph/empty-log 退役、密级 pill 收 title。

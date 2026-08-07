# MAP46-65 动态涡轮标识施工记录（task · 票 #65）

> 施工基线：origin/main @ 6e1e754（#61 定稿并入后）。口径唯一源：
> `docs/design/MAP46-61-DYNAMIC-TURBINE-LOGO.md` §六定稿结果（owner 2026-08-06 逐项裁）。
> 本票零设计决策；施工中唯一未覆盖抉择点（e2e 双锚处置）已给 owner 交互裁（2026-08-07：原子同批更新）。

## 一、定稿逐条落地对照

| 定稿 | 落地 | 证据 |
|---|---|---|
| Q1=甲：PNG 保留，单档扩三档 | `FlaiBloom.vue` state prop 扩 idle/slow/fast，flai-bloom.png 一个像素未动（sha256 锚测试不动） | `frontend/src/components/artwork/FlaiBloom.vue` |
| Q2：静止 0 / 慢速 8s/圈 / 高速 1.4s/圈，无中速档 | 两档 CSS `animation-duration`（8s/1.4s），静止档无类无动画=零残动 | 截图 manifest 各 duration 断言 |
| Q3=i 确定性信号映射 | 工作态 TASK_WORK_STATES 或 queued → 慢速；本会话在途（sending/流式）→ 高速；无信号 → 静止；信号消失回落 | `App.vue` brandBloomState；`GuidePage.vue:77/:514` |
| Q4=A 侧栏全局两档 | 侧栏 brand 只绑全局任务态（静止/慢速），taskFeed 共享轮询源（与 StatusDock 同一条 liveFeed tasks channel，零新链路）；identityReady 门控挂链（登录门后不轮询，同 Codex R1 审 P2 纪律）；高速不进侧栏 | `App.vue:16` + script 绑定 |
| ai-mark 现行绑定沿用 → 高速 | `m.streaming` → fast（:77）；`sending && !hasStreamingAssistant` 待首包 → fast（:514） | `GuidePage.vue` |
| hero 空态恒静态 | 不绑（无 state prop） | 截图 hero-idle |
| Q5a 登录门进静态花瓣标识 | WelcomeGate 品牌氛围面 + 窄屏登录卡各进一枚恒静态花瓣（无 state 绑定）；工牌插画氛围位保留、定性不动；≥900px 卡内那枚隐去（沿 .welcome-gate__art 同纪律，同屏不留第二锚点） | `WelcomeGate.vue`、gate-wide/narrow 截图 |
| Q5b favicon 花瓣重绘 | `public/favicon.svg` 以 flai-bloom.png 出图重绘（轮廓提取+Catmull-Rom 平滑，六瓣 <use> 旋转 + 转轴毂，瓣 #c66f55 / 毂 #a9513d 取自原图两阶 clay）；:2 虚标注释修正为真实口径；clay 语义不动 | favicon-render.png（16/32/48/128 + 暗底目检） |
| Q6 直切 | CSS animation-duration 直切，无 WAAPI ramp | FlaiBloom.vue 样式块 |
| 降级 reduced-motion=静态 | 继承现行媒体查询块，照 PR #64 互审 F2 先例补 `animation:none !important` + `transform:none !important` 双通道硬停 | reduced-* 截图 + batch_d ⑤ 断言强化 |

## 二、e2e 锚原子同批更新（owner 2026-08-07 裁）

- 抉择点：定稿词汇 idle/slow/fast 使 DOM 类 `is-generating` 退役，与票内「e2e 锚 additive 零触碰」字面冲突——定稿未覆盖，owner 交互裁=原子同批更新（map #46 红线「实现+测试+截图原子同批」允许）。
- `ui_lab_acceptance.py`：流式案选择器 `.flai-bloom.is-generating` → `.flai-bloom.is-fast`（标签/变量名同步，语义不变）。
- `batch_d_visual_acceptance.py` ⑤：编译 CSS reduced-motion 块断言由单档 is-generating 强化为 is-slow/is-fast 双档 `animation:none!important` 硬停覆盖（括号平衡提取逻辑不动）。

## 三、验证数字（隔离副本 /tmp/flai-os-65-verify，rsync 排除 .git/node_modules/dist）

- `verify_all.sh` EXIT=0 全绿（① build + ①a bundle + ② 全量 pytest + ①b node --test + 21 套 e2e）。
- pytest：1800 passed / 2 skipped（UV_OFFLINE=1，与基线一致）。
- node --test：286 passed。
- bundle：GuidePage 路由闭包 JS gzip 206,150 B / 225,280 B（增量 +93 B，余量 ~18.7 KiB）；入口同步 JS gzip 136,400 B；favicon.svg 1,754 B。
- e2e：21 套全绿（含本票更新的 ui_lab / batch_d）。

## 四、截图清单（docs/reviews/map46-65-turbine-shots/，断言见 manifest.json）

- 登录门：gate-wide（品牌氛围面静态花瓣）/ gate-narrow（窄屏卡内静态花瓣）。
- 侧栏 brand：hero-idle-sidebar-idle（静止档，hero 同帧恒静态）/ sidebar-slow + frame1/2（慢速，1s 间隔 45° 相位差）/ reduced-sidebar-slow（-f1/f2 字节一致）。
- ai-mark：aimark-pending-fast + frame1/2（待首包高速，真实栈）/ aimark-stream-fast-lab + frame1/2（流式中高速，ui-lab fixture——本 stub 栈内容 burst 落地、流式窗口亚秒级，fixture 钉死 streaming=true 定格，同一代码路径）/ aimark-idle-after-stream（信号消失回落静止）/ reduced-aimark-fast + reduced-stream-lab（两路 reduced 对照，帧对字节一致）。
- favicon：favicon-render.png（16/32/48/128 + 暗底目检，可读）。

## 五、红线自查

- 信任色锁五槽不增不改：动画零色彩变化；favicon 两阶 clay 取自原图，无新色。✓
- 诚实地板：静止档零残动（无类无动画）；信号消失回落（after_stream 断言全 none）；慢速/高速只绑真实在途信号。✓
- MOTION-SYSTEM 六条：仅 transform 旋转；reduced-motion 双通道硬停；零 rAF 新增（纯 CSS 合成层动画）；零第三方依赖；additive。✓
- 折叠保 DOM / #51 词表 / 双名制 /「二所」副标：未触碰。✓
- 工牌插画氛围位定性不动；favicon 换图不动 clay 语义。✓
- 零新依赖：package.json 未动。✓

## 六、互审处置（86gs 中转 codex exec，gpt-5.6，tokens 61,106；结论 request-changes 1 条）

- **F1（P1，信任/诚实）**：task feed 末位释放后 `feedTasks` 共享快照未清，`brandBloomState`
  在登出/身份失效后可能滞留 slow——违诚实地板（信号消失必须回落）。
  **处置=修**：`stores/taskFeed.js` releaseTaskFeed 末位释放清 `feedTasks/feedLoaded/feedError`
  三枚共享 ref（全部持有方此时已卸载/释放，无人再读；重新 acquire 经 watch immediate 重新水合）；
  并按评审要求补回落断言——`m11_auth_acceptance.py` 新增 ③b/④b 判别对（直插 queued 行做
  确定性信号源：信号在→brand 慢速；登出释放→回落静止）。tamper 实证：撤掉修复后 ④b 真红
  （`settled=False anim=flai-bloom-spin`），修复在时 7/7 全绿。
- 其余镜头（定稿符合性/降级/e2e/Vue 实现/资产/文档）评审均无 finding。

## 七、遗留与边界

- 审计栈 launcher 不起任务执行线程，开工任务停 queued——慢速演示信号=queued（定稿映射含 queued）；工作态（running 等）路径由同一谓词覆盖（TASK_WORK_STATES），e2e 已有同口径锚。
- 流式高速的 live 定格受 stub burst 限制走 fixture；真实模型内网复验（M4 线）同型挂账。
- 互审渠道与模型如实披露于 PR 正文（86gs 中转，照 PR #43/#50/#54/#59/#60/#64 先例）。

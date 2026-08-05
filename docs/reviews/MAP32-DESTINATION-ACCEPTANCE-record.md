# map #32 Destination 终点验收记录（成稿）

> 基线：main @ b732483 · 工作树 /tmp/flai-os-accept（detached，零 commit，仅 untracked 产物）
> 执行：2026-08-05，四波次（波 1 造段+A 组亮 1440 / 波 2a 暗+375+E7+C2 / 波 2b C3+E5+E6+E1-inbox+D2 退役态 / 波 3 B 组+C1+D2 补验+E1-peek 补验）
> 证据：`docs/reviews/map32-accept-shots/`（21 张）；驱动 `frontend/e2e/map32_destination_acceptance{,_wave2a,_wave3}.py` + /tmp/wave2b_*.py
> 波次 notes：/tmp/accept_notes_wave1.md / wave2a / wave2b / wave3

## 环境指纹

- **栈**：后端 `python /tmp/accept_launcher.py`（REPO 已改指工作树）pid 27526 @127.0.0.1:8620，
  `/api/health` agents=16、db_identity=acaec497d40b7dcd；前端 vite pid 28023 @127.0.0.1:5202（/api 代理 8620）。
- **worker**：波 3 起（uv 37415 / python 37419），`FLAI_DB_PATH=/tmp/flai-audit-stack/flai.db
  FLAI_LLM_TIMEOUT_S=5 bash scripts/dev_start_worker.sh`，单实例；log /tmp/worker_accept.log。
- **DB**：/tmp/flai-audit-stack/flai.db（波 1 清栈重建后全程持久）。
- **造段会话**：conv_c52ca8c5e4dc4a7bb9aaaf936a07e993（12 轮 3 段；轮 4 方案卡开工=边界 1，
  轮 7 guide 级 refuse=边界 2；stub 四模板轮换，链路真内容假）。
- **任务**：fta task_28b3d16fa5b451f8b4d74d47bed2ad4f（波 1 开工产物，波 3 被 worker 拾取→
  ModelConfigError 诚实失败）；fea_solve_agent 0-LLM 待签载体三枚（a5137…/d76d… 被驱动首二跑
  批准消耗，f7bd4f089cbb43faa6f25af35fe44ae6=终跑证据，现 completed）。
- **账户**：tester/Tester#2026（audit/Audit#2026 同库 seed，未用）。
- **驱动盘账**：波 1 15/15 · 波 2a 39/39 · 波 3 24/24+1 现状取证；波 2b 判定见下表（脚本在 /tmp）。

## 验收项总表

| # | 结论 | 证据（docs/reviews/map32-accept-shots/） |
|---|---|---|
| A1 三段结构+中段默认折 | PASS（波 1；暗/375 复判同绿） | seg_overview_light_1440.png |
| A2 折叠保 DOM 红线（6 泡 hidden 非 detached） | PASS（波 1） | 同上 |
| A3 段界锚（is-boundary 恒 1 vs 非段界恒 0） | PASS（波 1） | seg_boundary-anchor_light_1440.png |
| A4 豁免红线（首泡/最新 AI/当前段零折叠） | PASS（波 1） | — |
| A5 单向展开+切走切回复位 | PASS（波 1） | seg_unfolded_light_1440.png |
| A6 暗 1440 复判+暗色可辨人判 | PASS（波 2a 12/12） | seg_overview_dark_1440.png / seg_unfolded_dark_1440.png |
| A7 亮 375 复判+无横向溢出（scrollWidth=375） | PASS（波 2a） | seg_overview_light_375.png |
| A8 暗 375 同 A7 | PASS（波 2a） | seg_overview_dark_375.png |
| A9 扫读节奏人判（四图并读：有段/有界/有锚） | PASS（波 2a） | 上述四图并读 |
| B1 dock 待签 pill「✍ 待你签发 1」+ title 徽章「(1 待签) …」 | PASS（波 3） | status_dock-waiting_light_1440.png |
| B2 inbox 三组对账（待签·1+审阅 CTA；零工作态运行中组不渲染；落定组==API 真值） | PASS（波 3） | status_inbox_light_1440.png |
| B3 peek→批准放行（二次确认）→completed→pill 回落+徽章清零 | PASS（波 3） | status_peek_light_1440.png |
| B4 completed 恒中性（灯 rgb 实取 rgb(107,98,89) 暖灰，非 greenish） | PASS（波 3） | status_settled-neutral_light_1440.png |
| B5 worker 拾 fta→无 LLM 诚实失败（ModelConfigError）→落定红行 rgb(190,58,58) | PASS（波 3，预期产物如实记） | status_failed-row_light_1440.png |
| B6 dock 多点采样 retro④（/、/today、/tasks、/me 计数恒 1、徽章一致） | PASS（波 3，E4 闭合） | status_dock_sampling.png |
| C1 今日页/任务台同分组同计数同称呼（taskGroups+taskDisplayName SSOT） | PASS（波 3） | ia_today_light_1440.png / ia_tasks-rail_light_1440.png |
| C2 零待签窗口：首行摘要不渲染、组头无「· 0」 | PASS（波 2a） | ia_today-zero_light_1440.png |
| C3 一级导航仅 对话/今日；任务台行/今日卡深链达 /tasks/:id | PASS ×3（波 2b） | c3_task-deeplink_light_1440.png |
| D1 IntentGlyph/empty-log 源码面不存在 | PASS（波 2b 引用源码面） | —（源码面） |
| D2 密级 pill 收 title | PASS（波 3 fresh 窗口闭合：title 承载+零 pill 残留；波 2b 已核源码面） | retire_pill-title_light_1440.png |

## retro 八项逐条结论

- **E1 Esc 焦点**：**口径修正坐实**。inbox 态任意焦点 Esc 均收（el-plus document 级监听，
  close-on-press-escape=true）——retro「焦点在外不生效」不成立。peek 态：焦点在壳内 Esc
  退层回收件箱 PASS；**焦点在壳外 Esc 不收不退层=断档成立**（波 3 实测）——真问题候选
  在此（a11y 小批：peek 态补 document 级退层或焦点护栏）。drawer 关后 DOM 隐藏
  （hidden 非 detached）PASS；.sc-shell destroy-on-close 为防选择器重影的有意设计。
- **E2 首段过长仍豁免**：现状记录，观察项仍开（本验收未造 >10 轮首段）。
- **E3 展开后滚段首未实现**（toggleSegment 无滚动）：观察项仍开。
- **E4（=B6）**：本次闭合 PASS。
- **E5 scrollBehavior**：a 回顶 PASS；b 后退还原有效但**恒差 14px**（确定性复现，
  还原 scrollTo 落在首帧高度未长成的中间帧被 clamp，疑似 webfont 后至/布局沉降；
  常规视口无从触发，低 severity，观察项）；c /tasks 窗口级不可滚（自含三栏，
  滚动在左栏 .console-list），同 pageKey 不整页重挂由深链截图佐证。
- **E6 roving 让位**：PASS ×2（打字中不抢焦；打字中点导航焦点落 main.app-main，
  router/index.js:58 设计如此）。
- **E7 窄屏 dock**：PASS（375 探针量得 pill display:none；只余核心钮，不遮汉堡/标题区）。
  图 e7_dock_light_375.png。
- **E8 E3 门禁未实施**：out of scope，记录。

## 观察项汇总（交 owner 裁）

1. **E1-peek 焦点断档**（波 3 坐实）：retro 候选 a11y 小批的真实载体=peek 态。
2. **E5b 后退还原恒差 14px**（低 severity）：机制有效、精确性受首帧沉降影响。
3. **E2/E3** 现状仍开（首段豁免边界 / 展开滚段首未实现）。
4. **peek 产物预览 404=测试栈 env 不配平，非产品 bug**（波 3 新核因）：worker 只拿
   FLAI_DB_PATH，产物落仓默认 data/task_runs；launcher backend task_runs_dir=
   /tmp/flai-audit-stack/task_runs；下载门对 output 做路径根 fail-closed 校验
   （files.py:290-306），相对化失败→泛化 404。产物文件与 files 行俱在
   （owner_username=NULL 系 runtime 产物有意形态）。peek 如实显示「产物加载失败」
   不静默，诚实面合格；后续要验产物预览须让 worker 与 backend 同 task_runs 根
   （config.py 无 env 覆盖点）。
5. 今日页「进行中」含 created/queued（taskGroups.js）而 dock/状态中心工作态不含
   （format.js TASK_WORK_STATES）——两套既定口径，波 1/2b 已记，非回归。
6. D2 取证代理说明：抽样 fta_agent 未声明密级，title 无「密级」段（agentTaxonomyTip
   「缺项不占位不编造」SSOT）；结构面（title 承载+pill 零残留+敏感行 tabindex/aria
   机制）闭合，敏感行本样本未触发。

## 坑位留痕（本验收新增；波 1/2 坑见各 notes）

- **B3 批准一次性消耗**：驱动重跑前必须新建 fea 待签任务并改 FEA_TASK_ID（本波三跑两消耗）。
- **roster 成员行收在 details.route-disclosure 内默认折叠**——D2 hover 前必须点 summary
  展开，否则行在 DOM 不可见、hover 超时（波 3 首跑崩因）。
- 落定组/待签组行数断言必须 API 真值驱动（落定数随波次增长）；同名多行用组作用域
  定位+.first 避 playwright 严格模式冲突。
- worker 与 launcher backend 的 task_runs 根不配平→产物下载 404（观察项 4）。
- UV_OFFLINE 缓存无 pillow——拼图走 canvas；label 宽度须 measureText 否则截字。
- 波 1 旧坑仍有效：登录只收 JSON / send-btn 流式等待 / 开工按名字点 / launcher REPO
  硬编码 / 造段后重进会话再截图 / 375 侧栏走汉堡抽屉。

## 终态

- 8620 后端 / 5202 前端保持运行（波次间约定）；worker 波 3 验收完成后可停
  （queued 任务已清空：fta 已 failed、fea 三枚均 completed，无滞留执行任务）。
- 主 checkout 与产品树 flai-os-product-complete-v1 全程未碰；零 git 操作。

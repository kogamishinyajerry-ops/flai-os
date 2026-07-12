# SimMonitorFloat 仿真监控浮窗 · 交付与验证记录

日期：2026-07-11 ｜ 批次性质：实验性 UI 插件（默认关，零渲染）｜ owner 直接指令：
「监控不单开页面，以浮窗形式悬浮在会话区域——把它变成嵌入 FLAi-OS 的监控插件」。

## 1. 交付物

- `frontend/src/components/SimMonitorFloat.vue`（新增）：会话区右下浮窗
  = 收起态 pill ↔ 展开卡（iframe 装载 sim-live-hub `/embed.html`）。
- `frontend/src/App.vue`：根级挂载一行（`.page-turn` transform 劫持 fixed
  定位基准的动效判例，故必须根级）。
- 监控 UI 的 SSOT 留在 sim-live-hub 仓（零逻辑复制）；该仓侧交付
  `web/embed.html` + 接缝契约测试 + 实机探针（commit d782a66）。

## 2. 边界与纪律对照

- **默认关**：未配置 `?simhub=`（持久化 localStorage `flai.simMonitorHub`，
  `?simhub=off` 清除）时组件零渲染——e2e、生产构建、内网部署零影响。
- **postMessage 边界（未受信输入纪律）**：`event.origin` 必须逐字等于配置的
  hub origin，类型必须 `sim-live-status`，负载只读展示绝不执行；hub 侧
  targetOrigin 严格用宿主传入 origin，绝不 `"*"`（两侧各有测试咬合）。
- **信任色锁**：运行=clay（工作槽）/ 停滞失败=--trust-fail / 完成·空闲·
  未连接=中性灰——completed 不给绿的纪律沿用；未新增任何彩色信号。
- **诚实地板**：消息断流 >6s → pill 显式「未连接」，绝不让旧状态装活；
  嵌入视图保留停滞红横幅/provenance/回放徽标（嵌入 ≠ 缩水披露）。
- **z-index 140**：低于状态坞(150)与 ⌘K(200)——监控是背景信息，不抢签发。

## 3. 验证

- `scripts/verify_all.sh` 八步全绿（build + 全量 pytest + 6 套 e2e，浮窗默认
  关不进任何断言路径）。
- 实机探针 **8/8 ALL GREEN**（sim-live-hub `tests/probe_flai_embed.py`，
  against 本仓 :8620 真后端 + hub :8791）：①pill 渲染 ②postMessage 活流
  ③**伪造消息 tamper**（宿主页面自 post 假 running，origin=8620≠hub → 丢弃）
  ④真实 CLI run → pill 运行态 ⑤iframe src 契约 ⑥**真 SIGKILL tamper** →
  停滞红穿透收起态 pill ⑦嵌入视图红横幅。证据截图存 hub 仓
  `docs/embed-probe-*.png`。
- 探针过程中抓到并修复的真 bug：embed 首版对契约 stages/curves（对象数组）
  按 pair 解构 → render 抛错连带饿死宿主 pill；修复 = 心跳先于渲染 + 正确
  取形（hub 仓 d782a66，含回归说明）。

## 3.5 v2 追加：双页签「仿真｜工作台」（2026-07-11 同日，owner「像监控虚拟
工作台一样追踪 agent 正在看的页面/操作/中间结果/思考冒泡」）

- 新页签装载 hub `embed-workbench.html`：思考冒泡（真实 transcript thinking/
  text，标注叙事层）+ 正在看的页面 + 正在执行的操作（tool_use 无配对结果=
  进行时，证据层）+ 中间结果。hub 侧=转录 tailer surface（该仓 f382237，
  spec §10）。
- 双 iframe 常驻（切页签只切可见性）：报警跨页签穿透——任一 surface 停滞/
  失败，收起态 pill 即红且非活跃页签亮红点；负载 `surface` 字段分流，
  origin 闸不变。
- 实机探针扩到 **11/11 ALL GREEN**（新增：工作台页签显示真实会话身份/思考
  冒泡非空/pill 反映工具执行中；⑥ 断言锁定报警主体防蹭过）。verify_all
  九步全绿（含并行批新增的 m10 治理 e2e）。
- 探针逮到并修复的真设计错误：工作台停滞阈值 45s 把「Claude Code 会话里
  合法飞数分钟的长工具」误判为停滞（探针自身的 Bash 就中招）→ 默认 300s
  + 横幅如实披露歧义（「超长任务也可能仍在正常执行」）。

## 4. 残余与递延

- Codex 异源审：入 post-merge 补审队列（与 2a/2b/2c 批同队；纯前端、默认关、
  探针已双 tamper 咬合）。
- 浮窗与 GuidePage 悬浮 composer 在 <900px 窄屏可能重叠（实验期不处理，
  转正时随窄屏适配一并做）。
- V1 只做「单聚焦模块」披露；多模块并行时的切换器、与平台任务系统的联动
  （任务详情页挂对应仿真监控）递延到转正批。
- 嵌入视图为 hub 暖纸浅色，暗色主题下浮窗内容不随主题切换（iframe 内容
  归 hub 管；转正时可经 URL 参数传主题）。


## 5. Next-1 探针批：TaskDetail「查看仿真监控 ↗」深链（2026-07-12）

- **范围（并发避撞裁决）**：开工时发现另一 lane 正在飞 B1 鉴权（db.py/main.py/
  api/*/client.js 大面积未提交 WIP，迁移宿主 db.py 正在其手上）——探针降级为
  **零后端方案**：TaskDetail 头部动作区加深链按钮（读浮窗同款 localStorage
  `flai.simMonitorHub`，未配置零渲染），链到 hub 首页；**per-task run_ref 数据库列
  推迟到该 lane 落地后另批**（hub 侧 `#/mod@runid` 深链+run 对账提示已先行就位）。
- **归属核查**：TaskDetail.vue diff 仅含本批三个 hunk（按钮/常量/样式），与鉴权
  lane 零交叠；staging 只点名本文件。
- **验证（如实分级）**：npm build 绿 ✓；DOM 级实拍 PASS（.sim-link 可见，
  href=配置 hub origin；截图时鉴权 lane 的登录遮罩为其未提交 WIP，评估用途下
  隐藏并如实注明）✓；**m8 e2e 未跑通=△**——401 阻断，归因钉死为并行 lane
  未提交的 backend/app/auth/middleware.py（字符串亲验），非本改动路径；本改动
  在 e2e 上下文（localStorage 未配置）零 DOM 变化。**挂账：鉴权 lane 落地后
  补跑 verify_all 全量。**
- **挂账已清（2026-07-12）**：M11 鉴权 lane 落地（995cdd0）后 `scripts/verify_all.sh`
  **全量复跑全绿**——build + 全量 pytest + 8 套 e2e（含 m11_auth 5/5），`[失败]（无）`。
  浮窗默认关，确认零侵入真鉴权 e2e 路径。原 △ 升为 ✓：浮窗批与 TaskDetail 深链
  在真鉴权下不破坏任何 e2e 断言。
- **探针改真登录（2026-07-12，hub d4a00c0）**：兑现「鉴权落地探针改真登录」承诺——
  hub 侧 `tests/probe_flai_embed.py` 去掉 WelcomeGate 的 CSS 压制豁免，改为自起
  临时库 flai 后端（create_app+JobRunner，绝不碰真实 data/）+ seed_user +
  login_context 走真实 `POST /api/auth/login` 换会话 cookie（与本仓 e2e `_auth`
  同口径）。11/11 ALL GREEN 真登录下复跑。副产实证：flai 自起随机端口须注入
  hub embed_ancestors，否则 frame-ancestors CSP 正确挡掉嵌入页装载（先跌 3/11
  暴露的正是 CSP 在干活，非回归）。

## 6. 转正批：run_ref 落库 + 深链 + StatusDock 入口（2026-07-12，c293a83）

- **R1 前置最后一段完成**（M11 鉴权落地后）：per-task 仿真 run 关联，**复用
  tasks.metadata 袋（不加列不迁移，比新列更外科）**——`repos.set_task_sim_run_ref`
  写 `metadata.sim_run_ref`（BEGIN IMMEDIATE 防并发吞键）+ `POST /api/tasks/{id}/
  sim-run-ref`（module/run_id 安全字符白名单钳死防 hash 注入；设关联=metadata
  标注非状态迁移，不扩冻结事件枚举；404 诚实）。
- **前端消费**：TaskDetail 深链有 run_ref 则 `#/<mod>@<run_id>` 直达该 run，否则
  回退 hub 首页；StatusDock 加中性色监控发现入口（simhub 配置才现，不占信任色锁，
  `@click.stop` 不误触状态中心，默认关零渲染保 e2e）。
- **验证**：后端 4 测试 + `verify_all` 全绿（8 套 e2e，StatusDock 默认关零侵入）+
  hub 探针扩至 **14/14**（新增 ⑩a run_ref 落库/⑩b 深链 href/⑪ StatusDock 入口，
  激活路径唯一能诚实测处）。Codex 治理审 c293a83（新 operator endpoint 命中即审）。
- **并发纪律实录**：施工时 ADR-0021 数据分级 lane 同树在飞（改 repos.py 的
  create_file/record_sample 加必填 classification，其半应用态外溢为探针 backend 的
  `record_sample missing classification`——非本批引入）。本批唯一与其交叠 repos.py，
  按 hunk 精确 stage（`git apply --cached` 仅本函数），`git diff --cached` 亲验零
  classification 污染，对方 8 行分级 hunk 完好留树。

### 6.1 Codex 治理审 c293a83 收口（2026-07-12，fix commit b4f1e0d push）

**结论=零 P1 + 四 P2**（新 operator endpoint 命中即审，全部 grounded 复核确认为真，
无 over-claim）：

- **P2-1**（repos.py）：setter bump `updated_at` 会让「metadata 标注」误触终态未读
  信号（taskHasUnseen/hasUnseen 依 updated_at 判新鲜度），与我「非状态迁移」设计
  意图自相矛盾（同理由我本就没 append_event）。**修**=UPDATE 去掉 updated_at，只写
  metadata_json；加回归测试 `test_set_sim_run_ref_does_not_bump_updated_at`（_now_iso
  带微秒，bump 必改字符串故真咬）。
- **P2-2**（StatusDock.vue）：IIFE 只在挂载读一次 localStorage，`?simhub=` 挂载后
  确认启用不刷新不显示。**修**=改响应式 ref + 监听 `flai:simhub-changed`（同标签页
  自定义事件，storage 事件不自触发）+ `storage`（跨标签页）；SimMonitorFloat 确认
  新源后派发该事件。
- **P2-3**（StatusDock.vue）：anchor 的 keydown 冒泡到 `.status-dock`，Enter 同时开
  状态中心+跳链（`@click.stop` 不拦 keydown）。**修**=anchor 加
  `@keydown.enter.stop @keydown.space.stop`（stop 不 preventDefault，Enter 原生跳链
  照常，仅止住冒泡）。
- **P2-4**（TaskDetail.vue）：run_ref 全量渲染进不换行 header，module(64)+run_id(128)
  极限外溢挤走控件。**修**=拆前缀/ref/箭头，只对 ref 段 CSS 截断（max-width 22ch +
  ellipsis），全值进 title。

**验证**：后端 5 测试（含新回归）绿 · 前端 build 干净 · 探针 **14/14 ALL GREEN**
（真登录自起后端，⑩a/⑩b/⑪ 全过）。round cap R0（治理审仅一轮即零 P1）。repos.py
仍按 hunk 精确 stage（只落 P2-1，ADR-0021 分级 hunk 不动）。

## 6. 转正门槛清单批：暗色透传 + 窄屏适配（2026-07-12）

- §4 递延两项落地（本仓侧仅 SimMonitorFloat.vue 单文件）：
  ① **暗色透传**：`resolvedTheme` 为响应式依赖，暗色时 frameSrc 追加
  `&theme=dark`——hub 嵌入视图（该仓 2108a77 新增暗色变量）随平台换肤，
  切主题即 iframe 重载（嵌入页无长驻状态，1s 轮询重建，代价可接受）；
  ② **窄屏**：<900px 浮窗抬高至 bottom:96px 避开 GuidePage 悬浮 composer，
  卡宽 `min(400px, 100vw-24px)` 不溢出。
- 同批 hub 侧新增**多模块切换器**（embed.html，自动+各模块 pill）与
  provenance 点击复制——SSOT 仍全在 hub，本仓零逻辑复制。
- **验证**：npm build 绿 ✓；暗色实拍 PASS（卡片暗底+4 切换 pill+
  theme=dark 入 iframe src，截图 dark_switcher.png）✓；hub 实机探针
  **11/11 ALL GREEN** 复跑 ✓（探针对并行 lane 登录门做 CSS 压制豁免并
  注明，鉴权落地后改走真登录）；m8 e2e 挂账同 §5 不变。
- 转正门槛剩余：StatusDock 发现入口（等鉴权 lane 落地后同批）+ Codex 补审。

## 7. Codex 补审 R1：浮窗接收侧安全硬化（2026-07-12）

- **补审已执行**（86gs gpt-5.6-sol ultra，定向审浮窗/深链三处现状；两仓同批，
  hub 侧对应其 d535ddb）：本仓 CHANGES_REQUIRED → grounded 复核逐条落地：
  ① **scheme 白名单**：localStorage 配置值只认 http(s)（javascript:/data: 的
  origin 序列化为 "null"，若放行则任意 opaque-origin 文档可冒充 hub 发消息）；
  TaskDetail 深链同判据；② **?simhub= 确认闸**：新地址必须 ElMessageBox 显式
  确认才持久化——恶意链接不能静默把浮窗指向攻击者站点；pill/完整面板 title
  常显监控源 origin；③ **iframe sandbox**（allow-scripts allow-same-origin，
  顶层导航/弹窗/表单/下载不给）；④ **来源绑定**：postMessage 必须来自自家两
  iframe 的 contentWindow，surface 由来源窗口判定、负载自报不作数；⑤ **status
  枚举 fail-closed**（未知/非字符串状态不刷新心跳不入槽）；⑥ **断流披露补全**：
  单路断流→页签灰化+pill「另路断流」后缀，曾报警一路失联→pill 红「失联
  （曾报警）」，双路断流展开态红字「双路断流」，首连 15s 无响应如实显示；
  ⑦ label 类型钳制防非字符串负载炸 render。
- **验证**：npm build 绿；hub 实机探针 11/11 复跑（探针替用户点「启用」确认闸
  =兼验证闸存在；探针改为自起 pin 锁定本会话的 hub 副本——并发会话曾把
  auto-follow 焦点切走致 ⑨ 前提被击穿，N1 风险的实机复现）。
- **残余披露**：iframe sandbox 的 allow-same-origin+allow-scripts 组合对跨源
  hub 是标准配置（hub 需自身 fetch）；若用户把 simhub 配成与 FLAi-OS 同源的
  地址则 sandbox 失去隔离意义——内网部署手册须写明 hub 独立端口部署。
- **R2 复审（fix commit 5ca0c2f 复审 → 233f79b，零 P1）**：五 P2 verbatim
  落地——报警记忆跨 unreachable 保留（报警路断流后只发得出 unreachable，
  「曾报警」不被负载替换吞掉）· 换源清态+宽限期重起 · 从未发首拍的单路超
  15s=stale 披露 · 兜底空闲态补断流后缀 · 负载 surface 以来源窗口覆写。
  round cap（R0+2 fix）用满收口，build 绿+探针 11/11 两轮各复跑。

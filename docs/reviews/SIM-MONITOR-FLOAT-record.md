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

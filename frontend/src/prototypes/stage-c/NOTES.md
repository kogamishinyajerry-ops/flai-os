# Stage C 工作台原型 — 设计与审计笔记（work_item: flai-stage-c-kimi-uiux-001@1）

环境：EXTERNAL_DEVELOPMENT · fixtures：SYNTHETIC_ONLY · 内网数据/运行时依赖：NONE。
本原型不证明任何真实执行、内网导入或部署；签发按钮仅为原型演示，不落库。

## 0. 基线现状

冻结基线 `9220cc3e` 中 Stage C 只有只读观察合同（`observer-contract.js`）与运行时
适配器（`runtime-observer-adapter.js`）及其测试；没有任何 Stage C UI。因此本轮为
新建白名单内的原型文件，"before" 视觉证据 = 基线无 Stage C 页面（git 可证）。

## 1. 只读审计：高影响问题（P0 > P1 > P2）

- P0-1 基线无 UI：合同/适配器产出的快照没有任何可视化载体，真实性设计（fail-closed、
  停动画、五槽信任色）无从落地。→ 本轮新建原型承接。
- P0-2 completed 误绿风险：`preview/render` 终态极易被设计成"成功绿"。→ 信任槽
  `terminal` 中性色，绿只给 REAL 见证徽标，teal 只给真人签发动作。
- P0-3 假进度风险：任何定时器/随机数/自报文案都会制造假进展。→ 动画唯一开关是
  投影器输出的 `snapshot.motion`；步骤只显示合同 stepLabel，禁止百分比（有测试）。
- P1-4 unknown/stale/evidence-missing 必须诚实：投影器在这些分支返回的精简快照
  不带 evidenceRefs，UI 直接渲染会崩。→ 组件防御式读取 + 缺口卡显示原因码。
- P1-5 stale 必须停动画但保留最后可信对象：合同已保证，UI 用 `data-motion` 贯通到
  CSS，e2e 断言 motion=false。
- P1-6 右栏若做成固定"依据列表"会喧宾夺主。→ 右栏改为实时对象舞台（见 §4）。
- P2-7 大号标题/长段落/每句一框的认知噪声。→ 单 hero 卡 + 渐进披露（details）。
- P2-8 英文化 Dashboard 文案不适合目标用户。→ 全中文、办公术语。
- P2-9 键盘可达性：提交、签发、切换均可键盘完成，`:focus-visible` 明确。
- P2-10 1280px 溢出风险：右栏固定 340px + 主列 minmax(0,1fr)，e2e 双宽度断言。

## 2. 信息流（Composer → 执行 → 右侧对象 → 例外 → Delivery）

```
首页（低门槛 Composer + 3 个高价值入口）
  └─ 提交目标 ─▶ 连续执行工作台（无 A/B/C 方案选择）
       主列：hero（glyph + overline + 标题 + 详情 + 步段）
             → 缺口卡（例外聚合，failed/denied/unknown/stale，不弹窗）
             → 交付检查（产物/证据/残余风险/真人签发，仅 attention|preview）
             → Composer（追加指令，常驻）
       右栏：当前对象卡（preview.kind/title/caption/primary/secondary）
             → "为什么现在显示它"（由 snapshot.mode 推导）
             → 证据与来源（折叠）
             → 低优先级元数据（折叠）
```

## 3. Motion / Glyph token 表

动效唯一驱动：`.stage-c[data-motion="true"]`（= `snapshot.motion === true` 且未签发）。
`prefers-reduced-motion: reduce` 全部停动画。terminal/unknown/stale 由合同保证
motion=false，glyph 无动画规则。

| glyph | 触发 action/mode | 含义 | 动效（仅 motion=true） |
|---|---|---|---|
| guard | `guard`（validating） | 核验 | 盾形呼吸脉冲 1.6s |
| inspect | `inspect`（working） | 检查 | 扫描线往返 1.4s |
| rewrite | `rewrite`（working） | 生成可逆稿 | 虚线行进 1.4s |
| map | `map`（working） | 整理关系 | 连线虚线行进 1.8s |
| render | `render`（preview） | 渲染预览 | 静止（终态 motion=false） |
| wait | `hold`（attention） | 等待真人 | 静止（等待不抢注意力） |
| failed | `stop`+failed / `deny` | 失败停止 | 静止（红） |
| cancelled | `stop`+stopped | 已停止 | 静止 |
| unknown | `signal` / 其他 | 状态未知 | 静止（amber） |

信任色五槽（互不借用，颜色均配文字，非唯一信号）：

| slot | 色 | 只用于 |
|---|---|---|
| work | clay #b4562f | 正在工作（hero 左边条、步段、glyph） |
| real | 绿 #1e7d46 | REAL 执行见证徽标 |
| sign | teal #0e7c7b | 真人签发动作及徽标 |
| fail | 红 #b3352c | 真实失败/权限拒绝/停止 |
| unverified | amber #9a6b12 | UNKNOWN/MOCK/stale 未核 |
| terminal | 中性灰 | completed 终态（绝不给绿） |

## 4. 右侧实时对象舞台优先级规则

1. 当前正在处理/生成的具体对象（preview 卡，永远第一位）；
2. 可实时预览的对象元数据（caption/primary/secondary，只读措辞）；
3. 最需检查的待确认项（attention 时 why-now 置顶解释）；
4. 当前步骤证据与来源（折叠 details，含 reality-witness 引用）；
5. 历史依据与低优先级元数据（折叠 details）。
无验证对象时显示缺口卡（原因码 + 诚实文案），禁止漂亮占位。

## 5. 验证记录（真实命令与结果）

| 命令 | 结果 |
|---|---|
| `cd frontend && node --test` | 98 pass / 0 fail（含新增 fixtures.test.js 8 条） |
| `cd frontend && npm run build` | 成功（chunk>500kB 警告为主应用既有产物，与本原型无关） |
| `uv run --no-project --with playwright python frontend/e2e/stage_c_prototype_acceptance.py` | 29/29 PASS |
| e2e 截图 | `/private/tmp/stage-c-evidence/*.png`（9 张，1440px） |

e2e 覆盖：docx/meeting/cfd × running、guard glyph、waiting_review/completed/failed/
cancelled/evidence-missing/permission-denied/unknown/stale 停动画、completed 不绿、
缺口原因码、1440/1280 无横向溢出、reduced-motion 停动画、Ctrl+Enter 键盘提交、
真人签发 teal 徽标。

已知限制：e2e 未接入 `scripts/verify_all.sh`（该脚本不在写范围内，需 Codex/架构层
决定是否挂载）；截图仅作视觉证据，不替代测试。

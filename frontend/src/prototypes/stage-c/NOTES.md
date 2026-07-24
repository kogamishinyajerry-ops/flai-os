# Stage C 工作台原型 — 设计与审计笔记（work_item: flai-stage-c-kimi-uiux-001@3）

环境：EXTERNAL_DEVELOPMENT · fixtures：SYNTHETIC_ONLY · 内网数据/运行时依赖：NONE。
本原型不证明任何真实执行、内网导入或部署；原型内不存在任何签发路径（本地点击
不构成、也不模拟签发）。

## -1. v3 返工范围（rework_of: @2, base 6951c7a）

owner 会话指令 @3（小返工）：增加可达的 synthetic reality 展示入口及四形态 DOM
测试，修复三个 P2，重新提供完整 DevelopmentHandoffV1。逐条对应：

| 指令项 | 处置 |
|---|---|
| 可达的 synthetic reality 展示入口 | ① `vite.config.js` 增加多页 input，`npm run build` 现产出 `dist/stage-c.html`，dev / `vite preview` / dist 静态托管均可达 `/stage-c.html`（preview 实测 HTTP 200，见验证记录）。**scope 说明**：v2 冻结令 Vite 配置只读、入口留 Codex 集成门；本项为 owner @3 明确指令授权的 scope 扩边，handoff 中请求 owner 重新冻结确认。主应用内导航链接仍属 Codex 集成面，未改。② 顶栏新增「合成形态」picker（REAL/MOCK/TEST/UNKNOWN）+ `?reality=` URL 参数，四形态逐一直达；REAL/MOCK/TEST 经 `@reality` 显式覆盖，UNKNOWN 不是可观察形态（observer 合同只接受 REAL/MOCK/TEST），选择后强制落到 fail-closed 观察缺口并禁用状态选择器 + 诚实提示，非法 URL 形态参数 fail-closed 回 REAL。 |
| 四形态 DOM 测试 | e2e 新增 ⑪ 四形态 DOM 矩阵：3 场景 × REAL/MOCK/TEST 逐组合断言徽标文案 / `data-reality-form` / `data-source-kind` / `data-slot` / 无 real 槽负例；终态形态保持 3 条；UNKNOWN 强制缺口 3 条 + 选择器禁用提示 1 条；picker 即时切换 1 条；非法参数回退 1 条。徽标 `data-reality` 属性更名为 `data-reality-form` 并补 `data-source-kind="synthetic-fixture"`，机器消费者不会把形态字段误读为真实见证语义。 |
| 三个 P2 | P2-1：stale 快照保留最后观察 reality 字段，缺口状态仍展示「REAL 形态测试」徽标 → mode=unknown 一律压到 UNKNOWN 未核徽标（fail-closed 优先于形态字段），e2e ⑫ 3 场景 × 3 缺口态 @REAL 覆盖共 9 条负例。P2-2：permission-denied 隐式默认 MOCK、其余观察态默认 REAL，同源夹具默认形态不一致且无记录理由 → 统一默认 REAL，fixtures.test 新增「无隐式 MOCK 特例」+ e2e ⑬ 3 条。P2-3：failed/stopped 例外卡显示「原因码：observed」病句（原因码只属于观察 fail-closed）→ 拆为观察缺口卡（含原因码，仅 unknown 族）与执行例外卡（无原因码行，failed/stopped），e2e ⑭ 3 条。**诚实声明**：Codex v2 评审的三个 P2 原文未找到持久化记录（GitHub/docs/reviews/评审包均无），以上三条为按 @2 代码 grounded 自审确定的 P2；若与 owner 所指清单不符，按单立即返工。 |

## -1.1 验证记录（真实命令与结果，v3）

前置：`pwd`=`/private/tmp/flai-os-kimi-workspace-experience`，branch=
`codex/kimi-workspace-experience-v1`，HEAD=base_sha `6951c7a4`，`git status` 干净。

| 命令 | 结果 |
|---|---|
| `git diff --check` | 通过（无空白错误） |
| scope 检查 `git diff --name-only` | 白名单 8 文件中的 6 个 + owner @3 授权扩边的 `frontend/vite.config.js`（共 7 文件） |
| `cd frontend && node --test` | 102 pass / 0 fail（v2 为 101，+1：fixtures 默认形态无隐式 MOCK 特例） |
| `cd frontend && npm run build` | 成功；**新产出 `dist/stage-c.html`**（chunk>500kB 警告为主应用既有产物） |
| `npx vite preview` + `curl -o /dev/null -w %{http_code} /stage-c.html` | HTTP 200（dist 静态托管可达实测） |
| `uv run --no-project --with playwright python frontend/e2e/stage_c_prototype_acceptance.py` | 106/106 PASS（v2 为 73，+33：四形态 DOM 矩阵与三个 P2 断言） |
| e2e 截图 | `/private/tmp/stage-c-evidence-v3/*.png`（8 张，1440px） |

e2e 实际矩阵：v2 的 73 条（3 场景 × 9 要求状态 × 2 组断言 = 54 + 首页负例 /
validating / 3 缺口原因码 / 签发负例 3 / 三栏 2 / 双宽度 2 / reduced-motion /
键盘 / IME 4 / focus-visible）全部保留并通过；新增 33 条 = ⑪ 四形态 DOM 18
（3场景×3形态 running 9 + 终态形态保持 3 + UNKNOWN 强制缺口 3 + 禁用提示 1 +
picker 切换 1 + 非法参数回退 1）+ ⑫ fail-closed 压 UNKNOWN 9（3场景×3缺口态）
+ ⑬ permission-denied 默认形态 3 + ⑭ 例外卡 3，合计 33；总计 106，全部 PASS。
未挂载 `scripts/verify_all.sh`（不在写范围）。

## 0. v2 返工范围（rework_of: @1, base 547cb42）

v1 技术复核意见 NEEDS_REWORK_NON_AUTHORITATIVE 的阻断项与体验项逐条对应：

| 复核项 | 处置 |
|---|---|
| 合成夹具占用 REAL 可信绿 | 绿槽 REAL 只认 `source === "control-kernel"`；合成快照一律中性徽标“合成样例 · {REAL/MOCK/TEST} 形态测试 · 非真实见证”（UNKNOWN 形态走 amber“未核，非真实见证”）；首页未提交时不渲染任何执行类徽标。e2e 27 组合逐条负例：无 `data-slot=real`、无“有执行见证”。 |
| 本地点击冒充具名真人签发 | 删除 `signed=true` → teal 路径（组件、样式、徽标全部移除）。交付区只剩 amber“未签发：等待认证签发链”+ 中性“查看签发要求”（认证主体/时间/精确版本/有效 receipt 四条件）。v1 的假签发 e2e 已改为负例：点击后无 sign 槽、无“真人已签发/签发成功”、hero 信任槽不变。 |
| 信任色唯一语义 | `stopped/cancelled` 归 terminal 中性墨色（hero 边条、glyph、缺口卡、右栏卡），不进红 fail；红只给真失败与权限拒绝（两者文案各自区分）；签发 CTA 不预支 teal。 |
| 中文输入法误提交 | 两个 Composer 统一 `onComposerKeydown`：`event.isComposing` 时直接返回。e2e 用 CompositionEvent + `isComposing:true` 的 KeyboardEvent 断言 composition 中不提交、结束后可提交（首页与工作台各一组）。 |
| 右栏随状态切换当前对象 | `railObject` 按 `snapshot.mode` 切换：working/scanning=正在处理对象；attention=待检查清单（产物引用/证据数/合同版本/对象说明）；preview=已冻结产物；failed=最后可信对象+影响+恢复入口；stopped=最后可信对象+中性终止说明；unknown/evidence-missing/stale=缺口对象（不复用产物卡）。全部字段来自投影快照，不编造生产事实。 |
| 三栏 Workspace 范式 | workbench 改为 200px 左上下文轨（当前项目/最近工作/获准知识上下文，低噪声、无治理对象、无大标题卡片墙）+ 中央连续执行叙事 + 320px 右对象舞台；≤1100px 退化为单列。 |
| 验证陈述与真实矩阵一致 | fixture 新增 `${scene}:${state}@{REAL\|MOCK\|TEST}` 形态维度（`REQUIRED_STATES` 导出九态）；e2e 实际遍历 3 场景 × 9 要求状态逐组合断言 glyph/motion/trust/rail + 合成负例，另含 validating、焦点环、双宽度溢出、reduced-motion、IME。断言数按实际执行如实汇报（73 条）。 |

## 1. 信任色五槽（v2 锁定语义）

| slot | 色 | 只用于 |
|---|---|---|
| work | clay #b4562f | 正在工作（hero 左边条、步段、glyph） |
| real | 绿 #1e7d46 | 仅 `control-kernel` 来源 REAL 见证徽标（合成原型不可达） |
| sign | teal #0e7c7b | 仅真实认证签发链（本原型无任何路径，token 保留但禁止引用） |
| fail | 红 #b3352c | 真实失败 / 权限拒绝（取消不进此槽） |
| unverified | amber #9a6b12 | UNKNOWN/MOCK/未核、未签发、缺口 |
| terminal | 中性墨色 | completed 终态、cancelled/stopped 中性终止 |

## 2. 验证记录（真实命令与结果，v2）

前置：`pwd`=`/private/tmp/flai-os-kimi-workspace-experience`，branch=
`codex/kimi-workspace-experience-v1`，HEAD=base_sha `547cb42a`，`git status` 干净。

| 命令 | 结果 |
|---|---|
| `git diff --check` | 通过（无空白错误） |
| scope 检查 `git diff --name-only` | 仅白名单 8 文件（见下方提交） |
| `cd frontend && node --test` | 101 pass / 0 fail（含 fixtures.test.js 11 条） |
| `cd frontend && npm run build` | 成功；**不产出 `dist/stage-c.html`**（chunk>500kB 警告为主应用既有产物）→ Codex 集成门 |
| `uv run --no-project --with playwright python frontend/e2e/stage_c_prototype_acceptance.py` | 73/73 PASS |
| e2e 截图 | `/private/tmp/stage-c-evidence-v2/*.png`（8 张，1440px） |

e2e 实际矩阵：3 场景 × 9 要求状态 = 27 组合 × 2 组断言（glyph/motion/trust/rail +
合成负例）= 54；外加首页徽标负例、validating glyph、3 条缺口原因码、签发负例 3 条、
三栏 2 条、双宽度溢出 2 条、reduced-motion、键盘提交、IME 4 条、focus-visible，
合计 73 条，全部 PASS。未挂载 `scripts/verify_all.sh`（不在写范围）。

## 3. Codex 集成门（v3 已部分闭合，主应用内导航仍属 Codex）

v2 时 `npm run build` 不在 `frontend/dist` 产出 `stage-c.html`。v3 经 owner @3
明确指令授权扩边，`vite.config.js` 已加多页 input，`dist/stage-c.html` 现随
build 产出，dev / preview / dist 静态托管均可达 `/stage-c.html`。主应用
（index.html 体系）内的导航入口链接仍属 Codex 集成面，本次未改；`package.json`
未改。

# Stage C 工作台原型 — 设计与审计笔记（work_item: flai-stage-c-kimi-uiux-001@4）

环境：EXTERNAL_DEVELOPMENT · fixtures：SYNTHETIC_ONLY · 内网数据/运行时依赖：NONE。
本原型不证明任何真实执行、内网导入或部署；原型内不存在任何签发路径（本地点击
不构成、也不模拟签发）。

## -2. v4 Codex 受控返工（rework_of: @3, base cfb4a97）

`work-item-v4.json` 记录本轮精确文件、接口与检查范围；其内容承诺为
`sha256:3f1094a2d16d7157fe225d6d24e337ed8bc500d5eecd2c33eb66b9c8d6bc4f52`。
该摘要按文件声明的 profile 对“仅删除 `work_item_digest` 的完整对象”执行 JCS 与
SHA-256，已机械重算一致。由于没有 `AssistantDispatchReceiptV1`，且当前合同尚未冻结
`DeliveryWorkItemV1` 摘要的 domain separator，它只是
`LOCAL_CONTENT_COMMITMENT_NOT_PROTOCOL_FREEZE`，不能投影为权威 RUNNING 或
HANDOFF_SUBMITTED。

本轮范围：

- 撤回 `vite.config.js` 的未冻结多页生产构建扩边；默认 `npm run build` 必须只产出
  `dist/index.html`，不产出 `dist/stage-c.html`。原型源码仍可由 Vite dev 直接访问，
  正式入口与导航继续留给独立 Codex 集成工作项。
- `reality` 缺省仍为合成 REAL 形态；显式非法值 fail-closed 到 UNKNOWN 缺口，不得
  静默回退 REAL。
- 移除 `submitted` 与 `state` 双真相；首页提交、终态重新提交、左栏切换工作及形态切换后，
  状态选择器与实际渲染 fixture 必须保持一致。
- `permission-denied` 的合成默认 REAL 形态在 @4 中被显式冻结；它仍是
  `source-kind=synthetic-fixture`，不会进入可信 REAL 绿槽。
- 所有可见 11px/12px 直接文本在 running / waiting_review / unknown 三态下按 computed
  颜色与实际背景扫描，对比度必须不低于 4.5:1。
- E2E 自证截图清单精确为 7 张；不再依赖手工计数。

TDD 红灯证据：

- 未修复时默认 build 真实生成 `dist/stage-c.html`，构建边界检查退出 1。
- 首轮 @4 E2E 为 105/116 PASS，11 条失败精确覆盖非法 Reality、6 处低对比度与
  4 个状态一致性场景。
- 扩展为全部小字号文本扫描后，waiting_review 与 unknown 又分别捕获 amber
  `4.45:1`，结果为 111/113 PASS；随后才调整 amber token。

### -2.1 v4 验证结果

| 命令 | 结果 |
|---|---|
| `git diff --check` | PASS |
| `cd frontend && node --test` | 102 pass / 0 fail |
| `cd frontend && npm run build && test ! -e dist/stage-c.html` | PASS；仅生成 `dist/index.html`，Stage C 未进入默认生产构建 |
| `STAGE_C_SHOTS=<fresh-temp> uv run --no-project --with playwright python frontend/e2e/stage_c_prototype_acceptance.py` | 113/113 PASS；截图清单自证 7/7 |
| `bash scripts/verify_all.sh` | 首次完整运行 PASS：1063 Python、102 Node、19 个既有浏览器套件，无失败 |

最终 Stage C 证据目录：
`/private/tmp/stage-c-v4-final-focused.GRNmwA/`。已人工查看 running 三栏页与
UNKNOWN/stale 缺口页；未发现新增横向溢出、信任色串槽或文字不可读问题。完整门禁生成的
既有 `docs/reviews` 截图已在隔离 worktree 中恢复，未纳入本轮 diff。

以下 v3/v2 小节保留为历史返工记录；其中截图数量已按脚本与独立执行结果从 8 更正为 7。

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
| e2e 截图 | `/private/tmp/stage-c-evidence-v3/*.png`（7 张，1440px；@4 独立审计更正） |

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
| e2e 截图 | `/private/tmp/stage-c-evidence-v2/*.png`（7 张，1440px；@4 独立审计更正） |

e2e 实际矩阵：3 场景 × 9 要求状态 = 27 组合 × 2 组断言（glyph/motion/trust/rail +
合成负例）= 54；外加首页徽标负例、validating glyph、3 条缺口原因码、签发负例 3 条、
三栏 2 条、双宽度溢出 2 条、reduced-motion、键盘提交、IME 4 条、focus-visible，
合计 73 条，全部 PASS。未挂载 `scripts/verify_all.sh`（不在写范围）。

## 3. Codex 集成门（v4 已撤回未冻结扩边）

v3 曾在未形成权威冻结 payload 的情况下给 `vite.config.js` 增加多页 input。v4 已撤回
该扩边，默认 build 再次不产出 `dist/stage-c.html`。主应用（index.html 体系）内的入口、
导航和部署暴露方式仍属独立 Codex 集成面；`package.json` 未改。

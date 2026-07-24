# Workspace Shell V1 原型 — 设计与审计笔记（work_item: flai-workspace-shell-kimi-001@1）

环境：EXTERNAL_DEVELOPMENT · fixtures：SYNTHETIC_ONLY · 内网数据/运行时依赖：NONE。
本原型不证明任何真实执行、内网导入或部署；原型内不存在任何签发路径（本地点击
不构成、也不模拟签发）。实现为独立 no-copy 重表达：未复制 Open WebUI / ChatGPT /
Claude 的品牌、图标、文案、像素几何或动画曲线，也未读取 Open WebUI clone。

## 1. 范围与边界

- 新增文件全部落在独占写范围：`frontend/workspace-shell.html`、
  `frontend/src/prototypes/workspace-shell/**`、
  `frontend/e2e/workspace_shell_prototype_acceptance.py`。
- 只读 import Stage C 的 `observer-contract.js`（`projectObserverEvents` 与合同版本常量），
  不复制、不改名分叉；Stage C 与生产合同零改动。
- `vite.config.js` / `package.json` / lockfile 未改：默认 `npm run build` 只产出
  `dist/index.html`，不产出 `dist/workspace-shell.html`（已机械断言）。
- 新增依赖：0。实现本身不发任何网络请求；页面无 v-html、无 iframe，
  不执行模型提供的 HTML/JS/Python/shell。

## 2. 默认界面（Workspace 优先，治理退到背景）

- 左轨（240px）：搜索、固定工作、最近工作、每项轻量文字状态；
  「治理与权限」与「合成演示控制」默认折叠。
- 中央：短任务标题 + 当前动作卡（glyph + 文字标签 + 步骤）+ 紧凑执行历史 +
  独立指令队列 + 固定 Composer。默认不展示模型/Agent/Tool/policy ID。
- 右侧 Focus Surface（360px）：按观察投影选择 runtime 预览 / diff 对照 /
  终态 artifact / 执行例外 / 停止点 / 权限边界 / 证据缺口；缺口态不复用产物卡，
  不残留任何敏感预览字段（无 digest、无来源见证行）。

## 3. 信任槽（五值，互不借用；real/sign 连 token 都不定义）

| slot | 色 | 只用于 |
| --- | --- | --- |
| active | 靛蓝 #3d4f9e | fresh 活动观察驱动的当前动作 |
| attention | 琥珀 #7a5800 | waiting_review 边界 |
| terminal | 中性 #565b66 | completed 终态、cancelled 停止（completed 永不给绿） |
| fail | 红 #a32e26 | 真失败与权限拒绝 |
| unverified | 琥珀 #7a5800 | UNKNOWN / 未核 / 缺口 / 未签发 |

- 合成夹具即使请求 REAL 显示形态，也保持 `source-kind=synthetic-fixture`、
  文案「合成夹具 · REAL 显示形态 · 非真实见证」，永不进入可信 REAL 绿槽。
- 合成/unsigned delivery 永不 teal；UI 不能创建或暗示可验证的真人 receipt。
- fail-closed 优先于形态字段：evidence-missing / observation-invalid / stale /
  UNKNOWN 形态一律压到 UNKNOWN 未核徽标 + 缺口 Focus。

## 4. 动作 glyph 与动效

六类动态 glyph（search/read/parse/compute/render/waiting-review）由合同 action
映射驱动（`workspace-view.js`）：inspect→search、receive→read、guard→parse、
rewrite/map→compute、render→render、hold→waiting-review。
动画只由 `[data-motion="true"]` 驱动；`motion = projector.motion && trust=active`，
waiting_review / completed / failed / cancelled / stale / evidence-missing /
permission-denied / UNKNOWN 全部静止。`prefers-reduced-motion` 强制停动画。

## 5. Composer 与队列

- ⌘/Ctrl+Enter 提交；Enter 单独按下只换行；`isComposing` 期间快捷键不提交（IME 安全）。
- 活动期间的补充指令进入独立队列：稳定 ID（cmd-N）、保序、各自 synthetic
  receipt（ACCEPTED + receiptRef + 「不代表完成」）；绝不拼接成单一 prompt。

## 6. Synthetic 验收矩阵

单元矩阵（`workspace-view.test.js`，node --test）：3 工作流 × 8 状态
（running / waiting_review / completed / failed / cancelled / evidence-missing /
permission-denied / observation-invalid）× 4 显示形态（REAL/MOCK/TEST/UNKNOWN）
= 96 case，逐 case 断言 glyph / motion / trust / Focus 种类 / 徽标 / 信任不变量；
外加 stale 叠加态（停动画 + UNKNOWN 未核 + 清空敏感预览）、非法输入抛错、
glyph 覆盖与队列测试。

浏览器验收（`workspace_shell_prototype_acceptance.py`，59 条断言）：
9 核心页 + 5 异常页 + 4 形态 DOM + stale + 队列/IME/键盘/focus-visible/
1440/1280 溢出/reduced-motion/对比度/网络账本 + 17 张自证截图。
网络账本：零非 loopback 请求、零应用 fetch/XHR/WebSocket/EventSource/beacon/
service-worker；vite dev 的 HMR socket（固定 loopback + `vite-hmr` 子协议）
被黑洞化并单独计数披露（非应用请求）。

## 7. 验证记录（真实命令与结果）

| 命令 | 结果 |
| --- | --- |
| `git merge-base --is-ancestor 71ecc9ea… HEAD` | PASS |
| `git diff --check` | PASS |
| scope union（diff + untracked） | 仅 8 个白名单内文件 |
| `(cd frontend && node --test)` | 204 pass / 0 fail（既有 102 + 新增 102） |
| `(cd frontend && npm run build)` | 成功；`dist/index.html` 存在 |
| `test ! -e frontend/dist/workspace-shell.html` | PASS（未产出） |
| `WORKSPACE_SHELL_SHOTS=… uv run … workspace_shell_prototype_acceptance.py` | 59/59 PASS；截图 17/17 |
| `UV_OFFLINE=1 bash scripts/verify_all.sh` | 见 handoff（运行结果以实际输出为准） |

截图证据目录见 handoff；本文件不代替 `DevelopmentHandoffV1`。

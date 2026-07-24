# Kimi K3 Workspace Shell 两周原型工作合同

> 状态：`OWNER_REVIEW_REQUIRED_NOT_DISPATCHED`
> 本文件是候选工作合同，不是运行 receipt，不授权修改生产接口。

## 1. Work Item

```yaml
handoff_schema_version: DevelopmentHandoffV1
work_item_ref: flai-workspace-shell-kimi-001@1
work_item_digest: UNFROZEN_OWNER_REVIEW_REQUIRED
human_owner: JerryKogami
requested_model_identity: kimi-code/k3
actual_runtime_receipt: REQUIRED_BEFORE_RUNNING
executor_qualification:
  profile: WORKSPACE_PRESENTATION_ONLY
  status: REQUIRED_BEFORE_RUNNING
environment: EXTERNAL_DEVELOPMENT
fixtures: SYNTHETIC_ONLY
internal_data_access: NONE
internal_runtime_dependency: NONE
accepted_code_base_sha: 0d095df8257ad369851e2a4a598fe5cb1a1cef14
work_item_base_sha: TO_BE_BOUND_TO_CLEAN_DESIGN_SHA_AT_FREEZE
planned_branch: codex/kimi-workspace-shell-v1
planned_worktree: TO_BE_CREATED_AND_RECORDED_BY_COORDINATOR
classification: PUBLIC_AND_SYNTHETIC_ONLY
egress:
  executor_model_transport:
    mode: ALLOWLISTED_PROVIDER_ONLY
    provider: kimi-managed
    purpose: MODEL_INFERENCE_ONLY
  source_context_egress:
    mode: APPROVED_EXTERNAL_DEV_PATHS_ONLY
    classification: PUBLIC_AND_SYNTHETIC_ONLY
  implementation_runtime_network: DENY
  browser_test_network: FIXED_LOOPBACK_BOOTSTRAP_ONLY
  denied_context:
    - OPEN_WEBUI_CLONE
    - SECRETS
    - INTERNAL_DATA
    - NON_WHITELIST_PATHS
budget:
  calendar_days: 14
  working_days: 10
  new_dependencies: 0
  infrastructure_spend_cny: 0
result_class: SOURCE_CANDIDATE_NOT_INTERNAL_RELEASE
design_route: INDEPENDENT_NO_COPY_VUE_WORKSPACE_SHELL
open_webui_role: PINNED_READ_ONLY_REFERENCE
status: OWNER_REVIEW_REQUIRED_NOT_DISPATCHED
```

`accepted_code_base_sha` 是 owner 已接受的 Stage C @4 外网源码候选。它不是最终 work-item base，
因为不包含本次审计和蓝图。Codex 必须先把设计文件收敛成 clean SHA，再把该 SHA 作为
`work_item_base_sha` 写入 coordinator-owned freeze payload；该 payload 不放在 executor 可改写的
工作分支中。Kimi 开工前必须在新的隔离 worktree 中复核 HEAD，生成冻结 digest，并记录实际 dispatch
receipt；模型自报不能代替 receipt。

## 2. 目标

用现有 Vue 3 技术栈实现一个可点击、可测试、desktop-grade 的 Workspace Shell 原型，吸收
ChatGPT Desktop、Claude Desktop/Cowork 与 Open WebUI 的交互优点，同时严格消费 FLAi-OS
observer-contract v2 的只读语义。

原型要让普通用户首先感到：

- 任务提交后可以连续工作；
- Agent 当前动作清楚但不喧闹；
- 右侧能看到真实在形成的内容；
- 只有必要时才出现授权或审阅；
- 所有可信状态和 synthetic 状态都不混淆。

## 3. Kimi 独占写范围

```text
frontend/workspace-shell.html
frontend/src/prototypes/workspace-shell/**
frontend/e2e/workspace_shell_prototype_acceptance.py
```

Kimi 可以在该目录创建组件、样式、synthetic fixtures、fixture tests、说明文档和图标动画。不得修改
Stage C @4 已接受文件，以免把视觉探索与既有候选混成一个不可复核 diff。

## 4. 只读依赖

```text
frontend/src/prototypes/stage-c/observer-contract.js
frontend/src/prototypes/stage-c/runtime-observer-adapter.js
frontend/src/prototypes/stage-c/fixtures.js
frontend/src/prototypes/stage-c/StageCWorkbenchPrototype.vue
frontend/src/prototypes/stage-c/stage-c.css
docs/design/OPEN-WEBUI-REFERENCE-AUDIT.md
docs/design/WORKSPACE-SHELL-V1-BLUEPRINT.md
docs/adr/ADR-0063-external-development-airgap-internal-workspace.md
docs/adr/ADR-0064-workspace-foreground-verifiable-delivery-and-dual-track-development.md
```

允许 import 既有只读观察合同；不允许通过复制后改名的方式分叉合同。

实现必须使用全新 Kimi 会话，不得 resume
`session_2f449268-89fd-4104-bd95-fd7bd908557e`，不得挂载或读取 Open WebUI clone。实现会话只读取
冻结后的 FLAi-OS 行为规格和本仓库合同；不得打开其中的外部链接。“独立 no-copy 重实现”不构成
法律意义上的严格 clean-room 声明。

## 5. 禁止修改

- `backend/**`
- `frontend/src/api/**`
- `frontend/src/router/**`
- `frontend/src/stores/**`
- `frontend/vite.config.js`
- `frontend/package.json`
- `frontend/package-lock.json`
- `scripts/**`
- `docs/adr/**`
- 数据库、Schema、认证、ACL、classification、签名、人签和 Production Adapter
- Stage C @4 的现有源文件和测试

不得新增 npm/pip/系统依赖，不得把 Open WebUI 代码、品牌资源、图标或 CSS 复制到仓库。

## 6. 必做交互

### Workspace Rail

- 最近任务、固定项目、搜索和轻量状态；
- 治理入口默认折叠；
- 适配 1440px 和 1280px。

### Continuous Work Surface

- 紧凑任务标题、连续事件流和固定 composer；
- search/read/parse/compute/render/waiting-review 六类动态 glyph；
- 动画由 observer 状态驱动，stale、waiting、completed、failed、cancelled、unknown 停止；
- 多条补充指令按独立 ID 排队，不拼接；
- Ctrl/Cmd+Enter 提交，IME composition 不误提交。

### Focus Surface

- 根据 observer 投影选择 Artifact、运行输出、diff、证据缺口或知识依据；
- 切换有节制，不制造频繁闪烁；
- Artifact 标示 digest/reality/classification 的可验证摘要；
- completed 不显示绿色；本原型只有 unsigned/synthetic delivery，任务事实中永不显示 teal。

### Accessibility

- keyboard-only 可达；
- focus-visible 清楚；
- reduced-motion 停止非必要动画；
- 颜色不是唯一状态编码；
- 重要状态有可读文本和 DOM 属性。

## 7. Synthetic 验收矩阵

三个工作流：

- `docx`：Office 文档润色与对照预览；
- `meeting`：会议纪要、决策和待办提取；
- `cfd`：设置审查、受控建议与后处理预览。

精确的 unit/DOM fixture 矩阵是 96 个 case：

```text
3 workflows
× 8 observation states
× 4 requested display forms
= 96
```

八个 observation state 固定为：

- `running`
- `waiting_review`
- `completed`
- `failed`
- `cancelled`
- `evidence-missing`
- `permission-denied`
- `observation-invalid`

四个 requested display form 固定为 REAL、MOCK、TEST、UNKNOWN。只有 REAL/MOCK/TEST 是合法
execution reality；UNKNOWN 是 observer 对无效、缺失或不可信输入派生的 fail-closed projection，
不能写入合法 execution event。所有数据必须是 synthetic fixture，页面必须显式显示
`source-kind=synthetic-fixture` 或等价的可测试属性。

视觉 E2E 不要求 96 张截图，固定覆盖：

- 三工作流 × running/waiting_review/completed = 9 个核心页面；
- docx 的 failed/cancelled/evidence-missing/permission-denied/observation-invalid = 5 个异常页面；
- docx:running 的四种 requested display form = 4 个 DOM 形态；
- 1440px、1280px、reduced-motion、keyboard/IME、queue 与 network 各自独立断言。

## 8. 网络与事实约束

- 浏览器测试只允许固定 loopback origin 提供 document、ES module、CSS、字体和图片 bootstrap；
  bootstrap 后的 fetch/XHR、WebSocket、EventSource、beacon、service worker、外部域名或后端 API
  请求都必须立即失败并分别计数；
- 不读取环境变量、真实文件、真实用户身份或内网数据；
- 不调用后端；
- UI 不自己生成 REAL、green、human-signed；
- command receipt 只表示 synthetic adapter 接受，不表示任务完成；
- unknown、缺 witness、缺 digest、缺 ACL/classification 时 fail closed；
- 不执行模型返回的 HTML、JavaScript、Python 或 shell。

## 9. 验证命令

Kimi handoff 必须给出逐项结果：

```bash
test -n "${WORK_ITEM_BASE_SHA:?set WORK_ITEM_BASE_SHA from the frozen coordinator payload}"
git merge-base --is-ancestor "${WORK_ITEM_BASE_SHA}" HEAD
git diff --check
git status --porcelain=v1 --untracked-files=all
{
  git diff --name-only "${WORK_ITEM_BASE_SHA}"
  git ls-files --others --exclude-standard
} | LC_ALL=C sort -u
(cd frontend && node --test)
(cd frontend && npm run build)
test ! -e frontend/dist/workspace-shell.html
uv run --no-project --with playwright python frontend/e2e/workspace_shell_prototype_acceptance.py
bash scripts/verify_all.sh
```

大括号命令是提交前 scope union，输出必须全部落在第 3 节白名单。形成 final commit 后，再要求
`git status --porcelain=v1 --untracked-files=all` 为空，并用
`git diff --name-only "${WORK_ITEM_BASE_SHA}"..HEAD` 复核最终提交范围。

Playwright 证据至少包括：

- 1440px 三个工作流的 running / waiting / completed；
- 1280px 无横向溢出；
- reduced-motion；
- keyboard-only 和 IME；
- queue 顺序；
- REAL/MOCK/TEST/UNKNOWN；
- completed 不绿、所有任务 synthetic/unsigned delivery 永不 teal；
- unknown、permission denied 和 evidence missing fail closed；
- 零非 loopback 请求、零应用 fetch/XHR、零 WebSocket/beacon/service-worker。

`npm run build` 成功不代表原型进入生产；反而必须证明 `dist/workspace-shell.html` 不存在。

## 10. Stop If

出现任一条件立即停止并提交 `BLOCKED` handoff：

- 必须修改写范围外文件才能继续；
- 必须新增依赖或改变 Vite production input；
- 开工前 HEAD 不等于冻结 base、冻结 base 不是当前 HEAD 的祖先，或出现 owner 写范围外变化；
- 只读 observer 合同无法表达所需状态；
- 需要真实 API、真实内网数据、认证 token 或 secret；
- 发现 Open WebUI 代码/资产必须复制才能完成；
- 测试只能通过降低 fail-closed、信任色或人签规则；
- 不能获得可记录的 Kimi dispatch/model receipt；
- `scripts/verify_all.sh` 出现与本工作项相关的失败。

## 11. Handoff 要求

最终 handoff 必须包含：

- `work_item_ref` 与冻结 digest；
- dispatch receipt 和实际 runtime identity 证据状态；
- base SHA、final SHA、branch、commit refs；
- changed files 与 patch SHA-256；
- `production_changed_interfaces: []`；
- `prototype_changed_interfaces`：列出 URL、query、DOM testid、fixture shape 和 keyboard contract；
- 所有验证命令和逐项结果；
- screenshot paths；
- synthetic-only 与 no-internal-data 声明；
- risks、unresolved issues 和 recommended next step；
- `SOURCE_CANDIDATE_NOT_INTERNAL_RELEASE`；
- 不 push、不 merge、不申请人签、不声称内网发布。

# `flai-workspace-shell-kimi-001@6A` Codex Cage 构建与冻结提案

状态：`OWNER_APPROVAL_REQUIRED / PREPARATION_ONLY / NOT_FROZEN / NOT_DISPATCHED`

## 为什么不直接重派 Kimi

`@5` 已消耗 owner 批准的唯一全新 Kimi K3 会话，并因两项协议违例 fail closed：

1. 只读了 14 个必读文件中的 12 个，却声称 14/14；
2. 首个写入整文件替换了 `workspace-view.test.js`，没有先做唯一允许的
   lazy-`mkdtemp` E2E harness repair。

因此 unit red、E2E red、六 P1 映射与 `RED_GATE_COMPLETE` 都没有发生。没有提交、截图、测试、
build 或可接受 handoff。失败 session、脏工作树与空证据目录禁止续跑、复制、恢复或晋升。

后续安全复核又确认，不能简单依靠 Kimi 配置重派：

- Kimi Code 0.29.0 的 `kimi acp` 使用 v1 harness；`[tools]` 全局 allowlist 是 v2-only，
  不能证明模型只看到 `Read / Write / Edit`；
- ACP 只 broker 文本读写，stat/iterdir/glob/readBytes/exec 与 session bootstrap 仍可能走
  LocalKaos；
- Kimi native auth 与本地工具处于同一进程，不能靠同一个 Seatbelt principal 同时证明
  “runtime 能读 credential、任意模型工具不能读”；
- 由 Kimi 编写的测试本身也是不可信代码，不能直接在 cage 外运行；
- 在完整 cage、路径、策略和 digest 尚未形成时，owner 不应提前批准真实 K3 session。

所以把下一步拆成两个 owner gate：

```text
@6A：Codex 构建并验证 cage，只使用本地 mock provider 与 dummy credential
  ↓ 全部机械证据通过，生成完整 @6B freeze
@6B：JerryKogami 接受 exact freeze digest 后，才允许唯一真实 Kimi K3 session
```

本提案只请求 `@6A`，**不授权真实 K3、外部模型调用、真实 credential、产品实现或候选提交。**

## `@6A` 保持不变的产品边界

- 六个 P1 仍是：
  `URL-CONTRACT`、`DOM-CONTRACT`、`TRUST-COLORS`、`INVALID-HISTORY`、
  `NETWORK-LEDGER`、`RAIL-STATE`；
- 未来 K3 实现的六个源码写文件与 `@5` 完全相同；
- 12 个额外只读文件、合并后的 14 个必读文件与 `@5` 完全相同；
- 零新产品/package 依赖，零生产接口，零 Schema 变更；
- 环境仍是 `EXTERNAL_DEVELOPMENT / SYNTHETIC_ONLY / NONE internal data`；
- 不读取 OpenHands、Open WebUI、真实内网数据或 secret 值；
- 不包含 push、merge、生产集成、人签或内网发布。

四个不属于 14-path mandatory context 的额外只读文件：

```text
frontend/package.json
frontend/package-lock.json
frontend/vite.config.js
scripts/verify_all.sh
```

明确只供 Codex supervisor/cage 设计读取，不作为未来 Kimi 模型上下文。

## `@6A` 允许的仓库改动

### 1. 唯一行为前置提交

从 `47d191cb4799ec57f4739b4d1c709f490481fe77` 创建全新隔离工作树。Codex 只修改：

```text
frontend/e2e/workspace_shell_prototype_acceptance.py
```

唯一语义是把 `WORKSPACE_SHELL_SHOTS` fallback 变成真正 lazy：

- 环境变量存在时，raising `tempfile.mkdtemp` 替身零调用并返回固定路径；
- 环境变量缺失时，sentinel 替身恰好调用一次并返回 sentinel；
- 全文件 AST/diff 不变量证明没有在别处重新引入额外临时目录；
- 断言、截图清单、网络边界和其他测试语义完全不变；
- 单独提交后工作树 clean，新 base SHA 与文件 SHA-256 进入 `@6B` freeze。

### 2. 审计与冻结文档

Codex 可在 `docs/work-items/` 新增：

```text
flai-workspace-shell-kimi-001-v6a.cage-preflight.json
flai-workspace-shell-kimi-001-v6a.cage-manifest.json
flai-workspace-shell-kimi-001-v6a.tool-policy-matrix.json
flai-workspace-shell-kimi-001-v6a.dispatch-observation.json
flai-workspace-shell-kimi-001-v6b.freeze.json
flai-workspace-shell-kimi-001-v6b.prompt.md
flai-workspace-shell-kimi-001-v6b.executor-environment.json
flai-workspace-shell-kimi-001-v6b.authorization-proposal.md
flai-workspace-shell-kimi-001-v6b.authorization-proposal.json
```

这不授权任何产品实现文件修改。未来六文件源码候选的本地提交必须由 `@6B` 单独授权。

## `@6A` Coordinator Cage

Cage 源码、配置、mock fixture、日志和测试只放在一个由 `mktemp -d` 产生并立即固化的
`/private/tmp/flai-kimi-workspace-shell-v6a-control.*/`。它是外部 coordinator 控制夹具，
不进入产品依赖，也不是生产 sandbox。

### A. 固定 Kimi 二进制与真实 ACP engine

只允许读取公开元数据和执行无模型 metadata 命令：

- `kimi --version == 0.29.0`；
- 绝对路径与 SHA-256；
- `codesign --verify --deep --strict` 与 Team ID；
- 固定 tag/commit 的公开源码证明确认 ACP 使用 v1 harness；
- 明确记录 `[tools]` 不构成 v1 安全门，禁止再声称“三工具 surface”。

### B. 本地 mock ACP 校准

为了验证实际 0.29.0 二进制，而不是只相信静态设计，`@6A` 最多允许：

- 一个 Kimi ACP 进程；
- 一个全新、一次性、synthetic mock session；
- 最多 64 个有序 policy-probe prompts；
- provider、Web、MCP 与所有 Kimi 流量只能连接冻结 loopback mock server；
- 使用 `KIMI_MODEL_*` 合成 provider：`KIMI_MODEL_NAME` 指向 mock model、
  `KIMI_MODEL_API_KEY` 是 dummy fixture、`KIMI_MODEL_BASE_URL` 指向 loopback；
- 隔离 config 不含其他 provider/model；`session/new.configOptions[id="model"].currentValue`
  必须精确为 v1 合成 alias `__kimi_env_model__`，否则 fail closed；
- 真实 HOME、真实 KIMI_CODE_HOME、真实 `.agents`、真实 credential、真实 session 状态全部
  不可见；
- 零外部网络、零真实 K3/LLM 调用、零 token 费用；
- mock session 与其输出绝不允许作为 `@6B` 开发 session 或源码证据复用。

Mock upstream 只做两件事：

1. 收集并哈希 Kimi 实际发送的 tool schema，形成完整 built-in/custom/MCP surface inventory；
2. 以固定响应主动请求每个工具，用 sentinel 文件、进程、socket 与 provider-request count 验证
   deny policy 在 resolve/permission/execute 全链路没有副作用。

如果 mock protocol 无法驱动固定二进制或任何被禁工具产生副作用，`@6A` 结果是
`NO_GO_FOR_6B`，不得用第二个 mock session 重试。

### C. v1 deny-policy coverage

因为 v1 tool allowlist 不生效，安全合同改为：

- 启动前从 pinned v1 profile/static inventory 生成 deny seed；首个实际 mock request tool schema
  必须与该全集精确相等，出现 unknown/extra/missing 时，在 mock 返回任何 tool call 前停止；
- `Read / Write / Edit` 只在 phase-aware ACP broker 的 exact manifest 内可用；
- 其余每个实际工具必须有显式 first-match `decision = "deny"`；
- unknown/custom/MCP 工具默认 deny；
- `session/request_permission` 只能 `reject/cancelled`，`approve_always` 永不允许；
- 配置 deny 不是唯一边界，必须由 Seatbelt、broker、proxy 与 active negative probe 共同证明。

`@6A` 产出逐工具 coverage matrix：

```text
tool name
→ 是否出现在真实 v1 schema
→ resolve 是否发生
→ permission decision
→ filesystem/process/network/provider side effect
→ expected deny witness
→ result
```

Read/Write/Edit 正向 probe 只能作用于 control root 内的 disposable sentinel，mock session 对真实
repo 的 changed/untracked manifest 必须始终为空。

### D. Bootstrap 与文件边界

- 使用 synthetic `HOME`、isolated `KIMI_CODE_HOME`、空 `.agents`、空 skills、空 MCP、空 plugin、
  空 custom agent；
- 真实 HOME 和真实 Kimi home 的 read probe 只允许命中预先创建的非敏感 canary/metadata，
  不得尝试打开任何私有文件；必须被 Seatbelt 拒绝。唯一例外是执行并读取
  `/Users/Zhuanz/.kimi-code/bin/kimi` 本身及其 codesign metadata，禁止同目录枚举；
- cwd 只允许目录 metadata；源码正文默认拒绝；
- repo 根 `AGENTS.md` 若 ACP v1 bootstrap 必须读取，则作为单独的
  `FROZEN_SYSTEM_POLICY_INPUT` 绑定精确路径 `AGENTS.md`、hash 与 returned bytes，不计入
  14-path 业务上下文；若没有读取，receipt 明确记录 `NOT_READ`；
- brand/embedded AGENTS 由 pinned binary/source digest 绑定；
- 14 个业务文件的正文只允许走 coordinator `fs/read_text_file`；
- broker 使用 canonical parent dirfd、`openat + O_NOFOLLOW`、`fstat`、hardlink 检查、
  同目录原子写与 before/after SHA；
- traversal、NUL、symlink、hardlink、TOCTOU、wrong session/phase、oversize、unknown method
  全部主动负测。

### E. Kimi Process Cage

使用当前 macOS 的 `sandbox-exec`/Seatbelt，只作为外部合成开发门：

- Kimi 无 repo 直接正文读写；
- 无 fork、Bash、子进程和额外 executable；
- 只允许 isolated HOME/KIMI_CODE_HOME/TMP 的必要运行时写；
- 所有外网拒绝，只允许冻结 loopback mock endpoint；
- 其他 loopback 端口与 Unix domain socket 也必须拒绝；
- 关闭 ACP stdin/stdout/stderr 以外的继承 FD，使用最小环境；
- 固定累计 wall-clock、request/response bytes、prompt 与 transcript 上限；
- 记录 Seatbelt deny、PID/PGID、高频进程树、socket 与文件 manifest。

同一 profile 必须用 sentinel 主动证明范围外 read/write、`/bin/sh`、fork/exec、外部 socket
均为 EPERM。`ps`/`nettop` 只作 witness，不替代 enforcement。

### F. Canonical URL CONNECT Proxy

`@6A` 只用 mock upstream 验证未来网络方案，不接真实 provider：

- 未来 `@6B` 保持所选 credential class 对应的 canonical provider URL，不用 loopback
  application base URL 改写 credential slot；
- Kimi 只允许把 `HTTPS_PROXY` 指向 loopback CONNECT broker；
- broker 只允许 `CONNECT` 到 freeze 中精确 host:443，固定 DNS 解析结果并拒绝私网、redirect、
  rebinding、非 CONNECT、其他 host/port；
- broker 是会接触加密隧道 metadata 的 TCB，但不解密 TLS；
- 若未来使用 secret-bearing launcher，它只能“不记录、不持久化、不输出、不按 secret 值分支”，
  不能声称进程从未接触 secret；
- `@6A` 用 dummy header/body 主动验证所有日志、异常和 observation 都不会泄漏。

真实 credential 方案不在 `@6A` 选择或使用。`@6B` 必须从以下之一冻结成唯一方案：

1. secrets-stackdocker 向 Kimi launcher 注入 `KIMI_MODEL_*` 临时 API key，隔离 config 不含
   其他 provider，ACP model currentValue 必须是 `__kimi_env_model__`；值不进入 Codex、
   config 或日志，Bash/子进程/plugin/MCP/extension surface 必须被 cage 阻断；或
2. secrets-stackdocker 提供独立、最小、可刷新 credential volume。

真实个人 Kimi credential symlink 明确禁止。若无法形成不暴露值的精确 secret injection
reference，`@6B` 不得提出执行授权。

### G. TestRunnerCage

由 Kimi 编写的 JS/Python 测试视为不可信。`@6A` 必须构建第二个独立 runner cage：

- 六个授权源码文件及整个 repo 在 red/green test 时只读；
- supervisor control、receipt、stdout/stderr 目录只允许 coordinator 写，测试子进程不可写；
- 测试子进程只能写独立的非权威 evidence 与 disposable child scratch；
- `.vite` 只允许可信 baseline warm-up 写入；warm-up 后绑定 hash 并 seal 为只读，baseline/red/
  green 不得共享可写 cache；
- 外网全拒，只允许固定 loopback Vite/browser traffic；
- 最小环境、无 secret、固定 argv 数组/cwd/timeout；
- 完整 stdout/stderr 与正常 exit status 原样保存；
- 用只攻击 disposable sentinel 的恶意 synthetic test 主动验证不能改源码、不能自修改、不能
  篡改 control ledger、不能污染 sealed cache、不能出外网、不能逃逸进程；不得攻击共享 Git
  control dir；
- 每次 test 前后绑定六文件 hash 与 changed/untracked manifest。

### H. BuildRunnerCage 与状态机故障注入

`BUILD` 使用独立 runner profile：

- repo/source 只读，唯一产品写区是冻结 `frontend/dist/**`；
- 无外网、无 secret、无共享可写 test cache；
- supervisor control/stdout/stderr 仍为 coordinator-only；
- build 前后绑定 source hash、dist manifest 与范围外写拒绝。

`@6A` 还必须生成 `StateMachinePreflightReceiptV1`，主动注入：

- CAS 成功后、发帧前崩溃；
- 响应丢失与重复发送；
- 越序 Phase；
- Phase T terminal 后继续写测试；
- Phase I terminal 后继续写任一源码；
- Kimi PID 未退出时尝试 green；
- lock/receipt 持久化失败。

每个故障都必须证明：不重发、不重新解锁、不进入下一阶段。

## `@6A` 必须产出的机械证据

1. binary/version/SHA/codesign 与 v1 engine witness；
2. 实际 v1 tool inventory 与逐工具 deny-policy coverage matrix；
3. ACP Kaos bridge/local routing matrix；
4. synthetic HOME、AGENTS、skills、MCP、plugin、agent 注入负例；
5. broker path/TOCTOU/hardlink/wrong-phase/session 全负例；
6. Seatbelt file/process/exec/network 负例；
7. CONNECT proxy mock-upstream、host pinning 与日志脱敏负例；
8. dummy credential 与真实 HOME/credential 不可达证明；
9. TestRunnerCage control/cache/source/network/process 恶意测试负例；
10. BuildRunnerCage 范围与网络负例；
11. `StateMachinePreflightReceiptV1` 全部故障注入；
12. baseline focused unit/E2E 在同一 runner cage 中 green；
13. cage driver/profile/config/prompt/policy/test 的逐文件 digest；
14. 完整 `@6B` freeze，不含占位符并通过独立安全、范围、test-first 三轴复核。

任何一项失败，最终状态只能是 `NO_GO_FOR_6B`。不得把部分 cage、mock session 或失败测试包装
成执行就绪。

## `@6B` 必须冻结的 test-first 顺序

`@6A` 只设计和评审，不执行真实 K3。未来 `@6B` payload 必须精确绑定：

```text
BASELINE_GREEN
→ A_CONSUMED → READ_ACCEPTED
→ T_CONSUMED → T_TERMINAL
→ TEST_WRITES_REVOKED → TEST_LOCK_RECEIPT → TEST_AUTHORING_ACCEPTED
→ UNIT_RED_FINAL → E2E_RED_FINAL → RED_ACCEPTED
→ I_CONSUMED → I_TERMINAL
→ ALL_SOURCE_LOCKED → KIMI_EXITED
→ GREEN → BUILD → INDEPENDENT_REVIEW
```

并满足：

- 三个 prompt 各自发帧前持久 CAS-on-NULL；响应丢失也视为已消费；
- Phase T 只能写两个测试文件，终态后立即锁死，再运行 red；
- `TestAuthoringAcceptedV1` 只能由 Codex 签发，绑定 test diff、既有断言保留规则和六个预冻结
  assertion ID；测试 diff 不得删除/弱化既有断言、无条件失败或嵌入产品实现；
- `TEST_LOCK_RECEIPT` 前重跑 lazy-`mkdtemp` 双 probe、全文件 AST/diff 不变量与临时目录
  manifest，并把结果和 E2E hash 同时绑定进 `TestLockReceiptV1` 与 `RedGateAcceptedV1`；
- Red Gate 绑定 baseline、两个测试 hash、四个未改实现 hash、runner profile、精确 argv/cwd/
  env/timeout、完整 stdout/stderr、正常非零 exit 与两条输出并集覆盖六个 assertion ID；
- Phase I 只能写其余四文件，两个测试始终锁定；
- Phase I 终态后先锁死六文件、封存 hash、终止并确认 Kimi PID 消失，再跑 green/build；
- final green 前再次复核 lazy-`mkdtemp` 双 probe、全文件不变量与临时目录 manifest；
- 无效红、任何 prompt 异常、green/build 失败都禁止重发、重开、复用 patch；只能新授权、新
  工作树、新 session；
- 不存在第四个修复 prompt。

## 当前未执行

Owner 批准前，Codex 不会：

- 创建 `@6A` 工作树、分支、control/evidence 目录；
- 修改或提交 lazy-`mkdtemp` 前置修补；
- 启动 Kimi ACP，包括 mock session；
- 访问 secrets-stackdocker、真实 credential、真实 Kimi private state 或真实 provider；
- 运行实现测试或修改任何产品实现文件。

## 本次授权的精确效果

JerryKogami 回复：

> 批准 @6A Codex Cage 构建与冻结，仅限本地 mock，不创建真实 K3 会话

才授权 Codex：

1. 创建全新隔离工作树并形成唯一 lazy-`mkdtemp` 本地前置提交；
2. 创建一个 coordinator control 目录，使用 stdlib/系统能力构建与负测 cage；
3. 创建最多一个固定 Kimi ACP 进程和一个 synthetic mock session，最多 64 个 policy-probe
   prompts，只连 loopback mock provider，使用 dummy key；
4. 运行 TestRunnerCage baseline 与恶意 fixture 负例；
5. 只在上述 9 个精确 `docs/work-items/` 路径写入 `@6A` observation 与完整
   `@6B` freeze/authorization payload；
6. 对 `@6B` 做三轴独立只读复核。

该授权明确不允许：

- 真实 K3/LLM/provider 调用或 token 消耗；
- 读取、复制或使用任何真实 secret/credential 值；
- 产品实现、六文件候选提交、第四方系统写入；
- push、merge、生产集成、Schema 变更、人签或内网发布；
- 在没有 JerryKogami 对 exact `@6B` digest 的第二次批准时启动真实执行 session。

## 准备阶段隐私事件

在研究 ACP 配置可行性时，Codex 曾误执行一次针对真实 Kimi home 的宽泛只读 `rg`。界面输出
出现了经过隐藏/脱敏的私有状态片段。没有 secret 值被提取、转录、引用或复用，没有修改文件，
也没有选择、恢复或复用任何 session。

纠正控制已经写入 `@6A`：

- 禁止对真实 Kimi home 做递归搜索、目录枚举或 session 检查；
- 只使用固定版本公开源码、synthetic HOME/KIMI_CODE_HOME 与 dummy credential；
- 真实 secret 路径和值均不进入 `@6A`；
- 任何未来本机 metadata 或 secret injection reference 都必须先进入 `@6B` exact freeze，再由
  JerryKogami 单独批准。

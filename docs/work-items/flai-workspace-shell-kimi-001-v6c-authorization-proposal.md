# `flai-workspace-shell-kimi-001@6C` 诊断/准备提案（FINALIZED，待 commit 锚点与 owner 精确签发）

> **状态：`FINALIZED_PENDING_COMMIT_AND_OWNER_EXACT_RECEIPT — NOT_AUTHORIZED / NOT_EXECUTABLE`**
> 决策点已由 owner 于 2026-07-25 全部按推荐落定（D1a / D2=47d191c / D3 本文件 patch /
> D4=Track G 仅出证据、执行另立 @6D）。本文件仍需：协调器提交双文件得到
> coordinator_commit → 以精确文本签发 OwnerApprovalReceiptV1 → 之后才允许任何
> fetch / build / 进程。owner 的"按推荐执行"裁定了解策点，但不替代 digest 绑定的
> 签发步骤。

- proposal_ref: `flai-workspace-shell-kimi-001@6C-proposal-1`
- proposal_class: `DIAGNOSTIC_AND_PREPARATION_THEN_FULL_GATE_RERUN`
- human_owner: `JerryKogami`
- environment: `EXTERNAL_DEVELOPMENT`
- fixtures: `SYNTHETIC_ONLY`

## 1. 血脉与阻断继承

| 项 | 值 |
|---|---|
| source_work_item | `flai-workspace-shell-kimi-001@6A` → `NO_GO_FOR_6B` |
| @6A proposal_digest | `sha256:95a2d671a0816bccc796adf222f4273a4610bfc72608dd23adc90582ac9ef62a` |
| blocker_1 | `ACP_SESSION_NEW_INTERNAL_ERROR_SPAWN_EPERM`（outcome digest `sha256:162a449fd086506e1bf58489a6020bd76349d8683708568dee2d80ef3b82e090`） |
| blocker_2 | `PRESENT_EMPTY_WORKSPACE_SHELL_SHOTS_CALLS_MKDTEMP`（commit `43f02f1` 失败不可复用） |
| K3 handoff (r2) | digest `sha256:9b65ca10f1d9a07a1e3e814970535d147d419f7e95489674a20afc4110ffabc2` |
| 复用禁令 | 旧进程/session 额度、旧 control root、旧 worktree、旧 precondition commit、旧失败证据一律 `DENY` |

## 2. 源码取证结论（只读，已核实；8bf5bac）

1. `packages/kaos/src/local.ts:220` — `LocalKaos.create()` 无条件并发执行
   `applyLoginShellPathFromNode()`；
2. `packages/acp-adapter/src/server.ts:638-642` — `ensureInnerKaos()` 首个
   具备 fs 能力的 session 惰性触发；
3. `packages/kaos/src/login-shell-path.ts:62-66` — probe 以
   `$SHELL -l -c /usr/bin/env` 启动登录 shell；
4. 全仓搜索确认 8bf5bac **无任何现成禁用开关**，upstream-flag 路线不成立；
5. probe 有 memoization（`appliedLoginShellPath`），patch 必须保持该语义。

补充事实（Track P 背景）：基线 `47d191c` 的表达式是
`os.environ.get("WORKSPACE_SHELL_SHOTS", tempfile.mkdtemp(...))` ——
默认参数形式**每次运行都无条件调用 mkdtemp**；`43f02f1` 改为 `or` 形式后仅
修复了 present-nonempty 情形，present-empty 仍失败。冻结合同：
`CALL_MKDTEMP_ONLY_WHEN_WORKSPACE_SHELL_SHOTS_IS_ABSENT`。

## 3. Track P — precondition 前置修复（已定稿精确 diff）

新基线 `47d191cb4799ec57f4739b4d1c709f490481fe77` + 一个新独立 precondition
commit（不复用 `43f02f1`），唯一语义变更：

```diff
--- a/frontend/e2e/workspace_shell_prototype_acceptance.py
+++ b/frontend/e2e/workspace_shell_prototype_acceptance.py
@@ -57,7 +57,9 @@
  # 显式绑定 127.0.0.1：本机 vite 默认只绑 IPv6 ::1，会导致健康探测假阴性
  BASE = f"http://127.0.0.1:{PORT}"
  SHOTS = Path(
-    os.environ.get("WORKSPACE_SHELL_SHOTS", tempfile.mkdtemp(prefix="workspace-shell-shots-"))
+    os.environ["WORKSPACE_SHELL_SHOTS"]
+    if "WORKSPACE_SHELL_SHOTS" in os.environ
+    else tempfile.mkdtemp(prefix="workspace-shell-shots-")
  )
```

验收探针（机器可判，全部必须通过）：

| 情形 | mkdtemp 调用 | 取值 |
|---|---|---|
| key 缺失 | 恰 1 次 | sentinel 路径 |
| key 存在、值 `""` | **0 次** | `""` |
| key 存在、非空 | 0 次 | 原值 |

附加不变式：全文件 AST 确认 mkdtemp 调用点唯一；diff 仅含该表达式；无
断言/截图/网络等其他测试语义变更；present-empty 负例加入合同测试，并在
`@6D` 的 TestLockReceipt 中绑定。

## 4. Track D — spawn EPERM 诊断与 pinned build（已定稿 patch）

**唯一 patch**（`packages/kaos/src/login-shell-path.ts`，8bf5bac）：

```diff
 export function applyLoginShellPathFromNode(): Promise<void> {
   if (appliedLoginShellPath !== undefined) return appliedLoginShellPath;
+  if (process.env['KIMI_KAOS_DISABLE_LOGIN_SHELL_PATH_PROBE'] === '1') {
+    appliedLoginShellPath = Promise.resolve();
+    return appliedLoginShellPath;
+  }
   appliedLoginShellPath = applyLoginShellPath({
     platform: process.platform,
     env: process.env as Record<string, string | undefined>,
```

- 默认行为不变；仅 isolated ACP 启动环境注入该变量；
- 不放行 `/bin/sh`、`/bin/zsh`、`/usr/bin/env` 或任何通用 shell surface；
- patched binary 与官方 binary 的行为差异只允许这一处 probe gate，需 diff 级证明。

**build 策略（D1a，owner 已裁定）**：用 control root 已有
`kimi-code-8bf5bac.tar.gz` + 仓内 `pnpm-lock.yaml`；owner 批准**一次性**依赖
获取窗口，按 lockfile 锁定拉取并记录全部 integrity 哈希与获取清单，之后
build 环境封网。build 产物 digest、patch digest、toolchain 版本、codesign
状态全部冻结进 @6C 证据。

**诊断重放**：新 cage 中 patched binary 重放 `initialize` + `session/new`：
通过则 blocker_1 根因确认；仍失败则采集新失败帧并 fail closed 回 owner。

## 5. Track G — 全部 @6A 证据门重跑（仅出证据）

Track P、Track D 均绿后，从 `session/new` 起重跑：actual tool inventory、
23 工具权限矩阵、ask/reject/cancel 桥、broker/proxy 负例、TestRunnerCage、
BuildRunnerCage、状态机故障注入、baseline unit+E2E。**owner 已裁定 D4**：
Track G 只产出 GO/NO_GO 证据；任何真实执行另立 `@6D` 并单独精确批准。

## 6. 预算与隔离（全部一次性）

| 资源 | 值 |
|---|---|
| Kimi ACP 进程 | ≤ 1（patched pinned build） |
| 新 session | ≤ 1（synthetic mock） |
| ACP prompts / provider requests | ≤ 64 / ≤ 128（loopback mock） |
| control root / worktree | 全新 `mktemp -d` 0700 / 全新（从 Track P 新 precondition commit 的父基线 `47d191c` 创建） |
| 外网 | DENY（D1a 一次性依赖获取窗口除外，获取后封网） |
| 真实 K3 / 真实 provider / 真实 secret | DENY |

## 7. 安全不变式（继承或加严）

不放宽通用 shell/`/bin/zsh`/`/bin/sh`/`/usr/bin/env` execution surface；
synthetic HOME / 隔离 KIMI_CODE_HOME / dummy credential；不读真实 Kimi
home/session/secret（pinned executable 元数据例外同 @6A）；任何 deny 进入
execute、非 loopback 请求、uncontained side effect → 立即 fail closed；
LLM 不进判决链；人是唯一签发者。

## 8. 明确不授权

真实 K3 会话、真实 LLM/provider 流量、真实 secret 值、产品实现、六文件源码
候选提交、push/merge/生产集成/内网发布、第二次 mock session 重试、通用 shell
放行、`@6D` 执行 —— 均 `DENY`。

## 9. 签发流程与精确批准文本模板

1. 协调器提交本提案双文件（json + md）得到 coordinator_commit；
2. 以 json 定稿重算 proposal JCS digest、以 md 定稿重算 markdown sha256；
3. owner 以下列精确文本签发（占位符届时填入）：

```text
批准 @6C proposal_ref=flai-workspace-shell-kimi-001@6C-proposal-1 proposal_digest=<sha256:JCS> markdown_sha256=<sha256:hex> coordinator_commit=<40hex>；仅限本地 mock，不创建真实 K3 会话
```

4. receipt 以 CAS-on-NULL 写入新 control root 并绑进 cage preflight；
5. 此后才允许：新 control root/worktree → D1a 依赖窗口 → build →
   Track P commit → Track D 重放 → Track G 重跑。

## 10. Stop if

需要第二个 Kimi ACP 进程/session、真实 provider、外网（D1a 窗口外）或
secret；patched binary 与 patch digest 不符或出现第二处行为差异；需修改
授权路径之外的仓库文件或改写任何已绑定 commit/receipt；Track D 重放仍失败
且诊断超出本提案范围 —— 保留证据，fail closed 回 owner。

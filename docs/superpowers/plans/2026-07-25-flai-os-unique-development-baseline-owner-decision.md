# FLAi-OS 唯一开发基线 owner 决策记录（2026-07-25）

> 状态：**ACTIVE / OWNER-ACCEPTED DECISION / NOT_IMPLEMENTATION_AUTHORIZATION**
>
> `decision_ref = flai-os-unique-development-baseline-001@1`
>
> `candidate_base_sha = ec43768ff1ad2cb6bc3e571486bfda2d04c35780`
>
> `human_owner = JerryKogami` 已在当前 Codex 任务中具名接受选项 C，并绑定接受前候选文档：
> - `document_sha256 = 971fcc8884afbede27241721e287685e559f9d558897f3fcbd02f8f26d5b73fd`；
> - `patch_digest = c2c6a1f436cb890fcd3b74c817b775ce127af2b7e34a2c4de1cf8aaa63eb7193`。
>
> 决策对象：为后续工作确定唯一开发基线，同时保留历史候选线的供体与取证价值。
> 该具名接受是项目 owner 的摘要绑定裁决，不是密码学签名或组织生产签发；
> `activation_document_commit = COMMIT_CONTAINING_THIS_ACCEPTANCE_RECORD`。
> 本裁决不授权 Stage D、PoC、依赖引入、生产上线、Schema 变更、运行时代码移植、
> 分支删除、push 或 merge。

## 1. 一句话裁决

**已接受：把 `origin/main@ec43768ff1ad2cb6bc3e571486bfda2d04c35780` 确定为本次
裁决时点的唯一开发基线；**
所有新工作项从刷新后的 `origin/main` 创建隔离分支。现有 V0.2、Stage C、Workspace Shell、
safe-auto、Agent facts 等分支全部降为 `DONOR_ONLY / EVIDENCE_ONLY`，不得整线合并或直接
改称“事实主线”；需要的资产按另冻工作项、显式 allowlist 和独立验证逐片移植。

这不是选择“旧代码路线”，而是选择一个唯一、可验证、可回退的集成起点。V0.2 的已接受
方向继续有效，后续通过受控移植进入 main，而不是让任一历史混合分支反向接管代码真相。

## 2. 已验证的当前代码真相

### 2.1 Git 与 SSOT

- GitHub 代码真相：`origin/main@ec43768ff1ad2cb6bc3e571486bfda2d04c35780`。
- tree：`759e4f1dee88de1f34a725f7c145dd5b32239960`。
- PR #9 已将以下两份 owner 接受文档合入 main：
  - `2026-07-25-flai-os-takeover-status.md`；
  - `2026-07-25-composable-stack-vs-kernel-direction-review.md`。
- 当前方向：**受限选项 2**；FLAi Control Kernel 保持唯一控制面，第三方组件只可在
  明确 Port 边界内另行申请评估。

### 2.2 当前 main 的完整验证

Codex 在与上述 `origin/main` tree 完全一致的干净隔离工作树执行：

```bash
env UV_OFFLINE=1 bash scripts/verify_all.sh
```

结果：

- frontend production build：PASS；
- Python：`1063 passed, 16 warnings`；
- frontend Node：`29 passed, 0 failed`；
- 仓库声明的 19 组浏览器 E2E：全部 PASS；
- 最终 `verify_all.sh` exit code：`0`。

环境与诚实边界：

- 第一次运行在新工作树因缺少 `frontend/node_modules`，在 build 阶段以
  `vite: command not found` / exit `127` 停止，未进入代码测试；
- 复核主工作树与候选工作树的 `frontend/package.json`、`package-lock.json` 摘要一致后，
  仅复用既有本地依赖目录重新运行，没有新增或升级依赖；
- package hash：
  `bcaf55fc7f36e85e203bd5c3ca6c73acb55bb1472edb7e558d8fcab6416fddf7`；
- package-lock hash：
  `c2dd2e59b4b8ba3afd8429fc28d7cbecd3230ba55364b5cf5d95c122c830ccbe`；
- build 有既有的 `chunk > 500 kB` 警告，不影响退出状态；
- E2E 重写了隔离工作树中的 78 个受控截图，Codex 确认变化全部位于 `docs/reviews/`
  后恢复至 HEAD；最终工作树 clean，主工作树用户资产未受影响。

这个结果证明当前 main 是一个可复算的开发起点；它不替任何候选分支补测试或准入票据。

## 3. 候选线事实对比

所有计数均以刷新后的 `origin/main@ec43768` 为比较对象。

| 候选线 | 与 main 的关系 | 变更范围 | 判断 |
|---|---|---|---|
| `origin/codex/flai-v02-foundation@9023776` | merge-base=`7523edf`；main 独有 2，候选独有 2 | 67 文件，约 22,028 additions；含 62 文档、3 个 Stage C Adapter 源文件、2 个测试 | V0.2 权威文档和 observer Adapter 的重要供体；不是纯文档线，不可直接称唯一基线 |
| `origin/codex/desktop-workspace-shell-research-v1@007d9d6` | `flai-v02-foundation` 是其祖先；main 独有 2，候选独有 36 | 135 文件，34,824 additions；120 个 `docs/` 文件、14 个 `frontend/` 文件、`CONTEXT.md` | 含 V0.2、Stage C 原型和大量 Kimi dispatch/失败重派记录；整线升格会把产品资产与过程账本捆绑 |
| `origin/codex/v02-mainline-consolidation@8b5d9d9` | merge-base=`e504595`；main 独有 82，候选独有 10 | 143 文件，19,232 additions / 1,310 deletions；混合 backend、frontend、agents、tools、tests、docs | 与当前 main 深度分叉；只能作为逐提交代码供体，禁止整体 rebase/merge 后冒充基线 |
| `origin/codex/agent-fact-projection-ui@52c3856` | merge-base=`7523edf`；main 独有 2，候选独有 28 | 320 文件，81,555 additions / 1,312 deletions | 已有独立验收价值，但范围远超本次基线裁决；保持供体/取证线 |
| `origin/codex/integrate-safe-auto-dag@567de2d` | merge-base=`e504595`；main 独有 82，候选独有 6 | 83 文件，14,360 additions / 457 deletions | 保留被回撤 safe-auto DAG 的完整证据；不是当前主线候选 |

### 3.1 为什么不选 `desktop-workspace-shell-research-v1`

它与 V0.2 产品方向最接近，但不是单一产品切片：

- 前 5 个提交是 V0.2/F0/内外网双轨设计；
- 接着 5 个提交是 Stage C 原型与返工；
- 后续包含 Workspace Shell 研究、多个 freeze、dispatch、retry、fail-closed observation、
  acceptance manifest 和停止记录；
- 其中过程账本有审计价值，但不应全部进入日常开发基线。

正确做法是把它视作按 commit/blob 精确取材的供体，而不是把 36 个提交整体升格。

### 3.2 为什么不选 `v02-mainline-consolidation`

该线包含有价值的 vision fail-closed、safe-auto、验证门和 UI 信任体系改动，但它从
`e504595` 分叉，已落后当前 main 82 个提交。整体提升会把多项尚未逐项接受的运行时代码、
测试、文档编号双轨和历史整理提交一起带入，冲突与假绿风险都过高。

正确做法是逐个工作项重新评审其目标、diff 和当前 main 适配性；必要时重新实现，而不是
默认 cherry-pick。

## 4. owner 裁决选项

### 选项 A：把 `desktop-workspace-shell-research-v1` 直接升格为开发基线

- 优点：V0.2 与 Stage C 资产最集中。
- 缺点：产品资产、过程账本和多次失败重派捆绑；相对 main 为 36 个提交、135 个文件。
- 裁决建议：**REJECT**。

### 选项 B：把 `v02-mainline-consolidation` 直接升格为开发基线

- 优点：含若干经过局部验证的代码硬化和测试。
- 缺点：落后 main 82 个提交，运行时代码范围大，无法用既有局部回归证明整线可合。
- 裁决建议：**REJECT**。

### 选项 C（已接受）：当前 main 为唯一基线，候选线全部转为受控供体

- `origin/main` 是唯一代码真相与新工作项起点；
- 每个新分支必须从当时刷新后的 `origin/main` 创建；
- donor commit/blob 只作为输入，不自带实现授权或测试继承；
- 移植必须有独立工作项、文件 allowlist、基线 SHA、验证命令、Stop-if 和 owner 门；
- 不删除任何候选分支，直到其资产进入迁移账本并另获授权。

owner 裁决：**ACCEPTED**。

## 5. 选项 C 已接受并立即生效的规则

owner 具名接受选项 C 后：

1. `origin/main@ec43768ff1ad2cb6bc3e571486bfda2d04c35780` 成为此次裁决时点的唯一开发基线；
   后续以刷新后的 main tip 连续演进，不长期钉死在该 SHA。
2. `codex/flai-v02-foundation`、`codex/desktop-workspace-shell-research-v1`、
   `codex/v02-mainline-consolidation`、`codex/agent-fact-projection-ui`、
   `codex/integrate-safe-auto-dag` 全部标记为 `DONOR_ONLY / EVIDENCE_ONLY`。
3. 上述标记不等于废弃或删除；它只禁止“整线直接升格”和“以候选线替代 main”。
4. 当前接手 SSOT 中“owner 尚未裁决唯一后续开发基线”的缺口已关闭；包含本记录的最小
   激活提交同步更新该段，未改写其他历史证据等级。
5. 受限选项 2、Stage D 冻结、F0 `0/7 UNASSIGNED`、production `NO-GO` 等边界保持不变。

## 6. 不随本裁决自动获得授权的后续工作

即使选项 C 被接受，以下事项仍须另冻工作项：

1. **V0.2 权威文档移植**：从 `215c5ce`、`9023776`、`fb7e5a2`、`58bb0ad`、
   `9220cc3` 中建立显式文档 allowlist，解决 `CONTEXT.md` 与 ADR 编号冲突后再提 PR。
2. **Stage C 原型移植/重建**：对 `547cb42..0d095df` 重新定义 build、fixture、
   observer-contract 和视觉 E2E 门；不得把 prototype 绿灯当生产验收。
3. **Workspace Shell 研究材料归档**：区分产品蓝图、有效评审证据与 dispatch 过程日志，
   不把全部工作项账本铺进普通开发上下文。
4. **运行时代码供体评审**：`31efabb`、`c9b03e4`、`0002a33`、`c824fb6`、
   `b69eac4` 逐项比较当前 main；禁止批量 cherry-pick。
5. **分支清理**：不在本裁决范围内。

推荐的第一个后续工作项是：

```text
flai-v02-authority-docs-port-codex-001@1
```

它应是文档优先、无运行时代码、无生产 Schema 变化的受控移植；仍需 owner 另行冻结与授权。

## 7. owner 接受记录

- `human_owner`：`JerryKogami`；
- `decision_ref`：`flai-os-unique-development-baseline-001@1`；
- `accepted_option`：`C`；
- `accepted_document_sha256`：
  `971fcc8884afbede27241721e287685e559f9d558897f3fcbd02f8f26d5b73fd`；
- `accepted_patch_digest`：
  `c2c6a1f436cb890fcd3b74c817b775ce127af2b7e34a2c4de1cf8aaa63eb7193`；
- `acceptance_channel`：当前 Codex 任务中的 owner 具名消息；
- `activation_scope`：最小文档激活提交；
- `explicitly_not_authorized`：Stage D、PoC、依赖引入、运行时代码移植、分支删除、
  生产上线、push、merge。

---

*ACTIVE / OWNER-ACCEPTED DECISION · 2026-07-25 · 选项 C 已生效。
本文不构成实现、依赖、阶段推进、运行时代码移植、分支删除或生产授权。*

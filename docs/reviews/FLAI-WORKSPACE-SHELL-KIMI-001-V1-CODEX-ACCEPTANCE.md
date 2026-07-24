# `flai-workspace-shell-kimi-001@1` Codex 接受前证据包

> 复核日期：2026-07-24（Asia/Shanghai）
> 人工接受人：`JerryKogami`
> Codex 权限：只读复核，不代替人工接受
> 当前结论：`REWORK_REQUIRED_NOT_ACCEPTABLE`
> 候选等级：`SOURCE_CANDIDATE_NOT_INTERNAL_RELEASE`

## 1. 结论

不建议 JerryKogami 接受当前候选。

Kimi 已经完成实现、提交和 `DevelopmentHandoffV1` 草案。候选保持在冻结文件范围内，没有生产
Schema、API、路由、Store、Vite production input 或依赖变化；204 个 Node 测试、59 个视觉 E2E
断言、17 张截图和全仓门禁均能通过。

但是，独立复核证明这些绿灯没有覆盖若干冻结合同本身：

- URL 参数实现成 `form=`，冻结合同要求 `reality=`；
- 10 个冻结 `data-testid` 只实现 2 个；
- 工作信任色从锁定的 clay 改成靛蓝，并新增 `synthetic` 信任槽；
- 无效观察仍被直接渲染进“执行历史”；
- 网络账本在每次导航时清零，可形成假绿；
- Rail 可在当前任务仍在运行时显示“已完成”。

这些都是源候选接受前必须关闭的 P1。通过测试只能证明“当前测试描述的行为能够运行”，不能证明
冻结合同已经满足。

## 2. 精确候选

| 字段 | 值 |
| --- | --- |
| Work item | `flai-workspace-shell-kimi-001@1` |
| Work item digest | `sha256:160337f0556ca231a472bff553f2925ce9c35f8b94fdaf79f029ea3858199266` |
| Base SHA | `71ecc9eadd457dfe03d2737d112f727b4a2183fa` |
| Final SHA | `47d191cb4799ec57f4739b4d1c709f490481fe77` |
| Branch | `codex/kimi-workspace-shell-v1` |
| Patch SHA-256 | `f7596af1c70396ba222141dd0be57e562419b4b0b0298f069c3b23632094ae38` |
| Kimi session | `session_1ee76ca9-2967-40b4-98f0-18d19a171910` |
| Runtime identity | `DECLARED_NOT_VERIFIED` |
| Assistant dispatch receipt | `null` |
| Push / merge / release | 均未发生 |

冻结控制件：

- `docs/work-items/flai-workspace-shell-kimi-001-v1.freeze.json`
- `docs/work-items/flai-workspace-shell-kimi-001-v1.prompt.md`

Kimi 的完整 `DevelopmentHandoffV1` 草案存在于本地 session wire 的最终消息中：

```text
/Users/Zhuanz/.kimi-code/sessions/
wd_flai-kimi-workspace-shell.clhxzm_75b95e865c76/
session_1ee76ca9-2967-40b4-98f0-18d19a171910/
agents/main/wire.jsonl
```

草案诚实披露没有权威 `AssistantDispatchReceiptV1`，没有声称已接受、已集成或已内网发布。

## 3. 文件范围与生产边界

最终 diff 恰好 9 个文件，全部在冻结白名单内：

```text
frontend/e2e/workspace_shell_prototype_acceptance.py
frontend/src/prototypes/workspace-shell/NOTES.md
frontend/src/prototypes/workspace-shell/WorkspaceShellPrototype.vue
frontend/src/prototypes/workspace-shell/fixtures.js
frontend/src/prototypes/workspace-shell/main.js
frontend/src/prototypes/workspace-shell/workspace-shell.css
frontend/src/prototypes/workspace-shell/workspace-view.js
frontend/src/prototypes/workspace-shell/workspace-view.test.js
frontend/workspace-shell.html
```

通过：

- worktree clean；
- base 是 final 的祖先；
- patch digest 独立重算一致；
- `backend/**`、API、router、store、Schema、ADR、scripts、package/lockfile、Vite config 均未改；
- 原型源码静态扫描无 `fetch`、XHR、WebSocket、EventSource、beacon、service worker 或外部 URL；
- `npm run build` 成功；
- `dist/index.html` 存在；
- `dist/workspace-shell.html` 不存在。

因此文件范围和生产构建边界为 `PASS`。

## 4. 验证结果

### 4.1 正向门禁

| 检查 | 结果 |
| --- | --- |
| `git diff --check` | PASS |
| `node --test` | 204 pass / 0 fail |
| 96-case fixture matrix | 96/96 执行通过 |
| `npm run build` | PASS |
| Production entry boundary | PASS |
| Workspace Shell Playwright | 59/59 PASS |
| Fresh screenshots | 17/17 |
| 全仓 Python | 1063 pass |
| 既有浏览器套件 | 19/19 |

本次 Codex 新鲜截图目录：

```text
/private/tmp/flai-workspace-shell-codex-rerun.id8whk
```

截图集合摘要：

```text
sha256:1571bb0143e2dc619137530de0ab09c375d12b24912fbdf8ec762e9d0daa17e2
```

### 4.2 反向负例

#### URL 合同

真实浏览器结果：

```text
?reality=MOCK -> data-reality-form=REAL
?reality=FAKE -> data-reality-form=REAL
?form=MOCK    -> data-reality-form=MOCK
?form=FAKE    -> data-reality-form=UNKNOWN
```

冻结合同是 `reality=`，实现与测试共同使用 `form=`，所以现有 E2E 对错误接口自洽地通过。

#### 网络账本

使用测试自己的 `INIT_SCRIPT`，在第一页主动调用被拒绝的 `fetch`：

```text
before_navigation.fetch = 1
after_navigation.fetch  = 0
```

`window.__wsNet` 每次导航都会重新创建，而测试在多次导航后只读取最后一页。较早页面上的被拒绝
fetch/XHR/beacon/service-worker 尝试会消失，现有“零应用网络”断言可假绿。

#### 无效观察

真实浏览器打开 `docx:observation-invalid@REAL`：

```text
focus = gap
historyCount = 1
history = 06:00:17 / 计算 / 正在处理：气动周报-草稿.docx
```

右侧正确 fail closed，但中央历史仍直接消费未通过 projector 的原始事件。

#### 信任色

工作态动作卡真实计算色：

```text
rgb(61, 79, 158)  # #3d4f9e，靛蓝
```

仓库红线要求 clay 工作槽。`synthetic` 应当是来源/现实标记，而不是新增信任槽。

## 5. 阻断发现

### P1-1：URL 合同错误

- 冻结：`reality=REAL|MOCK|TEST|UNKNOWN`，缺失或非法必须 fail closed。
- 实现：`WorkspaceShellPrototype.vue:24-35` 读取 `form`，缺省为 REAL。
- 测试：`workspace_shell_prototype_acceptance.py:94-99` 也生成 `form=`。

### P1-2：DOM 合同不完整

冻结的 10 个 `data-testid`：

```text
workspace-shell
workspace-rail
continuous-work-surface
focus-surface
workspace-composer
action-glyph
reality-badge
execution-state
instruction-queue
delivery-state
```

候选只有 `action-glyph` 和 `reality-badge` 两个精确命中，其余使用了另一套名字或完全缺失。

### P1-3：信任五槽被重定义

- `workspace-shell.css:3-25` 把工作色定义为靛蓝；
- `workspace-view.js:45-53` 把信任状态改成
  `active/attention/terminal/fail/unverified`；
- `workspace-view.js:82-86` 又引入第六个 `synthetic` badge slot。

允许 REAL 绿和真人 teal 在合成原型中不可达，但不能删除或重新发明冻结语义。

### P1-4：invalid 事件绕过安全投影进入历史

- `fixtures.js:225-230` 构造已知无效事件；
- `workspace-view.js:179-187` 直接从原始 `events` 生成 history；
- `WorkspaceShellPrototype.vue:316-325` 将它渲染出来。

这与“只展示投影可证明的事件”及 fail-closed 不一致。

### P1-5：网络 E2E 可假绿

- `workspace_shell_prototype_acceptance.py:197-201` 在每个 document 初始化账本；
- `:604-618` 只读取最后一个 document 的账本。

必须使用跨导航持久账本，并加入“早期页面故意触发一次 fetch，最终测试必须变红”的负控。

### P1-6：Rail 生成冲突完成事实

`WorkspaceShellPrototype.vue:69-73` 把三种工作流状态硬编码。`cfd:running` 页面左侧显示
“已完成（合成）”，中央和右侧同时显示仍在处理。这正是用户要求避免的状态焦虑和假完成。

关键视觉证据：

- `/private/tmp/flai-workspace-shell-codex-rerun.id8whk/core-cfd-running.png`
- `/private/tmp/flai-workspace-shell-codex-rerun.id8whk/docx-observation-invalid.png`

## 6. 非阻断但必须披露

### P2-1：NOTES 文件数量错误

`NOTES.md` 写“仅 8 个白名单内文件”，实际为 9 个。

### P2-2：开发期网络影响未知

Kimi 工具日志显示执行了：

```text
cd frontend && npm ci --no-audit --no-fund
```

没有 `--offline`，且没有 OS 级网络 witness。package/lockfile 未变，后续离线验证通过，但这不能反证
当时没有访问 registry。结论只能是 `UNKNOWN`。

### P2-3：读取范围有轻微漂移

完整 Kimi tool log 还读取了冻结 read-only allowlist 外的：

- `frontend/src/prototypes/stage-c/main.js`
- `frontend/stage-c.html`
- `frontend/src/prototypes/stage-c/NOTES.md`

均是本仓合成原型文件，未发现 secrets、内网数据或 Open WebUI clone 访问，但需要在返工派发中收紧。

### P2-4：Handoff 只存在于 session wire

完整 handoff 草案已经返回，不是“缺失”；但它尚未成为 coordinator-owned 的耐久交接工件。

## 7. 两轴独立评审

### Standards

独立 Standards 评审发现 5 个 P1：

- 信任槽和信任色硬违反；
- invalid 原始事件泄漏；
- Rail 自造冲突完成状态；
- 网络账本不能证明全过程零调用。

另有 1 个 P2 判断项：单个 Vue SFC 承担过多 UI 职责。该代码味道不作为本轮阻断。

### Spec

独立 Spec 评审发现：

- P1：URL、testid、信任色、invalid history、网络账本；
- P2：Rail 状态与 NOTES 数量。

Spec 评审最初把 handoff 标为缺失；主审随后在 Kimi session wire 最终消息中找到完整草案，因此更正为
“存在但未持久化”的 P2。

## 8. JerryKogami 人工接受清单

当前请不要选择“接受”。建议选择：

```text
REWORK_REQUIRED
```

冻结 `flai-workspace-shell-kimi-001@2` 前，必须把以下内容写进新 digest：

1. 精确使用 `reality=`；缺失、空值、非法值全部 fail closed 到 UNKNOWN；
2. 实现并机械检查冻结的 10 个 `data-testid`；
3. 复用 clay / REAL green / human teal / fail red / unverified amber 五槽；
4. synthetic 只作为 source/reality 标签，不成为第六信任槽；
5. invalid、identity mismatch、reality conflict 等 projector 拒绝输入不得进入 history；
6. 网络账本跨导航持久，加入会让旧实现必红的主动负控；
7. Rail 当前项状态来自同一 observer projection；
8. 修正 NOTES 文件计数并持久化新的 `DevelopmentHandoffV1`；
9. 返工后重新运行 96-case、视觉 E2E、全仓门禁和 Codex 反向探针。

JerryKogami 仍是唯一接受人；Codex 和 Kimi 都不能自行把返工结果标记为已接受。

## 9. 交付物

- 本报告：
  `docs/reviews/FLAI-WORKSPACE-SHELL-KIMI-001-V1-CODEX-ACCEPTANCE.md`
- 机器可读清单：
  `docs/reviews/FLAI-WORKSPACE-SHELL-KIMI-001-V1-CODEX-ACCEPTANCE-MANIFEST.json`
- 新鲜视觉证据：
  `/private/tmp/flai-workspace-shell-codex-rerun.id8whk/`

本证据包没有修改 Kimi 候选、生产 Schema 或生产接口，也没有 push、merge、签发或发布。

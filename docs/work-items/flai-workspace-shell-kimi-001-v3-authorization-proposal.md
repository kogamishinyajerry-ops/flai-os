# `flai-workspace-shell-kimi-001@3` 最小重派授权提案

状态：`OWNER_APPROVAL_REQUIRED / NOT_FROZEN / NOT_DISPATCHED`

## 为什么需要新版本

`@2` 在开始修改前读取了两个未列入冻结只读清单的合成原型启动文件，触发明确的
fail-closed Stop Condition。运行已经中止，执行分支仍停在原始 base，没有源码修改、
测试结果或 `DevelopmentHandoffV1`。

## @3 相对 @2 的唯一范围变化

只把以下两个现有文件加入不可变只读输入：

- `frontend/workspace-shell.html`
- `frontend/src/prototypes/workspace-shell/main.js`

最终 `@3` 提示词将使用穷举式只读白名单，不再保留“传递依赖可自行扩读”的模糊例外。

以下内容全部不变：

- 六个 P1；
- 六个源码写文件；
- base `47d191cb4799ec57f4739b4d1c709f490481fe77`；
- 零新依赖、零生产接口、零 Schema 变更；
- 外网纯合成数据边界；
- Kimi 完成后由 Codex 独立复核，再交 JerryKogami 人工接受。

## 已完成的无副作用准备

- 新分支：`codex/kimi-workspace-shell-v3`
- 新隔离 worktree：`/private/tmp/flai-kimi-workspace-shell-v3.MHDHC6`
- 依赖：由 Codex 使用 `npm ci --offline` 预置，worktree 保持 clean
- Playwright Chromium：`149.0.7827.55`，离线启动探针通过
- 新截图目录：`/private/tmp/flai-kimi-workspace-shell-v3-evidence.C5A3NE`，为空且位于仓库外
- 新空 skills 目录：`/private/tmp/flai-kimi-empty-skills-v3.haGvfE`

这些准备不构成冻结或派发授权。

## 授权效果

JerryKogami 回复“批准 @3 最小重派”后，Codex 才会：

1. 生成并双实现校验完整 `@3` freeze/prompt digest；
2. 再做一次只读冻结审计；
3. 启动一个全新 Kimi K3 会话，不恢复 `@2` 会话；
4. 只允许六文件返工与既定验证；
5. 对候选重复范围、网络负控、96-case、视觉 E2E、信任色及生产边界独立复核；
6. 形成 JerryKogami 人工接受包。

该授权不包含 push、merge、生产集成、人签、内网发布或 Schema 修改。

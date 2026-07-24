# `flai-workspace-shell-kimi-001@4` 最小执行协议返工提案

状态：`OWNER_APPROVAL_REQUIRED / NOT_FROZEN / NOT_DISPATCHED`

## 为什么需要新版本

`@3` 已在红测阶段按 fail-closed 中止。Kimi 的源码读取和七次编辑都在白名单内，但它把
`node --test` 输出重定向到未授权的 `/tmp/red-unit.log`，触发冻结 Stop Condition。

本次运行没有提交、没有 `DevelopmentHandoffV1`、没有截图，也没有可接受源码候选。隔离工作树
只保留一份未提交的红测修改作为审计现场，后续不得续跑或提升。

## @4 相对 @3 的唯一实质变化

不改变六个 P1、六个源码写文件、穷举只读清单或生产边界，只收紧执行协议：

- 测试、构建和审计输出只允许通过工具的 stdout/stderr 返回；
- 禁止执行器使用 `>`、`>>`、`tee` 或其他方式创建测试日志、审计日志或临时结果文件；
- 不增加通用 `/tmp` 或 scratch 写权限；
- 明确区分六文件“源码写范围”和原提示词已经强制要求的验证产物：
  `npm run build` 仅可生成被忽略的 `frontend/dist/**`，视觉 E2E 仅可写入指定截图目录；
- 开始一个新工作树和全新 Kimi 会话，禁止恢复或续跑 @3。

这是一项执行协议修正，不是产品范围扩展。

## 不变项

- 六个 P1：URL、十个 testid、信任色、96+stale history、跨导航网络账本、Rail 3×8；
- base `47d191cb4799ec57f4739b4d1c709f490481fe77`；
- 零新依赖、零生产接口、零 Schema 变更；
- `EXTERNAL_DEVELOPMENT / SYNTHETIC_ONLY / NONE internal data`；
- Kimi 完成后仍由 Codex 独立复核，再交 JerryKogami 人工接受；
- 不包含 push、merge、生产集成、人签或内网发布。

## 已完成的无副作用准备

- 新分支：`codex/kimi-workspace-shell-v4`
- 新隔离工作树：`/private/tmp/flai-kimi-workspace-shell-v4.2ZYv0h`
- 固定 base：`47d191cb4799ec57f4739b4d1c709f490481fe77`
- 依赖：Codex 已用 `npm ci --offline` 预置，工作树 clean
- 新截图目录：`/private/tmp/flai-kimi-workspace-shell-v4-evidence.LzDXSx`，为空
- 新空 skills 目录：`/private/tmp/flai-kimi-empty-skills-v4.uiFQyN`

这些准备不构成冻结或派发授权。

## 授权效果

JerryKogami 回复“批准 @4 最小执行协议返工”后，Codex 才会：

1. 生成完整 `@4` freeze/prompt，并用 Python/Node 双实现校验 digest；
2. 做只读冻结审计；
3. 启动一次全新 Kimi K3 会话；
4. 实时审计源码范围、直接文件写入、网络和工具调用；
5. 若产生六文件候选，再执行 Codex 独立 96-case、视觉 E2E、信任色和生产边界复核；
6. 形成 JerryKogami 人工接受包。

该授权仍不允许把源码候选标记为内部发布或生产就绪。

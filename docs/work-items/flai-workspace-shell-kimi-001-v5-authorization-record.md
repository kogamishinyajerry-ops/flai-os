# `flai-workspace-shell-kimi-001@5` 最小重派授权记录

状态：`OWNER_APPROVED / FREEZE_PENDING / NOT_DISPATCHED`

## 授权

Human owner `JerryKogami` 已明确回复：

> 批准 @5 最小重派

该授权只允许生成并冻结 `@5` 载荷，以及在一个全新隔离工作树中启动一次全新 Kimi K3
会话。它不授权 push、merge、生产集成、人签、内网发布、Schema 变更或任何真实数据访问。

## 为什么需要 `@5`

`@4` 已由 Codex 按 fail-closed 终止，没有源码候选或 `DevelopmentHandoffV1`：

1. 执行器把 red E2E 放到后台运行，并在红测完成前编辑了产品实现，无法证明
   “对未修改的 `@1` 实现先跑红”；
2. 执行器主动读取了明确禁止选择或检查的工具内部 `output.log`；
3. 多条 Node 红测命令通过未启用 `pipefail` 的管道展示结果，退出状态不足以作为可靠见证。

`@4` 的脏工作树和 17 张 red-run 截图只保留用于审计，禁止续跑、复制或晋升。

## `@5` 相对 `@4` 的唯一实质变化

六个 P1、六个源码写文件、穷举只读清单、生产边界和验证目标全部不变。只收紧执行顺序：

- 红测、绿测、构建和审计命令必须前台同步运行；禁止 `run_in_background`、尾随 `&`、
  `nohup` 或任何后台任务；
- 完成全部测试修改后、产品实现首次编辑前，源码 diff 只能包含 unit test 和 E2E 两个测试文件；
- unit red 和 E2E red 都必须以直接、无管道命令返回非零退出状态后，才允许编辑产品实现；
- 禁止主动定位、读取、grep、复制或引用 `~/.kimi-code/**/tasks/**/output.log` 等工具内部状态；
- 测试、构建和审计命令禁止 `|`、`2>&1`、`head`、`tail` 或二次过滤；结果只取当前工具调用
  的直接 stdout/stderr 和退出状态。

这是一项执行协议修正，不是产品范围扩展。

## 不变项

- 六个 P1：URL、十个 testid、信任色、96+stale history、跨导航网络账本、Rail 3×8；
- base `47d191cb4799ec57f4739b4d1c709f490481fe77`；
- 零新依赖、零生产接口、零 Schema 变更；
- `EXTERNAL_DEVELOPMENT / SYNTHETIC_ONLY / NONE internal data`；
- Kimi 完成后仍由 Codex 独立复核，再交 JerryKogami 人工接受。

## 已完成的隔离准备

- 新分支：`codex/kimi-workspace-shell-v5`
- 新隔离工作树：`/private/tmp/flai-kimi-workspace-shell-v5.QjU0x6`
- 固定 base：`47d191cb4799ec57f4739b4d1c709f490481fe77`
- 依赖：Codex 已用 `npm ci --offline` 预置，工作树 clean
- 新截图目录：`/private/tmp/flai-kimi-workspace-shell-v5-evidence.mGixLe`，为空
- 新空 skills 目录：`/private/tmp/flai-kimi-empty-skills-v5.ipfzHH`
- Chromium 离线启动探针：`149.0.7827.55`

## 后续门禁

Codex 将先冻结并做双轴只读评审，再派发一次 Kimi 会话并实时审计。只有出现完整、
干净、六文件内的候选，才会继续独立 96+stale、视觉 E2E、信任色、构建和
`scripts/verify_all.sh` 复核。成功结果仍只能标记为
`SOURCE_CANDIDATE_NOT_INTERNAL_RELEASE`。

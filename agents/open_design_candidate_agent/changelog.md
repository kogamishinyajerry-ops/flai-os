# 变更记录

## 0.1.2（2026-07-20）

- `0.1.1 → 0.1.2`：P2.6 会话壳层更新后重新锁定 App.vue SSOT 字节、引用包与 fixture
  request/response/bundle 哈希；同步更新 input/output schema、eval 固定值和
  `open_design_fixture_generate` 工具依赖版本。
- 改动类型：schema、eval、tool dependency；仍为 `mock=true` 的 machine-only contract
  fixture，不改变 `candidate_only`、零发布和人工审核边界。

## 0.1.1（2026-07-19）

- 显式更新 Open Design fixture snapshot：重锁 App.vue SSOT 字节哈希，并将不可变 fixture id 升为 `flai-task-review-assets-v2`。
- 引用包结构、allowlist token 值与信任色约束未变，因此 package schema 仍为 `flai-design-reference-package/v1`。

## 0.1.0（2026-07-19）

- 初版：确定性设计引用包、Open Design 四步协议 fixture、手工 machine-only HTML/SVG 契约夹具与人工审核闸。
- 明确 `mock=true`、`candidate_only=true`、`release_effect=none`、不采样。

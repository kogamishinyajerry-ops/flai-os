# Open Design Agent 可信接入方案

> 状态：Phase 1 fixture seam 已完成；P2.7 固定槽位 loopback daemon adapter 已实现为
> disabled、default-off、sensitive 的 production-shaped trial。它尚无 live daemon、角色
> 强制、专用 sidecar、Windows 或供应链 attestation，不能称为 production-ready。P2.8 已有
> 独立比较/双闸/可恢复发布状态机与 TaskDetail 并排面，但当前 internal-only 政策会
> fail-closed 拒绝 P2.7 sensitive 候选；生产目标 registry 也默认为空。
> 上游只读审计：`/Users/Zhuanz/projects/misc-projects/Open Design/open-design`，
> HEAD `e06bff69edc6d4715228214c593d3a5a1849ad11`。上游工作树有用户改动，本仓不修改它。

## 1. 产品定位

Open Design 应作为 FLAi-OS 的**设计候选生成 Agent 工具**，而不是一个可绕开工程审核的
素材目录，也不是新的判决器。它的价值是让 Agent 以明确 brief、设计系统和 skill 生成或
迭代真实设计，再把完整 artifact 拉回工程事实链。

本仓保持三条边界：

- Open Design、LLM 与 FLAi Agent 都只能提出候选；人是唯一签发者。
- P2.8 候选选择同时写入任务人签与候选 selection，不再开放通用 task review 旁路；它不等同于
  发布、替换源码或晋升金图。
- release 批准是第二项独立具名人工事实；两项可由同一 username 作出，但动作、时间和证据不合并。
  fixture 与生产工具永不原地翻牌。

## 2. 经源码核对的上游公开形状

Open Design daemon 的公开 MCP 面支持：

```text
create_project (write)
  → start_run (write; Open Design 启动自己的设计 Agent)
  → get_run (read/poll terminal state)
  → get_artifact (read complete entry + referenced bundle)
```

上游另有 `list_skills`、`list_plugins`、`get_project`、`list_files`、`get_file`、
`create_artifact` 与 `write_file` 等公开工具。本集成只依赖公开 daemon/MCP 合同，不导入
Open Design 私有模块，不代理其终端，不复制凭据，也不把 FLAi 输入直接写进上游源码树。

## 3. Phase 1 已建立的 fixture 信任链

Phase 1 新增独立工具 `open_design_fixture_generate` 与 draft Agent
`open_design_candidate_agent`。P2.6 会话壳层更新 App.vue 后，fixture 以 0.1.2 补丁版本再次
锁定 source bytes；不可变 snapshot identity 仍为 `flai-task-review-assets-v2`，package shape
与 24 个 allowlisted token 值未变化：

```text
FLAi 三份设计 SSOT
  → flai-design-reference-package/v1
  → hash-fixed request
  → machine-only mock protocol fixture
  → 校验 request / package / response / candidate SHA-256
  → 写入候选 + provenance
  → task waiting_review
  → 具名工程师 approve/reject
```

设计引用包不是第二套设计系统。它只投影候选确实需要的 allowlisted token，并锁定：

- `frontend/src/App.vue`：light token 实值；
- `docs/design/UI-PARADIGM.md`：产品骨架与交互范式；
- `docs/design/MOTION-SYSTEM.md`：信任色和动效边界；
- 三份源文件的精确 SHA-256、token allowlist、五槽信任色约束与
  `human_is_only_signer=true`。

任一源缺失、哈希漂移、token 缺失/重复、request/response/candidate 字节漂移、schema
不符或协议轨迹错误都 fail-closed，零候选落盘。成功只生成 internal 候选与 provenance，
Runtime 因 `requires_human_review=true` 停在 `waiting_review`；不会产生 `task_completed`。

本轮 HTML/SVG 是 **machine-only contract fixture**：显式 `mock=true`、不进入产品 UI
渲染或发布、不代表 Open Design 真实运行结果，也不构成视觉 QA。它只证明 FLAi 能验证、
登记和审核这类 artifact。生产设计必须由真实 Open Design run 生成并另行浏览器比较。

本次 v2 fixture snapshot 的固定信任锚为：

- canonical request：`cb520812fe54090f5c2679eb6a746eda36d96be356ba650363c8dacad8fa1103`；
- design reference package：`b422a2671c30ff0ec7be2a7bbb36d0f8bae60d5be774bed4959671f4a5debbd3`；
- fixture bundle：`022e3fd28f61b59fba8bf974c9e2a960530ccbebf0f27ec514c5a817c12d0790`；
- response payload：`9f48b28bc8e4c22e712bbf634d97b0013df8e954565aa3f00065a1477daa92da`；
- HTML candidate：`e1242ccccb30758c184d798f50edc2b3fc0f38508c3f70f6a7c0238fa5e27db1`；
- SVG candidate：`8424d13080e3b1d79cef1e9a60a0e7a1a019d8f3a7bea4103fe3c523534bbd48`。

`flai-design-reference-package/v1` 保持不变，因为机械对比证明 allowlist、24 个 token 值、
信任色约束与 package shape 均未变化；变化的是受认证的 App.vue source bytes。旧 package
digest 的请求有专门 fail-closed 回归，不能被新 fixture 静默接受。

这些值只锚定当前机器协议夹具；真实 Open Design run 必须产生独立 run/artifact provenance，
不得复用上述 `mock=true` 身份。

## 4. P2.7：固定槽位 loopback daemon adapter

P2.7 已新增独立 `open_design_daemon_generate`（`mock=false`）与 disabled/L0
`open_design_daemon_candidate_agent`；fixture manifest 没有被伪装升级。Agent manifest 的
`admin_only` 只是计划性元数据，当前 Runtime/API 不强制消费；create/batch/teams 角色 gate
覆盖前不得改为 draft/active。当前诚实名称是“窄生产形态试运行”，不是通用设计提示入口或
生产就绪 adapter。

其外部输入合同被刻意收窄：只接受三个 `asset_slot` 与七个 comparison slot 枚举；没有自由
brief/prompt、附件、文件或 knowledge。`task_id` 只能由已验证 Runtime context 注入，payload
携带它会被拒绝；该 identity 只参与 project id 哈希，不进入 prompt。每个 intent 由 adapter
内置。但固定 FLAi 输入不能证明 Open Design ambient memory、app custom instructions 或宿主
文件未被读取，因此 tool 恒声明 `output_classification=sensitive`；
`execution_trust=untrusted_generated` 独立表达生成内容不可信。只有专用 sidecar/dataDir、可验证
ambient-context-off、最小 OS 权限和供应链 attestation 成立，并另立逐文件降密政策后，才可
讨论低于 sensitive。未来增加自由输入也必须升版并重做分级/角色政策。

adapter 默认关闭，只认 `ENABLED=1` 和 exact loopback HTTP origin；禁环境代理、redirect 与
retry。写操作前精确对账 version/channel、bind/ready/sandbox 报告、唯一 live/authenticated
Agent/请求模型，以及唯一 published design-system detail digest。上游 status 不返回实际执行
模型，所以 provenance 分开记录 `requested_model_id` 与 `model_execution_attested=false`；不得
把请求绑定写成执行模型证明。project id 来自 Runtime task+slot 的确定性哈希，POST 各只执行
一次；同一 task 冲突诚实失败，重试必须使用新 task。

产物不使用 MCP `get_artifact` 或 `/raw`。terminal success 后先验证
`open-design.run-result-package.v1` 与 `storage.kind=od-owned`，再取 exact file list；每个
`/api/projects/:id/files/<逐段编码 path>` 字节双取，最后重新列举并要求 file-list 未变化。
HTML/SVG/CSS/JSON/Markdown 走 strict UTF-8 静态策略；可见比较只接受经 signature/IHDR、
dimension、chunk CRC/allowlist、IDAT 解压长度、IEND/尾随字节检查的单帧非交错 PNG。
文本策略还拒绝重复 JSON key、active tag、event/URL-bearing attribute、entity、CSS URL/escape；
它只是保守语法 screen，不是 sanitizer 或降密器。

workflow 原子写 `open_design_daemon_candidate_bundle`，其中：

- `open_design_daemon_candidates.json`：candidate id、固定 asset slot、project/run/result-package
  provenance、captured file manifest 与 passive preview 的 raw-source/PNG 双哈希绑定；
- `open_design_daemon_provenance.json`：daemon/result/safety 证据；
- `flai_design_reference_package.json`：精确 FLAi SSOT 投影；
- `OPEN_DESIGN_DAEMON_REVIEW.md`：人审边界；
- `captured/**`：双取后锁定的原始候选字节。

Agent 输出给 pre-seal Runtime 的识别字段固定为
`review_contract=open-design-candidate/v1`、`generator_kind=open_design_daemon` 与
`candidate_manifest_sha256`；比较详情所需的 `project_id`、`run_id` 与
`result_package_sha256`、`classification=sensitive`、固定 `promotable_asset` 也由同一
manifest/output exact bind。上述字段必须在进入
`waiting_review` 前原子投影到 task metadata，不得 seal 后补写。

成功响应只声明 `real_daemon_candidate_captured=true`。失败响应不把“真实 daemon 曾发生写
操作”抹成 false：它保留 `failure_stage`、确定性 `project_id`、已知 `run_id`，并用
`unreconciled_upstream_side_effects_may_exist` 指出需要运维对账的 project/run。Tool Registry
timeout 目前不能杀死 Python thread，adapter 也没有 run cancel/reconcile；超时后 Open Design
poll 线程或 run 可能继续，故 Agent 保持 disabled，遗留对象必须由独立运维流程清理。

安全与部署约束：daemon 只绑定 loopback；认证与模型凭据留在 Open Design 进程；FLAi
事件、错误和产物 provenance 不记录 secret；每次运行使用隔离目录和最小权限。Windows
内网交付需要成对 `.sh/.ps1` 的 start/health/status/stop 脚本、固定版本、离线依赖包、
端口冲突与异常退出验收，且在实际开启 sidecar 前再获一次部署批准。

## 5. P2.8：候选比较与资产 promotion

P2.8 已建立候选解析、TaskDetail 并排比较、具名选择、独立发布双闸、append-only 账本与
intent/reconciliation。生产 `create_app` 没有 synthetic admission 逃生口：当前
role/per-file declassification policy 尚未交付，因此会正确拒绝 P2.7 sensitive manifest。
测试专用的 internal fixture 只验证状态机，不能作为真实端到端证据。

三个发布 target ID/path 是封闭 provisioning contract，但生产 `TargetRegistry` 默认为空，
不会猜测仓内图片或当前帧。部署方未来必须显式注入 exact current-frame matrix、同机本地卷、
独占写 ACL 后才能发布；未来先通过角色/降密门后，registry 仍未 provision 才会在比较创建处
返回 409。并排帧只以 `image/png`、`no-store`、`inline`、
`nosniff` 与禁执行 CSP 提供，绝不执行候选 HTML/SVG。

候选批准与 release 批准是两项独立具名事实；通用 task review 路由对 Open Design task 返回
409，不能绕过并排选择。发布前绑定 candidate/target/package hashes；崩溃恢复只有在目标
after-image 与 exact backup/quarantine 同时成立时才记 recovered commit，否则进入
`manual_intervention`。文件锁只协调遵守协议的本机进程，不对无视锁的外部写者作原子 CAS
承诺。

解除分级与 provisioning 阻断后允许形成的 UX 是：

- TaskDetail 先显示来源、package/run/artifact hashes、non-mock loopback trial/未证明生产就绪标记
  与安全扫描结果；
- 真实视觉候选转为安全截图后，在相同 viewport/state 下与当前 FLAi 页面并排比较；
- light/dark、desktop/narrow、focus、reduced-motion、error/empty/waiting_review 状态分别验收；
- 选择候选与批准发布分开；拒绝保留原因和 provenance；
- promotion 只复制经批准、哈希精确匹配的资产到明确目标，不改 token 或状态语义；
- 金图仍需显式 promotion 开关，普通 E2E 只写临时工件目录。

Open Design 可以生成新资产，但“高度统一”必须由 reference package、同 viewport 比较、
静态/浏览器契约与人审共同证明，不能由模型自述或“看起来很像”替代。

## 6. 阶段门与验证

| 阶段 | 可验收输出 | 退出门 |
|---|---|---|
| A fixture | draft agent、mock tool、reference package、候选/provenance | invalid-first tests；成功只到 waiting_review |
| B daemon trial | 独立 mock=false tool、固定槽位、loopback client、双取/static screen/provenance | Agent 保持 disabled；仍需角色 gate、专用 sidecar、live daemon、Windows 与供应链证明 |
| C compare | 已实现安全 PNG、同 viewport/state 对照与 TaskDetail 恢复入口 | 真实 sensitive 候选仍 403；未做真实用户走查 |
| D promote | 已实现 candidate→release approval→publish/rollback 状态机 | 生产 registry 默认空；只由 synthetic internal fixture 验证 |
| E deploy | Windows/offline sidecar 与运维脚本 | `.sh/.ps1` 对称、health/stop、冷启动与断连演练 |

Phase 1 定向验证：

```bash
pytest -q backend/tests/test_open_design_fixture.py backend/tests/test_runtime.py
bash scripts/verify_all.sh
```

P2.7 定向验证：

```bash
pytest -q backend/tests/test_open_design_daemon_policy.py \
  backend/tests/test_open_design_daemon_client.py \
  backend/tests/test_open_design_daemon_agent.py
```

P2.8 定向验证：

```bash
pytest -q backend/tests/test_p28_design_promotion_contract.py \
  backend/tests/test_p28_design_promotion_comparison.py \
  backend/tests/test_p28_design_promotion_storage.py \
  backend/tests/test_p28_design_promotion_deploy_gate.py
node --test frontend/tests/design_promotion.test.mjs
```

# ADR-0041：Open Design 固定槽位 loopback daemon adapter

- 状态：Accepted（disabled、default-off、sensitive 的 production-shaped trial；生产启用未批准）
- 日期：2026-07-20
- 关联：ADR-0021、ADR-0024、ADR-0035、ADR-0039

## 背景

Phase 1 的 `open_design_fixture_generate` 只证明 FLAi 能机械验证、登记并人工审核一组
`mock=true` 的手工协议夹具。它不能证明真实 Open Design daemon、真实 Agent/model、真实
project/run 或真实生成字节已经进入 FLAi 事实链。

直接把 Open Design 变成自由提示词入口会同时破坏两条边界：一是任意正文、附件或
knowledge 会形成数据外送通道；二是生成 HTML 可借 preview 执行，把“候选”混成代码
执行面。即使 FLAi 输入被收窄，锁定上游仍会拼入 daemon memory、app custom instructions，
且内层 Agent 的宿主文件权限不能由 `sandboxMode=true` 自报证明。因此输出保密分级必须为
`sensitive`；`execution_trust=untrusted_generated` 另行表达生成字节不可信，二者不能互相
替代。

## 决策

### 1. 新 tool id，绝不把 fixture 原地翻牌

新增 `open_design_daemon_generate`，恒为 `mock=false`，旧
`open_design_fixture_generate` 保持 `mock=true`。新工具仍只产生候选：

- `candidate_only=true`；
- `release_effect=none`；
- `execution_trust=untrusted_generated`；
- `production_readiness=trial_not_attested`；
- P2.8 候选选择与任务人签在同一事务形成一项具名事实；release 批准是第二项独立具名事实。
  两项可由同一 username 作出，但动作、时间和证据不合并。

### 2. 固定输入仍不降密：输出一律 `sensitive`

工具 `output_classification=sensitive`。外部 tool/Agent input 不是通用 brief：

- `task_id` 不允许出现在外部 payload，只由 Tool Registry 的 Runtime context 注入；adapter
  拒绝缺失 context 或伪造字段。它只哈希成隔离 project identity，不进入 prompt 正文；
- `asset_slot` 只允许 `task_review_summary`、`agent_activity_indicator`、
  `workflow_monitor_sidebar`；
- viewport/state/theme/locale 由七个服务端 comparison-slot 枚举给出；
- 禁止自由 `brief/prompt`、附件、文件、knowledge 和任意用户正文。

每个资产槽位的设计意图由 adapter 内置；comparison slots 必须包含固定
`default_desktop_light`。这只减少 FLAi 输入泄露面，不能证明 daemon 没有读取 ambient
memory/custom instructions/宿主文件并画入 PNG。只有专用 sidecar/dataDir、可验证 ambient
context off、最小 OS 权限与供应链 attestation 全部成立，并另立降密决策后，才可讨论低于
`sensitive`；结构扫描不是 confidentiality sanitizer。

### 3. 默认关闭并精确绑定上游身份

只有 `FLAI_OPEN_DESIGN_DAEMON_ENABLED=1` 才允许连接；未设置或 `0` 为关闭，`true/yes`
等模糊拼法拒绝。URL 只接受显式端口的
`http://127.0.0.1:PORT` 或 `http://[::1]:PORT`，拒绝 localhost、非 loopback、HTTPS、
userinfo、path、query、fragment 和缺端口。

同时必须显式配置并在写操作前精确核对：

- daemon version 与 release channel；
- bind host/port、ready 与非 shutting-down；
- daemon 报告 sandbox enabled；
- 唯一、available、auth ok、live-model catalog 中的 Agent/请求模型；上游 status 不回传
  实际执行模型，因此 provenance 明示 `requested_model_id` 与
  `model_execution_attested=false`，不伪称已证明执行模型；
- 唯一 `published` design system 及完整 detail canonical SHA-256。

HTTP client 使用 `trust_env=false`、`follow_redirects=false`，不读取代理，不跟 redirect，
没有任何自动 retry；拒绝 `Content-Encoding`，JSON/文件均流式累计并在 1 MiB/4 MiB 上界
前停止。`POST /api/projects` 与 `POST /api/runs` 各只尝试一次。

成功响应只把完成双取与策略验证的候选记为 `real_daemon_candidate_captured=true`。失败响应
不再把所有 upstream 事实抹成“未使用 daemon”：它保留 `failure_stage`、确定性
`project_id`、已知 `run_id` 与 `unreconciled_upstream_side_effects_may_exist`。POST timeout
属于提交结果未知，必须按可能存在 upstream 副作用处理并进入运维对账。

### 4. 只使用公开 REST 合同并绑定精确 result

project id 为 Runtime `task_id + asset_slot` 的确定性哈希，用户不能控制路径。它是 one-shot
identity：同一 task 不自动重试或复用遗留 project；冲突诚实失败，用户重试必须创建新的
FLAi task（新 task id），遗留 project 由独立运维清理，不在 adapter 内破坏性删除。顺序固定为：

```text
health / ready / version / daemon status / agents / design systems preflight
  → POST /api/projects
  → POST /api/runs
  → GET /api/runs/:id（有界轮询）
  → GET /api/runs/:id/result-package
  → GET /api/projects/:id/files
  → 每个 GET /api/projects/:id/files/<逐段编码路径> 两次
  → 再次 GET files 并精确对账
```

禁止 `/raw`。run/project/conversation/assistant/agent/design-system 必须逐项咬合；terminal
status 还必须证明 requested design-system id、selection source=`request` 与非空 execution
digest；result package
只接受 `open-design.run-result-package.v1` 且 `storage.kind=od-owned`、`baseDir=null`。抓取前后
完整 file-list 必须相同；file-list 的 32 文件、4 MiB/文件、8 MiB/总量上界必须在任何文件
GET 前通过。每个文件两次响应的 media type 与 bytes 必须相同，并与 list 的 size/mime 对账。

### 5. HTML 不执行；可见证据仅为严格 PNG

允许格式闭集为非空 strict UTF-8 HTML、SVG、CSS、JSON、Markdown，以及 PNG。文本执行
保守语法 screen：拒绝 active tags、event/URL-bearing attributes、HTML entity、CSS URL/escape、
DOCTYPE/ENTITY 与远程/可执行 scheme；JSON 还拒绝重复 key。此 screen 不承担保密降级，也
不把 HTML/SVG 变成可安全渲染的内容。路径要求 raw path 等于 canonical POSIX form，并同时
按 Windows 规则拒绝 traversal、drive、backslash、reserved name、NFC/casefold 冲突。

PNG 不是按扩展名放行：必须通过 signature、唯一 IHDR、宽高/像素上界、合法
bit-depth/color-type、非 interlace、chunk allowlist 与 CRC、连续 IDAT、zlib 解压后精确
scanline 长度与 filter byte、唯一终止 IEND、零尾随字节检查；APNG 与未知 ancillary
chunk 拒绝。HTML/SVG 永远只是附件；并排 UX 只能渲染通过扫描的 `image/png`。

每个 passive preview 显式绑定：

```text
slot_id + viewport(width,height,dpr) + state + theme + locale
  ↔ raw source path/SHA256
  ↔ PNG path/SHA256/size/width/height
  ↔ passive_preview_scan(passed=true, active_content_executed=false)
```

固定 `default_desktop_light` PNG 还投影为唯一 `promotable_asset`，精确携带
`slot_id/source_path/bundle_relpath/media_type/size_bytes/sha256`，并与 captured file 与
passive preview 各唯一咬合；其余 HTML/SVG/CSS/JSON/Markdown 永远只是附件。

### 6. Agent 包原子写候选，并为 pre-seal metadata 提供不可变见证

新增 disabled/L0 `open_design_daemon_candidate_agent`，`requires_human_review=true`。
manifest 中的 `permissions.visibility=admin_only` 当前只是计划性元数据，Runtime/API 尚不消费，
所以不能宣称已实施 admin-only；role gate 覆盖 create/batch/teams 前禁止改为 draft/active。
workflow 重新校验 tool response、base64、SHA-256、设计引用包、
file-set、candidate id 与 passive preview，先写同卷 staging，逐文件写后重哈希，再 rename
为全新的 `open_design_daemon_candidate_bundle`；失败不留下半包且不覆盖既有产物。

候选 manifest 固定为 `open_design_daemon_candidates.json`，并输出：

- `review_contract=open-design-candidate/v1`；
- `generator_kind=open_design_daemon`；
- `candidate_manifest_sha256=<exact file bytes>`。
- `classification=sensitive`；
- `project_id/run_id/result_package_sha256`；
- 唯一 `promotable_asset`。

Runtime 必须在 `running → waiting_review` 的同一 pre-seal 事务内把识别/分级/provenance
字段投影到 `task.metadata`，之后不可修改。P2.8 只依赖机器字段，不依赖 Agent 名称或 UI
文案，也不得在 seal 后补写。当前 P2.8 正确拒绝 sensitive 候选：在 role/per-file
declassification policy 交付前，P2.7→P2.8 live path 是显式阻断，不得称完整流水线可运行。

## 被拒方案

- **把 fixture tool 改成 mock=false**：破坏既有审计身份，拒绝。
- **允许自由 brief 却沿用固定输入的分级判断**：形成数据外送通道，拒绝。
- **只用 sensitive 替代 execution_trust**：混淆保密轴与执行信任轴，拒绝；本方案同时保留
  `classification=sensitive` 与 `execution_trust=untrusted_generated` 两个正交事实。
- **使用 MCP `get_artifact` 或 `/raw`**：不能按本合同对每个精确字节双取与 file-list 固定点，拒绝。
- **跟随 redirect、使用环境代理、对 POST retry**：扩大 loopback 与幂等边界，拒绝。
- **在 iframe 中预览生成 HTML**：把候选比较变成不可信代码执行，拒绝。
- **task review 自动等同选择/发布**：破坏人签边界和双闸，拒绝。

## 结果与限制

本实现已经建立真实 daemon 的 production-shaped REST 接缝，但不宣称 production-ready：

- 当前 `/api/version` 没有不可变 build SHA/签名；版本与 channel 精确对账仍不是供应链证明；
- loopback daemon 没有 FLAi 可验证的独立认证身份；`sandboxMode=true` 是上游报告，不是
  对内层 Agent 文件权限的远程证明；
- 当前开发机 `127.0.0.1:7456` 没有可用 daemon，尚无 live run 证据；
- 未完成 Windows 离线 sidecar、成对运维脚本、崩溃/端口冲突/冷启动演练；
- 单 Job Runner 会被长生成占用，真实负载前仍需调度容量验证；
- Tool Registry timeout 不能终止已经运行的 Python thread，adapter 也没有 Open Design run
  cancel/reconcile；task 超时失败后 poll 线程或 upstream run 可能继续。失败 witness 只能让
  orphan 可追查，不能自动回收它；启用前必须补独立 reconciliation/cleanup 运维路径；
- manifest 的 role 权限尚未被 Runtime/API 强制，Agent 保持 disabled；P2.8 internal-only
  admission 会 fail-closed 阻断本 sensitive 候选。角色轴、逐文件降密或具证明的专用 sidecar
  未交付前，不得宣称 P2.7→P2.8 live 比较/晋升流水线可运行。

因此 UI 必须显示“窄试运行 / 未证明生产就绪”，不得显示 REAL/绿色生产信任。通过 tool
与 workflow 测试只证明本地合同和失败路径，不证明 Open Design 生成质量。

## 验证

```bash
pytest -q \
  backend/tests/test_open_design_daemon_policy.py \
  backend/tests/test_open_design_daemon_client.py \
  backend/tests/test_open_design_daemon_agent.py
pytest -q backend/tests/test_tool_registry.py backend/tests/test_agent_registry.py
```

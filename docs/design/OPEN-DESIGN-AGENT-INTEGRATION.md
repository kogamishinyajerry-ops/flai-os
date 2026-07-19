# Open Design Agent 可信接入方案

> 状态：Phase 1 fixture seam 已完成；生产 daemon、可见候选比较与 promotion 尚未宣称完成。
> 上游只读审计：`/Users/Zhuanz/projects/misc-projects/Open Design/open-design`，
> HEAD `e06bff69edc6d4715228214c593d3a5a1849ad11`。上游工作树有用户改动，本仓不修改它。

## 1. 产品定位

Open Design 应作为 FLAi-OS 的**设计候选生成 Agent 工具**，而不是一个可绕开工程审核的
素材目录，也不是新的判决器。它的价值是让 Agent 以明确 brief、设计系统和 skill 生成或
迭代真实设计，再把完整 artifact 拉回工程事实链。

本仓保持三条边界：

- Open Design、LLM 与 FLAi Agent 都只能提出候选；人是唯一签发者。
- task review 只决定“本次候选是否被工程师接受”，不等同于发布、替换源码或晋升金图。
- 资产 promotion/release 是以后单列的具名人工动作；fixture 与生产工具永不原地翻牌。

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
`open_design_candidate_agent`。P2.2 更新 App.vue 后，fixture 以 0.1.1 补丁版本重新锁定
source bytes，并把不可变 snapshot identity 升为 `flai-task-review-assets-v2`：

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

- canonical request：`aab2740108a2d13aca53869f6c4c39b732a5ab3c2c3f3848f61bcb7915038f2c`；
- design reference package：`4fa241ae49d3c992168b2589779e24344749300a129e1f9478337974a3d68ca3`；
- fixture bundle：`70be2a7428ab385eb85e57845133b6b457402c6421c15d338a7f0a1b6b9eefd8`；
- response payload：`175f9c11a6853f7684e53ba603742414b9484f68ac6e33672fbf2f170bf35139`；
- HTML candidate：`e1242ccccb30758c184d798f50edc2b3fc0f38508c3f70f6a7c0238fa5e27db1`；
- SVG candidate：`8424d13080e3b1d79cef1e9a60a0e7a1a019d8f3a7bea4103fe3c523534bbd48`。

`flai-design-reference-package/v1` 保持不变，因为机械对比证明 allowlist、24 个 token 值、
信任色约束与 package shape 均未变化；变化的是受认证的 App.vue source bytes。旧 package
digest 的请求有专门 fail-closed 回归，不能被新 fixture 静默接受。

这些值只锚定当前机器协议夹具；真实 Open Design run 必须产生独立 run/artifact provenance，
不得复用上述 `mock=true` 身份。

## 4. Phase 2：生产 daemon adapter

生产接入必须新增 tool id，例如 `open_design_daemon_generate`，且 `mock=false`；不得修改
fixture manifest 伪装升级。建议按以下有界合同实现：

1. FLAi 在本地构造并验证当前 `flai-design-reference-package/v1`。
2. 为每个 task 建隔离 Open Design project；project id 来自服务端生成的稳定前缀与 task
   identity，用户输入不得控制路径。
3. `start_run` 的 prompt 明确资产槽位、viewport、状态矩阵、locale、禁止新信任色、
   exact package hash 和验收要求；可选 skill/plugin 必须来自 allowlist。
4. 有界轮询 `get_run`；timeout/canceled/failed 均映射为真实失败或取消，不自动成功重试。
5. terminal succeeded 后一次 `get_artifact` 拉完整 bundle；记录 Open Design revision、run id、
   project id、entry、artifact manifest、文件 SHA-256 与 package SHA-256。
6. 对文件数、总字节、mime、路径逃逸、外链、script/iframe、data URL、二进制与未知格式
   执行 fail-closed 策略；原始 HTML 不在 FLAi 权限面 iframe 执行。
7. 候选作为 task files 登记，状态停在 `waiting_review`。人签后也不自动写前端源码、覆盖
   design SSOT、更新金图或发布。

安全与部署约束：daemon 只绑定 loopback；认证与模型凭据留在 Open Design 进程；FLAi
事件、错误和产物 provenance 不记录 secret；每次运行使用隔离目录和最小权限。Windows
内网交付需要成对 `.sh/.ps1` 的 start/health/status/stop 脚本、固定版本、离线依赖包、
端口冲突与异常退出验收，且在实际开启 sidecar 前再获一次部署批准。

## 5. Phase 3：候选比较与资产 promotion

生产 adapter 稳定后再增加可见 UX：

- TaskDetail 先显示来源、package/run/artifact hashes、mock/REAL 标记与安全扫描结果；
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
| B daemon | 独立 production tool、loopback client、timeout/sanitize/provenance | 使用真实 Open Design fixture project，失败/断连/篡改全覆盖 |
| C compare | 安全截图、同 viewport/state 对照、差异清单 | app 内浏览器逐状态复核；不执行不可信 HTML |
| D promote | candidate→approved asset 的独立人工合同 | exact hash、明确目标、可回退、零自动发布 |
| E deploy | Windows/offline sidecar 与运维脚本 | `.sh/.ps1` 对称、health/stop、冷启动与断连演练 |

Phase 1 定向验证：

```bash
pytest -q backend/tests/test_open_design_fixture.py backend/tests/test_runtime.py
bash scripts/verify_all.sh
```

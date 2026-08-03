# FLAi-OS V1 源码就绪事实源

> 状态：**SOURCE CANDIDATE / NOT RELEASED**
> 版本：`1.0.0`
> 候选分支：`codex/v1-product-source-readiness`
> 候选创建基线：`origin/main@0b6ebeb4ea09241ba2642ff5e1754a1b9f6e6da0`（合并前仍需现场重读）
> 历史基线：`v0.1.0-sealed`
> 本文不是 merge receipt、release tag、内网上线批准或人工签发。

## 结论口径

本分支将 FLAi-OS 定义为 **V1 源码候选**，不把“版本号已改为 1.0.0”当成
“已发布”。只有同时满足以下条件，合并后的代码才可被记为 **V1 源码 READY**：

1. 该候选通过 `bash scripts/verify_all.sh`；
2. owner 对象隔离与 sample acknowledgement 的敌意/跨 owner 用例通过；
3. 桌面与 375px 移动端真实 UI 验收通过；
4. GitHub required checks 全绿，并通过受保护 PR 合并到 `main`。

本文只定义可验证的口径。在上述条件未全部成立时，结论仍是
**SOURCE CANDIDATE**，不得提前改写为已合并或已发布。

## V1 源码产品范围

### 1. 会话优先的自动路由

- 工程师从一个主会话输入自然语言或附件。Agent、模型、工具、Workflow、
  输入 schema 和资产分类是平台编排语言，不是用户的填表负担。
- 系统从会话、附件、不可变 Agent Package 快照、Registry、工具白名单、知识范围与
  输入输出契约中自动路由。缺少必要信息时在同一会话自然追问，不打开
  Agent 选择器、参数表单、JSON 编辑器或多块常驻轨道。
- 路由结果先以人话呈现。路由依据、边界与内部组件只读按需披露，披露区不提供
  改选、参数编辑或隐式开工。

### 2. 任务、运行与人工签发

- FastAPI 承载认证 API；SQLite 任务表是任务状态事实源；Job Runner 轮询
  queued 任务并追加事件证据，不引入 Redis/Celery 第二条状态链。
- 模型调用只经 Model Gateway，工具调用只经 Tool Registry。LLM 可理解、组织、
  解释和生成建议，但不进确定性校验、工程判决或签发链。
- 开工、影响工程判断的关键决定、结果签发与资产审批都必须由已认证人类
  显式触发，签发身份来自 session，客户端不能伪造。
- 对于 sample 级认可，本 PR 的成立条件是：认证 username 经 CAS-on-NULL 一次性冻结，
  幂等重试不改写首次签发者/时间，人工 reject、证据冲突或包损坏均 fail-closed。
  该项只在对应 required checks 通过后才能标记已实现。

### 3. owner 默认隔离

- user task、conversation、input file、output file 的权威 task、team blueprint、asset
  draft/Candidate/Skill Package 的对象读写默认要求 session `username` 与权威
  owner 精确相等；详细映射见 ADR-0037。
- 不存在、跨 owner、legacy NULL/空白 owner 与归属链不可证均返回同一泛化 404，
  且 owner gate 先于状态、密级、摘要、digest 或其他领域校验；不从显示名、
  客户端字段或关联内容猜测 owner。
- owner/cohort 列表过滤必须进入 SQL `WHERE`，先于 `ORDER/LIMIT/OFFSET`；不得
  先取全局分页窗口再在 Python 中过滤。
- `origin=eval` 是 tenant-wide 只读治理证据，受信 signer cohort 成员可读详情、
  子证据与 output；所有 mutation 仍过 exact task-owner gate。`origin=user` 不共享。
- 会话/任务/资产派生必须追溯并授权整个历史附件链；任一旧 `file_id` 为
  foreign、NULL、缺失、畸形或关系漂移即整链 fail-closed，不只检查最新消息。
- 这是本 PR 的必须验证项；在跨 owner 敌意用例全绿前，不得宣称 V1 源码
  READY。

### 4. 受治理资产链

```text
真实任务与签发证据
        |
        v
Asset Candidate Revision --人审绑定精确 digest-->
Approved Revision --确定性 Materializer-->
隔离 Skill Package (pending_review) --独立人审-->
Approved Skill Package --owner-scoped 确定性匹配/绑定/运行证据-->
Composition Eligibility (只读)
```

- Candidate 只证明草稿与任务证据的来源关系，不证明内容正确。
- Candidate accepted 只触发确定性生成隔离包；新包仍是 `pending_review`，不进 Agent
  源目录、Registry 或可执行导入路径。
- 包 approved 不代表已发布或可跳过任务门。复用时仍要重验精确摘要、文件字节、
  owner、任务绑定与实际 Application 证据。
- V1 只投影 Composition Eligibility，**尚未由该资产链形成 Workflow Revision 或
  Agent Package Revision**。单个 Skill 多次复用不自动升级为 Workflow/Agent。
- Registry 中现有 L0/draft Agent 是可运行/可评测的平台能力，不等于上述复用证据
  已形成成熟 Agent；UI 和 API 必须如实呈现 maturity 与 limitation。

### 5. 主会话内的功能/资产地图

- `GET /api/feature-asset-map` 只从认证 session 取 username，不接受前端传 owner。
- 功能部分来自同一代 `AgentShellCatalog` Registry 快照；个人资产只来自当前 owner
  可冷读复核的 Candidate 与隔离 Skill Package。
- owner、摘要、文件、Lineage、Package manifest 或数量上限任一不成立，整份投影
  停止；不把损坏项静默过滤成“0 个资产”。
- UI 只在主会话挂载一个默认收起的原生 disclosure，首次展开才读取。读取失败
  显示“地图暂不可用”，不渲染残缺结果。不新增 `/map`，不提供执行、注册、
  晋级、改选或参数编辑能力。

## 鉴权与职责边界

V1 使用真实账户/session 绑定操作者，并对个人对象默认 owner 隔离。但它
**不宣称已实现细粒度 RBAC 或职责分离**：

- 部署管理员创建/激活的所有账户都属于受信的 **human signer cohort**；
- 用户对象采用 **owner_signoff**：creator 与 owner 为同一 username 时允许显式自签，
  并如实审计 `self_review`；它不强制发起者、审核者与签发者分属不同人员。
- V1 不实现 reviewer assignment 或 owner delegation；Agent 级 eval/promotion 等全局
  governance API 仍只要求已认证 signer cohort，不把 owner 伪装成 admin/reviewer 角色；
- 多职级、部门、密级 clearance、双人复核与组织职责分离属于后续治理升级，
  不能被当前的 owner 隔离或人签证据替代。

因此，V1 源码的合法部署假设是：账户只发给组织已授权的工程师/签发人，
对象数据默认只对 owner 可见可操作，但组织仍需用现行管理流程决定谁有资格进行哪类签发。

## 不在本源码 PR 内的适配门

以下项目仍要在目标 Windows/内网环境完成，它们是**适配门**，不是本源码
候选分支已完成的事实：

- Windows PowerShell 启动/停止、worker 单例锁与文件安全分支的目标机实测；
- 内网模型网关的 endpoint、模型名、认证、限流和 p99 延迟探测；
- 目标网络中的 TLS/HTTPS、Cookie `Secure` 与反向代理配置；
- 离线依赖、浏览器、安装包与可回滚发布包；
- 真实性能盘 Tool Adapter 和目标机上的业务/性能验收。

不得用“源码 READY”代替上述适配证据；也不得因为适配尚未在本机执行，而把与之
无关的产品功能/UI/哲学/架构/机制源码验收写成未完成。两条门分别记账。

## 可复核命令

```bash
# 版本一致性
uv run --no-project --with tomli python - <<'PY'
import json, pathlib

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

root = pathlib.Path('.')
py_version = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
pkg_version = json.loads((root / 'frontend/package.json').read_text())['version']
lock_version = json.loads((root / 'frontend/package-lock.json').read_text())['version']
lock_package_version = json.loads(
    (root / 'frontend/package-lock.json').read_text()
)['packages']['']['version']
assert py_version == pkg_version == lock_version == lock_package_version == '1.0.0'
PY

# 源码全门（应由 PR required check 重跑）
bash scripts/verify_all.sh
```

## 状态变更规则

- 合并前：`SOURCE CANDIDATE / NOT RELEASED`。
- required checks 全绿且 PR 已合并后：可在独立合并回执中记为 `V1 SOURCE READY`。
- 只有 owner/发布负责人后续显式决定打 tag 和发布时，才能记为 `RELEASED`。
- Windows/内网导入、业务启用和正式生产上线各有独立证据门，不随源码状态自动升级。

# Kimi K3 Workspace Shell 只读研究记录

## 运行声明

```yaml
record_type: ExternalDesignResearchRecordV1
purpose: Open WebUI / ChatGPT Desktop / Claude Desktop 交互路线研究
requested_model_identity: kimi-code/k3
client: kimi-cli
client_version: 0.29.0
session_ref: session_2f449268-89fd-4104-bd95-fd7bd908557e
dispatch_transport: DIRECT_LOCAL_KIMI_CLI
actual_runtime_receipt: ACTUAL_RUNTIME_RECEIPT_NOT_AVAILABLE
source_repo_access: READ_ONLY
repository_writes: NONE
internal_data_access: NONE
result_authority: NON_AUTHORITATIVE_RESEARCH_INPUT
```

本次研究明确请求 `kimi-code/k3`，但没有得到可独立验签的 provider/backend dispatch receipt。因此只能
记录“请求了该模型”和客户端会话引用，不能把模型实际身份标记为已验证。

## 固定输入

- FLAi-OS base：`0d095df8257ad369851e2a4a598fe5cb1a1cef14`
- Open WebUI：`v0.10.2`
- Open WebUI commit：`ecd48e2f718220a6400ecf49eafd4867a38feb10`
- Open WebUI tree：`6273a9ed3d194683775893b36e4541b543156320`
- 数据：仓库源码与公开产品资料；无内网数据、无 secret。

## Kimi 研究结论

Kimi 在只读比较后推荐路线 C：

> 不直接 fork 或内嵌 Open WebUI；提取交互模式，在 FLAi-OS 现有 Vue 前端上独立重实现
> Workspace Shell，不复制上游代码或资产。

Kimi 的主要理由：

- Open WebUI 核心聊天组件与其 store、API、Socket、聊天持久化强耦合；
- 直接迁入会同时迁入与 FLAi 人签、证据、reality 和 fail-closed 不一致的状态假设；
- 新建隔离原型目录能让 Kimi 专注 Presentation/Renderer，同时让 Codex 继续拥有 Port、Adapter、
  认证、ACL、签名和生产集成；
- 先证明 desktop-grade 浏览器体验，再决定 macOS host，避免过早复制两套 Presentation。

## 采用情况

本研究结论已被吸收到：

- `docs/design/OPEN-WEBUI-REFERENCE-AUDIT.md`
- `docs/design/WORKSPACE-SHELL-V1-BLUEPRINT.md`
- `docs/agents/kimi-k3-workspace-shell-pilot.md`

其中两周实现工作项仍为 `OWNER_REVIEW_REQUIRED_NOT_DISPATCHED`。本研究会话不构成实现授权、源码
候选验收、主干集成或内网发布。

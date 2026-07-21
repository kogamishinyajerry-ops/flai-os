# ADR-0030 · ax 静态 Web 工具的 subprocess、出站与证据边界

> 后续状态（2026-07-21）：本文“角色轴未建立”的历史判断已由 ADR-0031 部分取代：
> Agent 调用、评测与任务签发已有角色门；sensitive 数据访问 capability 仍未完成，
> 故本文对 sensitive 产物的 fail-closed 与休眠边界继续有效。

- 状态：**已采纳（仅 L0 离线契约批）**；生产联网激活仍 **BLOCKED**
- 日期：2026-07-21
- 关联：ADR-0008（工具超时诚实）· ADR-0021（分级与角色轴）·
  ADR-0022（受控 subprocess 先例）· ADR-0024/0025（工具污点与不可变分级）·
  docs/03 Tool Package 标准
- 上游基线：`yusukebe/ax` `v0.1.18`，commit
  `764b90c9a05c119873d135f5b755602a9fafbbe1`

## 1. 背景与决策问题

`ax` 把静态网页/API 的 fetch → DOM 结构发现 → 结构化抽取收敛为一个本地
单文件程序，适合降低 Agent 临时编写 `curl + regex/Python` 的成本。但它读取的
是外部不可信内容，且其 HTTP 路径会自动跟随重定向；平台不能把“Agent Skill 中的
安全提醒”当成网络隔离，也不能把抓取成功冒充知识真实性或正式签发。

本 ADR 只授权一个**仅 fixture 可执行、未分配给任何 Agent 的 Tool 包合同**。生产
Runtime 不注入 fixture witness，环境变量也不能将它解锁为真实联网入口；它不授权
修改角色、知识准入或人签状态机。

## 2. 决策

### D1 · 定位与能力面

新增 `tools_impl/ax_web_extract`，类型为 `python_adapter`，只暴露三种语义操作：

- `fetch`：固定一次 HTTPS 获取，保存原始响应；
- `discover`：对已保存的本地快照做 `--outline`，或带 `needle` 做 `--locate`；
- `extract`：对同一份本地快照做 selector/row JSON 抽取。

一次调用最多发生一次网络获取；discover/extract 永远解析刚保存的本地快照，
不二次请求、不依赖 ax 两分钟缓存。它不是搜索引擎、递归爬虫、浏览器、PDF/OCR
工具或知识发布服务。JS-heavy SPA 必须转浏览器 adapter，且 fallback 原因要显式。

### D2 · subprocess 与供应链边界

- `FLAI_AX_BIN` 必须是部署方配置的绝对普通文件，拒绝 symlink、PATH 猜测和 fallback；
- `FLAI_AX_BIN_SHA256` 必须与执行前实算 SHA-256 完全一致；
- wrapper 只接受 ax `0.1.18`，升级 ax 必须升工具版本并重跑合同；
- 固定 argv 列表、`shell=False`、受限环境变量、受控 cwd；调用方不能提交二进制路径、
  headers、凭证、HTTP method、body、输出路径或任意 flags；
- version、fetch、derive 共用调用方给出的单一总预算（最长 15 秒），小于 Registry 的
  20 秒外层 timeout；超时/nonzero/空或坏 JSON
  全部返回 `status=failed`，绝不假绿；
- 内网发布只接受固定 release asset + hash + license/SBOM。禁止运行时 `curl | sh`、
  Homebrew、npm/npx 下载或在线升级。

### D3 · URL 与出站边界

L0 wrapper 当前先行执行的防线：

- L0 输入只接受三条固定 fixture URL（`/page`、`/slow`、`/large`），任何调用方 URL
  扩展都必须升 L1 合同；sensitive 工具无论输入有效与否，`tool_runs` 和
  `tool_started` 都只记录字段名，不记录值；
- 固定 URL 仅使用 RFC 保留的 `.invalid` 主机名；请求 origin 必须精确命中
  `FLAI_AX_ALLOWED_ORIGINS`，返回后最终 origin 再校验；
- 只有可信测试上下文 `ax_l0_fixture_mode is True` 才可执行；生产 Runtime 不注入该字段；
- `FLAI_AX_NETWORK_POLICY_ID` 在 L0 必须精确为 `l0-fixture-only`。

**重要限制**：最终 URL 校验发生在请求后，无法阻止已发生的恶意 redirect；hostname
allowlist 也不能单独消除 DNS rebinding。正因如此，本版本没有 live 开关，`.invalid`
与 fixture witness 只构成离线合同，不构成网络沙箱或生产出站授权。

因此生产联网能力仍被阻塞，直至新增独立 adapter，并由部署层在每次连接前强制：DNS/目标 IP 校验、
loopback/link-local/private/metadata 拒绝、每跳 redirect 复核、域名/端口 allowlist、
出口代理或防火墙，以及对应的可测试 policy identity。未满足时只能运行仓内 fake
binary/固定 fixture 验收。

### D4 · 工作区与 provenance

- Runtime 经只读 `tool_context.output_dir` 注入任务输出根；payload 不得自报路径；
- adapter 仅写 `<output_dir>/ax/<run_id>/`，保存原始 body、fetch/derive stdout/stderr
  和 `source-manifest.json`；原始 body 已生成后的失败也写失败 manifest，并将 raw path
  咬合到 `tool_runs`，原始件尚未形成的失败则清理本次未登记目录；
- manifest 至少记录 wrapper/tool 版本、ax 版本、实算 binary SHA、network policy id、
  requested/final URL、HTTP 状态、抓取时间、耗时、字节数、原始 body SHA、抽取参数、
  抽取件 SHA 与截断状态；
- Registry 只在 `save_raw_files is True` 且路径是可信 output_dir 内的绝对普通文件时，
  才把 raw path 写入 `tool_runs`；越界、symlink、缺失或成功无 raw path 整次 fail-closed；
- 外部 HTML 保持下载附件，不增加同源 iframe/静态站托管，避免 stored-XSS/API-origin 风险。

### D5 · 分级、人签与知识准入

- `output_classification: sensitive`：外部网页是不可考真源，不能为可用性谎标 internal；
- 工具不加入任何现有 Agent 的 `agent.yaml.tools`，因此 L0 不扩大 shipped 权限面；
- 当前角色轴未建立，sensitive 产物对所有人下载 403。故本批只能称为“休眠合同与
  provenance scaffold”，不能称为可用生产 Web 功能；
- live 激活前必须先解决具名角色的 sensitive 查看/下载，否则人类评审者也拿不到证据；
- ax 输出始终是候选证据，不直接写 `data/knowledge`，不改变 review/approval/release。
  后续知识准入只能消费已登记文件 id，并绑定源 URL、时间和 hash，经具名人批准后发布。

## 3. L0 验收

1. Registry 能注册 `ax_web_extract`，缺 fixture witness 时即使设置旧式 env 开关也不启动子进程；
2. 完全离线 fake binary 覆盖 fetch/discover/extract，且 discover/extract 只读本地快照；
3. 非固定 fixture URL、调用方 headers、任何 query/fragment 与 origin 越权在子进程前拒绝；
4. binary hash/version 不符、共享总预算超时、响应超限、跨 origin 最终 URL 全 fail-closed；
5. 成功及 raw body 已形成的失败均有 manifest/SHA/路径咬合，`tool_runs.raw_output_path` 真落库；
6. Registry 拒绝将 output_dir 外文件登记为 raw evidence；
7. 不修改任何 Agent 白名单，不执行真实网络，不安装 ax，不声称 Windows 已验证。

## 4. 后续生产解锁门

按顺序：独立 L1 adapter + 可执行出站策略 → 角色轴/敏感证据可用性 → Windows 固定
binary 离线包与目标机测试 → 受控 live pilot → browser fallback → 独立知识准入。
任何一步都不能用“配置了一个布尔开关”替代实际强制与 witness。

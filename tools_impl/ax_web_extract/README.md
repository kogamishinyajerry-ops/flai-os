# ax_web_extract

`ax_web_extract` 是 FLAi-OS 对 `yusukebe/ax` 的窄适配层。它只负责静态 HTTPS
页面的受控获取与结构化抽取，不是搜索引擎、爬虫、浏览器或知识发布器。

当前 `0.1.0` 为 L0 fixture-only 契约：只允许 `.invalid` 测试主机，不加入任何 Agent
白名单，生产 Runtime 也不注入测试 witness。后续必须先落地运行时角色轴，再落地并验证
可执行 egress policy；两者都闭合后才允许另提独立 L1 生产 adapter。L1 adapter 默认
disabled，代码存在不构成联网解锁。完整边界见
[`ADR-0046`](../../docs/adr/ADR-0046-ax-web-extract-subprocess-and-egress-boundary.md)。

## 公共合同

调用必须经过 `ToolRegistry.call("ax_web_extract", payload)`。支持：

- `operation=fetch`：保存一份原始 HTTPS 响应；
- `operation=discover`：本地快照 outline；带 `needle` 时 locate；
- `operation=extract`：本地快照 selector 抽取，可选 `row`。

调用方只能调整有界的 `limit`、`budget_tokens`、`max_bytes`、`timeout_seconds`；
不能提交 headers、凭证、HTTP method/body、ax flags、二进制路径或输出路径。
L0 的 `url` 只接受 `https://fixture.invalid/{page,slow,large}` 三个固定值；增加真实 URL
不是配置动作，而是 L1 的合同与安全边界变更。

## L0 测试配置（不是部署或生产授权）

| 变量 | 含义 |
|---|---|
| `FLAI_AX_BIN` | 固定 ax binary 的绝对路径 |
| `FLAI_AX_BIN_SHA256` | 该 binary 的 64 位小写 SHA-256 |
| `FLAI_AX_ALLOWED_ORIGINS` | 逗号分隔的精确 HTTPS origins |
| `FLAI_AX_NETWORK_POLICY_ID=l0-fixture-only` | 固定测试策略标识 |

测试还必须由可信 `tool_context.ax_l0_fixture_mode is True` 注入 witness；常规 Runtime
不会注入。任何 env 变量均无法解锁真实域名。sensitive 工具的 `tool_runs` 与
`tool_started` 只保留输入字段名，不保留 URL/selector 等值。

## 产物与真相边界

每次成功调用在可信任务输出根下写 `response.body`、诊断 stdout/stderr、派生输出及
`source-manifest.json`；raw body 已形成后的失败也会生成失败 manifest 并登记 raw path。
manifest 绑定 ax/version/binary hash、URL、HTTP 状态、时间、大小和文件 hash。所有内容
均为 `sensitive` 候选证据，不得直接进入知识库、不得冒充真实结论或人签产物。HTML
保持附件下载，不在 FLAi 同源页面内执行或 iframe 预览。

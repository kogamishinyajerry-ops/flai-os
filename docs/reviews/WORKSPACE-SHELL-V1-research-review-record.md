# Workspace Shell V1 研究候选具名评审记录

## 评审对象

- Stage C accepted code base：`0d095df8257ad369851e2a4a598fe5cb1a1cef14`
- Open WebUI reference：`v0.10.2@ecd48e2f718220a6400ecf49eafd4867a38feb10`
- `docs/design/OPEN-WEBUI-REFERENCE-AUDIT.md`
- `docs/design/WORKSPACE-SHELL-V1-BLUEPRINT.md`
- `docs/agents/kimi-k3-workspace-shell-pilot.md`
- 两份研究/接受记录

## 责任轴

| 评审任务 | 责任轴 | 身份证据状态 |
| --- | --- | --- |
| `workspace_shell_contract_review` | Interface、信任不变量、prototype/production 边界、测试与派发合同 | Codex 子任务引用；无独立可验签 reviewer receipt |
| `openwebui_compliance_review` | 上游固定、许可证表述、供应链、no-copy 与 egress 边界 | Codex 子任务引用；无独立可验签 reviewer receipt |

## 第一轮发现与关闭

第一轮结论为“路线 C 可继续，但工作项不可冻结/派发”。发现项包括：

- prototype-only observer/runtime projector 被误写成 Production Adapter；
- accepted code SHA 不包含新规范，且 Stop If 会在首个正常提交后自触发；
- 缺少 branch/worktree、预算、classification、egress 与 executor qualification；
- synthetic-only 原型与 teal 真人签发正路径冲突；
- Vite bootstrap 与“零网络”措辞冲突；
- projection/delta/receipt/撤权清除和 extension allowlist 不足；
- no-copy 过程、untracked scope、许可证组合与 lockfile 摘要未写清。

对应修改已完成：

- 生产 REAL 明确保持 `NOT_IMPLEMENTED / REAL CLOSED`；
- accepted code base 与未来 clean design base 分离；
- 工作项保持 `OWNER_REVIEW_REQUIRED_NOT_DISPATCHED`，冻结 payload 由 coordinator 持有；
- 新增严格 projection/delta/command/receipt/Delivery union、撤权清除与受限 extension；
- synthetic/unsigned delivery 永不 teal；
- 固定 96-case unit/DOM 矩阵与可视 E2E 子集；
- egress 拆成 provider transport、获准 source context、runtime deny 和 loopback-only browser test；
- 实现必须使用全新 Kimi 会话，不挂载 Open WebUI clone，不复制代码或资产；
- Open WebUI 按上游声明记录为多许可证快照，并固定前后端 lockfile 摘要。

## 最终结果

| 门 | 结果 |
| --- | --- |
| 研究文档提交 | `GO` |
| 文档层 P0 | `0` |
| 文档层 P1 | `0` |
| 文档层 P2 | `0` |
| 立即派发 Kimi 实现 | `NOT_DISPATCHED` |
| 生产 Schema/API/状态机变化 | `NONE` |
| Open WebUI 运行依赖 | `NONE` |

两个评审轴均确认本设计包可以作为隔离分支上的 `PROPOSED / OWNER_REVIEW_REQUIRED` 研究候选。
它不构成法律意见、模型身份验证、生产 Interface 冻结、Kimi 实现授权、主干合并或内网发布。

## 派发前机械门

1. human owner 接受路线 C 和 Kimi 写范围；
2. 提交本轮设计文件并取得 clean design SHA；
3. coordinator-owned freeze payload 绑定 clean SHA、准确 branch/worktree、预算、classification 和 egress；
4. 计算 work item digest；
5. 从 clean SHA 创建隔离 worktree，验证 HEAD 精确相等；
6. 完成 executor qualification；
7. 启动全新 Kimi 会话，不恢复源码研究 session，不挂载上游 clone；
8. 记录实际 dispatch/model receipt 后才能把状态改为 `RUNNING`。

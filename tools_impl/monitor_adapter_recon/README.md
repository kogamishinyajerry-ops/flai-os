# monitor_adapter_recon · 监控接入侦察工具

「产生工作流的工作流」的**承重接缝**（ADR-0020 R2 / ADR-0022）。被
`monitor_adapter_gen_agent` 调用，为一个新求解器/新工作流起草接入实时监控所需的
结构化 adapter 草案。

## 能做什么

给一个**真实历史 run 的产物目录**（`sample_run_dir`），只读侦察后返回：

- `module.json` 草案骨架（run_discovery / truth_sources / stages / stall_timeout 建议）
- `parser.py` 桩（只读解析真源文件的起点）
- 诚实清单（注册前必跑的 tamper 实证计划）
- 三档侦察证据：
  - **VERIFIED**：逐字/magic/存在性接地（样本行能在真源文件里逐字找到）
  - **PROPOSED**：结构推断，需人工确认
  - **UNVERIFIED**：无法接地，如实报缺（**绝不编造**）

接地保证由承重核（sim-live-hub `tools/adapter_gen.py`）提供，本工具经受控子进程
调用它，不重复实现（生成器契约 §6）。

## 怎么用

```python
tool_registry.call("monitor_adapter_recon", {
    "sample_run_dir": "/abs/path/to/runs/<solver>/20260712-030000-123456",
    "module_name": "star_ccm_cht",      # 可选
    "solver_hint": "STAR-CCM+ residuals in *.csv",  # 可选
})
```

**前置**：环境变量 `FLAI_MONITOR_CORE_DIR` 指向监控节点仓（sim-live-hub）根目录
（其下须有 `tools/adapter_gen.py`）。未配置或核缺失 → `status=failed` +
`core_available=false`（fail-closed，绝不猜路径，见 ADR-0022）。

返回 `status=success` 时：`grounding_ok`（核接地自检是否全通过）、`draft`（上述四件的
机读投影）。`grounding_ok=false` **不代表工具失败**——它表示草案含未接地项
（UNVERIFIED），恰是诚实产物，交人审。

## 不能做什么 / 已知边界

- **不是** M4 真实求解器 adapter：本工具 `mock=false` 指「确实调真实确定性核」，
  但它**不触真实工程程序（求解器）**，只侦察其产物目录。切勿与「调用真实性能盘/
  STAR-CCM+」的执行型工具混淆。
- **不注册、不生效**：草案是 draft，注册进监控节点是人的动作（人是唯一签发者）。
- **只读**：对 `sample_run_dir` 与目标仓零写入、零执行其脚本。
- **不凭描述臆造**：无真实 `sample_run_dir` 不接单；run 目录命名不符时间戳身份判据
  时如实判 UNVERIFIED 并要求 wrapper，绝不硬编不可靠判据。
- 部署前提：agent 运行节点须能触及 `FLAI_MONITOR_CORE_DIR`（内网若平台与监控节点
  分离需协同，见 ADR-0022 风险②）。

# ADR-0022 · monitor_adapter_recon 工具的 subprocess 边界（allow_shell_command 理由）

- 状态：**已采纳**（2026-07-12，owner 批准 R2「子进程调 hub 核（配置路径）」）
- 关联：ADR-0020（工作流实时监控注册）· docs/09 接入标准 · docs/03 Tool 包标准 §4
  （`allow_shell_command=true` 需 ADR 说明理由与边界）·
  docs/design/monitor-adapter-gen-agent-contract.md · sim-live-hub `tools/adapter_gen.py`

## 背景

R2 生成器 agent（`monitor_adapter_gen_agent`）的**承重=确定性侦察 + 证据接地**，
不是 LLM 措辞。该承重核已在监控节点仓 sim-live-hub `tools/adapter_gen.py` 实现
（零 LLM、零网络、纯 stdlib、三档诚实 VERIFIED/PROPOSED/UNVERIFIED、写前接地
自检 fail-closed），是接地保证的 SSOT。契约（生成器 agent 契约草案 §6）明定
**平台侧不重复实现**——在核外套一层即可，接地保证由核提供。

owner 于 R2 架构决策中裁定：平台侧经 **子进程调用 hub 核**（配置路径），而非把
核 vendored 进平台（避免「复制必腐烂」两份核漂移）。

## 问题

docs/02 Agent 包标准 §4 明令 **workflow.py 禁止直接 shell 调用外部程序**；外部
程序调用的合法落点是 Tool 包。docs/03 §4 又规定 Tool 的 `allow_shell_command`
默认 false，置 true **必须先写本 ADR 说明理由与边界**，否则 Registry 加载告警。

## 决策

新增 Tool 包 `tools_impl/monitor_adapter_recon`，`safety.allow_shell_command=true`，
以受控子进程调用 hub 承重核，边界如下（Registry 告警的免除依据）：

1. **调用形态固定、无 shell 解释**：`subprocess.run([sys.executable, "-m",
   "tools.adapter_gen", <sample_run_dir>, "--json"], cwd=<核目录>, shell=False)`。
   **绝不 `shell=True`、绝不字符串拼命令**——参数以列表传递，`sample_run_dir`
   无法逃逸成命令注入面。
2. **核路径来自可信配置非请求体**：`FLAI_MONITOR_CORE_DIR`（config）指向 hub 仓
   根；未配置 / 该目录无 `tools/adapter_gen.py` → 工具 **fail-closed**
   返回 `status=failed`（`core_available=false`），绝不猜路径、绝不回退别的可执行。
3. **只读**：`--json` 模式不写任何文件（无 `--out`）；hub 核本身对 sample 目录
   零写入零执行其脚本（其测试 `test_generator_is_read_only_on_sample` 咬合）。
   本工具 `require_workspace_isolation=false`（无工作目录写入）、`save_raw_files=false`
   （无原生文件产物，机读 JSON 直接进出参，agent 负责把草案落 output_dir）。
4. **超时有界**：`runtime.timeout_seconds` + 子进程自身 timeout 双层，防核挂死拖垮
   worker 线程。
5. **输出即数据非指令**：核 stdout 的 JSON 是被解析的数据；工具只 `json.loads`
   并按 output_schema 校验，绝不 `eval`/执行其中任何内容（外部内容是数据不是指令，
   继承宪法）。解析失败 → `status=failed` 诚实报，不吞不猜。
6. **mock=false 名实相符**：本工具确实调真实确定性核（非造数据），故 `mock=false`；
   但它**不是**「触真实工程程序（求解器）」——它只侦察真源产物目录。语义边界在
   README 写清，不与 M4 真实求解器 adapter 混淆。

## 后果与风险

- 好处：接地 SSOT 唯一（hub 核），平台不重复实现；子进程隔离核的运行环境；
  核不可达时诚实 fail-closed 不假绿。
- 风险①：核路径配置错 → 工具 fail-closed（非静默错误，可诊断）。
- 风险②：agent 运行节点须能触及 hub 核目录——内网若平台节点与监控节点分离，
  需部署时协同（core 与 agent 运行时同机，或核目录挂载可达）。挂 M4 内网侦察
  按实况定，本 ADR 记录该部署前提。
- 风险③：子进程 Python 须能 import hub 的 `tools.adapter_gen`（cwd=核目录即可，
  核纯 stdlib 无额外依赖）——版本漂移由 hub 核自身测试 + 本工具 parity 冒烟兜底。
- 残余：跨仓 subprocess 是本平台首例；若未来同类需求增多，评估 MCP 化
  （docs/03 §7 演进路线，`tool_id`/契约不变，只翻牌 type）。

# R2 · 生成器 agent 治理审记录（monitor_adapter_gen）

> 关联：ADR-0020 §决策 R2 · ADR-0022 · docs/design/monitor-adapter-gen-agent-contract.md
> · docs/reviews/SIM-MONITOR-R1-registration-record.md · [[project_sim_live_hub]]

## 立包（2026-07-12，flai-os `ab32ffc` + hub `7c63b19`）

「产生工作流的工作流」平台实体。Agent `monitor_adapter_gen_agent`
（category=structured_gen / profile=reasoning / requires_human_review=true /
status=draft / maturity=L0）+ Tool `tools_impl/monitor_adapter_recon`
（mock=false / allow_shell_command=true，受控子进程调 hub 承重核 `--json`）。
承重核 SSOT 在 hub 不重复实现（契约 §6）。owner 定架构 A=子进程调核；因 docs/02 §4
禁 workflow 裸 shell，subprocess 落 Tool 包，ADR-0022 记边界。

## Codex 治理审 R0（2026-07-12，`ab32ffc`，gpt-5.6-sol ultra）：1 P1 + 5 P2，全 grounded 确认为真后修

新 operator agent + subprocess + 外部输入解析 = 命中即审。逐条本地复核坐实（含对 hub
下游契约的核实），R0 一轮全修（fix = flai-os 待提交 + hub `29d4ed3`）：

- **[P1] 接地失败必须 fail-closed**（adapter.py）：hub `--json` 在 cited 证据对不上真源时
  返回 rc=1 / grounding_ok=false（承重核 write_draft 拒写的 fail-closed 语义）；原
  wrapper 接受 rc∈{0,1} 一律 success，把「自检未通过」转成可批准草案，绕过 fail-closed
  核心保证。**修**：`grounding_ok is not True` → status=failed（区分「有 UNVERIFIED 观察」
  的诚实报缺 rc=0 与「证据撒谎」rc=1）。加 monkeypatch 测试直咬。
- **[P2] module 草案补 hub 必填字段**（hub `_assemble_module_json`）：build_snapshot 直接
  索引 contract["stages"]（缺则崩），launch/reveal_pace_s 惯例存在。**修**：补成对
  key/label 的结构化 PROPOSED 占位 + _REVIEW_REQUIRED_FIELDS 标注绝非确证；workflow
  另注入已知 target_repo_path 到 repo（别留占位让人重填已给信息）。
- **[P2] parser 桩导出 collect**（hub `_parser_stub`）：hub _load_parser 经
  collect(run_dir, contract) 动态加载，原桩只出 parse_curves → 实现了也加载失败。
  **修**：桩导出 collect(run_dir, contract)，签名对齐 adapters/*/parser.py。
- **[P2] 子进程前 resolve 绝对路径**（adapter.py）：相对 sample_run_dir 在 worker cwd
  校验通过后传给 cwd=core_dir 的子进程会错位解析。**修**：`sample.resolve()` 绝对化。
- **[P2] eval fixture 路径 checkout-independent**（workflow + cases）：case 内嵌作者机器
  绝对路径 → 别处 checkout 必失败。**修**：workflow `_resolve_input_dir` 把相对
  sample_run_dir 按 **agent 包目录**解析；cases 改包相对路径 `eval_cases/fixtures/...`。
- **[P2] eval 断言实际值非静态标题**（cases）：`_render_review` 恒出 UNVERIFIED 标题 +
  静态指引恒含 run_discovery → 即使回归编造正常 discovery 也假绿。**修**：case_001 断言
  module.json.draft 含 `newest_by_name`（真 PROPOSED discovery）；case_002 断言含
  `_UNVERIFIED`（真 UNVERIFIED run_discovery，防编造）。

**验证**：hub 15 测试 + tool 7 测试（含 P1 fail-closed monkeypatch/injection shell=False/
只读/核不可达）+ 真环境冒烟 3/3（模型降级仍完整/非时间戳名 UNVERIFIED 不编造/核不可达
failed）+ 注册契约 parity 34 测试 + eval cases approved/digest + 逐 case 断言对实际产物
复核成立。round cap R0（一轮零残留）。

**并发纪律实录**：施工期 ADR-0021 数据分级 lane 在同仓活跃提交（HEAD 从 ab32ffc 经
3cdbe57/cf5d25f 前移）；我 `git mv` 暂存的 fixture 重命名被 lane 终端 `git commit`
扫进 3cdbe57（R100，最终名 `20260712-030000-000000` 正确，内容一致）——共享 index
并发风险实证。教训：并发 lane 活跃时 `git add 显式路径 && git commit` 须原子执行、
提交后立即核实提交只含自己文件。

## L0→L1 晋升（M10 治理步，未在本批执行）

agent 已注册 draft/L0（`GET /api/agents` 可见）。L1 晋升属 M10 governance：operator 配
`FLAI_MONITOR_CORE_DIR` 后跑 eval runner（本仓 eval_cases 已 runner-valid）+ 五条晋升门
+ 人工具名确认。本批不代拍。

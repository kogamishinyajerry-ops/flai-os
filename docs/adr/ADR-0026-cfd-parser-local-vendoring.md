# ADR-0026：CFD 日志解析器本地 vendoring + St oracle 独立实现

- **状态**：Accepted（2026-07-13）
- **背景**：CFD 真接线批（spec/plan = docs/superpowers/{specs,plans}/2026-07-13-cfd-flai-os-integration*.md）的 P2 需要在 FLAi-OS 侧解析 agent-cfd-live 产出的 `log.pimpleFoam`（残差）与 forceCoeffs（Cl/Cd）。解析器 SSOT 原生长在 sim-live-hub（`adapters/cfd_openfoam/cfd_log_parser.py`，P1.1 交付）。plan P2.2 给了两条路：跨仓 `sys.path`/`PYTHONPATH` import，或把两个纯 stdlib 函数复制进 FLAi-OS 并 golden 对账。

## 裁决

**选复制（vendoring）**：`backend/app/cfd/cfd_log_parser.py` 独立持有 `parse_residuals` / `parse_force_coeffs`。

理由：生产部署（内网 Windows，ADR-0006 语境）不应要求 sim-live-hub 仓在场或跨仓 PYTHONPATH 拼装——那是比 60 行纯 stdlib 双份更贵的部署耦合；工具 fail-closed 语义也不该依赖「另一个仓恰好 checkout 在某路径」这种环境事实。

## 一致性证据（2026-07-13 实测，非声称）

- **解析器**：复制版 vs hub 版逐行 diff 核心逻辑同构（仅注释差异；P2 评审 md5/逐行核）。
- **golden 夹具**：`backend/tests/fixtures/cfd_good_run/` 与 hub `tests/fixtures/cfd_good_run/` 的 log.pimpleFoam、forceCoeffs.dat **md5 逐字节一致**（同源 = agent-cfd-live `runbook/replay/good-run-01`，t=150、11+ 涡脱周期）。
- **St oracle 交叉对账**（同一 golden 双实现同跑）：
  - FLAi-OS `st_oracle.strouhal_from_cl` → **St=0.167292**（尾窗 60%，14 周期）
  - agent-cfd-live `parsers.estimate_strouhal` → **St=0.167344**（尾窗 50%，11 周期）
  - 相对差 0.03%；两者对 Williamson 参考 0.164 偏差均 ~2%。
  - **定性：同法（上升沿过零 + 线性插值）独立实现、带内一致，非逐位复刻**（尾窗与振幅地板参数不同）。st_oracle docstring 已按此措辞修正——不声称超出证据的「复刻」。

## 代价与缓解

- **漂移风险**：两仓各持一份解析器，未来任一侧修 bug 另一侧可能漏。缓解：①本 ADR 登记双份位置；②golden 夹具两侧字节一致，任一侧改动跑各自 golden 测试即咬；③轻量「两侧字节一致」CI 断言列为 P2 评审 Minor 挂账，终审 triage。
- **St 算法双份**：属**刻意不统一**——agent-cfd-live 的 estimate_strouhal 服务其面板显示，FLAi-OS 的 st_oracle 服务评估判据（带 converged/n_cycles/reason 结构化输出与 Goodhart 防御分支），语义不同不强行合并。

## 影响面

- `backend/app/cfd/{cfd_log_parser,st_oracle}.py`（新）、`tools_impl/cfd_result_read/`（消费者）、`agents/cfd_evaluate_agent`（P2.3，消费 st_oracle）。
- sim-live-hub / agent-cfd-live 零改动。

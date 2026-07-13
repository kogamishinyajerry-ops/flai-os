# CFD 真接线：FLAi-OS 工作台里一次多 agent 可实时监控的端到端流程

**日期**：2026-07-13
**状态**：设计已批准（brainstorming），待 spec 审阅 → writing-plans
**作者**：Jerry × Claude（Fable 5）
**跨仓**：FLAi-OS（`~/projects/aircraft-comac/flai-os`，主场）+ sim-live-hub（`~/projects/sim-live-hub`）；agent-cfd-live（`~/projects/cfd/agent-cfd-live`）**零改动·只读**。

---

## 1. 目标与非目标

### 目标
把一次**真实**的 CFD 求解（圆柱绕流 Re=100）接线成 FLAi-OS 工作台里一次**多 agent 协作、可实时监控、人工签发**的端到端流程——不重写任何现有系统，全部照三仓现有模板做薄接线。

### 成功判据
1. 编排官（真 GLM）能把"跑一个圆柱绕流 CFD 并评估结果"分流成召集 `cfd_solve_agent` + `cfd_evaluate_agent` 的协作会话。
2. 人提交「求解」任务 → 容器里**真跑 OpenFOAM**（非回放）→ FLAi-OS 工作台监控浮窗**实时流式**显示残差/Cl/Cd。
3. 人看到收敛后提交「评估」任务 → **确定性**算出 St/Cd_mean 对照 Williamson 0.164 → 出水印草案 → **人签发** → completed。
4. 求解发散/容器不可用/数据不足时**如实报错**，不伪造成功、不编造数字（诚实地板）。

### 非目标（本批不做）
- 参数化算例（Re/网格档可调）——固定 canonical case。
- FreeCAD→gmsh 几何建模全链——用预制 `case/template` + `cyl2d.msh`，跳过 FreeCAD。
- 把 CFD run 拷进 hub workspace / 重挂容器——直接只读 agent-cfd-live 的 `case/run`。
- 求解阶段并发多 run——固定算例，同一时刻一次求解。
- 求解自动触发评估——阶段间由人签发推进（贴 FLAi-OS「人是唯一签发者」）。

---

## 2. 已定决策（brainstorming 四问）

| # | 决策 | 选定 |
|---|------|------|
| 1 | 多 agent 拆分 | **两阶段：求解 Agent + 评估 Agent** |
| 2 | 求解形态 | **真实活求解**（fire-and-register，不阻塞 200s），回放 bundle 留作测试夹具 |
| 3 | 算例/入参 | **固定 canonical case（圆柱绕流 Re=100）**，评估对照 Williamson St=0.164 |
| 4 | hub 如何看见 run | **hub cfd_openfoam adapter 经配置路径只读 agent-cfd-live 的 `case/run`**（最薄；不拷贝/不重挂） |

---

## 3. 架构：三个薄接缝

```
用户 → 编排官(真GLM) → 计划：召集【cfd_solve_agent + cfd_evaluate_agent】
        │
  人建&提交「求解」任务
        ▼
① cfd_solve_agent ──→ [Tool: cfd_solve_launch]  (allow_shell_command, ADR-0022 同款)
        │   docker exec cfd-openfoam-live: 清run内容→铺template+gmshToFoam→checkMesh→nohup pimpleFoam&
        │   盖 run_id 时间戳 sidecar → 返回 run_id/run_dir → agent 设 task.sim_run_ref="cfd_openfoam@<run_id>"
        │   任务即 completed（fire-and-register，求解在容器后台真跑 ~200s）
        ▼
② sim-live-hub [native adapter: cfd_openfoam]  只读 case/run
        │   parser.collect(run_dir): 读 log.pimpleFoam 残差 + postProcessing/forceCoeffs1/0/*.dat 的 Cl/Cd
        ▼
   FLAi-OS 工作台监控浮窗 **实时流式** 残差/Cl/Cd（经 SimMonitorFloat 嵌 hub embed.html）
        │
  人看到收敛 → 建&提交「评估」任务（inputs.run_id）
        ▼
③ cfd_evaluate_agent ──→ [Tool: cfd_result_read]（只读）读该 run 的 log + forceCoeffs
        │   **确定性**算 St(Cl 振荡频率) + Cd_mean → 对照 st_ref=0.164 出判据
        │   LLM 只叙事（水印草案），数字全确定性 → requires_human_review → waiting_review
        ▼
  人签发 → completed  ← 人是唯一签发者，闭环
```

### 改动落点清单
**sim-live-hub**（1 个新 native 模块，不碰 `server/main.py`）：
- `adapters/cfd_openfoam/module.json`（kind=native，truth_sources 指向 CFD run 的 log/forceCoeffs，D/U/st_ref）
- `adapters/cfd_openfoam/parser.py`（`collect(run_dir, contract) -> dict`，读残差 + Cl/Cd → curves/state/provenance）
- run_dir 解析：hub 侧 config 指向 agent-cfd-live 的 `case/run`（见 §6）
- 现有 `adapters/cfd_external`（external_link 卡）**保留不动**——它是"独立面板"入口，与本 native 模块并存互补。

**FLAi-OS**（2 Tool + 2 Agent，照现有模板）：
- `tools_impl/cfd_solve_launch/`（adapter.py + tool.yaml + tests；allow_shell_command=true）
- `tools_impl/cfd_result_read/`（adapter.py + tool.yaml + tests；只读，mock=false，无 shell）
- `agents/cfd_solve_agent/`（agent.yaml 五件套：workflow.py + prompt.md + input_schema.json + output_schema.json + eval_cases/）
- `agents/cfd_evaluate_agent/`（同上）
- sim_run_ref 深链 / SimMonitorFloat / StatusDock：**复用现有**（R1 已建），零新前端码或极小。

---

## 4. 组件契约

### 4.1 Tool `cfd_solve_launch`（FLAi-OS，安全边界）
- **类型**：`allow_shell_command=true`，`mock=false`。照 `tools_impl/monitor_adapter_recon` 模板（ADR-0022 边界）。
- **输入**：`case: "cylinder_re100"`（固定枚举，本批只此一个）；`end_time`（可选，默认取 template 的 controlDict）。**无自由文本进 docker 命令**。
- **动作**（`subprocess.run(shell=False, 参数列表)`，每步 `docker exec ... bash -lc '<固定脚本>'`）：
  1. **重置** `case/run`：清内容**绝不删目录本体**（bind-mount 铁律，VirtioFS inode）——`bash -lc 'find /home/openfoam/run -mindepth 1 -delete'` 或等价，**不 `rm -rf` 整目录**。
  2. **铺算例**：从 `case/template` 复制 `0/ constant/ system/ cyl2d.msh` 到 `run/`。
  3. `gmshToFoam cyl2d.msh` → 修 frontAndBack 为 empty → `checkMesh | tee checkMesh.log`。
  4. **发起求解**：`nohup pimpleFoam > log.pimpleFoam 2>&1 &`（fire，立即返回）。
  5. 盖 `run_id`（`YYYYMMDD-HHMMSS`）写入 sidecar `case/run/.hub_run_id`。
- **输出**：`{run_id, run_dir, container, launched_at, checkmesh_ok}`。求解在后台跑，Tool 不等。
- **fail-closed**：容器未 up / config（`FLAI_CFD_*`）缺失 / checkMesh 失败 / gmshToFoam 报错 → 抛错，**绝不谎报已发起**。
- **安全**：容器名/路径来自可信 config（`FLAI_CFD_CONTAINER`/`FLAI_CFD_CASE_DIR`/`FLAI_CFD_TEMPLATE_DIR`），非请求体；`case` 枚举白名单；docker 命令为固定脚本模板，零用户串拼。

### 4.2 Tool `cfd_result_read`（FLAi-OS，只读）
- **类型**：`mock=false`，**无 shell**（source_mode=host，bind-mount 使 run 输出在宿主文件系统，直接 `read_text`）。
- **输入**：`run_id`（对账 sidecar `.hub_run_id`，防读错 run）。
- **动作**：读 `case/run/log.pimpleFoam` + `postProcessing/forceCoeffs1/0/*.dat`；解析残差序列 + Cl(t)/Cd(t)。
- **输出**：`{run_id, converged: bool, cl_series, cd_series, resid_tail, n_cycles, wall_clock_s, ended: bool}`（原始数据，不下判据）。
- **fail-closed**：run_id 与 sidecar 不符 / 文件缺失 / 求解未产数据 → 如实报缺，不补零、不编造。

### 4.3 Agent `cfd_solve_agent`
- **category**：`tool_automation`（Tool 驱动，零 LLM，照 `performance_disk_agent`）；**mode=job**；`requires_human_review=false`（发起动作本身不需审——人建任务即人的动作；审在评估阶段）。
- **input_schema**：`{case: enum["cylinder_re100"]}`（+ 可选 end_time）。
- **workflow.py**：调 `cfd_solve_launch` → 拿 run_id → 产 output（run_id + "已发起真实求解，实时监控见工作台浮窗"）→ completed。
- **sim_run_ref 写入（待 plan 钉的接缝）**：`task.sim_run_ref = cfd_openfoam@<run_id>` 经 `repos.set_task_sim_run_ref`（metadata 标注非状态迁移，非 HTTP 端点）。**plan 阶段确认 workflow 执行上下文是否有 repos 写权**；若无，退化为 JobRunner 在 agent 返回结构化 output（含 run_id）后由运行时回填 sim_run_ref，或人在求解任务完成页一键「关联监控」。三条路都不破「人是唯一签发者」（关联是 metadata 标注非状态迁移）。
- **maturity**：L0/status=draft。

### 4.4 Agent `cfd_evaluate_agent`
- **category**：`reasoning_assist`（LLM 叙事）；**mode=job**；`requires_human_review=true` → waiting_review → 人签。
- **input_schema**：`{run_id: string}`。
- **workflow.py**：
  1. 调 `cfd_result_read` 拿原始 Cl/Cd/残差。
  2. **确定性 oracle**（纯 Python，非 LLM）：从 Cl(t) 算振荡频率 f（末段稳定周期，zero-crossing 或 FFT）→ `St = f·D/U`；`Cd_mean`（末段均值）；收敛判据（残差 < tol 且 ≥N 个稳定周期）。
  3. **对照** `st_ref=0.164`：算相对误差；给"收敛/未收敛 · St 误差 X% · Cd_mean" 结构化判据。
  4. LLM（reasoning）**只叙事**这些确定性数字（工程解读），**强制水印**「AI 辅助草案，未经工程师确认」+ 数字来自确定性计算的声明。
  5. 数据不足/未收敛 → 如实草案"未达评估条件"，**绝不编造 St**。
- **产物**：`evaluation.json`（确定性数字 + provenance 指回真源）+ `cfd_eval_draft.md`（水印叙事草案）。
- **maturity**：L0/status=draft。

### 4.5 sim-live-hub `cfd_openfoam` adapter
- **module.json**：`kind=native`，`name=cfd_openfoam`，`domain=cfd`，`truth_sources={curves: log.pimpleFoam + forceCoeffs, write_mode: streaming, note}`，`D/U/st_ref`。
- **parser.py `collect(run_dir, contract)`**：读残差 + Cl/Cd → 返回 hub state schema（curves/state/provenance/停滞判据）。可参考 agent-cfd-live `server/parsers.py` 的正则（RESID_RE / forceCoeffs 列映射）**重实现**（跨仓不 import，复制数值行为 + golden 对账）。
- **停滞 fail-loud**：复用 hub 契约（真源断更 → 停滞报警穿透浮窗 pill）。

---

## 5. 数据流与时序（fire-and-register + 人门控）

1. 用户对编排官：「跑一个圆柱绕流 CFD 并评估结果」。
2. 编排官（GLM）出 orchestrate 计划：召集 `cfd_solve_agent`（预填 case=cylinder_re100）+ `cfd_evaluate_agent`（run_id 待求解后填）。协作会话锚 conversation_id。
3. 人在创建页提交「求解」任务 → `cfd_solve_agent` 跑 → Tool 发起求解 + 设 sim_run_ref → 任务 completed（秒级返回）。
4. 求解在 `cfd-openfoam-live` 容器后台真跑 ~200s；hub `cfd_openfoam` adapter 只读 case/run 流式；**FLAi-OS 工作台监控浮窗实时显示残差/Cl/Cd**（人点求解任务的「查看仿真监控↗」深链 `#/cfd_openfoam@<run_id>`，或浮窗自动聚焦运行态）。
5. 人看到 Cl 起振、涡街形成、残差收敛（~11 cycles）。
6. 人提交「评估」任务（inputs.run_id = 上一步 run_id）→ `cfd_evaluate_agent` 确定性算 St/Cd + LLM 叙事草案 → waiting_review。
7. 人审阅草案（St≈0.167 vs 0.164 → 误差~2%，收敛）→ **签发** → completed。协作会话闭环。

---

## 6. run 身份 / sim_run_ref / hub 观测（待 plan 阶段钉的实现细节）

- **run_id**：`YYYYMMDD-HHMMSS`，`cfd_solve_launch` 盖进 `case/run/.hub_run_id`。与 hub 时间戳-run 身份判据同构（停滞/换源判据依赖时间戳名，见 sim-live-hub spec §1）。
- **sim_run_ref**：`cfd_openfoam@<run_id>`（match 现有深链 `#/<mod>@<run_id>` 格式）。
- **hub Collector 如何拿到 run_dir**：hub 侧需一个 config 把 `cfd_openfoam` 模块的 run_dir 指到 agent-cfd-live 的 `case/run`（fixed 单目录，非时间戳子目录）。**这是本设计与 hub「每模块 workspace/时间戳子目录」惯例的唯一偏差，plan 阶段确认落法**：方案倾向 hub config 增 `cfd_openfoam.watch_dir` 显式配置项（默认指 agent-cfd-live case/run），run 身份靠 `.hub_run_id` sidecar 而非目录名。若与 hub 停滞判据（依赖时间戳目录名）冲突，退化为 hub 侧建一个指向 case/run 的时间戳符号链接（但 symlink 在 hub 有安全收紧史，需评估）。
- **config/env**（FLAi-OS 侧，全部 fail-closed 未设即拒）：
  - `FLAI_CFD_CONTAINER=cfd-openfoam-live`
  - `FLAI_CFD_CASE_DIR`=agent-cfd-live `case/run` 宿主绝对路径
  - `FLAI_CFD_TEMPLATE_DIR`=agent-cfd-live `case/template`
  - hub 侧：`config.json` 增 `cfd_openfoam.watch_dir`（或等价）。

---

## 7. 安全 / 治理

- **allow_shell_command 边界（命中即审）**：`cfd_solve_launch` 触安全边界 → **Codex 异源审阻塞**（同 ADR-0022/monitor_adapter_recon 纪律）。红线：`shell=False` 参数列表 · 容器名/路径来自可信 config 非请求体 · `case` 白名单枚举 · docker 脚本固定模板零用户串拼 · 容器未 up / config 缺失 fail-closed。
- **bind-mount 铁律**：清 `case/run` 只清内容**绝不 `rm -rf` 目录本体**（VirtioFS inode 悬空+breakout，memory 实测 P1）。tamper：注入删目录本体的变异必被守卫咬。
- **taint/分级**：CFD run 为通用圆柱算例，无 EAR/敏感 → classification=internal。评估产物同 internal。
- **人是唯一签发者**：求解 agent 只发起（人建任务=人的动作）；评估 agent 只产草案；**签发在人**。ADR 记新 Tool/Agent 与 allow_shell_command 边界。
- **L0/draft**：两 agent 均 L0/status=draft；L0→L1 晋升属 M10 治理步不代拍。

---

## 8. 错误处理（fail-closed 一览）

| 场景 | 行为 |
|------|------|
| `cfd-openfoam-live` 容器未 up | `cfd_solve_launch` 抛错，任务 failed，诚实文案「容器未就绪」，绝不谎报已发起 |
| `FLAI_CFD_*` 未配 | fail-closed 拒跑（同 monitor Tool `FLAI_MONITOR_CORE_DIR` 语义） |
| gmshToFoam/checkMesh 失败 | 抛错，failed，附 stderr 尾；不发起求解 |
| 求解发散/中途崩 | hub adapter 停滞报警穿透浮窗；`cfd_result_read` 如实报数据不足；评估草案「未收敛，无法给可信 St」 |
| run_id 与 sidecar 不符 | `cfd_result_read` fail-closed（防读错 run） |
| 清目录误删目录本体 | 守卫拒绝（bind-mount 铁律），tamper 咬合 |

---

## 9. 测试 / 验证

- **单元**：
  - `cfd_solve_launch`：mock docker（subprocess monkeypatch）验参数列表 shell=False / 容器名来自 config / case 白名单 / 清目录不删本体 / config 缺失 fail-closed。
  - `cfd_result_read`：golden log.pimpleFoam + forceCoeffs → 期望 Cl/Cd 序列；run_id 不符 fail-closed。
  - `cfd_evaluate` oracle：**golden 数据（回放 bundle 的 good-run forceCoeffs）→ St≈0.167（±tol）/ Cd_mean≈1.40**；未收敛数据 → 判「数据不足」不出 St。
  - hub `cfd_openfoam` parser：golden run_dir → 期望 curves/state；停滞判据。
- **E2E**（`frontend/e2e/` 新套，入 verify_all）：
  - 真求解路径（需容器）：提交求解 → sim_run_ref 落库 → 提交评估 → 确定性 St → 人签 → completed。
  - **回放 bundle 作确定性夹具**（无容器可跑）：用 agent-cfd-live good-run bundle 喂 `cfd_result_read` → 评估 → 签发，全链绿。
- **tamper（必咬）**：
  - 求解 Tool 强改成 `rm -rf` 目录本体 → 守卫红。
  - config 恒真绕过 fail-closed → 红。
  - 评估 St 从被篡改 forceCoeffs 算出错值 → oracle 对照 golden 咬。
  - 伪造「已发起」但容器没跑 → fail-closed 咬。
- **异源审**：`cfd_solve_launch` allow_shell_command 边界 → Codex 异源审（命中即审，阻塞落地）。
- **契约 parity**：两 agent + 两 Tool 过 registration 契约 parity gate（`test_contract_parity`）。

---

## 10. 诚实标注（load-bearing）

- 监控浮窗显示的是**真·实时** OpenFOAM 求解（非回放）——UI 不标"回放"。
- 评估 St/Cd **确定性计算**，LLM 只叙事；草案强制水印「AI 辅助 · 未经工程师确认 · 判定权在人」。
- 若数据不足/未收敛，草案如实报缺，**绝不编造 St 逼近 0.164**（Goodhart 防御：oracle 参照 0.164 但不得反向拟合）。
- 回放 bundle 仅作**测试夹具**，不冒充生产监控数据。

---

## 11. 递延 / 风险 / 开放项

- **递延**：参数化算例（Re/网格档）；FreeCAD 建模链；并发多 run；求解自动触发评估；L0→L1 晋升。
- **风险**：
  1. **hub run_dir 解析**（§6）是与 hub 惯例的唯一偏差——plan 阶段先钉落法（config watch_dir vs symlink），勿边写边猜。
  2. 真求解 ~200s：E2E 真跑慢，CI 走回放夹具；真跑作手动/演示验证。
  3. St 计算方法（zero-crossing vs FFT）需对 good-run golden 校准到 agent-cfd-live 的 0.16734 同量级——oracle 正确性是评估可信度的根，先写测试后写实现。
  4. 跨仓路径耦合（hub→agent-cfd-live case/run，FLAi-OS→两者）：全 config 驱动 + fail-closed，不硬编码。
- **开放项（可 plan 前定，也可 plan 中定）**：评估叙事是否真调 GLM（vs 纯确定性无 LLM）——当前设计=真 GLM 叙事+确定性数字；若要零 LLM 更稳可降为 structured_gen。

---

## 12. 实施顺序（writing-plans 展开）

建议相位（每相自证，接缝契约先行）：
1. **P1 hub cfd_openfoam adapter**（先有可监控真源，用 agent-cfd-live 现有 case/run 或 good-run 验 parser）。
2. **P2 FLAi-OS `cfd_result_read` + `cfd_evaluate_agent`**（确定性 oracle + 回放夹具全链，无需容器）。
3. **P3 FLAi-OS `cfd_solve_launch` + `cfd_solve_agent`**（真求解发起 + sim_run_ref，安全边界，Codex 审）。
4. **P4 编排官联调 + E2E + 监控浮窗深链**（真求解→监控→评估→签发全链 + tamper + verify_all）。

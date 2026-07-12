# R1 · 仿真 surface 平台注册记录（ADR-0020 分相 R1 收口）

> 状态：**已注册**（2026-07-12）
> 关联：ADR-0020 §决策 R1 · docs/09 接入标准 · docs/reviews/SIM-MONITOR-FLOAT-record.md
> · [[project_sim_live_hub]] · sim-live-hub 仓 docs/pm-review-2026-07-12.md

## 1. 注册对象与范围（owner 定位）

**注册对象 = 「把任意批式/流式计算工作流变成可实时追踪、可点验、不说谎的监控
窗口」这套接法（方法）**，不是某台机器上的某几个求解器实例（ADR-0020 定位重述）。
本次 R1 把其中的**仿真 surface**（求解器真源数据面）正式登记进平台发现面。

**范围声明（owner R1 裁决：暂不加访问控制 + 范围声明）**：

> 仿真监控数据面向**内网只读**。R1 不加独立访问控制（求解器真源敏感度低，
> fail-closed 启动门已保证操作员**转录** surface 不裸奔）。最小访问控制候选
> （共享 token / 反代 basic-auth）挂 M4 内网侦察后按实况定。

**明确不在 R1 范围**：
- **转录 surface**（操作员 Agent 会话思考/操作流）——留操作员本机档位，多用户
  可见性走「演示模式白名单」（owner R3 裁决，已在 hub 侧落地 `demo_mode` +
  `workbench_exposed()` + `bind_security_error` + 双页红标，仓库默认 `demo_mode=false`）；
  正式入平台发现面仍待 owner 授权模型（ADR-0020 §分相 R3）。
- CFD = agent-cfd-live 外链卡，不整合。

## 2. 前置条件核对（ADR-0020 R1 前置，全部已达成）

R1 前置 = M11 鉴权落地 → verify_all 全量复跑 + 探针改真登录 → StatusDock 发现
入口 + per-task run_ref 落库（监控线决策书 Next-2 转正批，顺序不跳队）。逐项实证：

| 前置 | 状态 | 证据 |
|---|---|---|
| M11 鉴权落地 | ✓ | flai-os `995cdd0`（ADR-0019，default-deny 会话鉴权 + Codex 5 轮治理审） |
| verify_all 全量复跑全绿 | ✓ | `ec9c4b1`（8 套 e2e 含 m11_auth 5/5，清掉浮窗记录 §5 最大挂账） |
| 探针改真登录 | ✓ | hub `d4a00c0`：去 WelcomeGate CSS 豁免，自起临时库 flai 后端 + seed_user + 真实 `POST /api/auth/login` |
| StatusDock 发现入口 | ✓ | flai-os `c293a83`：中性色监控入口（simhub 配置才现、不占信任色锁、默认关零渲染） |
| per-task run_ref 落库 | ✓ | flai-os `c293a83`：`repos.set_task_sim_run_ref` + `POST /api/tasks/{id}/sim-run-ref` + TaskDetail 深链 `#/<mod>@<run_id>` |
| 治理审收口 | ✓ | Codex 治理审 `c293a83` 零 P1 + 四 P2 → fix `b4f1e0d` push（记录见浮窗记录 §6.1） |

## 3. 「平台可发现」的落地形态（已交付代码，非本次新增）

R1 不引入 surface-manifest 系统（M8 已判之于本平台 over-eng）。可发现性由已交付
的三处 UI 承载，**config 门控**（`localStorage.flai.simMonitorHub`，经 `?simhub=`
确认闸设定）——不强制默认开，与「hub 侧无鉴权是已知边界 + 内网只读」posture 一致：

- **StatusDock 发现入口**：全局状态坞中性色「监控 ↗」链接（配置后出现，让同事不用
  记 `?simhub=` 咒语就能进）。
- **TaskDetail 深链**：任务关联仿真 run（`metadata.sim_run_ref`）时「查看仿真监控」
  深链直达 `#/<mod>@<run_id>` 该 run 视图，否则回退 hub 首页。
- **SimMonitorFloat 浮窗**：会话区悬浮双页签（仿真 / 工作台），iframe 装 hub
  `/embed.html`，postMessage 严格 origin 闸 + 类型闸 + status 枚举 fail-closed。

## 4. 三件套注册状态（ADR-0020 §决策 1）

| 件 | 内容 | R1 后状态 |
|---|---|---|
| **标准** | docs/09 接入契约（双层诚实模型 / 智能展示红线 / adapter 契约 / tamper 实证门 / 接缝契约） | 已成文（草案 v0.1），三异构域验证 |
| **窗口** | 浮窗 + 完整面板（消费接缝契约的通用 UI，SSOT 在监控节点） | 已交付 |
| **生成器** | `monitor_adapter_gen` agent（起草新接入的 adapter，L0→L1 治理轨道） | **R2 进行中**（承重核已在 hub 侧实现，平台 agent 包立包中） |

## 5. 智能展示红线（登记为注册约束，docs/09 §3）

- Agent 可智能化**选择权**（聚焦哪条曲线/哪帧场图/哪个参数）——属叙事层，
  必须标注「由 agent 推荐的视图」+ 依据。
- **绝不智能化数据权**：上屏任何数值/图像不得由模型生成、插值、平滑、美化。
- 监控线**永远只读观察者，不兼执行者**（观察者兼执行 = 自己给自己打分，
  验证价值归零）。

## 6. 残余风险（登记在案）

- 监控节点（mac）仍是单点、hub 侧无鉴权 = 已知边界；R1 以「内网只读」范围声明
  接受，最小访问控制挂 M4 内网前置清单一并裁。
- 转录 surface 可见性授权模型属 owner 决策，R1 不代拍；裁决前保持本机档位。
- 生成器起草的 adapter 若跳过 tamper 实证直接用 = 假绿批量化；对策见 docs/09 §4
  硬门（draft 不实证不注册，fail-closed）+ R2 治理轨道。

## 7. 结论

**仿真 surface R1 正式注册完成**：前置全达成、治理审 R0 收口、可发现性代码已交付、
范围与红线登记在案。R2 生成器 agent 注册继续推进；R3 转录 surface 待 owner 可见性
授权模型裁决。

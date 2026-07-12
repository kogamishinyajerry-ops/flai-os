# 09 · 工作流实时可视化接入标准（Workflow Live Monitor Standard）

> 状态：**草案 v0.1**（ADR-0020 立案，分相注册进行中）
> 实现契约 SSOT = 仿真节点仓 `sim-live-hub/docs/spec.md`（本文只定平台注册面的
> 要求与边界，不复制实现细节——复制必腐烂）。参考实现已在三个异构域验证：
> SIMP 拓扑优化（CLI+csv）、CalculiX 结构应力（.sta/.cvg 流式）、PCMS/MATLAB
> （批处理+wrapper 分段），外加 CFD 外链卡。

## 1. 定位

本标准回答一件事：**任何批式/流式计算工作流，怎样接入平台变成一个可实时
追踪、可点验、不说谎的监控窗口**。注册对象是这套接法（方法），不是某台机器
上的某几个求解器实例。内网换 STAR-CCM+ 或任何别的引擎，变的只是 adapter 里
「真源文件长什么样」，方法不变。

## 2. 双层诚实模型（不可协商的地基）

- **证据层**：曲线数值、场图、收敛判据、gate 结果——只来自求解器/harness
  真实产物文件，采集侧与展示侧全程只读，**零生成、零插值、零代算**。
- **叙事层**：发起意图、阶段自述、（若有）Agent 的思考与推荐——可以展示，
  必须显著标注为叙事层，可与证据层并排对账。
- **每个上屏数字必须带 provenance**（真源文件路径+读取方式），观众可点验。
- **fail-loud 两路停滞**：真源断更（目录无增长）与发起未落地（ledger 有
  launch 而无对应新生 run）都必须报警，绝不让旧数据装活。run 身份判据用
  时间戳命名目录（迟到写入推得高 mtime、改不了出生名）。

## 3. 智能展示的红线（本次注册新增的一条）

允许 Agent 智能化**选择权**：判断当前聚焦哪条曲线、哪帧场图、哪个参数信息量
最大——该选择属叙事层，必须标注「由 agent 推荐的视图」+ 依据。
**绝不允许智能化数据权**：上屏的任何数值与图像不得由模型生成、插值、平滑、
美化。选择权与数据权的边界一旦模糊，双层模型即塌缩为好看的假绿仪表盘。

## 4. adapter 接入契约（每个工作流声明一份）

必须声明：真源仓路径与 run 发现规则（时间戳目录+marker）· truth_sources
（curves/field/gates 各自的文件与解析）· write_mode（streaming | batch_at_end，
后者的 paced-reveal 揭示必须全程 disclose，不冒充实时）· stages · 停滞阈值。
硬性质量门：**新增 adapter 零改动监控核**（server 通用轮询环）；上线前必须
完成 **tamper 实证**（SIGKILL/断源必须咬红）+ 对称正测（真跑必须绿）——
「全绿但无咬合实证 = 假信心」，视同未验证。

## 5. 嵌入接缝（平台浮窗侧契约）

postMessage 单向上报：类型 `sim-live-status`，`surface` 分流，targetOrigin
严格等于宿主传入的规范化 http(s) origin，**绝不 `"*"`**；嵌入页由服务端
`frame-ancestors` CSP 白名单锁定装载方；宿主侧四道闸（origin 逐字等 / 来源
绑定到自家 iframe 窗口 / 类型闸 / status 枚举 fail-closed）。状态枚举与字段
冻结于接缝契约测试，扩状态集=先改契约测试再改码。

## 6. 安全与可见性分相

- 监控服务默认回环绑定；非回环 + 会话转录未锁定 = **拒绝启动**（fail-closed）。
- **仿真 surface**（求解器真源数据）：注册后平台可发现，面向团队。
- **转录 surface**（操作员 Agent 会话的思考/操作流）：留在操作员本机档位，
  多用户可见性授权模型经 owner 裁决前不入平台发现面（ADR-0020 §分相）。

## 7. 注册路径

新工作流接入 = 起草 adapter（可由 `monitor_adapter_gen` agent 生成草案，见
`docs/design/monitor-adapter-gen-agent-contract.md`）→ 人审 + tamper 实证 →
注册进监控节点 config → 评测 case 固化，走平台 07 评测标准与 M10 治理轨道
（L0 draft → 评审 → L1）。draft 产物**永不自动生效**。

# ADR-0028：TeleAI 同源律/集成律评估 + Model Gateway `profile="draft"` 有限开闸

- **状态**：Partially Accepted（2026-07-19）——**作为架构决策否决**，**作为 agent 实现技巧开放**
- **关联**：Fable5 执行任务书 §2（Agent 是平台插件）· Constitution 第 9 条（LLM 不负责确定性计算）·
  ADR-0011（M5 平台泛化）· 研讨会纪要 `/Users/Zhuanz/docs/FLAi-OS-V0.2-同源嵌套研讨会纪要.md`
- **评估依据**：arXiv 2506.12479v3《AI Flow: Perspectives, Scenarios, and Approaches》(60页, 2025-07) ·
  TeleAI 李学龙 WAIC 2025 论坛演讲稿 · 3-agent 对抗式研讨会（正方/反方/工程师视角）

## 一、议题与裁决

**议题**：FLAi-OS 工位 agent 与中心 agent 之间的关系，是否采用 TeleAI 智传网提出的"同源嵌套"
（工位 agent 是中心 agent 的参数子集，共享中间表示，draft-then-verify 接力）？

**裁决**（研讨会三方共识，2026-07-19）：

| 维度 | 决策 | 理由 |
|---|---|---|
| 同源嵌套作为 V0.2 架构决策 | **否决** | 破坏"Agent 是平台插件"契约（Fable5 §2）；依据强度进不了 ADR |
| Model Gateway 增加 `profile="draft"` | **采纳**（纯增量） | 现有 profile 机制零改动承载，不动 Constitution/agent.schema.json |
| 同源嵌套作为单个 agent workflow.py 实现技巧 | **开放**（不强制、不禁止） | 6 个已封板 case 一个不重写；新 agent 自选 |
| 性能盘 Agent V0.2 异常识别试点 | **采纳** | 唯一识别出的真应用点（见 §三） |
| 对外宣称"基于 TeleAI 同源律" | **禁止** | 三大定律为企业自提概念，credibility 不足以支撑对外叙事 |

## 二、否决"作为架构决策"的四条理由

### 2.1 代码层与"多 profile 路由"是同一件事（研讨会识别的伪命题）

```python
# 现状（已有能力）
model_gateway.chat(profile="reasoning", messages=...)  # GLM-5.1 4bit

# 所谓"同源嵌套"在代码层的表现
draft = model_gateway.chat(profile="draft", messages=...)      # GLM-1.5B
final = model_gateway.chat(profile="reasoning", draft=draft)   # GLM-5.1
```

**就是两次 chat 调用**。Model Gateway 已有的 profile 机制天然承载，agent.yaml/workflow.py 独立
决定要不要用——平台层零架构改动。把"两次 chat 调用"包装成"架构决策"是过度叙事。

### 2.2 Constitution 第 9 条已划定红线

> "LLM 不负责确定性计算。确定性计算、文件解析、数值校验、工具调用必须由工程代码完成。"

性能盘 Agent 的 `agent.yaml` 进一步禁止 LLM 参与：性能数值计算 / 硬规则校验 /
输入文件确定性生成 / 输出文件确定性解析 / 数据入库 / 判断最终工程结论。

这意味着就算工位用 1.5B 出 draft，**这份 draft 在工程链路上没有任何决策价值**——
反正最后都要 Tool Registry 调 performance_disk_runner 走工程代码，反正最终都要
工程师人工签发（"人是唯一签发者"）。draft-verify 范式在 FLAi-OS 的 LLM 参与面上
收益极小。

### 2.3 三大定律依据强度不足

- 信容律 / 同源律 / 集成律目前是 TeleAI 单方面命名
- arXiv 2506.12479 是技术报告（technical report），非同行评议期刊论文
- 学界尚未广泛跟进引用
- `docs/adr/` 现有 27 个 ADR，每条都有"替代方案 + 公理/行业共识引用"——
  企业自提概念作为 ADR 决策依据，3 个月后业务部门同事问"根据是什么"答不上来

**作为"已评估概念"记录在案可以，作为"决策依据"不行。**

### 2.4 FLAi-OS 真痛点是 CAE 算力，不是 LLM 算力

- 数字部手里的是 HPC（CAE 仿真算力），300 万算力方案买的也是 CAE 算力
- LLM 推理算力内网已部署 GLM-5.1 4bit，够用
- 同源嵌套解决的是 LLM 端-边-云协同——**对解决核心阻塞零贡献**
- speculative decoding 对 FLAi-OS 整体性能影响 < 1%（LLM 调用本就是非瓶颈）

把精力错配到 LLM 端-边-云协同上，不如推进 300 万算力方案与数字部 HPC 配额谈判。

## 三、唯一识别的真应用点：性能盘 Agent V0.2 异常预筛

研讨会在 5 条共识之外，识别出**同源嵌套在 FLAi-OS 唯一有工程价值的落点**：

**场景**：性能盘 Agent V0.2 异常识别环节（V0.1 尚未涉及，V0.2 路线图已规划）

**当前流程**：
```
性能盘跑完 → 全量结果进 Excel → 工程师人眼扫一遍找异常 → LLM 生成摘要报告
```

**引入 draft 后**：
```
性能盘跑完 → 1.5B 小模型先扫 50 case 标记"看起来异常的"（draft）
         → 大模型只 verify 这几个 → 报告
```

**为什么这个用法合法**：
- 绕开 Constitution 第 9 条——小模型只预筛不判定，最终工程结论仍由工程师签发
- 绕开工位硬件瓶颈——1.5B 量化版办公电脑能跑（或在科室共享服务器上跑）
- 绕开"LLM 不参与判定"红线——draft 是辅助标注，不是决策
- 省工程师的人眼扫描时间，对账从 50 case 缩到 5-10 case

**验收口径**（写入性能盘 Agent V0.2 eval）：
- draft 预筛命中率 ≥ 70%（不是工程精度，是真异常 case 的召回率）
- draft 误报率 ≤ 30%（非异常 case 被误标的比例）
- draft 漏报率 = 0%（真异常 case 漏标即失败——fail-closed，宁可多报不可漏）

## 四、落地动作

| 序号 | 动作 | 工作量 | 验收标准 |
|---|---|---|---|
| 1 | 在 Model Gateway 配置层注册 `profile="draft"`，绑定 GLM-1.5B 4bit 量化版（走环境变量，不入库入仓） | 半天 | `model_gateway.chat(profile="draft")` 返回非空，端点通过 `FLAIOS_DRAFT_BASE_URL` 等环境变量注入 |
| 2 | `contracts/model_profile.schema.json` 零改动（schema 本就支持任意蛇形小写 profile 名） | 0 | 现有契约已承载 |
| 3 | 性能盘 Agent V0.2 异常识别 workflow.py 实现 draft-verify 试点 | 2-3 天 | 在 50 case 批量跑中，验收口径三项达标 |
| 4 | V0.1 已封板 6 个 case 一个不重写 | 0 | agent-cfd-live / agent-structure / 等零改动 |
| 5 | control_logic_agent / fta_agent（M5 里程碑）不强制使用同源嵌套 | 0 | 各 agent.yaml 独立声明，平台中立 |

**不做的事**：
- 不改 `docs/00_FLAi-OS_Constitution.md`
- 不改 `contracts/agent.schema.json`
- 不在 `docs/08_Department_AI_Playbook.md` 引入"同源嵌套"术语
- 不对外（含所长汇报、部门培训）宣称"基于 TeleAI 同源律/集成律"

## 五、残余风险（诚实标注）

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| GLM-1.5B 4bit 量化版在工位办公电脑上实际性能未知 | 中 | 先在科室共享服务器部署，不直接推工位；试点期收集实际推理时延 |
| draft 预筛在异常 case 极少时（< 5%）可能全报正常 | 中 | fail-closed 兜底：当 draft 全标正常时仍走一遍大模型 verify |
| 性能盘 Agent V0.2 异常识别本身尚未定义"异常"的工程标准 | 高 | 本 ADR 不解决此问题，挂账给性能盘 Agent 业务负责人，落地前先出"异常判定准则" |
| 后续若 TeleAI 三大定律获同行评议广泛引用，本 ADR 需要复审 | 低 | 复审触发条件：Google Scholar 同源律引用 ≥ 10 次或顶会正式论文出现 |

## 六、对外口径（统一话术）

**问：FLAi-OS V0.2 是否基于 TeleAI 智传网同源律？**

答：**不是**。我们在 V0.2 规划期评估了 TeleAI 的同源嵌套范式，结论是 FLAi-OS 现有的
Model Gateway profile 机制已经能承载同等能力，不需要把它上升为架构决策。性能盘 Agent V0.2
的异常识别环节会使用 `profile="draft"` 做小模型预筛试点，这只是 agent 层的实现选择，
不是平台架构变更。FLAi-OS 的核心阻塞是 CAE 仿真算力（在数字部手里），与 LLM 端-边-云
协同无关，我们的精力优先放在真痛点上。

## 影响面

- `backend/app/model_gateway/`（配置层注册 draft profile，零 schema 改动）
- `agents/performance_disk_agent/workflow.py`（V0.2 异常识别环节，**未来改动**）
- `agents/cfd_solve_agent/`、`agents/structure_agent/` 等 V0.1 已封板 agent：**零改动**
- `contracts/model_profile.schema.json`：**零改动**（schema 本就支持）
- `docs/00_FLAi-OS_Constitution.md`：**零改动**
- 对外叙事：**不引用同源律/集成律作为架构依据**

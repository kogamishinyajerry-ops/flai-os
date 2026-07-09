# ADR-0011: M5 平台泛化验证两项裁决

- 状态：已接受（2026-07-09）
- 背景：M5（任务书 §12.6）需证明平台承载不同类型 Agent 而非性能盘专用。
  新增两个轻量 Agent，各自首次激活一条此前无真实 Agent 用过的平台能力。
- 决策：
  1. **三类 Agent 同一 Runtime 承载即泛化实锤**：tool_automation
     （hello/performance_disk）、structured_gen（control_logic）、
     reasoning_assist（fta）共用同一 AgentRuntime/Registry/Task Center，
     平台内核零改动——新增 Agent = 新增 Package + 注册（宪法对象关系）。
  2. **control_logic_agent 纯确定性、无 LLM**：结构一致性检查（重名/悬空
     转移）与可达性分析（BFS）是精确图问题，LLM 参与只会引入不可复核的
     噪声；「结构化生成型」的价值恰在于展示平台对 0-LLM Agent 的承载。
     语义校验失败一次列出全部问题（不挤牙膏）。
  3. **fta_agent 首次激活两条链**：①Model Gateway 真实调用链
     （model.profile=reasoning，Agent 不见具体模型名）；②waiting_review
     人工放行链（M1 建成 review API 至今无真实 Agent 使用）。
  4. **fta 的 LLM 边界（三重防线）**：草案原样存档绝不解析为真值（workflow
     不据此下任何结论）；fta_draft.md 头部强制水印「未经工程师确认不得用于
     安全性判断或设计决策」；requires_human_review=true 强制具名放行
     （宪法铁律六 + §11.2）。上游失败诚实 failed，绝不伪造草案。
     system prompt 唯一来源=包内 prompt.md（运行时读取，无内嵌副本，
     改 prompt 必升版本）。
  5. **stub gateway 测试策略**：成功路径在 TestClient 启动后
     `app.state.runtime.model_gateway = stub` 注入（AgentRuntime 逐次
     execute 读该属性，与构造注入等价）；失败路径刻意用真实 Gateway +
     清空 FLAI_LLM_* 环境变量（fail-closed 不触网络，顺带验证 gateway
     的 model_calls 留痕）。真实模型调用待内网配置三个环境变量后即通，
     Agent/平台代码零改动（docs/04）。
- 影响与风险：fta 草案质量未经真实模型验证（stub 只证链路）——首次内网
  真跑时按 docs/07 建评测集；control_logic 不理解转移条件语义（互斥/覆盖
  不检查），已写入 limitations。

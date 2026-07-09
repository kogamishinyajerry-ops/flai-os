# ADR-0003: 所有模型调用必须经过 Model Gateway（画像制）

- 状态：已接受（2026-07-08）
- 背景：模型会持续升级（GLM-5.1→5.2→多模态/Embedding/Rerank），Agent 直连模型
  = 每次升级全量改代码；上一代平台两处 LLM 调用点各自硬编码端点已被证明是债。
- 决策：Agent 只声明模型画像（profile：reasoning/fast/vision/code/embedding/
  rerank），Gateway 按 `backend/app/model_gateway/profiles.yaml` 解析到具体模型；
  agent.yaml 的 profile 字段 pattern 禁止出现模型名形态（含点号/连字符即拒）；
  每次调用落 model_calls 表。
- **fail-closed 条款**：上游不可达 → 如实报错 + 落事件，绝不静默降级、绝不返回
  编造内容（宪法第五条在模型层的落点）。
- 替代方案：环境变量直连（被否：无画像抽象，多模型时代必乱）。
- 影响与风险：多一层间接（V0.1 代价极小）；profiles.yaml 是敏感配置，端点/key
  走环境变量绝不入仓。

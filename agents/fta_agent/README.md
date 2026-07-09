# fta_agent（FTA 辅助草案生成）

「推理辅助型」平台样板（M5 泛化验证），也是平台**首个真实走通两条链**的 Agent：

1. **Model Gateway 调用链**：经 `model.profile: reasoning` 画像调用推理模型
   （Agent 不知道也不关心具体模型名，宪法铁律一）；
2. **waiting_review 人工放行链**：`requires_human_review: true`——任务永远
   停在 waiting_review，由工程师经 `POST /api/tasks/{id}/review` 具名放行
   （approve→completed / reject→failed），M1 建成以来首次被真实 Agent 使用。

## LLM 边界（铁律，勿破）

- 模型输出的自由文本**原样**存为 `fta_draft.md` 草案：workflow 不解析其内容
  当确定性真值，不据此下任何工程结论；
- 草案文件头**强制水印**：「⚠ 本故障树为 AI 辅助生成的草案，未经工程师确认，
  不得用于任何安全性判断或设计决策」；
- 不做定量概率计算——草案中出现的任何数字均不可信（见 limitations）；
- Gateway 无 key/上游失败：任务诚实 failed（`model_call` error 事件留痕），
  **绝不伪造草案**。

## 使用

inputs：`{top_event, system_description, components:[...]}`。任务跑完停
waiting_review，工程师在任务详情页审阅 `fta_draft.md` 后批准/拒绝。

## prompt 版本化

system prompt 的唯一来源是包内 `prompt.md`（workflow 运行时读取，不内嵌
副本）；prompt 改动必须升 `agent.yaml.version` 并记 changelog（宪法铁律七）。

## 环境要求

真实调用需运行环境配置 `FLAI_LLM_BASE_URL` / `FLAI_LLM_API_KEY` /
`FLAI_LLM_MODEL_REASONING`（内网侦察后配，docs/04）；未配置时任务 failed
（fail-closed），测试用 stub gateway 注入（见 ADR-0011）。

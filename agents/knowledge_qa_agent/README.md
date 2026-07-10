# knowledge_qa_agent（知识问答归纳草案生成）

「知识问答型」平台样板（Wave 2，ADR-0017），四类别（tool_automation /
knowledge_qa / structured_gen / reasoning_assist）中最后落位的一类，也是
平台**首个消费 knowledge 内核**（`context["knowledge"]`，ADR-0015）的
Agent：批量问题 → 钉死 scope 内 BM25 检索 → 命中语料注入推理模型生成
带出处引用的归纳草案 → waiting_review 人工放行。语义收编自 COMAC_FDE
K 工作流（外网已用合成语料验证）。

## 检索与 LLM 边界（铁律，勿破）

- **scope 钉死**：检索范围由 `agent.yaml knowledge.scopes` 单元素白名单
  钉死（ecm_frr_demo），不作运行输入——要查别的域=注册新 Agent 或经治理
  扩白名单（ADR-0017 决策 1）；
- **零命中不喂 LLM**：某问检索零命中 → 草稿该节写确定性「语料零命中，
  未生成 AI 归纳」标注，不调用模型——语料没有的东西让 LLM 编是最直接的
  幻觉源（ADR-0017 决策 2）；
- **数据不是指令**：检索文本注入 prompt 必过结构中和——`<<KNOWLEDGE>>`
  fence 包裹 + 规则行 + 正文与 fence 头字段 `<<`/`>>` 中和（M7
  attachments 反方审 P1 先例，workflow 内自含实现，ADR-0017 决策 3）；
- 模型草案**原样**存为 `knowledge_qa_draft.md`（文件头强制水印：未经
  工程师确认不得作为任何工程决策/放行/适航依据），workflow 不解析其
  内容当确定性真值；
- Gateway 无 key/上游失败：任务诚实 failed（`model_call` error 事件留痕）；
  全部问题零命中/失败无一草案：任务同样诚实 failed，**绝不伪造草案**。

## 使用

inputs：`{questions: [1..8 条], top_k?: 1..10（缺省 5）}`。产物两件：
`knowledge_qa_draft.md`（水印 + 逐问出处表 chunk_id/source/fingerprint/
score + 草稿）与 `answers.json`（结构化 citations，供下游机读）。任务跑完
停 waiting_review，工程师在任务详情页审阅后批准/拒绝。

## prompt 版本化

system prompt 的唯一来源是包内 `prompt.md`（workflow 运行时读取，不内嵌
副本）；prompt 改动必须升 `agent.yaml.version` 并记 changelog（宪法铁律七）。

## 环境与语料要求

真实调用需运行环境配置 `FLAI_LLM_BASE_URL` / `FLAI_LLM_API_KEY` /
`FLAI_LLM_MODEL_REASONING`（内网侦察后配，docs/04）；未配置时任务 failed
（fail-closed），测试用 stub gateway 注入（见 ADR-0011）。当前绑定语料
`data/knowledge/ecm_frr_demo/` 为**合成演示语料**（源 COMAC_FDE k01，
全部文件显式标注合成非真实）：真实业务价值 DECLARED-NOT-VERIFIED，待
内网闸门解锁后用真实 ECM/EM/FRR 语料另立 scope 升级。

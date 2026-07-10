# knowledge_qa_agent 变更记录

## 0.1.0（Wave 2，2026-07-09）

- 初版：批量问题 → context["knowledge"] BM25 检索 → LLM 归纳草案（带出处
  引用）→ waiting_review 人工放行（ADR-0017）。knowledge_qa 类别首个
  Agent，四类别全占；平台首个消费 knowledge 内核的 Agent。
- 检索边界：scope 由 agent.yaml 钉死（ecm_frr_demo 合成演示语料）；零命中
  不喂 LLM；语料注入 prompt 过 <<KNOWLEDGE>> fence + 结构中和（数据不是
  指令，M7 attachments 反方审 P1 先例的自含实现）。
- LLM 边界：草案原样存档+强制水印+逐问出处表；requires_human_review=true；
  上游失败诚实 failed 不伪造草案；全部问题无一草案 → 任务诚实 failed。
- system prompt 固化于 prompt.md（运行时读取，无内嵌副本）。

# knowledge_qa_agent 变更记录

## 0.1.1（2026-07-09，codex 治理审 R1/R2 修复）

- 0.1.0 → 0.1.1。改动类型：prompt / workflow / schema（三者皆变，无工具依赖变更）。
- prompt.md：行内引用改 `[source · chunk]` 复合键（同名文件 chunk 编号碰撞，
  单独 chunk 不唯一定位出处）。
- workflow.py：①问题文本过 _neutralize_sentinels——questions[] 伪造
  <<KNOWLEDGE>> 块不再能冒充平台检索语料；②单命中正文 4000 字符预算截断
  （带显式标记）；③finish_reason 白名单判定（非 stop 即亮"草案不完整"
  banner；非字符串畸形值同判异常，不炸任务）；④草案头部增 scope 声明行。
- input_schema.json：questions 单条 maxLength 2000（prompt 聚合上界确定 ≈42K 字符）。
- 绑定语料 ecm_frr_demo：两份演示 CSV 每行首列增「数据性质=合成演示数据
  （非真实记录）」行级标记（检索命中级自我声明，防被当真实历史采信）。

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

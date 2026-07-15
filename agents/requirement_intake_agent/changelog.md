# changelog — requirement_intake_agent

## 0.1.0(2026-07-15)

- 首版(ADR-0028):需求接件评估闭环——确定性工时账(2026-07 问卷口径)+
  asset_catalog 资产初筛 + LLM 六节评估叙述草稿 + assessment_card.md/
  assessment.json 产物 + backlog.jsonl 待办登记(按 rid 幂等)。
- 纪律基线:requires_human_review=true;清单不可读诚实 failed;空内容
  failed;finish_reason 白名单横幅;fence+中和防注入(knowledge_qa 同款);
  安全 A 级/未定级处置线为确定性常量。

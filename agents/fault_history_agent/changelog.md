# fault_history_agent 变更记录

## 0.1.0（2026-07-17）

- 初版：新增 fault_history 专长、L2 有用性章程、fault_case 依据纪律与 internal 密级上限。
- 新增 12 条跨三个虚构型号的全合成故障案例库。
- 新增 job workflow：确定性候选检索，模型仅做候选白名单内排序与摘要，输出前经 schema 校验。
- 新增 findings/refusals/cross_model_matches 契约；cross_model_matches.similarity_basis 强制非空。
- 新增正常检索、未收录型号拒答与跨型号匹配三个 eval cases；任务强制人工审核。
- 改动类型：data / prompt / workflow / schema / eval / docs。

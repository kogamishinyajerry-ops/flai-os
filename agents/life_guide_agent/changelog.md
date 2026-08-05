# life_guide_agent 变更记录

## 0.1.0 — 2026-08-05

- 首版:L1 生活场景教学 demo 的对话入口
- 复用 guide_agent 的 `_load_system_prompt` / `_VisibleReplyStream` 机制
- prompt.md 全生活语境,三比喻贯穿(老张审报告/妈妈方子 v3/装修队长工具箱)
- workflow.py 全新写(职责是投影 Asset Candidate,不是编排其他 agent)
- domain=generic 避开工程耦合;profile=fast 避免 reasoning 依赖(R4)
- Skill Package 走 quarantine 隔离区,不进 reuse_eligible 全局池(R3)

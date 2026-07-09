# ADR-0001: 技术栈定版 FastAPI + Vue 3 + Element Plus + SQLite

- 状态：已接受（任务书 §6 定版，2026-07-08）
- 背景：内核需要一套内网 Windows 可部署、多人可上手、十年可维护的最小栈。
- 决策：后端 FastAPI + Python 3.10+ + SQLite + Pydantic + JSON Schema + pytest；
  前端 Vue 3 + Vite + Element Plus；后台任务 = SQLite 任务表 + Python Job Runner
  轮询（V0.1 禁 Redis/Celery 等重依赖）。
- 理由：①FastAPI/Pydantic 与 JSON Schema 契约天然同构；②SQLite 零运维、单文件
  可备份，内网审批面最小；③Vue+Element Plus 在国内工程团队人才面最广，任务书
  明令「页面简洁，不追求视觉复杂」。
- 替代方案：React（资产库 COMACAgentPlatform 有现成 React 工作台）——被否：
  任务书定版 Vue，且旧工作台语义是「多 agent 作战室」与门户六页不同轴，复用收益
  低于认知负担；Celery/Redis——被否：V0.1 过度设计。
- 影响与风险：并发吞吐受 SQLite 限制（V0.1 用户规模下可接受）；平台稳定后再评估
  任务队列升级（写新 ADR）。

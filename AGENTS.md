# FLAi-OS

二所工程智能体运行底座（轻内核）。FastAPI + Python 3.10+ + SQLite（无 ORM，仓储层）+ Pydantic + jsonschema；前端 Vue 3 + Vite + Element Plus。后台任务 = SQLite 任务表 + 轮询 Job Runner（禁 Redis/Celery）。内网部署目标 = Windows（scripts 成对 `.ps1` + `.sh`）。

焊死红线：人是唯一签发者（LLM 不进判决链）· 假绿死罪 · fail-closed · mock 如实标注 · 信任色锁五槽（clay 工作/绿 REAL/teal 人签/红 真失败/amber 未核，completed 不给绿）· 不可变列用 CAS-on-NULL · 安全 gate 判定 `is True`/`is False` 绝不 truthiness。

跑测：`bash scripts/verify_all.sh`（build + pytest -n auto + e2e 全套）。

## Agent skills

### Issue tracker

Issues and PRDs live as GitHub issues in `kogamishinyajerry-ops/flai-os`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `CONTEXT.md` (created lazily by `/domain-modeling`) + `docs/adr/` (27 ADRs). See `docs/agents/domain.md`.

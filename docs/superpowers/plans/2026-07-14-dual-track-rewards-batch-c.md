# 批C「双轨奖励」Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 FLAi-OS 两面「谁在成长、成长了多少」的镜子——Agent 成长档案（扩现有治理弹窗）+ 工程师私有贡献页 `/me`（只精确归因），数字全来自真实治理事件。

**Architecture:** 后端零 schema 变更：`list_tasks` 加 `created_by_username` 过滤参数 + 3 个只读端点（curated_cases_count / me.contributions / me.tasks），me 端点一律从 session 派生 username 拒绝 query 越权。前端扩 `AgentPortal.vue` 治理弹窗成四版块成长档案 + 晋升同步成功回调播中性 burst 亲历；新 `MePage.vue` 深链 `/me` 五版块。新 e2e `batch_c_rewards_acceptance.py` 入 verify_all，含私有越权断言 + 亲历动效断言。

**Tech Stack:** FastAPI + SQLite（无 ORM，repos 层）后端；Vue3 + Element Plus 前端；pytest oracle 先行；Playwright 自起后端 e2e。

## Global Constraints

以下为 spec `docs/superpowers/specs/2026-07-14-dual-track-rewards-batch-c-design.md` 的项目级红线，每个 task 的要求隐含包含本节：

- **零 schema 变更**：不 ALTER TABLE、不改 `contracts/task.schema.json`；只加只读端点与 SQL 查询。
- **私有=安全线**：`/api/me/*` 端点归因主键**一律取 `request.state.user["username"]`（服务端派生），绝不接受 username 查询参数**——杜绝越权查他人。
- **只精确归因**：工程师侧只有「我发起的任务」按 `created_by_username` 精确；签发/样本个人归因本批不做，**诚实缺口条显式上屏**（非省略）；反馈按 `created_by`(display_name) 近似，**版块显式标注「可能与同名者混计」**。
- **信任色锁五槽不动**：成长/贡献数字与晋升庆祝一律中性 ink 色；teal 仅人签动作本身；completed/晋升**不给绿**。晋升庆祝用 `burstNeutral`（中性），**绝不** `burstSigned`。
- **诚实除零**：eval 通过率 `total=0` 时显「无有效用例」，**绝不显 0%**。
- **成熟度阶梯诚实**：L2/L3 标「范围外（仅 L0→L1 机器化把关）」，不暗示平台能自动晋 L2+。
- **亲历者纪律**：晋升动效**仅**在本会话内点成晋升的**同步成功回调**触发；历史直开弹窗恒静态。reduced-motion 降级（`burstNeutral` 已内置 no-op）。
- **Py3.10 兼容**：`since` 解析必须先把尾缀 `Z`→`+00:00` 再 `fromisoformat`（内网 Windows 定版下限 3.10 不认 Z）；naive/纯日期 422 fail-closed；`OverflowError` 同归 422。
- **sensitive 遮蔽 chokepoint**：任何经 `dict(row)` 投影任务行的端点，返回前必过 `cgate.redact_task_row_if_sensitive(conn, row)`（ADR-0025 单 chokepoint），`/api/me/tasks` 同样适用。
- **git 暂存显式路径**：每次 commit 只 `git add` 本 task 明列文件，**绝不** `git add -A`/`git add .`。
- **tamper 咬合**：oracle 测试写完先 tamper（拆掉过滤/断言）验证必红，再实现转绿——「全绿」无咬合实证=假信心。

---

## File Structure

**后端（Python）**
- `backend/app/storage/repos.py`（改）：`list_tasks` 加 `created_by_username` 过滤参数。
- `backend/app/api/_since.py`（新）：`parse_since_utc(since) -> str` 共享 since 解析（从 stats.py 抽出）。
- `backend/app/api/stats.py`（改）：改用 `_since.parse_since_utc`（去重复代码，行为不变）。
- `backend/app/api/governance.py`（改）：加 `GET /api/agents/{id}/curated_cases_count`。
- `backend/app/api/me.py`（新）：`GET /api/me/contributions` + `GET /api/me/tasks`。
- `backend/app/main.py`（改）：注册 `me_api.router`。

**前端（Vue）**
- `frontend/src/views/AgentPortal.vue`（改）：治理弹窗扩成四版块成长档案 + 晋升亲历动效。
- `frontend/src/views/MePage.vue`（新）：`/me` 工程师私有贡献页五版块。
- `frontend/src/api/me.js`（新）：me 端点 fetch 封装。
- `frontend/src/router/index.js`（改）：加 `/me` 路由。
- `frontend/src/App.vue`（改）：侧栏加「我的贡献」入口（深链，不重载登出按钮语义）。

**测试**
- `backend/tests/test_repos.py`（改）：list_tasks created_by_username 过滤 + tamper。
- `backend/tests/test_api.py`（改）：curated_cases_count / me.contributions / me.tasks（精确/私有/近似/遮蔽/since）。
- `backend/tests/test_stats.py`（改，若存在则加回归；否则并入 test_api.py）：since 抽取后 stats 行为不变。
- `frontend/e2e/batch_c_rewards_acceptance.py`（新）：入 `scripts/verify_all.sh` E2E_SCRIPTS。

**关键既有接口（各 task implementer 直接消费，勿重新发明）**
- `repos.list_tasks(conn, *, agent_id=None, status=None, conversation_id=None, origin=None, limit=100, offset=0)` → `list[dict]`；`_decode_task` = `dict(row)` 自动投影新列。
- `repos.list_promotions(conn, agent_id)` → `list[dict]`，字段 `from_maturity/to_maturity/eval_run_id/confirmed_by/created_at/checks/confirmations/id`。
- `repos.list_eval_runs(conn, agent_id, *, limit=20)` → `list[dict]`，字段 `id/passed/total/failed/skipped/started_at/finished_at/case_results/draft_cases/status`。
- `stats.count_curated_cases(agents_dir)` 用 glob `*/eval_cases/case_*.json`；单 agent 版 glob `agents_dir / agent_id / "eval_cases" / "case_*.json"`。
- `governance._agent_or_404(request, agent_id) -> dict`（agent 不存在抛 404）。
- `request.state.user` = `{"username": str, "display_name": str}`；`request.app.state`：`conn_factory` / `agents_dir` / `agent_registry`。
- `cgate.redact_task_row_if_sensitive(conn, row)`（tasks.py 已 import 为 `cgate`）。
- 前端 `frontend/src/effects/burst.js`：`burstNeutral(el)`（中性尘埃，reduced-motion no-op）。
- 前端 `frontend/src/stores/session.js`：`currentUser`（ref `{username, display_name}`）。
- 前端 `frontend/src/api/client.js`：`request(path, {method, json})`。
- e2e `frontend/e2e/_auth.py`：`seed_user(db_path, display_name, *, username, password)` / `login_context(context, base, *, username, password)` / `login_httpx(base, *, username, password)`。

---

## Task 1: `repos.list_tasks` 加 `created_by_username` 过滤参数

**Files:**
- Modify: `backend/app/storage/repos.py:121-157`（`list_tasks`）
- Test: `backend/tests/test_repos.py`

**Interfaces:**
- Consumes: 既有 `create_task(..., created_by_username=None)`（迁移 #9 已加）。
- Produces: `list_tasks(conn, *, agent_id=None, status=None, conversation_id=None, origin=None, created_by_username=None, limit=100, offset=0)`——`created_by_username` None=不过滤（仓储层中立），非 None 精确匹配该列。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_repos.py` 末尾追加（复用文件内既有 `conn` fixture / `create_task` 调用样板；若无 fixture 则用文件顶部既有建连方式）：

```python
def test_list_tasks_filters_by_created_by_username(conn):
    # 三条：alice 两条（含一条 eval origin）、bob 一条、无归因一条（None）
    from backend.app.storage import repos
    repos.create_task(conn, task_id="t-a1", agent_id="hello_agent", agent_version="0.1.0",
                      name=None, created_by="Alice", created_by_username="alice")
    repos.create_task(conn, task_id="t-a2", agent_id="hello_agent", agent_version="0.1.0",
                      name=None, created_by="Alice", created_by_username="alice", origin="eval")
    repos.create_task(conn, task_id="t-b1", agent_id="hello_agent", agent_version="0.1.0",
                      name=None, created_by="Bob", created_by_username="bob")
    repos.create_task(conn, task_id="t-legacy", agent_id="hello_agent", agent_version="0.1.0",
                      name=None, created_by="Legacy")  # created_by_username 省略=None

    alice = repos.list_tasks(conn, created_by_username="alice")
    assert {t["id"] for t in alice} == {"t-a1", "t-a2"}  # 精确，不含 bob/legacy

    bob = repos.list_tasks(conn, created_by_username="bob")
    assert {t["id"] for t in bob} == {"t-b1"}

    # None 归因行不被任何 username 误计（NULL != 任何值）
    assert repos.list_tasks(conn, created_by_username="legacy") == []

    # None 参数=不过滤，四条全回
    assert len(repos.list_tasks(conn, created_by_username=None)) == 4
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os && uv run python -m pytest backend/tests/test_repos.py::test_list_tasks_filters_by_created_by_username -v`
Expected: FAIL —`list_tasks() got an unexpected keyword argument 'created_by_username'`

- [ ] **Step 3: 实现——加参数与 SQL 子句**

在 `backend/app/storage/repos.py` 的 `list_tasks` 签名加参数（`origin` 之后、`limit` 之前）：

```python
def list_tasks(
    conn: sqlite3.Connection,
    *,
    agent_id: str | None = None,
    status: str | None = None,
    conversation_id: str | None = None,
    origin: str | None = None,
    created_by_username: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
```

在 origin 子句之后加（`where = ...` 行之前）：

```python
    if created_by_username is not None:
        clauses.append("created_by_username = ?")
        params.append(created_by_username)
```

并在 docstring 末尾补一行：`created_by_username（批C）：仓储层 None=不过滤中立；API 的 /me 端点按登录会话 username 精确归因「我发起的任务」，NULL 存量行不被任何 username 误计。`

- [ ] **Step 4: 跑测试验证通过**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os && uv run python -m pytest backend/tests/test_repos.py::test_list_tasks_filters_by_created_by_username -v`
Expected: PASS

- [ ] **Step 5: tamper 咬合（必红）**

临时把 Step 3 的子句注释掉，重跑 Step 4：Expected FAIL（alice 会拿到全部 4 条）。确认咬合后恢复子句，再跑一次转 PASS。

- [ ] **Step 6: 全量 repos 回归**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os && uv run python -m pytest backend/tests/test_repos.py -q`
Expected: 全绿（新增列过滤不影响既有分页/排序测试）。

- [ ] **Step 7: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add backend/app/storage/repos.py backend/tests/test_repos.py
git commit -m "feat(batch-c): list_tasks 加 created_by_username 过滤参数（NULL 存量不误计）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: since 解析抽共享 helper

**Files:**
- Create: `backend/app/api/_since.py`
- Modify: `backend/app/api/stats.py:26-45`
- Test: `backend/tests/test_api.py`（新增 `_since` 单元测试）

**Interfaces:**
- Produces: `parse_since_utc(since: str | None) -> str`——空/naive/非法 ISO8601/OverflowError 一律抛 `fastapi.HTTPException(status_code=422, detail=...)`；合法则返回归一化 UTC `+00:00` ISO 字符串。
- Consumes: 无（纯函数）。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_api.py` 顶部 import 区之后追加：

```python
def test_parse_since_utc_normalizes_and_rejects():
    import pytest
    from fastapi import HTTPException
    from backend.app.api._since import parse_since_utc

    # Z 后缀归一化为 +00:00（Py3.10 兼容路径）
    assert parse_since_utc("2026-07-01T00:00:00Z") == "2026-07-01T00:00:00+00:00"
    # 任意偏移归一化到 UTC
    assert parse_since_utc("2026-07-01T08:00:00+08:00") == "2026-07-01T00:00:00+00:00"
    # 空 → 422
    with pytest.raises(HTTPException) as e1:
        parse_since_utc(None)
    assert e1.value.status_code == 422
    # naive（无时区）→ 422 fail-closed
    with pytest.raises(HTTPException) as e2:
        parse_since_utc("2026-07-01T00:00:00")
    assert e2.value.status_code == 422
    # 非法 ISO → 422
    with pytest.raises(HTTPException) as e3:
        parse_since_utc("not-a-date")
    assert e3.value.status_code == 422
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os && uv run python -m pytest "backend/tests/test_api.py::test_parse_since_utc_normalizes_and_rejects" -v`
Expected: FAIL —`ModuleNotFoundError: No module named 'backend.app.api._since'`

- [ ] **Step 3: 实现——新建 `_since.py`**

创建 `backend/app/api/_since.py`（逻辑逐字搬自 stats.py 现有 since 解析，含 Codex R2 的 Py3.10 兼容与 OverflowError 处理）：

```python
"""since 参数解析共享 helper（批C：stats.py 与 me.py 同款口径，抽出去重）。

offset-aware ISO8601 必填；Z 后缀先归一化再 fromisoformat（Py3.10 兼容，内网
Windows 定版下限不认 Z）；naive/纯日期 422 fail-closed；OverflowError 同归 422。
归一化为 UTC '+00:00' 表示——库内 repos 写入即该格式，字典序比较才恒等时间序。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException


def parse_since_utc(since: str | None) -> str:
    if not since:
        raise HTTPException(status_code=422, detail="since 必填（ISO8601）")
    parse_src = since[:-1] + "+00:00" if since[-1] in ("Z", "z") else since
    try:
        dt = datetime.fromisoformat(parse_src)
        if dt.tzinfo is None:
            raise HTTPException(
                status_code=422, detail=f"since 必须带时区偏移（offset-aware）：{since}"
            )
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError) as exc:
        raise HTTPException(status_code=422, detail=f"since 不是合法 ISO8601：{since}") from exc
```

- [ ] **Step 4: 改 stats.py 改用 helper**

把 `backend/app/api/stats.py` 的 `stats_overview` 里从 `if not since:` 到 `since = dt.astimezone(...)` 这段（约 28-45 行）整体替换为：

```python
    since = parse_since_utc(since)
```

并在 stats.py 顶部 import 区加：`from ._since import parse_since_utc`。删除现在不再用的 `from datetime import datetime, timezone`（若 stats.py 其它地方不再引用 datetime/timezone）。

- [ ] **Step 5: 跑测试验证通过 + stats 回归**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os && uv run python -m pytest "backend/tests/test_api.py::test_parse_since_utc_normalizes_and_rejects" backend/tests/test_api.py -k "stats or overview or since" -v`
Expected: PASS——新 helper 测试绿 + 既有 stats/overview 的 since 边界测试全绿（行为不变）。

- [ ] **Step 6: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add backend/app/api/_since.py backend/app/api/stats.py backend/tests/test_api.py
git commit -m "refactor(batch-c): since 解析抽 _since.parse_since_utc（stats/me 共享，行为不变）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `GET /api/agents/{id}/curated_cases_count`

**Files:**
- Modify: `backend/app/api/governance.py`（末尾加端点 + import stats helper 或本地 glob）
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `GET /api/agents/{agent_id}/curated_cases_count` → `{"agent_id": str, "count": int}`；agent 不存在 404；`agents/{id}/eval_cases/` 缺失=0。
- Consumes: `_agent_or_404`、`request.app.state.agents_dir`。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_api.py` 找到既有治理端点测试所用的 app fixture（m10/governance 测试用的 `client`/`app_env`——沿用同一 fixture 名）。追加：

```python
def test_curated_cases_count_scoped_and_missing(governance_client_env):
    # governance_client_env 需给出 (client, agents_dir)，沿用 m10 测试的 env fixture；
    # 若该 fixture 只给 client，则用 client.app.state.agents_dir 取目录。
    client, agents_dir = governance_client_env
    # 造 hello_agent 两个固化 case + 另一 agent 一个，验证按 agent 精确 scope
    (agents_dir / "hello_agent" / "eval_cases").mkdir(parents=True, exist_ok=True)
    (agents_dir / "hello_agent" / "eval_cases" / "case_001.json").write_text("{}", encoding="utf-8")
    (agents_dir / "hello_agent" / "eval_cases" / "case_002.json").write_text("{}", encoding="utf-8")

    r = client.get("/api/agents/hello_agent/curated_cases_count")
    assert r.status_code == 200
    assert r.json() == {"agent_id": "hello_agent", "count": 2}

    # 无 eval_cases 目录的 agent = 0（不抛）
    r2 = client.get("/api/agents/review_agent/curated_cases_count")
    assert r2.status_code == 200
    assert r2.json()["count"] == 0

    # 不存在的 agent → 404
    assert client.get("/api/agents/no_such_agent/curated_cases_count").status_code == 404
```

> 若既有测试没有 `governance_client_env` fixture，implementer 用 test_api.py 里 m10 治理测试同款的 app/client 构造方式（TestClient + tmp agents_dir + seed 登录）自建，agents_dir 从 `client.app.state.agents_dir` 取。

- [ ] **Step 2: 跑测试验证失败**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os && uv run python -m pytest "backend/tests/test_api.py::test_curated_cases_count_scoped_and_missing" -v`
Expected: FAIL — 404（端点不存在，被 SPA catch-all 或路由未匹配拦下）。

- [ ] **Step 3: 实现——governance.py 加端点**

在 `backend/app/api/governance.py` 顶部 import 区加：`from .stats import count_curated_cases`（复用 glob 逻辑做单 agent scope）。在文件末尾（`list_promotions_all` 之后）加：

```python
@router.get("/agents/{agent_id}/curated_cases_count")
def curated_cases_count(agent_id: str, request: Request) -> dict[str, Any]:
    """该 agent 已固化 eval case 数（批C Agent 成长档案）。按仓内落盘文件计
    （ADR-0018 固化即落盘无 DB 行）：agents/{id}/eval_cases/case_*.json。
    agent 不存在 404；目录缺失=0（不抛）。只读。"""
    _agent_or_404(request, agent_id)
    agent_dir = request.app.state.agents_dir / agent_id
    count = count_curated_cases(agent_dir) if agent_dir.is_dir() else 0
    return {"agent_id": agent_id, "count": count}
```

> `count_curated_cases` 的 glob 是 `*/eval_cases/case_*.json`——传单 agent 目录时，`agent_dir` 下一层正是 `eval_cases/`，但 glob 首段 `*` 会匹配 `eval_cases` 这一层，路径变成 `agent_dir/eval_cases/eval_cases/...` 不对。**因此必须传 agent_dir 的父级不行**。改用直接 glob：

把上面实现改为**不复用** `count_curated_cases`（其 glob 段数不匹配单 agent scope），直接内联：

```python
@router.get("/agents/{agent_id}/curated_cases_count")
def curated_cases_count(agent_id: str, request: Request) -> dict[str, Any]:
    """该 agent 已固化 eval case 数（批C Agent 成长档案）。按仓内落盘文件计
    （ADR-0018 固化即落盘无 DB 行）。agent 不存在 404；目录缺失=0（不抛）。只读。"""
    _agent_or_404(request, agent_id)
    cases_dir = request.app.state.agents_dir / agent_id / "eval_cases"
    count = sum(1 for _ in cases_dir.glob("case_*.json")) if cases_dir.is_dir() else 0
    return {"agent_id": agent_id, "count": count}
```

删除 Step 3 顶部那条 `from .stats import count_curated_cases` import（未使用）。确认 governance.py 顶部已有 `from fastapi import APIRouter, HTTPException, Request` 与 `from typing import Any`（现有），无需再加。

- [ ] **Step 4: 跑测试验证通过**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os && uv run python -m pytest "backend/tests/test_api.py::test_curated_cases_count_scoped_and_missing" -v`
Expected: PASS

- [ ] **Step 5: tamper 咬合（必红）**

临时把实现里 `cases_dir.glob("case_*.json")` 改成 `glob("*.json")`（放宽匹配），再造一个非 case 前缀文件断言——或更简单：把 `count` 恒返回 `0`，重跑 Step 4 Expected FAIL（count=2 断言破）。确认后恢复。

- [ ] **Step 6: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add backend/app/api/governance.py backend/tests/test_api.py
git commit -m "feat(batch-c): GET /api/agents/{id}/curated_cases_count（按仓内落盘文件计,404/缺失=0）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `backend/app/api/me.py` — 工程师私有贡献端点

**Files:**
- Create: `backend/app/api/me.py`
- Modify: `backend/app/main.py:23-30,156-163`（import + include_router）
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces:
  - `GET /api/me/contributions?since=<iso>` → `{"username": str, "since": str, "since_created": int, "since_completed": int, "waiting_review": int, "total_created": int, "feedback_count_approx": int}`——全部按登录会话身份，username 服务端派生。
  - `GET /api/me/tasks?limit=<1-100>` → `list[dict]`（我发起的任务，最近优先，sensitive 遮蔽）。
- Consumes: `parse_since_utc`（Task 2）、`repos.list_tasks(..., created_by_username=)`（Task 1）、`cgate.redact_task_row_if_sensitive`、`request.state.user`。

- [ ] **Step 1: 写失败测试（精确 + 私有 + 近似 + 遮蔽 + since）**

在 `backend/tests/test_api.py` 追加。用 test_api.py 既有的「可登录 app」构造方式（沿用文件内 tasks/review 测试同款 fixture；需要两个身份 alice/bob）：

```python
def test_me_contributions_precise_private_and_feedback_approx(me_two_user_env):
    # me_two_user_env: (base_or_client_factory) —— 给出可分别以 alice/bob 登录的 client。
    # 沿用 test_api.py 既有多用户登录样板；下面用 alice_client / bob_client 两个已登录 client。
    alice_client, bob_client, seed = me_two_user_env
    # seed(username, display_name, n_created, n_completed, n_waiting, n_feedback) 造数据的 helper，
    # 由 implementer 按 test_api.py 既有 create_task/set_task_status/create_feedback 样板实现。
    seed("alice", "Alice", created=3, completed=1, waiting=1, feedback=2)
    seed("bob", "Bob", created=5, completed=2, waiting=0, feedback=1)

    since = "2000-01-01T00:00:00Z"  # 远早 → since_* 窗口含全部
    a = alice_client.get(f"/api/me/contributions?since={since}").json()
    assert a["username"] == "alice"
    assert a["total_created"] == 3          # 只计 alice，绝不含 bob 的 5
    assert a["since_completed"] == 1
    assert a["waiting_review"] == 1
    assert a["feedback_count_approx"] == 2  # 按 display_name "Alice"

    # 私有实证：bob 登录只拿到 bob 的数，无 username 参数可越权查 alice
    b = bob_client.get(f"/api/me/contributions?since={since}").json()
    assert b["username"] == "bob"
    assert b["total_created"] == 5
    # 端点不接受 username query（多给了也被忽略，仍返回自己的）
    b2 = bob_client.get(f"/api/me/contributions?since={since}&username=alice").json()
    assert b2["total_created"] == 5 and b2["username"] == "bob"

    # since 必填 422
    assert alice_client.get("/api/me/contributions").status_code == 422


def test_me_tasks_private_and_sensitive_redacted(me_two_user_env):
    alice_client, bob_client, seed = me_two_user_env
    seed("alice", "Alice", created=2, completed=0, waiting=0, feedback=0)
    seed("bob", "Bob", created=1, completed=0, waiting=0, feedback=0)

    a = alice_client.get("/api/me/tasks?limit=50").json()
    assert all(t["created_by_username"] == "alice" for t in a)  # 只我的
    assert len(a) == 2
    b = bob_client.get("/api/me/tasks?limit=50").json()
    assert all(t["created_by_username"] == "bob" for t in b)
    assert len(b) == 1
    # limit 夹取：>100 被拒或夹取（ge/le），0 被拒
    assert alice_client.get("/api/me/tasks?limit=0").status_code == 422
```

> `me_two_user_env` fixture：implementer 按 test_api.py 既有 TestClient + tmp 库 + `_auth`/`create_user` 样板构造，seed 两个账户并分别 login 得两个带 cookie 的 client。`seed(...)` 用 `repos.create_task(..., created_by_username=, created_by=display_name)` + `repos.set_task_status` 造 completed/waiting、`repos.create_feedback(..., created_by=display_name)` 造反馈。sensitive 遮蔽的专项断言可选加：造一条 `data_classification='sensitive'` 任务，断言返回行 `content_withheld` 为 True——沿用 test_api.py 既有 ADR-0025 遮蔽测试样板。

- [ ] **Step 2: 跑测试验证失败**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os && uv run python -m pytest "backend/tests/test_api.py::test_me_contributions_precise_private_and_feedback_approx" "backend/tests/test_api.py::test_me_tasks_private_and_sensitive_redacted" -v`
Expected: FAIL — 404（端点不存在）。

- [ ] **Step 3: 实现——新建 `me.py`**

创建 `backend/app/api/me.py`：

```python
"""工程师个人贡献只读端点（批C 轨2）。

私有=安全线：归因主键一律取 request.state.user["username"]（服务端派生），
绝不接受 username 查询参数——登录者只能看到自己的贡献，杜绝越权查他人。
只精确归因：只有「我发起的任务」按 created_by_username 精确；反馈按 created_by
(display_name) 近似（可撞名，前端显式标注）。签发/样本个人归因本批不做（唯一
身份仅在审计轨留痕），前端诚实缺口条明说。零 schema 变更。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from . import classification_gate as cgate  # 与 tasks.py 同款遮蔽 chokepoint（tasks.py:15 同）
from ..storage import repos
from ._since import parse_since_utc

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me/contributions")
def me_contributions(request: Request, since: str | None = None) -> dict[str, Any]:
    username = request.state.user["username"]
    display_name = request.state.user["display_name"]
    since_utc = parse_since_utc(since)
    conn = request.app.state.conn_factory()
    try:
        since_created = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_by_username = ?"
            " AND origin = 'user' AND created_at >= ?",
            (username, since_utc),
        ).fetchone()[0]
        since_completed = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_by_username = ?"
            " AND origin = 'user' AND status = 'completed'"
            " AND finished_at IS NOT NULL AND finished_at >= ?",
            (username, since_utc),
        ).fetchone()[0]
        waiting_review = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_by_username = ?"
            " AND origin = 'user' AND status = 'waiting_review'",
            (username,),
        ).fetchone()[0]
        total_created = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_by_username = ? AND origin = 'user'",
            (username,),
        ).fetchone()[0]
        # 反馈近似：feedback 表只有 created_by(display_name)，无 username 列——可撞名
        feedback_count_approx = conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE created_by = ?",
            (display_name,),
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "username": username,
        "since": since_utc,
        "since_created": since_created,
        "since_completed": since_completed,
        "waiting_review": waiting_review,
        "total_created": total_created,
        "feedback_count_approx": feedback_count_approx,
    }


@router.get("/me/tasks")
def me_tasks(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, Any]]:
    username = request.state.user["username"]
    conn = request.app.state.conn_factory()
    try:
        rows = repos.list_tasks(
            conn, origin="user", created_by_username=username, limit=limit
        )
        # ADR-0025 单 chokepoint：sensitive 任务承载字段遮蔽，与 /api/tasks 同款。
        return [cgate.redact_task_row_if_sensitive(conn, t) for t in rows]
    finally:
        conn.close()
```

> **import 已核对**：tasks.py:15 = `from . import classification_gate as cgate`；me.py 与 tasks.py 同在 `backend/app/api/` 包，照抄同一行即可（上面代码已用正确路径）。

- [ ] **Step 4: 注册路由**

在 `backend/app/main.py` import 区（`from .api import tasks as tasks_api` 附近）加：

```python
from .api import me as me_api
```

在 `app.include_router(stats_api.router)` 之后加：

```python
    app.include_router(me_api.router)
```

- [ ] **Step 5: 跑测试验证通过**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os && uv run python -m pytest "backend/tests/test_api.py::test_me_contributions_precise_private_and_feedback_approx" "backend/tests/test_api.py::test_me_tasks_private_and_sensitive_redacted" -v`
Expected: PASS

- [ ] **Step 6: tamper 咬合（私有 = 安全线，必咬）**

临时把 `me_contributions` 里 `created_by_username = ?` / `(username, ...)` 改成不带 username 过滤（全表 COUNT），重跑 Step 5：Expected FAIL——alice 会看到含 bob 的总数，私有断言破。确认咬合后恢复。这是本批安全线的咬合实证。

- [ ] **Step 7: 全量 api 回归**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os && uv run python -m pytest backend/tests/test_api.py -q`
Expected: 全绿。

- [ ] **Step 8: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add backend/app/api/me.py backend/app/main.py backend/tests/test_api.py
git commit -m "feat(batch-c): /api/me/contributions + /api/me/tasks（session派生username私有,只精确归因)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: AgentPortal 成长档案四版块（静态）

**Files:**
- Modify: `frontend/src/views/AgentPortal.vue`

**Interfaces:**
- Consumes: 既有 `governanceRuns`（含 `passed/total/skipped/finished_at/started_at`）、`governancePromotions`（含 `from_maturity/to_maturity/confirmed_by/created_at/checks`）、`GET /api/agents/{id}/curated_cases_count`（Task 3）。
- Produces: 弹窗内四版块渲染，供 Task 6 挂动效、Task 8 e2e 断言。DOM 契约：成熟度阶梯 `.gov-ladder`、eval 趋势 `.gov-eval-trend`、晋升史 `.gov-promotion-card`（每条一个）、固化计数 `.gov-cases-count`。

**前端 task 说明**：本仓前端无 Vue 单元测试框架，行为由 Task 8 e2e 把关；本 task 的机械门=`npm run build` 通过 + 截图目视四版块。**不许**引入新依赖。

- [ ] **Step 1: 加 curated case 计数 fetch**

在 `<script setup>` 加 ref 与 fetch。`governanceRuns`/`governancePromotions` 声明之后加：

```javascript
const curatedCasesCount = ref(null);
```

在 `loadGovernance(agentId)` 的 `Promise.all` 里加第三个请求（连同 epoch 守卫一起）：

```javascript
    const [runs, promotions, casesCount] = await Promise.all([
      request(`/api/agents/${agentId}/eval-runs`),
      request(`/api/agents/${agentId}/promotions`),
      request(`/api/agents/${agentId}/curated_cases_count`),
    ]);
    if (epoch !== governanceEpoch) return;
    governanceRuns.value = runs;
    governancePromotions.value = promotions;
    curatedCasesCount.value = casesCount?.count ?? null;
```

在 `catch` 分支与 `openGovernance`/`resetGovernanceDialog` 的重置里，把 `curatedCasesCount.value = null` 一并加上（与 governanceRuns 同处重置），保持弹窗切换不串数据。

- [ ] **Step 2: 加成长档案 computed**

在 `latestPromotion` computed 之后加：

```javascript
const MATURITY_LADDER = ["L0", "L1", "L2", "L3"];
const maturityLadder = computed(() => {
  const current = governanceAgent.value?.maturity || "L0";
  const curIdx = MATURITY_LADDER.indexOf(current);
  return MATURITY_LADDER.map((level, idx) => ({
    level,
    reached: idx <= curIdx,
    current: idx === curIdx,
    outOfScope: idx >= 2, // L2/L3 仅 L0→L1 机器化把关，诚实标范围外
  }));
});
// 最近 ≤8 次评测，旧→新（时间轴左旧右新）；pct=null 表示 total=0「无有效用例」
const evalTrend = computed(() =>
  (governanceRuns.value || [])
    .slice(0, 8)
    .map((r) => ({
      id: r.id,
      passed: r.passed ?? 0,
      total: r.total ?? 0,
      pct: r.total > 0 ? Math.round((r.passed / r.total) * 100) : null,
      at: r.finished_at || r.started_at,
    }))
    .reverse()
);
```

- [ ] **Step 3: 加模板四版块**

在弹窗 `<template v-else>` 内。**成熟度阶梯**——把现有 `.gov-maturity-tag`（`<div class="gov-maturity-tag">…</div>`，在 `<template v-else>` 之前）保留不动，在 `<template v-else>` **内最前面**插入阶梯条：

```html
          <div class="gov-ladder">
            <div class="gov-section-label">成熟度</div>
            <div class="gov-ladder-track">
              <span
                v-for="step in maturityLadder"
                :key="step.level"
                class="gov-ladder-step"
                :class="{ reached: step.reached, current: step.current, oos: step.outOfScope }"
                :title="step.outOfScope ? 'L2/L3 范围外：当前仅 L0→L1 由机器把关晋升' : ''"
              >{{ step.level }}<em v-if="step.outOfScope" class="gov-oos-tag">范围外</em></span>
            </div>
            <div class="gov-ladder-note">仅 L0→L1 机器化把关；L2/L3 范围外</div>
          </div>
```

**eval 通过率趋势**——在 `.gov-run-block`（最近评测）**之前**插入：

```html
          <div v-if="evalTrend.length" class="gov-eval-trend">
            <div class="gov-section-label">评测通过率（近 {{ evalTrend.length }} 次）</div>
            <div class="gov-trend-bars">
              <span
                v-for="run in evalTrend"
                :key="run.id"
                class="gov-trend-bar"
                :class="{ 'is-empty': run.pct === null }"
                :style="run.pct !== null ? { height: Math.max(6, run.pct) + '%' } : {}"
                :title="run.pct === null
                  ? `无有效用例 · ${formatTime(run.at)}`
                  : `${run.passed}/${run.total}（${run.pct}%） · ${formatTime(run.at)}`"
              ></span>
            </div>
          </div>
```

**固化 case 计数**——在「跑评测」按钮之后插入：

```html
          <div v-if="curatedCasesCount !== null" class="gov-cases-count">
            已固化 <b>{{ curatedCasesCount }}</b> 个 eval case（按仓内固化文件计）
          </div>
```

**晋升史时间线**——把现有单行 `<div v-if="latestPromotion" class="gov-promotion-history">…</div>` 整块替换为全量时间线：

```html
          <div v-if="governancePromotions.length" class="gov-promotion-timeline">
            <div class="gov-section-label">晋升史</div>
            <div
              v-for="p in governancePromotions"
              :key="p.id"
              class="gov-promotion-card"
            >
              <div class="gov-promotion-head">
                <span class="gov-promotion-jump">{{ p.from_maturity }}→{{ p.to_maturity }}</span>
                <span class="gov-promotion-meta">{{ p.confirmed_by }} · {{ formatTime(p.created_at) }}</span>
              </div>
              <el-collapse v-if="p.checks && Object.keys(p.checks).length">
                <el-collapse-item title="五门判定快照">
                  <ul class="gov-checks-list">
                    <li v-for="(check, name) in p.checks" :key="name">
                      {{ name }}：{{ check && check.ok === true ? '✓' : '✗' }}
                      <span v-if="check && check.detail"> · {{ check.detail }}</span>
                    </li>
                  </ul>
                </el-collapse-item>
              </el-collapse>
            </div>
          </div>
```

- [ ] **Step 4: 加 CSS（中性色，信任色锁）**

在 `<style scoped>` 末尾（删掉的 `.gov-promotion-history` 规则可留可删）追加。**全部中性 ink 色，绝不用 teal/绿**：

```css
.gov-ladder { margin-bottom: 16px; }
.gov-ladder-track { display: flex; gap: 6px; margin: 6px 0 4px; }
.gov-ladder-step {
  flex: 1; text-align: center; padding: 5px 0; border-radius: 6px;
  font-size: 12px; font-weight: 700; color: var(--ink-faint);
  background: var(--paper-rail); border: 1px solid var(--hairline);
}
.gov-ladder-step.reached { color: var(--ink); }
.gov-ladder-step.current { border-color: var(--clay-softer); color: var(--clay); }
.gov-ladder-step.oos { opacity: 0.6; }
.gov-oos-tag { display: block; font-size: 9px; font-style: normal; font-weight: 500; }
.gov-ladder-note { color: var(--ink-faint); font-size: 11px; }
.gov-eval-trend { margin: 14px 0; }
.gov-trend-bars {
  display: flex; align-items: flex-end; gap: 4px; height: 48px;
  padding: 4px 0; margin-top: 4px;
}
.gov-trend-bar {
  flex: 1; min-height: 6px; background: var(--ink-mid); border-radius: 2px 2px 0 0;
  opacity: 0.75;
}
.gov-trend-bar.is-empty {
  background: transparent; border: 1px dashed var(--hairline); min-height: 100%;
  opacity: 1;
}
.gov-cases-count { margin-top: 12px; color: var(--ink-soft); font-size: 12.5px; }
.gov-cases-count b { color: var(--ink); }
.gov-promotion-timeline {
  margin-top: 18px; padding-top: 12px; border-top: 1px dashed var(--hairline);
}
.gov-promotion-card {
  padding: 8px 0; border-bottom: 1px solid var(--hairline);
}
.gov-promotion-card:last-child { border-bottom: none; }
.gov-promotion-head {
  display: flex; justify-content: space-between; align-items: baseline; gap: 8px;
}
.gov-promotion-jump { color: var(--ink); font-weight: 700; font-size: 13px; }
.gov-promotion-meta { color: var(--ink-faint); font-size: 11.5px; }
.gov-checks-list {
  margin: 4px 0 0; padding-left: 16px; color: var(--ink-soft);
  font-size: 11.5px; line-height: 1.7;
}
```

- [ ] **Step 5: 构建验证**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os/frontend && npm run build`
Expected: 构建成功，无编译错误。

- [ ] **Step 6: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add frontend/src/views/AgentPortal.vue
git commit -m "feat(batch-c): AgentPortal 治理弹窗扩成 Agent 成长档案四版块（阶梯/趋势/晋升史/固化数,中性色）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: AgentPortal 晋升亲历动效

**Files:**
- Modify: `frontend/src/views/AgentPortal.vue`

**Interfaces:**
- Consumes: `burstNeutral(el)`（`../effects/burst.js`）、Task 5 的 `.gov-promotion-card`、既有 `promoteToL1` 成功分支。
- Produces: 本会话点成晋升的同步回调里，最新晋升卡加临时 class `.promote-burst`（Task 8 e2e 断言）+ 播 `burstNeutral`。历史直开恒无 `.promote-burst`。

- [ ] **Step 1: import + ref**

在 `<script setup>` import 区加：

```javascript
import { nextTick } from "vue";
import { burstNeutral } from "../effects/burst.js";
```

（`nextTick` 若已在 `import { ref, computed, onMounted } from "vue"` 里则并入那一行。）在 refs 区加晋升史容器 ref 与亲历标记：

```javascript
const promotionTimelineRef = ref(null);
const witnessedPromotionBurst = ref(false);
```

在 Step 3 模板的 `.gov-promotion-timeline` 根 div 上加 `ref="promotionTimelineRef"`；在 `.gov-promotion-card` 的 `:class` 上加亲历标记（仅第一张=最新）：

```html
            <div
              v-for="(p, idx) in governancePromotions"
              :key="p.id"
              class="gov-promotion-card"
              :class="{ 'promote-burst': idx === 0 && witnessedPromotionBurst }"
            >
```

- [ ] **Step 2: 在 promoteToL1 成功回调播亲历动效**

在 `promoteToL1` 的成功分支——`await Promise.all([load(), loadGovernance(agentId)]);` 之后、`if (governanceOpen.value && ...)` 刷新 agent 那段**之后**，加（仍在「还看同一 agent」的守卫内）：

```javascript
      // 亲历者动效（批C）：仅本次同步点成晋升触发一次中性 burst——历史直开恒静态。
      // burstNeutral 对 reduced-motion 内置 no-op；.promote-burst class 仍加（e2e 可断言）。
      witnessedPromotionBurst.value = true;
      await nextTick();
      const topCard = promotionTimelineRef.value?.querySelector(".gov-promotion-card");
      if (topCard) burstNeutral(topCard);
      window.setTimeout(() => { witnessedPromotionBurst.value = false; }, 1600);
```

在 `resetGovernanceDialog` 与 `openGovernance` 的重置里加 `witnessedPromotionBurst.value = false;`——保证换 agent / 重开弹窗绝不残留亲历标记（历史直开静态的硬保证）。

- [ ] **Step 3: 加 `.promote-burst` CSS（reduced-motion 降级）**

在 `<style scoped>` 末尾加：

```css
.gov-promotion-card.promote-burst {
  animation: promote-glow 1.5s var(--ease-out-soft, ease-out);
  border-radius: 6px;
}
@keyframes promote-glow {
  0% { background: var(--clay-softer, rgba(193,95,60,0.14)); }
  100% { background: transparent; }
}
@media (prefers-reduced-motion: reduce) {
  .gov-promotion-card.promote-burst { animation: none; }
}
```

> class 用中性/clay 高亮（clay=工作语义非信任色），**绝不用 teal/绿**——信任色锁。

- [ ] **Step 4: 构建验证**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os/frontend && npm run build`
Expected: 构建成功。

- [ ] **Step 5: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add frontend/src/views/AgentPortal.vue
git commit -m "feat(batch-c): 晋升亲历动效（同步成功回调播中性burst+.promote-burst,历史直开静态)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: MePage.vue + 路由 + 侧栏入口 + api/me.js

**Files:**
- Create: `frontend/src/views/MePage.vue`
- Create: `frontend/src/api/me.js`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/App.vue`

**Interfaces:**
- Consumes: `GET /api/me/contributions?since=`、`GET /api/me/tasks?limit=`（Task 4）、`GET /api/stats/overview?since=`（批B 既有）、`currentUser`（session store）、`request`（api/client）。
- Produces: `/me` 路由、侧栏「我的贡献」入口、五版块页面。DOM 契约供 Task 8 e2e：概览四格 `.me-overview .me-stat`、我发起的任务列表 `.me-task-item`、反馈近似标注 `.me-feedback-note`、诚实缺口条 `.me-honest-gap`。

- [ ] **Step 1: api/me.js**

创建 `frontend/src/api/me.js`：

```javascript
import { request } from "./client";

export function fetchMyContributions(since) {
  return request(`/api/me/contributions?since=${encodeURIComponent(since)}`);
}

export function fetchMyTasks(limit = 20) {
  return request(`/api/me/tasks?limit=${limit}`);
}
```

- [ ] **Step 2: MePage.vue**

创建 `frontend/src/views/MePage.vue`。since 用批B TodayPage 同款「本地周一零点」算式（避免口径漂移）：

```vue
<template>
  <div class="me-page">
    <div class="page-header">
      <h2>我的贡献</h2>
      <p class="page-sub">仅你本人可见 · 只统计可精确归因的贡献</p>
    </div>

    <el-alert v-if="loadError" type="error" :title="loadError" show-icon :closable="false" class="page-alert" />

    <!-- 版块1：贡献概览（精确） -->
    <div class="me-overview">
      <div class="me-stat"><span class="me-stat-num">{{ contrib?.since_created ?? "—" }}</span><span class="me-stat-label">本周发起</span></div>
      <div class="me-stat"><span class="me-stat-num">{{ contrib?.since_completed ?? "—" }}</span><span class="me-stat-label">本周完成</span></div>
      <div class="me-stat"><span class="me-stat-num">{{ contrib?.waiting_review ?? "—" }}</span><span class="me-stat-label">待我跟进</span></div>
      <div class="me-stat"><span class="me-stat-num">{{ contrib?.total_created ?? "—" }}</span><span class="me-stat-label">累计发起</span></div>
    </div>

    <!-- 版块2：我发起的任务（精确） -->
    <div class="me-section">
      <div class="me-section-label">我发起的任务</div>
      <EmptyState v-if="!loading && !myTasks.length" description="你还没有发起任务" />
      <div v-else class="me-task-list">
        <a v-for="t in myTasks" :key="t.id" class="me-task-item" @click="openTask(t)">
          <span class="me-task-name">{{ t.name || t.agent_id }}</span>
          <span class="me-task-status">{{ t.status }}</span>
          <span class="me-task-time">{{ formatTime(t.created_at) }}</span>
        </a>
      </div>
    </div>

    <!-- 版块3：我的反馈（近似，显式标注） -->
    <div class="me-section">
      <div class="me-section-label">我的反馈</div>
      <div class="me-feedback-count">{{ contrib?.feedback_count_approx ?? "—" }} 条</div>
      <div class="me-feedback-note">按显示名近似统计（可能与同名者混计）——反馈无唯一身份列</div>
    </div>

    <!-- 版块4：团队总量（复用批B，无人际排名） -->
    <div class="me-section">
      <div class="me-section-label">团队本周总量</div>
      <div class="me-team-bar">
        <span>完成 {{ team?.tasks_completed ?? "—" }}</span>
        <span>签发 {{ team?.reviews_approved ?? "—" }}</span>
        <span>固化 {{ team?.curated_cases_total ?? "—" }}</span>
        <span>晋升 {{ team?.promotions ?? "—" }}</span>
      </div>
      <div class="me-team-note">团队总量仅作氛围对照，不含任何人际排名</div>
    </div>

    <!-- 版块5：诚实缺口条（显式上屏，非装饰） -->
    <div class="me-honest-gap">
      签发 / 样本认可的个人归因待后续——签发唯一身份当前仅在审计轨留痕（人是唯一签发者），暂无应用数据读路径。此页只统计可精确归因的发起贡献。
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { fetchMyContributions, fetchMyTasks } from "../api/me";
import { request } from "../api/client";
import EmptyState from "../components/EmptyState.vue";
import { formatTime } from "../utils/format";

const router = useRouter();
const contrib = ref(null);
const myTasks = ref([]);
const team = ref(null);
const loading = ref(true);
const loadError = ref("");

// 批B TodayPage 同款：本地周一零点（避免与后端窗口口径漂移）
function weekStartIso() {
  const now = new Date();
  const day = (now.getDay() + 6) % 7; // 周一=0
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - day, 0, 0, 0, 0);
  return monday.toISOString();
}

async function load() {
  loading.value = true;
  loadError.value = "";
  const since = weekStartIso();
  try {
    const [c, t, s] = await Promise.all([
      fetchMyContributions(since),
      fetchMyTasks(20),
      request(`/api/stats/overview?since=${encodeURIComponent(since)}`),
    ]);
    contrib.value = c;
    myTasks.value = t;
    team.value = s;
  } catch (err) {
    loadError.value = err.detail || err.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

function openTask(t) {
  router.push({ path: `/tasks/${t.id}` });
}

onMounted(load);
</script>

<style scoped>
.page-header { margin-bottom: 20px; }
.page-header h2 { font-family: var(--serif); font-size: 27px; font-weight: 600; margin: 0 0 6px; }
.page-sub { margin: 0; color: var(--ink-faint); font-size: 13px; }
.page-alert { margin-bottom: 16px; }
.me-overview { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
.me-stat {
  display: flex; flex-direction: column; gap: 4px; padding: 16px 18px;
  border: 1px solid var(--hairline); border-radius: 12px; background: var(--paper-rail);
}
.me-stat-num { font-size: 26px; font-weight: 700; color: var(--ink); font-family: var(--serif); }
.me-stat-label { font-size: 12px; color: var(--ink-soft); }
.me-section { margin-bottom: 22px; }
.me-section-label { font-size: 11.5px; font-weight: 700; color: var(--ink-faint); margin-bottom: 8px; }
.me-task-list { display: flex; flex-direction: column; gap: 6px; }
.me-task-item {
  display: flex; align-items: center; gap: 12px; padding: 10px 14px; cursor: pointer;
  border: 1px solid var(--hairline); border-radius: 8px;
}
.me-task-item:hover { border-color: var(--clay-softer); }
.me-task-name { flex: 1; color: var(--ink); font-size: 13.5px; }
.me-task-status { color: var(--ink-soft); font-size: 12px; }
.me-task-time { color: var(--ink-faint); font-size: 11.5px; }
.me-feedback-count { font-size: 18px; font-weight: 700; color: var(--ink); }
.me-feedback-note { color: var(--ink-faint); font-size: 11.5px; margin-top: 4px; }
.me-team-bar { display: flex; gap: 18px; color: var(--ink-soft); font-size: 13px; }
.me-team-note { color: var(--ink-faint); font-size: 11px; margin-top: 6px; }
.me-honest-gap {
  margin-top: 24px; padding: 12px 14px; border: 1px dashed var(--hairline);
  border-radius: 8px; background: var(--paper-rail);
  color: var(--ink-faint); font-size: 12px; line-height: 1.6;
}
</style>
```

- [ ] **Step 3: 加路由**

在 `frontend/src/router/index.js` 的 `routes` 数组里，`/today` 之后加：

```javascript
  { path: "/me", name: "me", component: () => import("../views/MePage.vue"), meta: { title: "我的贡献" } },
```

- [ ] **Step 4: 侧栏加入口（不重载登出语义）**

在 `frontend/src/App.vue` 的身份按钮（`<button class="sb-identity" …>`）**之前**加一个独立的「我的贡献」深链（不并进登出按钮）：

```html
      <a class="sb-mine" :class="{ 'is-active': route.path === '/me' }" @click="$router.push('/me')">我的贡献</a>
```

在 `<style scoped>` 里加（贴合既有 `.sb-identity` 视觉）：

```css
.sb-mine {
  display: block; padding: 6px 10px; margin: 0 8px 4px; cursor: pointer;
  color: var(--ink-soft); font-size: 12.5px; border-radius: 6px;
}
.sb-mine:hover, .sb-mine.is-active { color: var(--ink); background: var(--paper-rail); }
```

> `route` 在 App.vue 的 `<script setup>` 里已有（模板用到 `route.meta.pageKey`/`route.path`），直接复用；若未 import 则 `import { useRoute } from "vue-router"; const route = useRoute();`（先确认，避免重复声明）。

- [ ] **Step 5: 构建验证**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os/frontend && npm run build`
Expected: 构建成功。

- [ ] **Step 6: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add frontend/src/views/MePage.vue frontend/src/api/me.js frontend/src/router/index.js frontend/src/App.vue
git commit -m "feat(batch-c): /me 工程师私有贡献页五版块（含诚实缺口条+反馈近似标注）+侧栏入口

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: e2e batch_c_rewards_acceptance + verify_all 注册

**Files:**
- Create: `frontend/e2e/batch_c_rewards_acceptance.py`
- Modify: `scripts/verify_all.sh:69-81`（E2E_SCRIPTS 数组）

**Interfaces:**
- Consumes: `_auth.seed_user/login_context/login_httpx`、批B e2e 的自起后端样板、Task 5-7 的 DOM 契约。
- Produces: verify_all 内一条新 e2e 步骤，覆盖 spec §三①-⑤。

**e2e task 说明**：脚本自包含（自起后端到 tmp 目录 + Job Runner + 真 chromium），照抄 `batch_b_today_acceptance.py` 的骨架（自起后端 / seed / 登录 / 保活）。**先构建前端** `cd frontend && npm run build`。

- [ ] **Step 1: 写 e2e 脚本（照 batch_b 骨架改）**

创建 `frontend/e2e/batch_c_rewards_acceptance.py`。骨架（自起后端、WORK tmp 目录、seed agent、启 uvicorn 线程、健康探测、SHOTS 目录）**逐段照抄 `batch_b_today_acceptance.py`**，只改验收断言体。覆盖五点：

```python
# —— 覆盖点（spec §三 e2e）——
# ① 打开某 agent 治理弹窗 → 成长档案四版块可见（.gov-ladder / .gov-eval-trend
#    或空态 / .gov-promotion-timeline / .gov-cases-count）；造 2 次晋升 → 晋升史
#    卡 .gov-promotion-card 数 >= 2（摊开全部，非只 [0]）。
# ② 弹窗内点「申请晋升 L1」成功 → 最新晋升卡出现 .promote-burst（本会话亲历）。
# ③ /me 概览四格数字 === httpx 直查 /api/me/contributions（同 since，since 从
#    页面 JS evaluate 取 MePage 同款 weekStartIso）。
# ④ 私有越权断言：seed 第二账户 bob（httpx 直登），bob 的 /api/me/contributions
#    total_created 只反映 bob 自己；且 alice 浏览器带 ?username=bob 直打端点仍返回
#    alice 自己的数（query 越权被忽略）。
# ⑤ 诚实缺口条 .me-honest-gap 文案在屏。
```

关键断言片段（在 batch_b 骨架的 `with sync_playwright()` 内、登录后）：

```python
    # 造评测 + 两次晋升：用已登录 httpx client 走真实治理 API
    # （run eval → promote L1 需要一次全绿评测；hello_agent 的 eval 用例即全绿样板）。
    api = login_httpx(base, username="e2e_engineer", password="e2e-pass-flai")
    # ① 成长档案：打开门户 → 点某 agent「治理」→ 断言四版块
    page.goto(f"{base}/portal")
    page.wait_for_selector(".agent-card")
    page.click("text=治理")
    page.wait_for_selector(".gov-ladder")
    assert page.query_selector(".gov-cases-count") is not None
    # ② 亲历动效：点「申请晋升 L1」（先跑评测 + 勾确认）
    page.click("text=跑评测")
    page.wait_for_selector(".gov-run-summary")
    # 勾确认 checkbox 后点申请晋升
    page.check(".gov-promote-confirm input")
    page.click("text=申请晋升 L1")
    page.wait_for_selector(".gov-promotion-card.promote-burst", timeout=8000)  # 亲历必现
    # ③④⑤ /me
    page.goto(f"{base}/me")
    page.wait_for_selector(".me-overview")
    since = page.evaluate(
        "() => { const n=new Date(); const d=(n.getDay()+6)%7;"
        " return new Date(n.getFullYear(),n.getMonth(),n.getDate()-d,0,0,0,0).toISOString(); }"
    )
    api_contrib = api.get(f"/api/me/contributions?since={since}").json()
    ui_total = page.inner_text(".me-overview .me-stat:last-child .me-stat-num")
    assert str(api_contrib["total_created"]) == ui_total.strip()
    assert page.query_selector(".me-honest-gap") is not None
    # ④ 私有越权：query username 被忽略
    spoof = api.get(f"/api/me/contributions?since={since}&username=someone_else").json()
    assert spoof["username"] == "e2e_engineer"
```

> 亲历动效断言的前提：`hello_agent`（或所选 agent）能跑出一次全绿评测以满足晋升门。若所选 agent 无全绿评测样板，implementer 改选 m10 e2e 里用的可晋升 agent（打开 `m10_governance_acceptance.py` 看它用哪个 agent 走通了 promote），保持一致。私有越权第二账户 bob 的 seed + 断言按需补齐（seed_user 传不同 username/display_name）。截图落 `docs/reviews/batch-c-shots/`（照 batch_b 的 SHOTS 落图）。

- [ ] **Step 2: 构建前端**

Run: `cd /Users/Zhuanz/projects/aircraft-comac/flai-os/frontend && npm run build`
Expected: 成功（e2e 跑 dist）。

- [ ] **Step 3: 跑新 e2e（自起后端）**

Run:
```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
uv run --no-project --with playwright --with uvicorn --with fastapi \
  --with jsonschema --with pyyaml --with httpx --with python-multipart \
  --with "pydantic>2" --with jieba python frontend/e2e/batch_c_rewards_acceptance.py > /tmp/batch_c_e2e.log 2>&1; echo "exit=$?"
tail -40 /tmp/batch_c_e2e.log
```
Expected: `exit=0`，日志显示五点全过 + 截图落 `docs/reviews/batch-c-shots/`。
（canon #51：用 `> log 2>&1; echo exit=$?` 取真退出码，别用管道吞码。）

- [ ] **Step 4: 注册进 verify_all**

在 `scripts/verify_all.sh` 的 `E2E_SCRIPTS=(` 数组里，`batch_b_today_acceptance.py` 之后加：

```bash
  "frontend/e2e/batch_c_rewards_acceptance.py"
```

- [ ] **Step 5: 全量 verify_all 真跑（取真退出码）**

Run:
```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
bash scripts/verify_all.sh > /tmp/verify_all_c.log 2>&1; echo "exit=$?"
tail -30 /tmp/verify_all_c.log
```
Expected: `exit=0`，全部后端套件 + 全部 e2e（含新 batch_c）绿。若 m10 治理 flake 复现（retro 队列已知），单独重跑该套件确认是 flake 非本批回归。

- [ ] **Step 6: Commit**

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
git add frontend/e2e/batch_c_rewards_acceptance.py scripts/verify_all.sh docs/reviews/batch-c-shots/
git commit -m "test(batch-c): e2e 验收（成长档案四版块+晋升亲历+/me私有越权断言）入 verify_all

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: 收口——Codex 治理审 + 全绿封板

**Files:** 无代码（审查与修复轮）。

**说明**：命中「新 API 端点 + 治理/贡献数字上屏 + 私有访问控制」→ 治理审同步阻塞。

- [ ] **Step 1: Codex 治理审（86gs gpt-5.6-sol ultra）**

Run:
```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os
codex-review-relay --base main
```
审查范围=批C 全部 commit。重点盯：`/api/me/*` 私有 session 派生（能否被 query 越权）、`created_by_username` 过滤 SQL 注入面（参数化已用 `?`，确认无字符串拼接）、诚实缺口/近似标注是否真上屏、信任色锁（burst 是否误用 teal）、eval 除零口径。

- [ ] **Step 2: 逐条 grounded 复核 + 修复**

每条 finding 先 grounded 复核（审查方也会 over-claim）；确认为真 → 新 commit 修复再审。round cap=3；第 3 轮仍有 P1 → 交用户裁决。verbatim 例外：逐字落地 Codex Suggested fix 直接做，commit 标 `confidence`。

- [ ] **Step 3: APPROVE 后 SDD 全分支终审**

Codex APPROVE + `verify_all exit=0` 后，SDD 收口跑一次 whole-branch code review（最强模型）。全绿 → 交用户裁合并（feedback_review_pass_auto_merge_push：过审即自主合并 push，但本批为多批次工程台，合并前向用户报一句收尾）。

---

## Self-Review

**1. Spec coverage**（逐节对照 spec）：
- §一 轨1 成熟度阶梯/eval通过率/晋升史/固化case → Task 3（端点）+ Task 5（四版块）✅
- §一 晋升亲历动效 → Task 6 ✅
- §二 轨2 /me 五版块（概览/我发起/我的反馈近似/团队总量/诚实缺口）→ Task 7 ✅
- §二 私有=session 派生拒 query → Task 4（端点）+ Task 8④（e2e 越权断言）✅
- §二 后端 list_tasks 加过滤 + 2 只读端点 → Task 1 + Task 4 ✅
- §三 pytest oracle 先行 + tamper → Task 1/3/4 均含 tamper 步 ✅
- §三 e2e 入 verify_all + 私有越权 + 亲历断言 → Task 8 ✅
- §三 视觉存证 → Task 8（SHOTS）；§三 Codex 治理审 → Task 9 ✅
- §四 诚实缺口非装饰=验收项 → Task 7（`.me-honest-gap`）+ Task 8⑤断言 ✅；反馈近似标注 → Task 7（`.me-feedback-note`）✅
- §四 晋升动效不接 liveFeed（同步回调）→ Task 6 ✅；NULL 存量不误计 → Task 1 测试覆盖 ✅

**2. Placeholder scan**：无 TBD/TODO；每个代码步含完整代码；e2e 骨架显式指向 batch_b 照抄并给出关键断言片段（非「类似 Task N」）。Task 3 特意纠正了 `count_curated_cases` glob 段数不匹配单 agent scope 的陷阱，给出内联正确实现。

**3. Type consistency**：`created_by_username` 参数名跨 Task 1（repos）/Task 4（me.py 调用）/Task 8（e2e 断言）一致；`me/contributions` 返回字段名（`since_created/since_completed/waiting_review/total_created/feedback_count_approx`）在 Task 4 定义、Task 7 消费（`contrib?.since_created` 等）、Task 8 断言（`total_created`）三处一致；DOM class 契约（`.gov-promotion-card`/`.promote-burst`/`.me-overview .me-stat`/`.me-honest-gap`）在 Task 5/6/7 产出、Task 8 消费一致；`burstNeutral` 签名一致。

**已知残差（诚实标注，非本批修）**：m10 治理 flake（retro 队列）；me/contributions 的 waiting_review 是当前快照非 since 窗口（设计如此，"待我跟进"是活状态）。

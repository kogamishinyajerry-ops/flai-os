# 批B「今日工作台 + 交付叙事」Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/today` 今日工作台五版块（待签发置顶/进行中/今日交付叙事卡/Agent 动态/团队总量条），数字全部来自真实治理事件，零 schema 变更。

**Architecture:** 后端加两个只读端点（`GET /api/stats/overview?since=` SQL 直查聚合 + `GET /api/promotions` 全局最近晋升）；前端新 TodayPage 复用批A liveFeed tasks channel 作 1-3 版块唯一数据源，4-5 版块进页拉一次 + onTransition 低频补拉；交付卡复用 CompletionSeal/产物指纹/时长 SSOT。

**Tech Stack:** FastAPI+SQLite（无 ORM，repos 层）、Vue3+Element Plus、批A liveFeed store、pytest、Playwright e2e。

## Global Constraints（逐字来自 spec）

- 每个数字来自真实治理事件（tasks/task_events/promotions 既有表 + eval_cases 落盘文件）——绝不虚构积分池。
- 零 schema 变更；后端只加只读端点；无新依赖。
- 信任色锁五槽不动：团队总量条与统计数字一律中性 ink 色；teal 仅人签动作本身；completed 不给绿。
- MOTION-SYSTEM 六条有效；新动效只用既有 token/fx-*；reduced-motion 全降级。
- 诚实口径三处上屏：①「基于最近 100 条任务窗口」页脚 ②今日/本周=本地时区日切（前端算 since 传 UTC ISO）③固化 case「累计（按仓内固化文件计）」。
- 仪式只属亲历者：历史卡 animate 恒 false；仅本会话 onTransition 亲历翻终态的卡播 seal-animate。
- 导航 A 案（owner 拍板）：NAV 加第二项「今日」。
- stats `since` 必填合法 ISO8601，非法 422 fail-closed；统计沿用 origin='user' 语义排除 eval 任务。
- e2e 断言走「同源对照」（页面数字 vs 直查 API/角标），不断言写死常数。
- 跑测口径：后端 `uv run --no-project --with pytest --with jsonschema --with pyyaml --with fastapi --with httpx --with python-multipart --with "pydantic>2" --with jieba --with openpyxl python -m pytest -q backend/tests/test_stats_api.py`；e2e 用 verify_all 内既有 uv run 样板。

---

### Task 1: 全局 promotions 只读端点

**Files:**
- Modify: `backend/app/storage/repos.py`（`list_promotions` 附近 ~1101 行后新增）
- Modify: `backend/app/api/governance.py`（`list_promotions` 路由后新增）
- Test: `backend/tests/test_stats_api.py`（新建，本任务先放 promotions 部分）

**Interfaces:**
- Consumes: `repos._decode_json`（已有）、promotions DDL（db.py:192-203，列：agent_id/agent_version/from_maturity/to_maturity/eval_run_id/checks_json/confirmations_json/confirmed_by/created_at）、`repos.record_promotion`（已有写入函数，grep 确认签名后在测试里用它种数据；若无则直接 INSERT）。
- Produces: `repos.list_promotions_all(conn, limit: int = 20) -> list[dict]`（ORDER BY id DESC，JSON 列解码同单 agent 版）；`GET /api/promotions?limit=20`（limit 1-100 夹取，默认 20）。

- [ ] **Step 1: 写失败测试**（conftest 的 `app_env` fixture 给 `(client, app)`，登录已 seed；种数据用 `app.state.conn_factory()`）

```python
# backend/tests/test_stats_api.py
"""批B 只读聚合端点：全局 promotions + stats/overview。oracle=夹具种入已知
治理事件后断言精确计数；tamper 语义见各测试注释。"""
from __future__ import annotations

import json


def _insert_promotion(conn, agent_id: str, created_at: str) -> None:
    conn.execute(
        "INSERT INTO promotions (agent_id, agent_version, from_maturity, to_maturity,"
        " eval_run_id, checks_json, confirmations_json, confirmed_by, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (agent_id, "0.1.0", "L0", "L1", "er-1", json.dumps({}), json.dumps({}), "测试签发人", created_at),
    )
    conn.commit()


def test_global_promotions_desc_and_limit(app_env):
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        _insert_promotion(conn, "hello_agent", "2026-07-13T01:00:00+00:00")
        _insert_promotion(conn, "review_agent", "2026-07-13T02:00:00+00:00")
    finally:
        conn.close()
    r = client.get("/api/promotions")
    assert r.status_code == 200
    rows = r.json()
    assert [x["agent_id"] for x in rows[:2]] == ["review_agent", "hello_agent"]  # 最近优先
    assert "checks" in rows[0] and "confirmed_by" in rows[0]
    r2 = client.get("/api/promotions", params={"limit": 1})
    assert len(r2.json()) == 1


def test_global_promotions_empty_ok(app_env):
    client, _ = app_env
    r = client.get("/api/promotions")
    assert r.status_code == 200
    assert r.json() == []
```

- [ ] **Step 2: 跑测确认失败**：上文跑测口径命令。Expected: FAIL（404，路由不存在）。
- [ ] **Step 3: 实现**——repos.py 在 `list_promotions` 后加：

```python
def list_promotions_all(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    """全局最近晋升（批B /today Agent 动态）。与单 agent 版同解码，最近优先。"""
    rows = conn.execute(
        "SELECT * FROM promotions ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        _decode_json(d, "checks_json", "checks", default={})
        _decode_json(d, "confirmations_json", "confirmations", default={})
        out.append(d)
    return out
```

governance.py 在 `list_promotions` 路由后加：

```python
@router.get("/promotions")
def list_promotions_all(request: Request, limit: int = 20) -> list[dict[str, Any]]:
    """全局最近晋升（批B /today）。只读；limit 夹取 1-100 防全表倾倒。"""
    limit = max(1, min(int(limit), 100))
    conn = request.app.state.conn_factory()
    try:
        return repos.list_promotions_all(conn, limit)
    finally:
        conn.close()
```

- [ ] **Step 4: 跑测确认过**（该文件全部）。
- [ ] **Step 5: Commit**：`git add backend/app/storage/repos.py backend/app/api/governance.py backend/tests/test_stats_api.py && git commit -m "feat(api): 全局 promotions 只读端点（批B Task 1）"`

### Task 2: stats/overview 聚合端点

**Files:**
- Create: `backend/app/api/stats.py`
- Modify: `backend/app/main.py`（~92 行 app.state 区加 `app.state.agents_dir = agents_dir`；~155 行加 `app.include_router(stats_api.router)` 及对应 import）
- Test: `backend/tests/test_stats_api.py`（追加）

**Interfaces:**
- Consumes: tasks 表（status/finished_at/origin 列）、task_events 表（event_type='review_approved'，created_at）、promotions 表、`app.state.agents_dir`（Path）。
- Produces: `GET /api/stats/overview?since=<iso>` → `{"since", "tasks_completed", "reviews_approved", "curated_cases_total", "promotions"}` 全 int；纯函数 `count_curated_cases(agents_dir: Path) -> int`（stats.py 内，glob `*/eval_cases/case_*.json`）。

- [ ] **Step 1: 写失败测试**（追加到 test_stats_api.py；种任务/事件走 SQL 直插以控制时间戳——列名先 `sqlite3` 查 conftest 库或读 db.py:40-60 核对，缺省列给合法值）

```python
def _insert_completed_task(conn, task_id: str, finished_at: str, origin: str = "user") -> None:
    # 只填 stats 查询涉及列 + NOT NULL 列；其余列以 db.py DDL 为准补默认。
    conn.execute(
        "INSERT INTO tasks (id, agent_id, agent_version, name, status, inputs_json,"
        " input_file_ids_json, output_file_ids_json, created_by, origin,"
        " created_at, updated_at, finished_at)"
        " VALUES (?, 'hello_agent', '0.1.0', ?, 'completed', '{}', '[]', '[]',"
        " '测试工程师', ?, ?, ?, ?)",
        (task_id, task_id, origin, finished_at, finished_at, finished_at),
    )
    conn.commit()


def _insert_review_event(conn, task_id: str, created_at: str) -> None:
    conn.execute(
        "INSERT INTO task_events (task_id, seq, event_type, payload_json, created_at)"
        " VALUES (?, 1, 'review_approved', '{}', ?)",
        (task_id, created_at),
    )
    conn.commit()


SINCE = "2026-07-13T00:00:00+00:00"
BEFORE = "2026-07-12T23:59:59+00:00"
AFTER = "2026-07-13T08:00:00+00:00"


def test_stats_overview_exact_counts(app_env, tmp_path):
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        _insert_completed_task(conn, "t-in", AFTER)
        _insert_completed_task(conn, "t-out", BEFORE)          # 界前不计
        _insert_completed_task(conn, "t-eval", AFTER, origin="eval")  # eval 不计
        _insert_review_event(conn, "t-in", AFTER)
        _insert_review_event(conn, "t-out", BEFORE)
        _insert_promotion(conn, "hello_agent", AFTER)
        _insert_promotion(conn, "hello_agent", BEFORE)
    finally:
        conn.close()
    r = client.get("/api/stats/overview", params={"since": SINCE})
    assert r.status_code == 200
    body = r.json()
    # tamper：把实现里 event_type 过滤/origin 过滤/since 比较任一拆掉，本测必红。
    assert body["tasks_completed"] == 1
    assert body["reviews_approved"] == 1
    assert body["promotions"] == 1
    assert isinstance(body["curated_cases_total"], int)


def test_stats_since_boundary_inclusive(app_env):
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        _insert_completed_task(conn, "t-edge", SINCE)  # 恰在界上：计入（>=）
    finally:
        conn.close()
    body = client.get("/api/stats/overview", params={"since": SINCE}).json()
    assert body["tasks_completed"] == 1


def test_stats_since_required_and_valid(app_env):
    client, _ = app_env
    assert client.get("/api/stats/overview").status_code == 422
    assert client.get("/api/stats/overview", params={"since": "昨天"}).status_code == 422


def test_count_curated_cases_pure(tmp_path):
    from backend.app.api.stats import count_curated_cases
    d = tmp_path / "agents" / "a1" / "eval_cases"
    d.mkdir(parents=True)
    (d / "case_001_from_sample.json").write_text("{}")
    (d / "case_002_from_sample.json").write_text("{}")
    (d / "notes.md").write_text("")  # 非 case_*.json 不计
    assert count_curated_cases(tmp_path / "agents") == 2
    assert count_curated_cases(tmp_path / "不存在") == 0
```

- [ ] **Step 2: 跑测确认失败**（import/404）。
- [ ] **Step 3: 实现** `backend/app/api/stats.py`：

```python
"""批B /today 只读聚合（spec docs/superpowers/specs/2026-07-13-today-workbench-batch-b-design.md §三）。
零 schema 变更：SQL 直查既有表 + eval_cases 落盘文件计数。since 必填合法
ISO8601（fail-closed 422，不默认兜底窗口）；ISO8601 UTC 字符串字典序可比，
与 repos 写入格式一致，SQL 直接 >= 比较。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api", tags=["stats"])


def count_curated_cases(agents_dir: Path) -> int:
    """累计固化 case 数=agents/*/eval_cases/case_*.json 落盘文件（治理产物的
    真实存在形式，ADR-0018 固化即落盘无 DB 行）。目录缺失=0，不抛。"""
    if not agents_dir.is_dir():
        return 0
    return sum(1 for _ in agents_dir.glob("*/eval_cases/case_*.json"))


@router.get("/stats/overview")
def stats_overview(request: Request, since: str | None = None) -> dict[str, Any]:
    if not since:
        raise HTTPException(status_code=422, detail="since 必填（ISO8601）")
    try:
        datetime.fromisoformat(since)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"since 不是合法 ISO8601：{since}") from exc
    conn = request.app.state.conn_factory()
    try:
        tasks_completed = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'completed'"
            " AND origin = 'user' AND finished_at IS NOT NULL AND finished_at >= ?",
            (since,),
        ).fetchone()[0]
        reviews_approved = conn.execute(
            "SELECT COUNT(*) FROM task_events WHERE event_type = 'review_approved'"
            " AND created_at >= ?",
            (since,),
        ).fetchone()[0]
        promotions = conn.execute(
            "SELECT COUNT(*) FROM promotions WHERE created_at >= ?", (since,)
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "since": since,
        "tasks_completed": tasks_completed,
        "reviews_approved": reviews_approved,
        "curated_cases_total": count_curated_cases(request.app.state.agents_dir),
        "promotions": promotions,
    }
```

main.py：import 区加 `from .api import stats as stats_api`（对齐现有 import 风格）；app.state 区（92 行附近）加 `app.state.agents_dir = agents_dir`；include_router 区（155 行后）加 `app.include_router(stats_api.router)`。

- [ ] **Step 4: 跑测确认全过**；再跑全量后端 pytest 确认零回归。
- [ ] **Step 5: Commit**：`git add backend/app/api/stats.py backend/app/main.py backend/tests/test_stats_api.py && git commit -m "feat(api): stats/overview 聚合端点（批B Task 2,零schema,fail-closed since）"`

### Task 3: 前端 API 封装 + /today 路由与导航 + 页面骨架（版块 1/2 + 口径页脚）

**Files:**
- Create: `frontend/src/api/stats.js`
- Create: `frontend/src/views/TodayPage.vue`
- Modify: `frontend/src/router/index.js`（routes 数组加一条）
- Modify: `frontend/src/App.vue`（NAV 数组 ~215 行）

**Interfaces:**
- Consumes: `acquireChannel("tasks")`（stores/liveFeed.js，state={tasks,loaded,error}）、`taskLampColor/statusLabel`（utils/format.js SSOT）、`SkeletonBlock.vue`、`EmptyState.vue`、api/client.js 的请求封装（Read 对齐其余 api/*.js 写法）。
- Produces: `getStatsOverview(sinceIso) -> Promise<obj>`、`listGlobalPromotions(limit=20) -> Promise<list>`（api/stats.js）；TodayPage 五版块容器（本任务落 1 待签发/2 进行中 + 3/4/5 占位区块 + 页脚口径小字「基于最近 100 条任务窗口」）；路由 `{ path: "/today", name: "today", component: () => import("../views/TodayPage.vue"), meta: { title: "今日" } }`；NAV=`[{ path: "/", label: "对话" }, { path: "/today", label: "今日" }]`（同时更新 App.vue:212-214 范式注释：双入口=对话+今日，其余仍深链）。
- 版块 1 待签发：`tasks.filter(t => t.status === "waiting_review")`，卡片=lamp+名称+agent+等待时长（`taskElapsedMs` 起点口径 Read utils/format 决定），点击 `router.push('/tasks/'+id)`；空态 EmptyState「没有等你签发的任务」。版块 2 进行中：filter `["created","queued","running","validating"].includes(status)`。首载 SkeletonBlock（`!loaded && !error`），错误走既有 error 展示模式（Read TaskConsole 对齐）。onUnmounted release。
- 验收：`npm run build` 过；手动 playwright 截图 /today（两版块+占位）存 docs/reviews/batch-b-shots/1_today_shell.png；既有 e2e m2 回归绿。Commit：`feat(ux): /today 路由+导航双入口+待签发/进行中版块（批B Task 3）`。

### Task 4: 交付叙事卡 + 今日交付版块

**Files:**
- Create: `frontend/src/components/DeliveryCard.vue`
- Modify: `frontend/src/views/TodayPage.vue`（版块 3 接卡）

**Interfaces:**
- Consumes: `CompletionSeal.vue`（props task+animate）、`fetchOutputFile`/`downloadUrl`（api/files.js）、`listModelCalls`/`listTaskEvents`（api/tasks.js，Read 确认导出名）、`taskElapsedMs/formatDuration/statusLabel`。
- Produces: `<DeliveryCard :task="t" :animate="false" />`（本任务 animate 恒 false 占位；Task 6 接线成 `sealAnimateIds.has(t.id)`）。DeliveryCard 自身 props 与 CompletionSeal 对齐：`{ task: Object, animate: Boolean }`。卡结构：CompletionSeal 头行 → 名称+agent_id·version+created_by+用时 → 产物条（output_file_ids 前 3 件文件名 chip，fetchOutputFile 一次性取 meta，fileId 去重，>3 显「+N」，无产物不渲染该条）→ 尾行：挂载时一次性 `listModelCalls(taskId).catch(()=>null)`（null→「模型调用：未知」，[]→「无模型调用」，有→「N 次调用·token 合计 X」凑不出 token 显「未知」）与 `listTaskEvents(taskId,{offset:0}).catch(()=>null)` 派生批量 ok/failed（无批量事件不显示）。终态数据静态，**绝不轮询**。整卡点击跳 `/tasks/:id`（内部 chip 点击 stopPropagation 下载）。failed 状态词用 `--trust-fail`，其余全中性。
- 版块 3 过滤：`tasks.filter(终态 && finished_at 本地今日)`——本地日切：`const todayStart = new Date(); todayStart.setHours(0,0,0,0)`，比较 `new Date(t.finished_at) >= todayStart`。
- 验收：build 过；造 1 个完成任务（httpx 直调 API，参考 batch_a e2e 的 approver 做法）截图卡片存 docs/reviews/batch-b-shots/2_delivery_card.png；m2+batch_a e2e 回归绿。Commit：`feat(ux): 交付叙事卡+今日交付版块（批B Task 4）`。

### Task 5: Agent 动态 + 团队总量条

**Files:**
- Modify: `frontend/src/views/TodayPage.vue`（版块 4/5 实装）

**Interfaces:**
- Consumes: Task 3 的 `getStatsOverview/listGlobalPromotions`；liveFeed `onTransition`。
- Produces: 版块 4a 最近晋升列表（≤5 条：「{agent_id} 晋升 {from}→{to} · 相对时间 · 签发人 {confirmed_by}」，空态「本周暂无晋升」）；4b 今日最活跃 Agent（tasks 窗口按 agent_id 分组计数 top3，小字标注窗口口径）；版块 5 团队总量条=四格横条（本周完成/本周人签放行/累计固化 case/本周晋升），全中性 ink 色，格内大数字+小字口径（「本周」=本地周一零点转 UTC ISO 作 since；「累计（按仓内固化文件计）」）。
- 拉取纪律：进页各拉一次（stats+promotions）；`onTransition` 观察到 `ev.to === "completed"` 或 `ev.from === "waiting_review"` 时补拉一次 stats（30s 内去重，防事件雨连环拉）；**不进 liveFeed 轮询**。off 订阅随 onUnmounted。
- 验收：build 过；数字与直查 API 相等（临时脚本对照即可，正式同源断言在 Task 6 e2e）；截图 docs/reviews/batch-b-shots/3_stats_bar.png。Commit：`feat(ux): Agent动态+团队总量条（批B Task 5,真实治理事件口径）`。

### Task 6: 亲历仪式接线 + e2e 验收入 verify_all

**Files:**
- Modify: `frontend/src/views/TodayPage.vue`（sealAnimateIds 接线）
- Create: `frontend/e2e/batch_b_today_acceptance.py`
- Modify: `scripts/verify_all.sh`（E2E 清单加一行）

**Interfaces:**
- Consumes: liveFeed `onTransition`（事件 `{id,from,to,task}`；亲历判据与 TaskDetail 同款：`ev.from != null && !TERMINAL.includes(ev.from) && TERMINAL.includes(ev.to)`，TERMINAL 从 liveFeedCore import `TERMINAL_STATUSES`）；batch_a e2e 的登录/approver/保活样板（Read frontend/e2e/batch_a_livefeed_acceptance.py 复用其结构）。
- Produces: TodayPage 内 `const sealAnimateIds = reactive(new Set())`，onTransition 亲历时 `sealAnimateIds.add(ev.id)`（页面生命周期内不清除——同一会话回看仍算亲历过，与 TaskDetail 语义一致）。e2e 四断言（spec §五）：①/today 渲染五版块且待签发计数 === StatusDock 角标数（同源）②跨会话 approver 批准 → /today 不动 12s 内该任务出现在「今日交付」且其卡 `.seal-animate` 出现（亲历）③团队总量条四格数字 === httpx 直查 `/api/stats/overview`（同 since）返回值（同源）④重新打开 /today（新页面导航）该卡无 `.seal-animate`（历史直开不播）。轮询等待循环每秒 `page.evaluate("1")` 保活（headless 冻结坑，canon#50）。
- 验收：新 e2e 全绿两连跑；verify_all 全量绿。Commit：`test(ux): 批B /today 验收 e2e 入 verify_all（批B Task 6）`。

### Task 7: 全批收口

- [ ] `bash scripts/verify_all.sh > <scratchpad>/verify_b.log 2>&1; echo exit=$?` 真实 exit=0（canon#51：不用管道 tail 包 gate 命令）。
- [ ] /today 亮/暗主题全页截图存 docs/reviews/batch-b-shots/（4_today_light.png / 5_today_dark.png）。
- [ ] 治理审：命中「新 API 端点+治理数字上屏」→ `codex-review-relay --base main`；findings 逐条 grounded 复核再落地；round cap=3。
- [ ] ledger 收口 + spec 验收标准逐条对照打钩。

## Self-Review 记录

- Spec 覆盖：§一五版块+导航A案（T3/T4/T5）✓ §二交付卡（T4）✓ §三两端点（T1/T2）✓ §四实时接线（T3 channel/T5 低频补拉/T6 仪式）✓ §五测试（T1/T2 oracle+T6 e2e+T7 存证/治理审）✓ 诚实口径三处（T3 页脚/T4 窗口过滤/T5 格内小字）✓。
- 类型一致性：`list_promotions_all`（repos/route 同名）、`count_curated_cases(agents_dir)`、`getStatsOverview(sinceIso)`/`listGlobalPromotions(limit)`、`sealAnimateIds` T4 消费 T6 生产——T4 先以 `:animate="false"` 占位、T6 接线，已在 T4 接口块注明 animate 来源为 T6。
- 无占位符；测试 INSERT 列名标注「以 db.py DDL 为准核对」是实现者动手前的核对指令而非 TBD。

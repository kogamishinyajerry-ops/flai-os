"""M8 P3 协作会话数据模型（ADR-0016）。

导引编排官把一次会话的计划分流成 N 个**人签发**任务，各任务记 conversation_id
归到同一次会话下——协作工作台据此按会话聚合展示。本测覆盖：

- 迁移 #3：tasks.conversation_id。存量库（无该列）经 init_db 幂等补列；重复安全。
- 归属往返：create_task 带 conversation_id 落库可读；不带则 NULL。
- 过滤：list_tasks(conversation_id=...) 只取该会话成员。
- API：POST /api/tasks 带真实会话 id → 任务归属；带不存在会话 id → 404（防悬空
  引用）；门户直建（不带）→ conversation_id NULL。
- 会话视图：GET /api/conversations/{id}/tasks 返回成员任务；会话不存在 → 404。
- 红线守恒：本路径不新建/签发任务——任务仍由人经 /api/tasks 亲手提交。
"""

from __future__ import annotations

import json
from typing import Any, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.storage import db as db_mod
from backend.app.storage import repos

REPO_ROOT = Path(__file__).resolve().parents[2]

_LLM_ENV_VARS = ("FLAI_LLM_BASE_URL", "FLAI_LLM_API_KEY", "FLAI_LLM_MODEL_REASONING", "FLAI_LLM_MODEL_FAST")


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    for var in _LLM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def client(app_env) -> Iterator[TestClient]:
    c, _ = app_env
    yield c


def _open_conversation(client: TestClient) -> str:
    resp = client.post("/api/conversations", json={"agent_id": "guide_agent", "created_by": "m8_test"})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


# ── 迁移 #3：tasks.conversation_id 存量库补列 + 幂等 ──────────────────────


def _make_pre_m8_tasks_db(db_path) -> None:
    """造 pre-M8 老库：重建 tasks 为不含 conversation_id 的旧形状（rebuild-rename，
    任何 SQLite 版本可用；迁移探测只看列名，AS SELECT 丢约束无妨）。"""
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        legacy_cols = ", ".join(
            r[1] for r in conn.execute("PRAGMA table_info(tasks)") if r[1] != "conversation_id"
        )
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(f"CREATE TABLE tasks_legacy AS SELECT {legacy_cols} FROM tasks")
        conn.execute("DROP TABLE tasks")
        conn.execute("ALTER TABLE tasks_legacy RENAME TO tasks")
        conn.execute("COMMIT")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)")}
        assert "conversation_id" not in cols, "老库夹具必须不含新列"
    finally:
        conn.close()


def _tasks_columns(db_path) -> set[str]:
    conn = db_mod.get_conn(db_path)
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(tasks)")}
    finally:
        conn.close()


def test_migration_adds_conversation_id_to_legacy_db(tmp_path) -> None:
    db_path = tmp_path / "legacy.db"
    _make_pre_m8_tasks_db(db_path)
    assert "conversation_id" not in _tasks_columns(db_path)

    db_mod.init_db(db_path)  # 迁移 #3 补列
    assert "conversation_id" in _tasks_columns(db_path)

    db_mod.init_db(db_path)  # 再跑一次幂等，不得报 duplicate column
    assert "conversation_id" in _tasks_columns(db_path)


def test_fresh_db_has_conversation_id(tmp_path) -> None:
    """新库直接经 CREATE TABLE 带 conversation_id（不依赖迁移路径）。"""
    db_path = tmp_path / "fresh.db"
    db_mod.init_db(db_path)
    assert "conversation_id" in _tasks_columns(db_path)


# ── 归属往返 + 过滤（repos 层）──────────────────────────────────────────


def test_create_task_conversation_id_roundtrip(app_env) -> None:
    _, app = app_env
    conn = app.state.conn_factory()
    try:
        grouped = repos.create_task(
            conn, task_id="task_g1", agent_id="fta_agent", agent_version="0.1.0",
            name="会话任务", created_by="王工", conversation_id="conv_abc",
        )
        assert grouped["conversation_id"] == "conv_abc"
        # 不带 conversation_id → NULL（门户直建语义）
        solo = repos.create_task(
            conn, task_id="task_s1", agent_id="fta_agent", agent_version="0.1.0",
            name="门户任务", created_by="王工",
        )
        assert solo["conversation_id"] is None

        # get_task 也带出该列
        assert repos.get_task(conn, "task_g1")["conversation_id"] == "conv_abc"

        # 过滤：只取该会话成员
        rows = repos.list_tasks(conn, conversation_id="conv_abc")
        assert [t["id"] for t in rows] == ["task_g1"]
        assert repos.list_tasks(conn, conversation_id="conv_none") == []
    finally:
        conn.close()


# ── API：创建带会话归属 + 悬空引用 fail-closed ───────────────────────────


def test_create_task_api_with_valid_conversation_groups(app_env) -> None:
    client, _ = app_env
    conv_id = _open_conversation(client)
    # 人拿导引草案去创建任务，带上会话 id（fta_agent 是非 interactive，可直建）
    resp = client.post(
        "/api/tasks",
        json={
            "agent_id": "fta_agent",
            "inputs": {"top_event": "供电完全丧失", "system_description": "双通道供电", "components": ["A", "B"]},
            "created_by": "王工",
            "conversation_id": conv_id,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["conversation_id"] == conv_id

    # 会话视图返回该成员任务
    members = client.get(f"/api/conversations/{conv_id}/tasks").json()
    assert [t["id"] for t in members] == [resp.json()["id"]]


def test_create_task_api_nonexistent_conversation_404(app_env) -> None:
    """带一个不存在的会话 id → 404 且不建任务（防悬空引用，先于副作用）。"""
    client, _ = app_env
    resp = client.post(
        "/api/tasks",
        json={
            "agent_id": "fta_agent",
            "inputs": {"top_event": "X", "system_description": "S", "components": ["A"]},
            "created_by": "王工",
            "conversation_id": "conv_does_not_exist",
        },
    )
    assert resp.status_code == 404
    assert "会话不存在" in resp.json()["detail"]
    assert client.get("/api/tasks").json() == [], "悬空引用必须零副作用（任务不建）"


def test_portal_direct_task_has_null_conversation(app_env) -> None:
    """门户直建（不带 conversation_id）→ conversation_id NULL，不属于任何会话。"""
    client, _ = app_env
    conv_id = _open_conversation(client)
    resp = client.post(
        "/api/tasks",
        json={"agent_id": "fta_agent", "inputs": {"top_event": "X", "system_description": "S", "components": ["A"]}, "created_by": "李工"},
    )
    assert resp.status_code == 200
    assert resp.json()["conversation_id"] is None
    # 该任务不出现在任何会话视图里
    assert client.get(f"/api/conversations/{conv_id}/tasks").json() == []


def test_conversation_tasks_view_404_for_missing_conversation(client: TestClient) -> None:
    assert client.get("/api/conversations/conv_missing/tasks").status_code == 404


def test_conversation_tasks_view_paginates_beyond_500(app_env) -> None:
    """成员视图是「完整分组」不是「最近流」——取尽不静默截断（异源 Codex M8-P3）：
    >500 成员任务必须全部返回，不丢最旧那批。"""
    client, app = app_env
    conv_id = _open_conversation(client)
    conn = app.state.conn_factory()
    try:
        for i in range(501):
            repos.create_task(
                conn, task_id=f"task_big_{i:04d}", agent_id="fta_agent", agent_version="0.1.0",
                name=f"t{i}", created_by="王工", conversation_id=conv_id,
            )
    finally:
        conn.close()
    members = client.get(f"/api/conversations/{conv_id}/tasks").json()
    assert len(members) == 501, f"完整成员视图必须取尽（不静默截断在 500），实得 {len(members)}"
    assert len({t["id"] for t in members}) == 501, "取尽不得重复"


def test_multiple_tasks_same_conversation_grouped(app_env) -> None:
    """一次会话分流出多个任务：全部归到同一会话视图下（协作工作台的分组基石）。"""
    client, _ = app_env
    conv_id = _open_conversation(client)
    ids = []
    for agent_id, inputs in [
        ("fta_agent", {"top_event": "X", "system_description": "S", "components": ["A"]}),
        ("control_logic_agent", {}),
    ]:
        r = client.post(
            "/api/tasks",
            json={"agent_id": agent_id, "inputs": inputs, "created_by": "王工", "conversation_id": conv_id},
        )
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])

    members = client.get(f"/api/conversations/{conv_id}/tasks").json()
    assert set(t["id"] for t in members) == set(ids)
    assert all(t["conversation_id"] == conv_id for t in members)


# ── 异源 Codex 复审回归闸（R2-#3 / R6-#7 / R6-#8）────────────────────────


def test_create_task_on_concluded_conversation_rejected(client: TestClient) -> None:
    """异源 Codex R2-#3：会话 concluded 后 API 真只读——不再接受新成员任务
    （「结束协作」= 真结束）。关闭陈旧创建页 / 直连 API 在归档后挂任务的旁路。"""
    conv_id = _open_conversation(client)
    assert client.post(f"/api/conversations/{conv_id}/conclude").status_code == 200
    resp = client.post(
        "/api/tasks",
        json={
            "agent_id": "fta_agent",
            "inputs": {"top_event": "X", "system_description": "S", "components": ["A"]},
            "created_by": "王工",
            "conversation_id": conv_id,
        },
    )
    assert resp.status_code == 409, resp.text
    assert "concluded" in resp.json()["detail"] or "只读" in resp.json()["detail"]
    # 归档会话零副作用：不得多出成员任务
    assert client.get(f"/api/conversations/{conv_id}/tasks").json() == []


def test_create_task_rejects_contract_violating_fields(client: TestClient) -> None:
    """异源 Codex R6-#7：请求校验必须与 task.schema 对齐——空/纯空白 name、空 created_by、
    重复 input_file_ids 一律 422，绝不落库产出违契约（minLength/uniqueItems）的响应。"""
    base = {
        "agent_id": "fta_agent",
        "inputs": {"top_event": "X", "system_description": "S", "components": ["A"]},
    }
    assert client.post("/api/tasks", json={**base, "name": "  ", "created_by": "王工"}).status_code == 422
    assert client.post("/api/tasks", json={**base, "created_by": "  "}).status_code == 422
    assert client.post("/api/tasks", json={**base, "created_by": "王工", "input_file_ids": ["d", "d"]}).status_code == 422
    # 对照：合法输入 200（证明只咬违约输入，不误伤正常创建）
    ok = client.post("/api/tasks", json={**base, "name": "正常名", "created_by": "王工"})
    assert ok.status_code == 200, ok.text


def test_agentless_event_omits_agent_id_not_null(app_env) -> None:
    """异源 Codex R6-#8：无 Agent 上下文的系统事件以 NULL 存 agent_id；读出口必须
    **省略** agent_id（而非还原成 null）——event.schema 的 agent_id 只许 string 或省略，
    不许 null。把该读路径钉成契约回归闸。"""
    from jsonschema import validate as _validate

    client, app = app_env
    resp = client.post(
        "/api/tasks",
        json={
            "agent_id": "fta_agent",
            "inputs": {"top_event": "X", "system_description": "S", "components": ["A"]},
            "created_by": "王工",
        },
    )
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["id"]
    # 直接写一条**不带 agent_id** 的系统事件（模拟 Job Runner 兜底 task_failed）
    conn = app.state.conn_factory()
    try:
        repos.append_event(
            conn, task_id=task_id, event_type="task_failed", level="error",
            message="兜底：无 agent 上下文的系统事件",
        )
    finally:
        conn.close()
    event_schema = json.loads((REPO_ROOT / "contracts" / "event.schema.json").read_text(encoding="utf-8"))
    events = client.get(f"/api/tasks/{task_id}/events").json()
    agentless = [e for e in events if e.get("message", "").startswith("兜底")]
    assert agentless, "应有那条兜底事件"
    for e in agentless:
        assert "agent_id" not in e, "无 Agent 上下文事件必须省略 agent_id，不得为 null"
    for e in events:
        _validate(e, event_schema)  # 整列表都过契约（含那条兜底）


def test_create_task_concluded_race_is_atomic(app_env, tmp_path) -> None:
    """异源 Codex R1 复审 #3：会话归属创建的『复查 active + INSERT』必须**原子**。确定性
    竞态（仿迁移竞态测）：victim 的 create 连接挂 SQL trace，走到 `INSERT INTO tasks` 时
    放行 rival 并等待；rival（模拟并发 conclude）用短 timeout 直连抢 BEGIN IMMEDIATE 归档。

    修好（BEGIN IMMEDIATE 锁内复查 + INSERT）：victim 此刻持写锁 → rival 被锁拒（1s 快速
    失败）→ 会话仍 active、任务落 active 会话，不变量守住。未修（锁外 check-then-insert）：
    rival 抢先归档 → victim 仍 INSERT → 任务被挂进**已归档**会话（不变量破）。两种实现均
    确定性终止；仅未修变红 = tamper 必咬点。"""
    import sqlite3
    import threading

    client, app = app_env
    conv_id = _open_conversation(client)
    db_path = tmp_path / "flai_os.db"

    about_to_insert = threading.Event()
    rival_done = threading.Event()
    real_factory = app.state.conn_factory
    fired = {"n": 0}

    def traced_factory():
        conn = real_factory()

        def trace(stmt: str) -> None:
            if "INSERT INTO tasks" in stmt and fired["n"] == 0:
                fired["n"] += 1
                about_to_insert.set()
                rival_done.wait(timeout=10)

        conn.set_trace_callback(trace)
        return conn

    app.state.conn_factory = traced_factory
    resp_box: dict[str, Any] = {}

    def victim() -> None:
        try:
            resp_box["resp"] = client.post(
                "/api/tasks",
                json={
                    "agent_id": "fta_agent",
                    "inputs": {"top_event": "X", "system_description": "S", "components": ["A"]},
                    "created_by": "王工",
                    "conversation_id": conv_id,
                },
            )
        finally:
            app.state.conn_factory = real_factory

    t = threading.Thread(target=victim)
    t.start()
    assert about_to_insert.wait(timeout=10), "victim 未走到 INSERT——测试前提失效"

    # rival：短 timeout 直连抢锁归档。修好时 victim 持写锁 → 这里被拒快速失败；
    # 未修时 victim 无锁 → 这里成功归档。两种结果都放行，裁决交给不变量。
    rival = sqlite3.connect(str(db_path), isolation_level=None, timeout=1.0)
    try:
        rival.execute("BEGIN IMMEDIATE")
        rival.execute("UPDATE conversations SET status='concluded' WHERE id=?", (conv_id,))
        rival.execute("COMMIT")
    except sqlite3.OperationalError:
        pass  # 修好：被 victim 写锁挡住——防御生效
    finally:
        rival.close()
        rival_done.set()

    t.join(timeout=15)
    assert not t.is_alive(), "victim 未终止"

    # 安全不变量：绝不出现「会话已 concluded 且该竞态任务仍落进该会话」。
    conn = real_factory()
    try:
        conv = repos.get_conversation(conn, conv_id)
        members = repos.list_tasks(conn, conversation_id=conv_id)
    finally:
        conn.close()
    resp = resp_box.get("resp")
    assert resp is not None, "victim 请求未完成"
    if conv["status"] == "active":
        # 修好：rival 被写锁拒 → 会话仍 active → victim 正常创建（200）且任务归本会话
        # （正向诊断断言，异源 Codex R2 建议：证明不是靠"两边都没发生"空过）。
        assert resp.status_code == 200, resp.text
        assert [t["id"] for t in members] == [resp.json()["id"]]
    else:
        # 会话已 concluded（仅未修实现会走到）：绝不应再有任务落进已归档会话
        assert members == [], "并发 conclude 抢先后，任务不得落进已归档会话（check-then-insert 非原子 = 破）"

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

from typing import Any, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.storage import db as db_mod
from backend.app.storage import repos

REPO_ROOT = Path(__file__).resolve().parents[2]

_LLM_ENV_VARS = ("FLAI_LLM_BASE_URL", "FLAI_LLM_API_KEY", "FLAI_LLM_MODEL_REASONING", "FLAI_LLM_MODEL_FAST")


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    for var in _LLM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def app_env(tmp_path):
    app = create_app(
        agents_dir=REPO_ROOT / "agents",
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        db_path=tmp_path / "flai_os.db",
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app) as client:
        yield client, app


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

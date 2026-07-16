"""迁移 #12 tasks.retry_of（评审 N4b「复制为新任务」血缘注记）测试。

钥匙对（正反都测，oracle 对称性）：
1. 不带 retry_of 创建 → 投影 retry_of=null 且过 task.schema.json（额外列不破契约）；
2. 带合法 retry_of → 持久化 + 投影回读 + 过契约；
3. retry_of 指向不存在任务 → 404 且**零任务落库**（先查后建，不留半截血缘）；
4. 空白/超长 → 422（与 conversation_id 同口径的入参卫生）。
"""

from __future__ import annotations

import json

import jsonschema
from conftest import REPO_ROOT

from backend.app.storage.db import get_conn

_TASK_SCHEMA = json.loads(
    (REPO_ROOT / "contracts" / "task.schema.json").read_text(encoding="utf-8")
)


def _create_hello(client, **extra):
    payload = {"agent_id": "hello_agent", "inputs": {"name": "回归测试"}}
    payload.update(extra)
    return client.post("/api/tasks", json=payload)


def _task_count(app) -> int:
    conn = get_conn(app.state.db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()


def test_retry_of_absent_defaults_null_and_schema_valid(app_env) -> None:
    client, _app = app_env
    resp = _create_hello(client)
    assert resp.status_code == 200, resp.text
    task = client.get(f"/api/tasks/{resp.json()['id']}").json()
    assert task["retry_of"] is None
    jsonschema.validate(task, _TASK_SCHEMA)  # additionalProperties=false 的契约门


def test_retry_of_valid_persists_and_projects(app_env) -> None:
    client, _app = app_env
    origin_id = _create_hello(client).json()["id"]
    resp = _create_hello(client, retry_of=origin_id)
    assert resp.status_code == 200, resp.text
    task = client.get(f"/api/tasks/{resp.json()['id']}").json()
    assert task["retry_of"] == origin_id
    jsonschema.validate(task, _TASK_SCHEMA)
    # 血缘是注记不是行为：新任务自身状态机不受影响，仍是全新 queued 任务。
    assert task["status"] == "queued"
    assert task["id"] != origin_id


def test_retry_of_nonexistent_404_and_no_task_created(app_env) -> None:
    client, app = app_env
    before = _task_count(app)
    resp = _create_hello(client, retry_of="t_ghost_never_exists")
    assert resp.status_code == 404, resp.text
    assert "t_ghost_never_exists" in resp.json()["detail"]
    # 先查后建：404 时绝不留下半截任务（否则悬空血缘会污染后续审计口径）。
    assert _task_count(app) == before


def test_retry_of_blank_rejected_422(app_env) -> None:
    client, _app = app_env
    resp = _create_hello(client, retry_of="   ")
    assert resp.status_code == 422, resp.text


def test_retry_of_overlong_rejected_422(app_env) -> None:
    client, _app = app_env
    resp = _create_hello(client, retry_of="x" * 65)
    assert resp.status_code == 422, resp.text

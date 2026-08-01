"""迁移 #12 tasks.retry_of（评审 N4b「复制为新任务」血缘注记）测试。

钥匙对（正反都测，oracle 对称性）：
1. 不带 retry_of 创建 → 投影 retry_of=null 且过 task.schema.json（额外列不破契约）；
2. 带合法 retry_of（来源状态严格为 failed）→ 持久化 + 投影回读 + 过契约；
3. retry_of 指向不存在任务 → 404 且**零任务落库**（先查后建，不留半截血缘）；
4. retry_of 指向 queued 等非失败任务 → 422 且**零任务落库**；
5. 空白/超长 → 422（与 conversation_id 同口径的入参卫生）。
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


def _mark_task_failed(app, task_id: str) -> None:
    """测试准备：直接把既有任务置为失败，隔离 retry_of 的准入语义。"""
    conn = get_conn(app.state.db_path)
    try:
        updated = conn.execute(
            "UPDATE tasks SET status = 'failed' WHERE id = ?",
            (task_id,),
        ).rowcount
        conn.commit()
        assert updated == 1
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
    client, app = app_env
    origin_id = _create_hello(client).json()["id"]
    _mark_task_failed(app, origin_id)
    resp = _create_hello(client, retry_of=origin_id)
    assert resp.status_code == 200, resp.text
    task = client.get(f"/api/tasks/{resp.json()['id']}").json()
    assert task["retry_of"] == origin_id
    jsonschema.validate(task, _TASK_SCHEMA)
    # 血缘是注记不是行为：新任务自身状态机不受影响，仍是全新 queued 任务。
    assert task["status"] == "queued"
    assert task["id"] != origin_id


def test_retry_of_queued_origin_rejected_422_and_no_task_created(app_env) -> None:
    client, app = app_env
    origin_id = _create_hello(client).json()["id"]
    before = _task_count(app)

    resp = _create_hello(client, retry_of=origin_id)

    assert resp.status_code == 422, resp.text
    assert "只能指向失败任务" in resp.json()["detail"]
    assert origin_id in resp.json()["detail"]
    assert _task_count(app) == before


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


def test_retry_of_schema_rejects_empty_string() -> None:
    """Codex 治理审 R0 P3：schema minLength:1 消除 parity 漂移——
    API 422 拒空串，schema 的 retry_of 子契约也必须拒空串、放行 null 与非空串。
    隔离校验子契约，避免整对象缺 required 字段导致「因错误原因通过」。"""
    import jsonschema
    import pytest

    subschema = _TASK_SCHEMA["properties"]["retry_of"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate("", subschema)  # 空串必拒
    jsonschema.validate(None, subschema)  # null 放行（非重跑任务）
    jsonschema.validate("t_origin_123", subschema)  # 合法非空串放行

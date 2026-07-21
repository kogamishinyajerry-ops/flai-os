"""Agent permissions 的认证角色轴：手动执行与人签不得绕过 safe-auto 门。"""

from __future__ import annotations

import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from backend.app.api import tasks as tasks_api
from backend.app.auth import service as auth_service
from backend.app.auth.authorization import agent_is_callable, role_can_access_agent
from backend.app.governance import eval_runner
from backend.app.storage import repos


def _create_and_login_business_user(client, app) -> None:
    conn = app.state.conn_factory()
    try:
        auth_service.create_user(
            conn,
            username="business_operator",
            display_name="业务操作员",
            password="business-password-123",
            role="business_user",
        )
    finally:
        conn.close()
    response = client.post(
        "/api/auth/login",
        json={"username": "business_operator", "password": "business-password-123"},
    )
    assert response.status_code == 200, response.text


def test_business_user_cannot_manually_execute_admin_only_agent(app_env) -> None:
    client, app = app_env
    _create_and_login_business_user(client, app)

    response = client.post(
        "/api/tasks",
        json={
            "agent_id": "control_logic_agent",
            "inputs": {
                "system_name": "越权探针",
                "states": ["OFF"],
                "transitions": [],
            },
        },
    )

    assert response.status_code == 403, response.text
    conn = app.state.conn_factory()
    try:
        assert repos.list_tasks(conn) == []
    finally:
        conn.close()


@pytest.mark.parametrize("task_status", ["created", "queued"])
def test_business_user_cannot_cancel_admin_only_agent_task(
    app_env, task_status: str
) -> None:
    client, app = app_env
    depends_on: list[str] = []
    if task_status == "created":
        blocker = client.post(
            "/api/tasks",
            json={"agent_id": "hello_agent", "inputs": {"name": "阻塞任务"}},
        )
        assert blocker.status_code == 200, blocker.text
        depends_on = [blocker.json()["id"]]

    created = client.post(
        "/api/tasks",
        json={
            "agent_id": "control_logic_agent",
            "inputs": {
                "system_name": "取消授权探针",
                "states": ["OFF"],
                "transitions": [],
            },
            "depends_on": depends_on,
        },
    )
    assert created.status_code == 200, created.text
    task_id = created.json()["id"]
    assert created.json()["status"] == task_status
    _create_and_login_business_user(client, app)

    response = client.post(f"/api/tasks/{task_id}/cancel")

    assert response.status_code == 403, response.text
    conn = app.state.conn_factory()
    try:
        task = repos.get_task(conn, task_id)
        assert task is not None and task["status"] == task_status
        event_types = {event["event_type"] for event in repos.list_events(conn, task_id)}
        assert "task_cancelled" not in event_types
    finally:
        conn.close()


def test_cancel_holds_registry_snapshot_until_transaction_commit(
    app_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, app = app_env
    created = client.post(
        "/api/tasks",
        json={"agent_id": "hello_agent", "inputs": {"name": "取消锁探针"}},
    )
    assert created.status_code == 200, created.text
    task_id = created.json()["id"]

    live = app.state.agent_registry
    shadow = type(live)(live.agents_dir, live.schema_path)
    shadow.scan()
    revoked = copy.deepcopy(shadow.get("hello_agent"))
    assert revoked is not None
    revoked["status"] = "disabled"
    shadow._agents["hello_agent"] = revoked

    cancel_event_inserted = threading.Event()
    commit_entered = threading.Event()
    release_commit = threading.Event()
    commit_wait_timed_out = threading.Event()
    adopt_started = threading.Event()
    adopt_finished = threading.Event()
    real_append_event = repos.append_event
    real_conn_factory = app.state.conn_factory

    def signal_cancel_event(*args: Any, **kwargs: Any):
        event = real_append_event(*args, **kwargs)
        if kwargs.get("event_type") == "task_cancelled":
            cancel_event_inserted.set()
        return event

    def traced_conn_factory():
        conn = real_conn_factory()

        def trace(statement: str) -> None:
            if statement.strip().upper() == "COMMIT" and cancel_event_inserted.is_set():
                commit_entered.set()
                if not release_commit.wait(5):
                    commit_wait_timed_out.set()

        conn.set_trace_callback(trace)
        return conn

    def publish_revocation() -> None:
        adopt_started.set()
        live.adopt(shadow)
        adopt_finished.set()

    monkeypatch.setattr(repos, "append_event", signal_cancel_event)
    monkeypatch.setattr(app.state, "conn_factory", traced_conn_factory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        cancel_future = pool.submit(client.post, f"/api/tasks/{task_id}/cancel")
        assert cancel_event_inserted.wait(5)
        assert commit_entered.wait(5)
        assert not cancel_future.done()
        adopt_future = pool.submit(publish_revocation)
        assert adopt_started.wait(1)
        assert not adopt_finished.wait(0.1), "adopt 不得越过取消事务的 COMMIT 线性化点"
        release_commit.set()
        response = cancel_future.result(timeout=5)
        adopt_future.result(timeout=5)

    assert not commit_wait_timed_out.is_set()
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert adopt_finished.is_set()


def test_business_user_cannot_discover_or_open_draft_guide(app_env) -> None:
    client, app = app_env
    _create_and_login_business_user(client, app)

    listed = client.get("/api/agents")
    assert listed.status_code == 200, listed.text
    assert "guide_agent" not in {agent["id"] for agent in listed.json()}

    detail = client.get("/api/agents/guide_agent")
    assert detail.status_code == 403, detail.text

    created = client.post("/api/conversations", json={"agent_id": "guide_agent"})
    assert created.status_code == 403, created.text
    conn = app.state.conn_factory()
    try:
        assert repos.list_conversations(conn, created_by="business_operator") == []
    finally:
        conn.close()


def test_direct_task_reloads_manifest_at_admission(app_env, monkeypatch) -> None:
    """事务取锁后采用的新 manifest 若收紧权限，旧对象不得继续授权。"""
    client, app = app_env
    registry = app.state.agent_registry
    original_agent = registry.get("control_logic_agent")
    original_match = tasks_api.current_actor_matches

    def _replace_manifest_then_match(*args, **kwargs):
        replacement = copy.deepcopy(original_agent)
        replacement["permissions"] = {"visibility": "all", "allowed_roles": []}
        registry._agents["control_logic_agent"] = replacement
        return original_match(*args, **kwargs)

    monkeypatch.setattr(tasks_api, "current_actor_matches", _replace_manifest_then_match)
    try:
        response = client.post(
            "/api/tasks",
            json={
                "agent_id": "control_logic_agent",
                "inputs": {
                    "system_name": "权限切换探针",
                    "states": ["OFF"],
                    "transitions": [],
                },
            },
        )
        assert response.status_code == 403, response.text
        conn = app.state.conn_factory()
        try:
            assert repos.list_tasks(conn) == []
        finally:
            conn.close()
    finally:
        registry._agents["control_logic_agent"] = original_agent


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_business_user_cannot_review_admin_only_agent_task(app_env, action: str) -> None:
    client, app = app_env
    created = client.post(
        "/api/tasks",
        json={
            "agent_id": "fta_agent",
            "inputs": {
                "top_event": "供电完全丧失",
                "system_description": "双通道供电系统",
                "components": ["发电机A", "发电机B"],
            },
        },
    )
    assert created.status_code == 200, created.text
    task_id = created.json()["id"]
    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE tasks SET status = 'waiting_review' WHERE id = ?",
            (task_id,),
        )
    finally:
        conn.close()
    _create_and_login_business_user(client, app)

    response = client.post(
        f"/api/tasks/{task_id}/review",
        json={"action": action, "comment": "越权签发探针"},
    )

    assert response.status_code == 403, response.text
    conn = app.state.conn_factory()
    try:
        task = repos.get_task(conn, task_id)
        assert task is not None and task["status"] == "waiting_review"
        event_types = {event["event_type"] for event in repos.list_events(conn, task_id)}
        assert "review_approved" not in event_types
        assert "review_rejected" not in event_types
    finally:
        conn.close()


def test_business_user_cannot_trigger_admin_only_agent_eval(app_env) -> None:
    client, app = app_env
    _create_and_login_business_user(client, app)

    response = client.post("/api/agents/control_logic_agent/eval-runs", json={})

    assert response.status_code == 403, response.text
    conn = app.state.conn_factory()
    try:
        assert repos.list_eval_runs(conn, "control_logic_agent") == []
        assert conn.execute("SELECT COUNT(*) FROM eval_snapshots").fetchone()[0] == 0
        assert repos.list_tasks(conn, origin="eval") == []
    finally:
        conn.close()


def test_eval_commit_time_authorization_denial_rolls_back_snapshot(
    app_env, monkeypatch
) -> None:
    """提交点失权时，冻结快照与 eval run 必须一起回滚，不能留孤立证据。"""
    client, app = app_env
    monkeypatch.setattr(eval_runner, "current_actor_matches", lambda *args, **kwargs: None)

    response = client.post("/api/agents/control_logic_agent/eval-runs", json={})

    assert response.status_code == 403, response.text
    conn = app.state.conn_factory()
    try:
        assert repos.list_eval_runs(conn, "control_logic_agent") == []
        assert conn.execute("SELECT COUNT(*) FROM eval_snapshots").fetchone()[0] == 0
    finally:
        conn.close()


def test_eval_reloads_live_manifest_after_snapshot_freeze(app_env, monkeypatch) -> None:
    """冻结期间采用的新 manifest 若撤权，旧快照不得继续入队。"""
    client, app = app_env
    registry = app.state.agent_registry
    original_agent = registry.get("control_logic_agent")
    original_freeze = eval_runner.freeze_eval_snapshot

    def _freeze_then_revoke(*args, **kwargs):
        handle = original_freeze(*args, **kwargs)
        replacement = copy.deepcopy(original_agent)
        replacement["permissions"] = {"visibility": "all", "allowed_roles": []}
        registry._agents["control_logic_agent"] = replacement
        return handle

    monkeypatch.setattr(eval_runner, "freeze_eval_snapshot", _freeze_then_revoke)
    try:
        response = client.post("/api/agents/control_logic_agent/eval-runs", json={})
        assert response.status_code == 403, response.text
        conn = app.state.conn_factory()
        try:
            assert repos.list_eval_runs(conn, "control_logic_agent") == []
            assert conn.execute("SELECT COUNT(*) FROM eval_snapshots").fetchone()[0] == 0
        finally:
            conn.close()
    finally:
        registry._agents["control_logic_agent"] = original_agent


@pytest.mark.parametrize(
    ("permissions", "role", "expected"),
    [
        ({"visibility": "admin_only", "allowed_roles": ["admin"]}, "admin", True),
        (
            {"visibility": "admin_only", "allowed_roles": ["admin", "agent_developer"]},
            "agent_developer",
            False,
        ),
        (
            {
                "visibility": "department_trial",
                "allowed_roles": ["admin", "agent_developer"],
            },
            "agent_developer",
            True,
        ),
        (
            {"visibility": "all", "allowed_roles": ["business_user"]},
            "business_user",
            True,
        ),
        ({"visibility": "all", "allowed_roles": ["admin"]}, "business_user", False),
        ({"visibility": "unknown", "allowed_roles": ["admin"]}, "admin", False),
        ({"visibility": "all", "allowed_roles": ["admin", 7]}, "admin", False),
        ({"visibility": "all", "allowed_roles": ["admin", "bogus"]}, "admin", False),
        ({"visibility": "all", "allowed_roles": ["admin", "admin"]}, "admin", False),
        (
            {"visibility": "all", "allowed_roles": ["admin"], "unexpected": True},
            "admin",
            False,
        ),
        ("malformed", "admin", False),
        ({}, "admin", False),
    ],
)
def test_role_can_access_agent_is_fail_closed(permissions, role: str, expected: bool) -> None:
    assert role_can_access_agent(
        {"status": "released", "permissions": permissions}, role
    ) is expected


@pytest.mark.parametrize(
    ("status", "role", "expected"),
    [
        ("draft", "admin", True),
        ("draft", "agent_developer", True),
        ("draft", "business_user", False),
        ("trial", "business_user", True),
        ("released", "business_user", True),
        ("disabled", "admin", False),
        ("bogus", "admin", False),
        (None, "admin", False),
    ],
)
def test_role_can_access_agent_enforces_lifecycle(status, role: str, expected: bool) -> None:
    agent = {
        "status": status,
        "permissions": {
            "visibility": "all",
            "allowed_roles": ["admin", "agent_developer", "business_user"],
        },
    }
    assert role_can_access_agent(agent, role) is expected


@pytest.mark.parametrize(
    ("status", "mode", "expected"),
    [
        ("draft", "job", True),
        ("trial", "job", True),
        ("released", "interactive", True),
        ("disabled", "job", False),
        ("bogus", "job", False),
        (None, "job", False),
    ],
)
def test_agent_is_callable_allowlists_lifecycle(status, mode: str, expected: bool) -> None:
    agent = {"status": status, "workflow": {"mode": mode}}
    assert agent_is_callable(agent, mode=mode) is expected

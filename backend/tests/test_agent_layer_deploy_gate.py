from __future__ import annotations

import json

from backend.app.storage.execution_binding_schema import (
    EXECUTION_BINDING_SCHEMA_WITNESS_KEYS,
)
from scripts import deploy_selfcheck


def test_health_and_readyz_publish_exact_execution_binding_witnesses(app_env) -> None:
    client, _app = app_env

    health = client.get("/api/health")
    assert health.status_code == 200
    health_agent_layer = health.json()["agent_layer"]
    assert health.json()["agent_layer_axis"] is True
    assert health_agent_layer["contract"] == "flai.agent-layer.v1"
    assert health_agent_layer["runtime_attested"] is False
    assert set(health_agent_layer["schema_witnesses"]) == set(
        EXECUTION_BINDING_SCHEMA_WITNESS_KEYS
    )
    assert all(
        value is True for value in health_agent_layer["schema_witnesses"].values()
    )

    ready = client.get("/api/readyz")
    assert ready.status_code in (200, 503)
    ready_agent_layer = ready.json()["agent_layer"]
    assert ready_agent_layer["runtime_generation"] is True
    assert ready_agent_layer["schema_ready"] is True
    assert ready_agent_layer["schema_witnesses"] == health_agent_layer["schema_witnesses"]


def test_readyz_fails_closed_when_execution_binding_guard_is_missing(app_env) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        conn.execute("DROP TRIGGER trg_tasks_execution_binding_immutable")
    finally:
        conn.close()

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["agent_layer"]["schema_witnesses"]["required_triggers"] is False

    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    assert ready.json()["agent_layer"]["schema_ready"] is False


def test_execution_binding_witness_uses_literal_booleans(app_env) -> None:
    _client, app = app_env
    conn = app.state.conn_factory()
    try:
        from backend.app.storage.execution_binding_schema import (
            execution_binding_schema_witnesses,
        )

        witnesses = execution_binding_schema_witnesses(conn)
    finally:
        conn.close()
    assert set(witnesses) == set(EXECUTION_BINDING_SCHEMA_WITNESS_KEYS)
    assert all(type(value) is bool for value in witnesses.values())
    assert all(value is True for value in witnesses.values())


def test_deploy_selfcheck_covers_local_and_live_agent_layer_witnesses(
    app_env,
    monkeypatch,
) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        local = deploy_selfcheck.check_execution_binding_schema(conn)
    finally:
        conn.close()
    assert local.ok is True

    payload = client.get("/api/health").json()
    monkeypatch.setattr(
        deploy_selfcheck,
        "_http_get",
        lambda _url: (200, json.dumps(payload).encode("utf-8")),
    )
    assert deploy_selfcheck.check_live_agent_layer_generation("http://flai.test").ok is True

    poisoned = json.loads(json.dumps(payload))
    poisoned["agent_layer"]["schema_witnesses"]["required_triggers"] = 1
    monkeypatch.setattr(
        deploy_selfcheck,
        "_http_get",
        lambda _url: (200, json.dumps(poisoned).encode("utf-8")),
    )
    assert deploy_selfcheck.check_live_agent_layer_generation("http://flai.test").ok is False


def test_live_agent_layer_selfcheck_rejects_worker_api_binding_split(
    app_env,
    monkeypatch,
) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        from backend.app import config
        from backend.app.storage import repos

        repos.beat_worker_heartbeat(
            conn,
            generation=config.WORKER_GENERATION,
            execution_bindings={
                ("native_python", "native.workflow.v1"),
                ("jerryagent_sidecar", "flai.agent-layer.v1"),
            },
        )
    finally:
        conn.close()

    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    monkeypatch.setattr(
        deploy_selfcheck,
        "_http_get",
        lambda _url: (ready.status_code, ready.content),
    )

    result = deploy_selfcheck.check_live_agent_layer_readiness(
        "http://flai.test"
    )
    assert result.ok is False
    assert "binding" in result.detail

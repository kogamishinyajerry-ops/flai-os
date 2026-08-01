"""API 响应 <-> contracts/*.schema.json 常驻咬合测试（P1-2/P1-3 契约对账）。

这是防未来漂移的常驻 gate：走真实 FastAPI TestClient 打 POST /api/tasks、
GET /api/tasks/{id}、GET /api/tasks/{id}/events，把响应体逐条
jsonschema.validate 对 contracts/task.schema.json 与 contracts/event.schema.json。
两份契约都是 additionalProperties=false，任何一方（API 序列化字段 / schema
声明）单方面漂移——多一个字段、少一个必填字段——都会被本测试咬住，而不是
等到前端联调才发现契约说谎。

反方审查发现的两处具体漂移，本测试即回归钉子：
1. task 对象带 `inputs` 键，但 task.schema.json 未声明该属性
   （additionalProperties=false 下会校验失败）——已在 contracts/task.schema.json
   补充 `inputs` 属性。
2. event 对象把 sqlite 自增主键 `id` 也带出来了，但 event.schema.json 只认
   `event_id` 为对外唯一键——已在 repos._decode_event 里 `d.pop("id", None)`。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient
from jsonschema import validate

from backend.app.jobs.runner import JobRunner
from backend.app.storage import repos

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"


def _load_schema(name: str) -> dict[str, Any]:
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))


TASK_SCHEMA = _load_schema("task.schema.json")
EVENT_SCHEMA = _load_schema("event.schema.json")
AGENT_SHELL_SCHEMA = _load_schema("agent_shell.schema.json")
ASSET_DRAFT_BUNDLE_SCHEMA = _load_schema("asset_draft_bundle.schema.json")


@pytest.fixture()
def client(app_env) -> Iterator[TestClient]:
    c, _ = app_env
    yield c


def test_create_task_response_matches_task_schema(client: TestClient) -> None:
    resp = client.post(
        "/api/tasks",
        json={"agent_id": "hello_agent", "inputs": {"name": "契约对账"}},
    )
    assert resp.status_code == 200
    validate(resp.json(), TASK_SCHEMA)


def test_agent_shell_response_matches_catalog_schema(client: TestClient) -> None:
    resp = client.get("/api/agent-shell")
    assert resp.status_code == 200
    validate(resp.json(), AGENT_SHELL_SCHEMA)


def test_asset_draft_preview_response_matches_bundle_schema(
    client: TestClient, app_env
) -> None:
    _, app = app_env
    conversation_id = "conv_asset_parity"
    conn = app.state.conn_factory()
    try:
        repos.create_conversation(
            conn,
            conversation_id=conversation_id,
            agent_id="guide_agent",
            created_by="测试工程师",
        )
        repos.append_message(
            conn,
            conversation_id=conversation_id,
            role="user",
            content="把入口边界核对方法沉淀为资产",
        )
    finally:
        conn.close()

    response = client.post(
        f"/api/conversations/{conversation_id}/asset-draft-preview",
        json={
            "schema_version": "asset_draft_preview_request.v1",
            "generalization": {
                "title": "入口边界复核",
                "trigger": "收到待计算的稳态算例",
                "desired_outcome": "形成可签认的复核清单",
                "inputs": ["边界条件表"],
                "outputs": ["复核清单"],
                "steps": ["核对输入", "标出缺口"],
                "evidence_requirements": ["保留原始位置"],
                "human_decision_points": ["冲突值由工程师确认"],
                "limitations": ["不适用于瞬态工况"],
            },
        },
    )

    assert response.status_code == 200
    validate(response.json(), ASSET_DRAFT_BUNDLE_SCHEMA)


def test_get_task_response_matches_task_schema(client: TestClient) -> None:
    create_resp = client.post(
        "/api/tasks",
        json={"agent_id": "hello_agent", "inputs": {"name": "契约对账2"}},
    )
    task_id = create_resp.json()["id"]

    resp = client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    validate(resp.json(), TASK_SCHEMA)


def test_list_tasks_each_response_matches_task_schema(client: TestClient) -> None:
    for suffix in ("列表一", "列表二"):
        create_resp = client.post(
            "/api/tasks",
            json={
                "agent_id": "hello_agent",
                "inputs": {"name": f"契约对账{suffix}"},
            },
        )
        assert create_resp.status_code == 200

    resp = client.get("/api/tasks")
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) >= 2
    for task in tasks:
        validate(task, TASK_SCHEMA)


@pytest.mark.parametrize(
    "action, expected_status",
    [("approve", "completed"), ("reject", "failed")],
)
def test_review_response_matches_task_schema(
    client: TestClient,
    app_env,
    action: str,
    expected_status: str,
) -> None:
    _, app = app_env
    create_resp = client.post(
        "/api/tasks",
        json={
            "agent_id": "hello_agent",
            "inputs": {"name": f"契约对账 review {action}"},
        },
    )
    assert create_resp.status_code == 200
    task_id = create_resp.json()["id"]

    conn = app.state.conn_factory()
    try:
        for status in ("validating", "running", "waiting_review"):
            repos.set_task_status(conn, task_id, status)
    finally:
        conn.close()

    resp = client.post(
        f"/api/tasks/{task_id}/review",
        json={"action": action, "comment": "响应体对账"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == expected_status
    validate(body, TASK_SCHEMA)


def test_completed_task_response_matches_task_schema(client: TestClient, app_env) -> None:
    """跑完整生命周期到 completed，覆盖 started_at/finished_at/output_file_ids 均非空的分支。"""
    _, app = app_env
    create_resp = client.post(
        "/api/tasks",
        json={"agent_id": "hello_agent", "inputs": {"name": "契约对账3"}},
    )
    task_id = create_resp.json()["id"]

    runner = JobRunner(app.state.runtime, app.state.conn_factory)
    assert runner.run_once() is True

    resp = client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    validate(body, TASK_SCHEMA)


def test_task_events_response_matches_event_schema_across_full_lifecycle(client: TestClient, app_env) -> None:
    """跑到 completed 覆盖尽量多的 event_type（task_created/validation_started/
    tool_started/tool_finished/agent_log/task_completed），逐条校验对 event.schema.json。
    """
    _, app = app_env
    create_resp = client.post(
        "/api/tasks",
        json={"agent_id": "hello_agent", "inputs": {"name": "契约对账4"}},
    )
    task_id = create_resp.json()["id"]

    runner = JobRunner(app.state.runtime, app.state.conn_factory)
    assert runner.run_once() is True

    events_resp = client.get(f"/api/tasks/{task_id}/events")
    assert events_resp.status_code == 200
    events = events_resp.json()
    assert len(events) >= 5, "覆盖面太窄，未能跑出足够的事件类型用于契约抽检"

    event_types = {e["event_type"] for e in events}
    assert {"task_created", "validation_started", "tool_started", "tool_finished", "task_completed"} <= event_types

    for event in events:
        validate(event, EVENT_SCHEMA)
        assert "id" not in event, "事件对外响应不得泄漏 sqlite 自增主键 id，唯一键=event_id"

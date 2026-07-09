"""Feedback API 测试（任务书 §7.8，M2）。

覆盖：提交→feedback 落库+feedback_received 事件（逐条过 event.schema.json）/
task 不存在 404（POST 与 GET 双向）/created_by 空白 422/rating·category 非法
枚举 422/响应形状钉死（feedback 无对外契约 schema，形状由本测试常驻锁定）/
agent_id·agent_version 服务端自填不信客户端/GET 列表升序/E2E 完成任务反馈往返。
DB/uploads/task_runs 全落 tmp_path，绝不碰真实 data/。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from jsonschema import validate

from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app
from backend.app.storage import repos

REPO_ROOT = Path(__file__).resolve().parents[2]

EVENT_SCHEMA = json.loads(
    (REPO_ROOT / "contracts" / "event.schema.json").read_text(encoding="utf-8")
)

# 响应形状钉子：feedback 无对外契约 schema，形状由这组键常驻锁定——
# 增删响应字段必须先改这里（等于改契约），不许静默漂移。
EXPECTED_FEEDBACK_KEYS = {
    "id", "task_id", "agent_id", "agent_version",
    "rating", "category", "message", "created_by", "created_at",
}


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


def _create_task(client: TestClient) -> str:
    resp = client.post(
        "/api/tasks",
        json={"agent_id": "hello_agent", "inputs": {"name": "反馈用"}, "created_by": "fb_test"},
    )
    assert resp.status_code == 200
    return resp.json()["id"]


# ── 提交成功：落库 + 事件 + 响应形状 ─────────────────────────────────────


def test_create_feedback_persists_row_and_emits_schema_valid_event(client: TestClient, app_env) -> None:
    _, app = app_env
    task_id = _create_task(client)

    resp = client.post(
        "/api/feedback",
        json={
            "task_id": task_id,
            "rating": "good",
            "category": "suggestion",
            "message": "结果可用，建议输出加上单位",
            "created_by": "王工",
        },
    )
    assert resp.status_code == 200
    record = resp.json()

    # 响应形状钉死
    assert set(record.keys()) == EXPECTED_FEEDBACK_KEYS
    assert record["task_id"] == task_id
    assert record["rating"] == "good"
    assert record["category"] == "suggestion"
    assert record["message"] == "结果可用，建议输出加上单位"
    assert record["created_by"] == "王工"
    assert isinstance(record["id"], int)
    assert record["created_at"]

    # agent_id/agent_version 服务端自填（来源=task 记录）
    assert record["agent_id"] == "hello_agent"
    assert record["agent_version"] == "0.1.0"

    # 落库回读一致
    conn = app.state.conn_factory()
    try:
        rows = repos.list_feedback(conn, task_id)
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0] == record

    # feedback_received 事件存在且过 event.schema.json 校验（无事件=没发生）
    events = client.get(f"/api/tasks/{task_id}/events").json()
    fb_events = [e for e in events if e["event_type"] == "feedback_received"]
    assert len(fb_events) == 1
    validate(fb_events[0], EVENT_SCHEMA)
    assert fb_events[0]["level"] == "info"
    payload = fb_events[0]["payload"]
    assert payload["rating"] == "good"
    assert payload["category"] == "suggestion"
    assert payload["created_by"] == "王工"
    assert payload["message_summary"] == "结果可用，建议输出加上单位"


def test_feedback_event_message_summary_truncated_to_200(client: TestClient) -> None:
    task_id = _create_task(client)
    long_message = "长" * 500

    resp = client.post(
        "/api/feedback",
        json={
            "task_id": task_id,
            "rating": "bad",
            "category": "result_incomplete",
            "message": long_message,
            "created_by": "李工",
        },
    )
    assert resp.status_code == 200
    # 落库的 message 保留全文；事件 payload 只存 ≤200 摘要
    assert resp.json()["message"] == long_message

    events = client.get(f"/api/tasks/{task_id}/events").json()
    fb = [e for e in events if e["event_type"] == "feedback_received"][0]
    assert len(fb["payload"]["message_summary"]) == 200
    assert fb["payload"]["message_summary"] == long_message[:200]


def test_feedback_without_message_is_allowed(client: TestClient) -> None:
    task_id = _create_task(client)
    resp = client.post(
        "/api/feedback",
        json={"task_id": task_id, "rating": "good", "category": "other", "created_by": "赵工"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] is None

    events = client.get(f"/api/tasks/{task_id}/events").json()
    fb = [e for e in events if e["event_type"] == "feedback_received"][0]
    validate(fb, EVENT_SCHEMA)
    assert fb["payload"]["message_summary"] is None


def test_client_supplied_agent_fields_are_ignored(client: TestClient) -> None:
    """客户端多传 agent_id/agent_version 也不采信——服务端一律以 task 记录为准。"""
    task_id = _create_task(client)
    resp = client.post(
        "/api/feedback",
        json={
            "task_id": task_id,
            "rating": "good",
            "category": "usability",
            "created_by": "钱工",
            "agent_id": "forged_agent",
            "agent_version": "9.9.9",
        },
    )
    assert resp.status_code == 200
    record = resp.json()
    assert record["agent_id"] == "hello_agent"
    assert record["agent_version"] == "0.1.0"


# ── 失败路径：404 / 422 ──────────────────────────────────────────────────


def test_create_feedback_unknown_task_404_and_no_residue(client: TestClient, app_env) -> None:
    _, app = app_env
    resp = client.post(
        "/api/feedback",
        json={"task_id": "no_such_task", "rating": "good", "category": "other", "created_by": "王工"},
    )
    assert resp.status_code == 404

    # 404 拒绝后不得留下任何 feedback 行（fail-closed 无半成品）
    conn = app.state.conn_factory()
    try:
        assert repos.list_feedback(conn, "no_such_task") == []
    finally:
        conn.close()


def test_list_feedback_unknown_task_404(client: TestClient) -> None:
    resp = client.get("/api/tasks/no_such_task/feedback")
    assert resp.status_code == 404


@pytest.mark.parametrize("bad_created_by", ["", "   ", "\t\n"])
def test_create_feedback_blank_created_by_422(client: TestClient, bad_created_by: str) -> None:
    task_id = _create_task(client)
    resp = client.post(
        "/api/feedback",
        json={"task_id": task_id, "rating": "good", "category": "other", "created_by": bad_created_by},
    )
    assert resp.status_code == 422


def test_create_feedback_missing_created_by_422(client: TestClient) -> None:
    task_id = _create_task(client)
    resp = client.post(
        "/api/feedback",
        json={"task_id": task_id, "rating": "good", "category": "other"},
    )
    assert resp.status_code == 422


def test_create_feedback_invalid_rating_422(client: TestClient) -> None:
    task_id = _create_task(client)
    resp = client.post(
        "/api/feedback",
        json={"task_id": task_id, "rating": "excellent", "category": "other", "created_by": "王工"},
    )
    assert resp.status_code == 422


def test_create_feedback_invalid_category_422(client: TestClient) -> None:
    task_id = _create_task(client)
    resp = client.post(
        "/api/feedback",
        json={"task_id": task_id, "rating": "good", "category": "乱写类别", "created_by": "王工"},
    )
    assert resp.status_code == 422


def test_created_by_is_stored_stripped(client: TestClient) -> None:
    """前后空白具名（如 ' 王工 '）合法但统一存 strip 后的名字（与 reviewer 同手法）。"""
    task_id = _create_task(client)
    resp = client.post(
        "/api/feedback",
        json={"task_id": task_id, "rating": "good", "category": "other", "created_by": "  王工  "},
    )
    assert resp.status_code == 200
    assert resp.json()["created_by"] == "王工"


# ── GET 列表升序 ─────────────────────────────────────────────────────────


def test_list_feedback_returns_ascending_by_created_at(client: TestClient) -> None:
    task_id = _create_task(client)
    for i, (rating, category) in enumerate(
        [("bad", "tool_error"), ("good", "suggestion"), ("good", "other")]
    ):
        resp = client.post(
            "/api/feedback",
            json={
                "task_id": task_id,
                "rating": rating,
                "category": category,
                "message": f"第{i}条",
                "created_by": "王工",
            },
        )
        assert resp.status_code == 200

    listed = client.get(f"/api/tasks/{task_id}/feedback").json()
    assert [f["message"] for f in listed] == ["第0条", "第1条", "第2条"]
    created_ats = [f["created_at"] for f in listed]
    assert created_ats == sorted(created_ats), "必须按 created_at 升序返回"


# ── E2E：完成任务 → 反馈 → 读回 ─────────────────────────────────────────


def test_e2e_completed_task_feedback_roundtrip(client: TestClient, app_env) -> None:
    _, app = app_env
    task_id = _create_task(client)

    runner = JobRunner(app.state.runtime, app.state.conn_factory)
    assert runner.run_once() is True
    assert client.get(f"/api/tasks/{task_id}").json()["status"] == "completed"

    resp = client.post(
        "/api/feedback",
        json={
            "task_id": task_id,
            "rating": "good",
            "category": "suggestion",
            "message": "E2E 反馈：结果正确",
            "created_by": "e2e_王工",
        },
    )
    assert resp.status_code == 200

    listed = client.get(f"/api/tasks/{task_id}/feedback").json()
    assert len(listed) == 1
    assert listed[0]["message"] == "E2E 反馈：结果正确"
    assert listed[0]["agent_id"] == "hello_agent"

    # 事件时间轴：完整生命周期事件 + feedback_received 共存
    event_types = [e["event_type"] for e in client.get(f"/api/tasks/{task_id}/events").json()]
    assert "task_completed" in event_types
    assert "feedback_received" in event_types

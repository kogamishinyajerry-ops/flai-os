"""M1 端到端验收钉子测试（任务书 §12.2 七条验收）。

用真实 hello_agent + mock_echo（M0 Golden Sample，非本层新造 fixture）跑通
create_app -> POST /api/tasks -> JobRunner.run_once() -> 完整生命周期，
钉死：健康检查、Agent 列表、任务创建、Job Runner 驱动执行、任务终态、
事件全链路、产物下载、samples/tool_runs 落库。全部路径落 tmp_path，
绝不碰真实 data/（任务书 §13.3 纪律②）。

另加反例：queued 任务被 cancel 后，run_once() 不得执行它（无事件=没发生
的另一面——被取消的任务不应产生任何执行类事件）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app
from backend.app.storage import repos

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def app_env(tmp_path) -> Iterator[tuple[TestClient, object]]:
    db_path = tmp_path / "flai_os.db"
    uploads_dir = tmp_path / "uploads"
    task_runs_dir = tmp_path / "task_runs"
    app = create_app(
        agents_dir=REPO_ROOT / "agents",
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        db_path=db_path,
        uploads_dir=uploads_dir,
        task_runs_dir=task_runs_dir,
    )
    with TestClient(app) as client:
        yield client, app


def test_m1_e2e_full_lifecycle(app_env) -> None:
    client, app = app_env

    # ① health ok
    health_resp = client.get("/api/health")
    assert health_resp.status_code == 200
    health_body = health_resp.json()
    assert health_body["status"] == "ok"
    assert health_body["agents"] >= 1
    assert health_body["tools"] >= 1

    # ② GET /api/agents 见 hello_agent
    agents_resp = client.get("/api/agents")
    assert agents_resp.status_code == 200
    agent_ids = [a["id"] for a in agents_resp.json()]
    assert "hello_agent" in agent_ids

    # ③ POST /api/tasks 建 hello 任务
    create_resp = client.post(
        "/api/tasks",
        json={"agent_id": "hello_agent", "inputs": {"name": "E2E小明"}, "created_by": "e2e_test"},
    )
    assert create_resp.status_code == 200
    task = create_resp.json()
    assert task["status"] == "queued"
    task_id = task["id"]

    # ④ JobRunner.run_once() 执行完成
    runner = JobRunner(app.state.runtime, app.state.conn_factory)
    did_work = runner.run_once()
    assert did_work is True

    # ⑤ GET /api/tasks/{id} = completed 且 events 含全链路
    task_resp = client.get(f"/api/tasks/{task_id}")
    assert task_resp.status_code == 200
    finished_task = task_resp.json()
    assert finished_task["status"] == "completed"

    events_resp = client.get(f"/api/tasks/{task_id}/events")
    assert events_resp.status_code == 200
    event_types = [e["event_type"] for e in events_resp.json()]
    for required_type in (
        "task_created",
        "validation_started",
        "tool_started",
        "tool_finished",
        "task_completed",
    ):
        assert required_type in event_types, f"缺失事件类型：{required_type}（无事件=没发生）"

    # ⑥ 输出文件可 GET download 且内容含问候语
    assert finished_task["output_file_ids"], "hello_agent 产出必须注册进 files"
    file_id = finished_task["output_file_ids"][0]
    download_resp = client.get(f"/api/files/{file_id}/download")
    assert download_resp.status_code == 200
    output_body = json.loads(download_resp.content)
    assert "你好" in output_body["greeting"]
    assert "E2E小明" in output_body["greeting"]

    # ⑦ samples 表一行、tool_runs 表 mock=1 一行
    conn = app.state.conn_factory()
    try:
        samples = repos.list_samples(conn, task_id)
        assert len(samples) == 1
        assert samples[0]["agent_id"] == "hello_agent"

        tool_runs = repos.list_tool_runs(conn, task_id)
        assert len(tool_runs) == 1
        assert tool_runs[0]["mock"] is True
        assert tool_runs[0]["status"] == "success"
    finally:
        conn.close()


def test_cancel_queued_task_then_run_once_does_not_execute_it(app_env) -> None:
    client, app = app_env

    create_resp = client.post(
        "/api/tasks",
        json={"agent_id": "hello_agent", "inputs": {"name": "取消我"}, "created_by": "e2e_test"},
    )
    assert create_resp.status_code == 200
    task_id = create_resp.json()["id"]

    cancel_resp = client.post(f"/api/tasks/{task_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    runner = JobRunner(app.state.runtime, app.state.conn_factory)
    did_work = runner.run_once()
    assert did_work is False, "queued 任务已被取消，run_once 不应再拾取任何任务"

    task_resp = client.get(f"/api/tasks/{task_id}")
    assert task_resp.json()["status"] == "cancelled"

    events = client.get(f"/api/tasks/{task_id}/events").json()
    event_types = [e["event_type"] for e in events]
    assert "task_cancelled" in event_types
    # 被取消的任务绝不应产生任何执行类事件（无事件=没发生的反面同样成立）。
    for forbidden_type in ("validation_started", "tool_started", "task_completed"):
        assert forbidden_type not in event_types

    conn = app.state.conn_factory()
    try:
        assert repos.list_samples(conn, task_id) == []
        assert repos.list_tool_runs(conn, task_id) == []
    finally:
        conn.close()

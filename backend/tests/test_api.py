"""FastAPI 层集成测试：health/agents/tasks/files 全链路，含 JobRunner 驱动真实执行。

Registry 扫描指向仓库真实 agents/、tools_impl/（hello_agent + mock_echo 是
M0 已交付的 Golden Sample，非本层新造 fixture），DB/uploads/task_runs 全部
落 tmp_path，绝不碰真实 data/（任务书 §13.3 纪律②）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def app_env(tmp_path):
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


@pytest.fixture()
def client(app_env) -> Iterator[TestClient]:
    c, _ = app_env
    yield c


# ── health / agents ──────────────────────────────────────────────────────


def test_health(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["agents"] >= 1
    assert body["tools"] >= 1


def test_list_agents_contains_hello_agent(client: TestClient) -> None:
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    ids = [a["id"] for a in resp.json()]
    assert "hello_agent" in ids


def test_get_agent_not_found(client: TestClient) -> None:
    resp = client.get("/api/agents/does_not_exist")
    assert resp.status_code == 404


def test_get_agent_found(client: TestClient) -> None:
    resp = client.get("/api/agents/hello_agent")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "hello_agent"
    assert body["limitations"], "limitations 必须非空（宪法：每个 Agent 声明不做什么）"


# ── tasks: create -> queued + task_created 事件 ──────────────────────────


def test_create_task_for_unknown_agent_404(client: TestClient) -> None:
    resp = client.post("/api/tasks", json={"agent_id": "no_such_agent"})
    assert resp.status_code == 404


def test_create_task_missing_agent_id_422(client: TestClient) -> None:
    """P3-1：CreateTaskRequest.agent_id 是必填字段，缺失必须 422（pydantic 校验拒收），
    而不是 500 或被当成某个默认 agent 静默放行。
    """
    resp = client.post("/api/tasks", json={})
    assert resp.status_code == 422


def test_create_task_success_then_run_once_completes(client: TestClient, app_env) -> None:
    _, app = app_env
    resp = client.post(
        "/api/tasks",
        json={"agent_id": "hello_agent", "inputs": {"name": "小明"}, "created_by": "tester"},
    )
    assert resp.status_code == 200
    task = resp.json()
    assert task["status"] == "queued"
    task_id = task["id"]

    events_resp = client.get(f"/api/tasks/{task_id}/events")
    assert events_resp.status_code == 200
    event_types = [e["event_type"] for e in events_resp.json()]
    assert "task_created" in event_types

    runner = JobRunner(app.state.runtime, app.state.conn_factory)
    did_work = runner.run_once()
    assert did_work is True

    get_resp = client.get(f"/api/tasks/{task_id}")
    assert get_resp.status_code == 200
    finished_task = get_resp.json()
    assert finished_task["status"] == "completed"

    events_after = client.get(f"/api/tasks/{task_id}/events").json()
    types_after = [e["event_type"] for e in events_after]
    assert "task_completed" in types_after
    assert "tool_started" in types_after
    assert "tool_finished" in types_after

    assert finished_task["output_file_ids"], "hello_agent 产出必须注册进 files"
    file_id = finished_task["output_file_ids"][0]
    download_resp = client.get(f"/api/files/{file_id}/download")
    assert download_resp.status_code == 200


# ── tasks: cancel 语义 ────────────────────────────────────────────────────


def test_cancel_queued_task_succeeds(client: TestClient) -> None:
    resp = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "A"}})
    task_id = resp.json()["id"]

    cancel_resp = client.post(f"/api/tasks/{task_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


def test_cancel_completed_task_409(client: TestClient, app_env) -> None:
    _, app = app_env
    resp = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "B"}})
    task_id = resp.json()["id"]

    runner = JobRunner(app.state.runtime, app.state.conn_factory)
    runner.run_once()

    cancel_resp = client.post(f"/api/tasks/{task_id}/cancel")
    assert cancel_resp.status_code == 409


def test_cancel_validating_task_409(client: TestClient, app_env) -> None:
    """P2-5 竞态场景之一：claim_next_queued 把任务从 queued 拾到 validating 后，
    cancel 端点仍应如实拒绝（V0.1 只支持 created/queued 两态取消），不得静默
    放行造成状态机之外的隐式转移。
    """
    from backend.app.storage import repos as repos_mod

    _, app = app_env
    resp = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "D"}})
    task_id = resp.json()["id"]

    conn = app.state.conn_factory()
    try:
        claimed = repos_mod.claim_next_queued(conn)
        assert claimed is not None and claimed["id"] == task_id
        assert claimed["status"] == "validating"
    finally:
        conn.close()

    cancel_resp = client.post(f"/api/tasks/{task_id}/cancel")
    assert cancel_resp.status_code == 409


def test_double_cancel_second_call_409(client: TestClient) -> None:
    resp = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "C"}})
    task_id = resp.json()["id"]

    first = client.post(f"/api/tasks/{task_id}/cancel")
    assert first.status_code == 200
    second = client.post(f"/api/tasks/{task_id}/cancel")
    assert second.status_code == 409


# ── files: upload -> download 往返 ───────────────────────────────────────


def test_upload_then_download_sha256_roundtrip(client: TestClient) -> None:
    content = b"hello flai-os upload roundtrip"
    upload_resp = client.post(
        "/api/files/upload",
        files={"file": ("sample.txt", content, "text/plain")},
    )
    assert upload_resp.status_code == 200
    record = upload_resp.json()
    assert record["filename"] == "sample.txt"
    assert record["size_bytes"] == len(content)

    download_resp = client.get(f"/api/files/{record['id']}/download")
    assert download_resp.status_code == 200
    assert download_resp.content == content


def test_download_unknown_file_404(client: TestClient) -> None:
    resp = client.get("/api/files/does-not-exist/download")
    assert resp.status_code == 404


def test_download_file_record_exists_but_disk_missing_404_not_500(client: TestClient) -> None:
    """P3-3：files 表有记录但磁盘文件被删——必须 404 如实说明，绝不 500。"""
    content = b"this file will be deleted from disk after upload"
    upload_resp = client.post(
        "/api/files/upload",
        files={"file": ("will_vanish.txt", content, "text/plain")},
    )
    assert upload_resp.status_code == 200
    record = upload_resp.json()

    Path(record["path"]).unlink()

    download_resp = client.get(f"/api/files/{record['id']}/download")
    assert download_resp.status_code == 404
    assert "磁盘缺失" in download_resp.json()["detail"]


# ── files: P1-1 路径穿越 ──────────────────────────────────────────────────


def test_upload_path_traversal_filename_is_sanitized(client: TestClient, app_env) -> None:
    """filename="../../evil.txt" 上传：落盘名净化为 evil.txt、库里 filename 无路径
    分隔符、文件必须落在 uploads_dir 内，uploads 外绝不产生任何产物。
    """
    _, app = app_env
    uploads_dir: Path = app.state.uploads_dir
    content = b"path traversal payload"

    upload_resp = client.post(
        "/api/files/upload",
        files={"file": ("../../evil.txt", content, "text/plain")},
    )
    assert upload_resp.status_code == 200
    record = upload_resp.json()

    assert record["filename"] == "evil.txt"
    assert "/" not in record["filename"] and "\\" not in record["filename"]

    dest_path = Path(record["path"])
    assert dest_path.is_file()
    assert dest_path.resolve().is_relative_to(uploads_dir.resolve()), (
        "落盘文件必须仍在 uploads_dir 内，未发生路径穿越"
    )

    # 穿越修复前的真实逃逸目标：dest_dir(=uploads_dir/file_id)/"../../evil.txt"
    # resolve 后落在 uploads_dir 的父目录——这里必须绝无产出。
    escaped_path = uploads_dir.parent / "evil.txt"
    assert not escaped_path.exists()


def test_upload_filename_only_separators_falls_back_to_unnamed(client: TestClient) -> None:
    upload_resp = client.post(
        "/api/files/upload",
        files={"file": ("///", b"x", "text/plain")},
    )
    assert upload_resp.status_code == 200
    assert upload_resp.json()["filename"] == "unnamed"


def test_upload_resolve_guard_bites_when_sanitize_layer_fails(
    client: TestClient, app_env, monkeypatch
) -> None:
    """二层防御独立咬合 witness（loop-auditor 收口审计 gap-1）。

    `_sanitize_filename` 的 `Path.name` 在 POSIX 上已压平一切分隔符，正常路径
    到不了 resolve 校验层——它是纵深防御。本测试模拟一层失效（净化函数被
    monkeypatch 成恒等），穿越 payload 必须被 resolve 层以 400 拦下且
    uploads 外零产物；若删除 files.py 的 resolve 校验块，本测试变红。
    """
    from backend.app.api import files as files_api

    _, app = app_env
    uploads_dir: Path = app.state.uploads_dir
    monkeypatch.setattr(files_api, "_sanitize_filename", lambda raw: raw or "unnamed")

    upload_resp = client.post(
        "/api/files/upload",
        files={"file": ("../../evil_layer2.txt", b"x", "text/plain")},
    )
    assert upload_resp.status_code == 400
    assert "逃出 uploads 目录" in upload_resp.json()["detail"]
    assert not (uploads_dir.parent / "evil_layer2.txt").exists()
    # 校验在 mkdir/写盘之前：uploads 内也不许留下本次的半成品目录
    assert not any(uploads_dir.rglob("evil_layer2.txt"))


# ── files: P2-6 上传限额 ──────────────────────────────────────────────────


def test_upload_exceeding_limit_returns_413_and_leaves_no_residue(
    client: TestClient, app_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FLAI_MAX_UPLOAD_MB", "0")  # 0MB -> 任何非空内容都超限
    _, app = app_env
    uploads_dir: Path = app.state.uploads_dir

    upload_resp = client.post(
        "/api/files/upload",
        files={"file": ("too_big.bin", b"x" * 1024, "application/octet-stream")},
    )
    assert upload_resp.status_code == 413

    # 磁盘无残留：uploads_dir 下不应留下任何文件或空目录。
    leftovers = list(uploads_dir.rglob("*")) if uploads_dir.exists() else []
    assert leftovers == [], f"上传超限后磁盘应无残留，实际残留：{leftovers}"

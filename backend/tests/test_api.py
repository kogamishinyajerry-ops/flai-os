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


# ── tasks: 列表分页（P2-B：拆掉硬 LIMIT 100 静默截断）─────────────────────


def _create_n_tasks(client: TestClient, n: int) -> list[str]:
    ids = []
    for i in range(n):
        resp = client.post(
            "/api/tasks",
            json={"agent_id": "hello_agent", "inputs": {"name": f"分页{i}"}, "name": f"page-{i}"},
        )
        assert resp.status_code == 200
        ids.append(resp.json()["id"])
    return ids


def test_list_tasks_limit_offset_slice(client: TestClient) -> None:
    """5 任务验 limit=2/offset=2 切片：最近任务流（created_at 降序）第二页
    恰是第 3、4 新的两条，且与全量列表的对应切片逐条一致。
    """
    _create_n_tasks(client, 5)

    full = client.get("/api/tasks", params={"limit": 500}).json()
    assert len(full) == 5

    page = client.get("/api/tasks", params={"limit": 2, "offset": 2}).json()
    assert len(page) == 2
    assert [t["id"] for t in page] == [t["id"] for t in full[2:4]]

    # 末页不足一页：offset=4 只剩 1 条（前端「加载更多」按钮消失的判定依据）
    last_page = client.get("/api/tasks", params={"limit": 2, "offset": 4}).json()
    assert len(last_page) == 1
    assert last_page[0]["id"] == full[4]["id"]


def test_list_tasks_pagination_covers_all_without_dup_or_loss(client: TestClient) -> None:
    """翻页不重不漏：limit=2 连续翻 3 页拼起来 == 全量 5 条。"""
    _create_n_tasks(client, 5)
    collected = []
    for offset in (0, 2, 4):
        collected += client.get("/api/tasks", params={"limit": 2, "offset": offset}).json()
    full = client.get("/api/tasks", params={"limit": 500}).json()
    assert [t["id"] for t in collected] == [t["id"] for t in full]


@pytest.mark.parametrize("params", [
    {"limit": 0},        # 下越界
    {"limit": 501},      # 上越界
    {"limit": -1},
    {"offset": -1},
    {"limit": "abc"},    # 非整数
])
def test_list_tasks_out_of_range_pagination_422(client: TestClient, params: dict) -> None:
    resp = client.get("/api/tasks", params=params)
    assert resp.status_code == 422


# ── tasks: 事件时间轴分页（P2）────────────────────────────────────────────


def test_list_events_limit_offset_slice(client: TestClient, app_env) -> None:
    """跑完整生命周期攒出多条事件，验 limit/offset 切片与全量逐条一致（id 升序）。"""
    _, app = app_env
    resp = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "分页事件"}})
    task_id = resp.json()["id"]
    JobRunner(app.state.runtime, app.state.conn_factory).run_once()

    full = client.get(f"/api/tasks/{task_id}/events").json()
    assert len(full) >= 5, "hello_agent 全生命周期应产生 ≥5 条事件"

    page = client.get(f"/api/tasks/{task_id}/events", params={"limit": 2, "offset": 2}).json()
    assert len(page) == 2
    assert [e["event_id"] for e in page] == [e["event_id"] for e in full[2:4]]

    # 翻页拼接 == 全量（不重不漏）
    collected = []
    offset = 0
    while True:
        chunk = client.get(f"/api/tasks/{task_id}/events", params={"limit": 3, "offset": offset}).json()
        collected += chunk
        if len(chunk) < 3:
            break
        offset += 3
    assert [e["event_id"] for e in collected] == [e["event_id"] for e in full]


@pytest.mark.parametrize("params", [
    {"limit": 0},
    {"limit": 5001},
    {"limit": -1},
    {"offset": -1},
    {"limit": "abc"},
])
def test_list_events_out_of_range_pagination_422(client: TestClient, params: dict) -> None:
    resp = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "E"}})
    task_id = resp.json()["id"]
    assert client.get(f"/api/tasks/{task_id}/events", params=params).status_code == 422


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


# ── tasks: P1-B 人工放行 API（waiting_review 的唯一合法出口）──────────────


@pytest.fixture()
def review_app_env(tmp_path):
    """tmp agents 目录：hello_agent 复制为 review_agent（requires_human_review=true），
    工具/契约用真实交付件；DB/uploads/task_runs 全落 tmp_path。
    """
    import shutil

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    review_dir = agents_dir / "review_agent"
    shutil.copytree(REPO_ROOT / "agents" / "hello_agent", review_dir)
    yaml_path = review_dir / "agent.yaml"
    yaml_text = yaml_path.read_text(encoding="utf-8")
    yaml_text = yaml_text.replace("id: hello_agent", "id: review_agent")
    yaml_text = yaml_text.replace("requires_human_review: false", "requires_human_review: true")
    yaml_path.write_text(yaml_text, encoding="utf-8")

    app = create_app(
        agents_dir=agents_dir,
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        db_path=tmp_path / "flai_os.db",
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app) as client:
        yield client, app


def _run_to_waiting_review(client: TestClient, app) -> str:
    resp = client.post(
        "/api/tasks",
        json={"agent_id": "review_agent", "inputs": {"name": "待审"}, "created_by": "e2e_review"},
    )
    assert resp.status_code == 200
    task_id = resp.json()["id"]
    runner = JobRunner(app.state.runtime, app.state.conn_factory)
    assert runner.run_once() is True
    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "waiting_review"
    return task_id


def test_review_approve_e2e_full_chain(review_app_env) -> None:
    """E2E：requires_human_review=true 任务跑到 waiting_review → 人工 approve →
    completed + review_approved 事件（payload 记 reviewer/comment）。
    """
    client, app = review_app_env
    task_id = _run_to_waiting_review(client, app)

    review_resp = client.post(
        f"/api/tasks/{task_id}/review",
        json={"action": "approve", "reviewer": "张工", "comment": "结果核对无误"},
    )
    assert review_resp.status_code == 200
    approved = review_resp.json()
    assert approved["status"] == "completed"
    assert approved["finished_at"] is not None

    events = client.get(f"/api/tasks/{task_id}/events").json()
    event_types = [e["event_type"] for e in events]
    assert "review_requested" in event_types
    approved_events = [e for e in events if e["event_type"] == "review_approved"]
    assert len(approved_events) == 1
    assert approved_events[0]["payload"] == {"reviewer": "张工", "comment": "结果核对无误"}


def test_review_reject_e2e_full_chain(review_app_env) -> None:
    client, app = review_app_env
    task_id = _run_to_waiting_review(client, app)

    review_resp = client.post(
        f"/api/tasks/{task_id}/review",
        json={"action": "reject", "reviewer": "李工", "comment": "输出与图纸不符"},
    )
    assert review_resp.status_code == 200
    rejected = review_resp.json()
    assert rejected["status"] == "failed"
    assert "人工拒绝" in rejected["error_message"]
    assert "输出与图纸不符" in rejected["error_message"]

    events = client.get(f"/api/tasks/{task_id}/events").json()
    rejected_events = [e for e in events if e["event_type"] == "review_rejected"]
    assert len(rejected_events) == 1
    assert rejected_events[0]["payload"]["reviewer"] == "李工"
    assert rejected_events[0]["level"] == "warning"


def test_review_non_waiting_review_task_409(client: TestClient) -> None:
    """任务不在 waiting_review（此处为 queued）→ 409 如实拒绝，不得静默转移。"""
    resp = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "R"}})
    task_id = resp.json()["id"]

    review_resp = client.post(
        f"/api/tasks/{task_id}/review",
        json={"action": "approve", "reviewer": "张工"},
    )
    assert review_resp.status_code == 409


def test_review_unknown_task_404(client: TestClient) -> None:
    resp = client.post(
        "/api/tasks/no_such_task/review",
        json={"action": "approve", "reviewer": "张工"},
    )
    assert resp.status_code == 404


def test_review_missing_or_empty_reviewer_422(review_app_env) -> None:
    """reviewer 缺失或空字符串 → 422（人是唯一签发者，匿名放行=没有签发者）。
    422 被拒后任务必须仍停在 waiting_review，未被部分放行。
    """
    client, app = review_app_env
    task_id = _run_to_waiting_review(client, app)

    missing = client.post(f"/api/tasks/{task_id}/review", json={"action": "approve"})
    assert missing.status_code == 422

    empty = client.post(
        f"/api/tasks/{task_id}/review", json={"action": "approve", "reviewer": ""}
    )
    assert empty.status_code == 422

    bad_action = client.post(
        f"/api/tasks/{task_id}/review", json={"action": "自动放行", "reviewer": "张工"}
    )
    assert bad_action.status_code == 422

    assert client.get(f"/api/tasks/{task_id}").json()["status"] == "waiting_review"


def test_review_whitespace_only_reviewer_422_and_stored_stripped(review_app_env) -> None:
    """R1 复审 P3：全空白 reviewer = 事实匿名签发，必须 422；合法 reviewer
    两端空白 strip 后入事件（审计账面上是具名的干净签名）。
    """
    client, app = review_app_env
    task_id = _run_to_waiting_review(client, app)

    blank = client.post(
        f"/api/tasks/{task_id}/review", json={"action": "approve", "reviewer": "   "}
    )
    assert blank.status_code == 422
    assert client.get(f"/api/tasks/{task_id}").json()["status"] == "waiting_review"

    padded = client.post(
        f"/api/tasks/{task_id}/review", json={"action": "approve", "reviewer": "  王工  "}
    )
    assert padded.status_code == 200
    events = client.get(f"/api/tasks/{task_id}/events").json()
    approved = [e for e in events if e["event_type"] == "review_approved"]
    assert approved[0]["payload"]["reviewer"] == "王工"


def test_review_concurrent_race_returns_409_not_500(review_app_env, monkeypatch) -> None:
    """R1 复审 P2：两个 review 并发命中同一 waiting_review 任务，后到者通过预检
    但被状态机层拒绝（IllegalTransitionError）——必须折叠为 409 与预检同口径，
    绝不 500 逃逸。用注入状态机拒绝精确复现「预检已过、转移被拒」的竞态窗口。
    """
    from backend.app.core.errors import IllegalTransitionError
    from backend.app.storage import repos as repos_mod

    client, app = review_app_env
    task_id = _run_to_waiting_review(client, app)

    def _concurrent_reject(*args, **kwargs):
        raise IllegalTransitionError("非法转移：completed -> completed（已被并发放行）")

    monkeypatch.setattr(repos_mod, "set_task_status", _concurrent_reject)
    resp = client.post(
        f"/api/tasks/{task_id}/review", json={"action": "approve", "reviewer": "张工"}
    )
    assert resp.status_code == 409
    assert "并发" in resp.json()["detail"]

    monkeypatch.undo()
    # 竞态被拒后任务未被本次请求触碰，仍可正常人工放行。
    ok = client.post(
        f"/api/tasks/{task_id}/review", json={"action": "approve", "reviewer": "张工"}
    )
    assert ok.status_code == 200


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

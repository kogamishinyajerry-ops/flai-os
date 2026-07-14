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

from conftest import TEST_DISPLAY_NAME, login, seed_and_login, seed_user

from backend.app import config
from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_parse_since_utc_normalizes_and_rejects():
    import pytest
    from fastapi import HTTPException

    from backend.app.api._since import parse_since_utc

    # Z 后缀归一化为 +00:00（Py3.10 兼容路径）
    assert parse_since_utc("2026-07-01T00:00:00Z") == "2026-07-01T00:00:00+00:00"
    # 任意偏移归一化到 UTC
    assert parse_since_utc("2026-07-01T08:00:00+08:00") == "2026-07-01T00:00:00+00:00"
    # 空 → 422
    with pytest.raises(HTTPException) as e1:
        parse_since_utc(None)
    assert e1.value.status_code == 422
    # naive（无时区）→ 422 fail-closed
    with pytest.raises(HTTPException) as e2:
        parse_since_utc("2026-07-01T00:00:00")
    assert e2.value.status_code == 422
    # 非法 ISO → 422
    with pytest.raises(HTTPException) as e3:
        parse_since_utc("not-a-date")
    assert e3.value.status_code == 422


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


def test_health_llm_configuration_flags_are_booleans(client: TestClient) -> None:
    body = client.get("/api/health").json()
    keys = {"llm_base_url_set", "llm_api_key_set", "llm_model_reasoning_set"}
    assert keys <= body.keys()
    assert all(type(body[key]) is bool for key in keys)


def test_health_exposes_generation_markers_is_true(client: TestClient) -> None:
    """运行进程代际标记（部署自检据此拦版本偏斜）：迁移 #9 的
    created_by_username_axis 与既有 classification_axis 均须 is True——活进程
    真的自报，否则自检恒 FAIL 上不了线。"""
    body = client.get("/api/health").json()
    assert body["created_by_username_axis"] is True
    assert body["classification_axis"] is True


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


def test_get_agent_exposes_input_schema(client: TestClient) -> None:
    """详情端点透出 input_schema，供前端按契约动态渲染创建表单（P0-1）。

    列表端点不带（省带宽）；详情端点必带，且为该 Agent 真实 input_schema.json
    的解析结果（hello_agent required=[name]）。schema 缺失时为 None 而非 500。
    """
    resp = client.get("/api/agents/hello_agent")
    body = resp.json()
    assert "input_schema" in body, "详情投影必须含 input_schema 键"
    schema = body["input_schema"]
    assert isinstance(schema, dict) and schema.get("type") == "object"
    assert "name" in schema.get("properties", {})
    assert schema.get("required") == ["name"]

    # 列表端点不透出 input_schema（最小字段集，省带宽）
    listed = client.get("/api/agents").json()
    hello = next(a for a in listed if a["id"] == "hello_agent")
    assert "input_schema" not in hello


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
        json={"agent_id": "hello_agent", "inputs": {"name": "小明"}},
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


def test_create_task_captures_creator_username_from_session(client: TestClient) -> None:
    """迁移 #9：创建任务从登录会话落 created_by_username（不可变唯一身份），
    与 created_by（display_name）并存。TEST_USERNAME=test_engineer /
    TEST_DISPLAY_NAME=测试工程师，两轴不互相污染。"""
    resp = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "小明"}})
    assert resp.status_code == 200
    task = resp.json()
    assert task["created_by_username"] == "test_engineer"
    assert task["created_by"] == "测试工程师"


# ── tasks: 仿真 run 关联（per-task run_ref，复用 metadata 袋，不加列）──────


def test_set_sim_run_ref_writes_metadata_and_get_reflects(client: TestClient) -> None:
    created = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "关联"}})
    task_id = created.json()["id"]
    resp = client.post(
        f"/api/tasks/{task_id}/sim-run-ref",
        json={"module": "structopt", "run_id": "20260712-030000-123456"},
    )
    assert resp.status_code == 200
    ref = resp.json()["metadata"]["sim_run_ref"]
    assert ref["module"] == "structopt"
    assert ref["run_id"] == "20260712-030000-123456"
    assert "set_at" in ref
    # GET 独立复查落库（非仅回显）
    got = client.get(f"/api/tasks/{task_id}").json()
    assert got["metadata"]["sim_run_ref"]["run_id"] == "20260712-030000-123456"


def test_set_sim_run_ref_missing_task_404(client: TestClient) -> None:
    resp = client.post(
        "/api/tasks/no-such-task/sim-run-ref",
        json={"module": "structopt", "run_id": "20260712-030000-000000"},
    )
    assert resp.status_code == 404


def test_set_sim_run_ref_rejects_injection_chars(client: TestClient) -> None:
    created = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {}})
    task_id = created.json()["id"]
    # module 含 hash 元字符 / run_id 含路径分隔——白名单必须 422 拒绝
    bad_module = client.post(f"/api/tasks/{task_id}/sim-run-ref",
                             json={"module": "a@b/../x", "run_id": "ok-1"})
    bad_run = client.post(f"/api/tasks/{task_id}/sim-run-ref",
                          json={"module": "structopt", "run_id": "../../etc/passwd"})
    assert bad_module.status_code == 422
    assert bad_run.status_code == 422


def test_set_sim_run_ref_preserves_other_metadata(client: TestClient) -> None:
    """read-modify-write 不得吞掉 metadata 其他键。"""
    created = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {}})
    task_id = created.json()["id"]
    # 先塞一次 run_ref，再塞第二次——两次之间 metadata 应累积（这里验第二次不丢第一次 set_at 语义）
    client.post(f"/api/tasks/{task_id}/sim-run-ref",
                json={"module": "structopt", "run_id": "20260712-010000-000000"})
    second = client.post(f"/api/tasks/{task_id}/sim-run-ref",
                         json={"module": "fea_ccx", "run_id": "20260712-020000-000000"})
    assert second.json()["metadata"]["sim_run_ref"]["module"] == "fea_ccx"


def test_set_sim_run_ref_does_not_bump_updated_at(client: TestClient) -> None:
    """sim_run_ref 是 metadata 标注不是状态迁移（Codex 治理审 P2）：绝不 bump
    updated_at——否则给已完成/失败任务设关联会让终态未读信号误亮、任务在「最近
    更新」序里假抬。_now_iso 带微秒，若回归 bump 时间戳必变，此断言真咬。"""
    created = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {}})
    task_id = created.json()["id"]
    before = client.get(f"/api/tasks/{task_id}").json()["updated_at"]
    resp = client.post(f"/api/tasks/{task_id}/sim-run-ref",
                       json={"module": "structopt", "run_id": "20260712-030000-999999"})
    assert resp.status_code == 200
    assert resp.json()["metadata"]["sim_run_ref"]["run_id"] == "20260712-030000-999999"
    after = client.get(f"/api/tasks/{task_id}").json()["updated_at"]
    assert after == before, "设 sim_run_ref 不得改动 updated_at（非状态迁移）"


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

    db_path = tmp_path / "flai_os.db"
    app = create_app(
        agents_dir=agents_dir,
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        db_path=db_path,
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app) as client:
        seed_and_login(client, db_path)
        yield client, app


def _run_to_waiting_review(client: TestClient, app) -> str:
    resp = client.post(
        "/api/tasks",
        json={"agent_id": "review_agent", "inputs": {"name": "待审"}},
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
        json={"action": "approve", "comment": "结果核对无误"},
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
    assert approved_events[0]["payload"] == {
        "reviewer": TEST_DISPLAY_NAME,
        "comment": "结果核对无误",
    }


def test_review_audit_self_review_basis_is_username_exact(review_app_env, caplog) -> None:
    """迁移 #9 后签发审计自审判定升级：新任务带 created_by_username，签发者=同
    一登录身份 → self_review=True 且 basis='username'（精确身份，非显示名近似）。
    tamper：把实现的 self_review_basis 改回恒 'display_name'，本 basis 断言必红。"""
    import logging

    client, app = review_app_env
    task_id = _run_to_waiting_review(client, app)
    with caplog.at_level(logging.INFO):
        approved = client.post(
            f"/api/tasks/{task_id}/review",
            json={"action": "approve", "comment": "同一人签发=自审"},
        )
    assert approved.status_code == 200
    audit_line = next((r.getMessage() for r in caplog.records if "task_review" in r.getMessage()), "")
    assert '"self_review": true' in audit_line
    assert '"self_review_basis": "username"' in audit_line
    assert '"created_by_username": "test_engineer"' in audit_line


def test_review_reject_e2e_full_chain(review_app_env) -> None:
    client, app = review_app_env
    task_id = _run_to_waiting_review(client, app)

    review_resp = client.post(
        f"/api/tasks/{task_id}/review",
        json={"action": "reject", "comment": "输出与图纸不符"},
    )
    assert review_resp.status_code == 200
    rejected = review_resp.json()
    assert rejected["status"] == "failed"
    assert "人工拒绝" in rejected["error_message"]
    assert "输出与图纸不符" in rejected["error_message"]

    events = client.get(f"/api/tasks/{task_id}/events").json()
    rejected_events = [e for e in events if e["event_type"] == "review_rejected"]
    assert len(rejected_events) == 1
    assert rejected_events[0]["payload"]["reviewer"] == TEST_DISPLAY_NAME
    assert rejected_events[0]["level"] == "warning"


def test_review_non_waiting_review_task_409(client: TestClient) -> None:
    """任务不在 waiting_review（此处为 queued）→ 409 如实拒绝，不得静默转移。"""
    resp = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "R"}})
    task_id = resp.json()["id"]

    review_resp = client.post(
        f"/api/tasks/{task_id}/review",
        json={"action": "approve"},
    )
    assert review_resp.status_code == 409


def test_review_unknown_task_404(client: TestClient) -> None:
    resp = client.post(
        "/api/tasks/no_such_task/review",
        json={"action": "approve"},
    )
    assert resp.status_code == 404


def test_review_client_reviewer_forbidden_and_session_identity_stored(review_app_env) -> None:
    """reviewer 已从请求模型删除：显式发送字段 422；省略字段时由会话身份签发。"""
    client, app = review_app_env
    task_id = _run_to_waiting_review(client, app)

    forged = client.post(
        f"/api/tasks/{task_id}/review", json={"action": "approve", "reviewer": ""}
    )
    assert forged.status_code == 422

    bad_action = client.post(
        f"/api/tasks/{task_id}/review", json={"action": "自动放行"}
    )
    assert bad_action.status_code == 422

    assert client.get(f"/api/tasks/{task_id}").json()["status"] == "waiting_review"

    honest = client.post(f"/api/tasks/{task_id}/review", json={"action": "approve"})
    assert honest.status_code == 200
    events = client.get(f"/api/tasks/{task_id}/events").json()
    approved = [e for e in events if e["event_type"] == "review_approved"]
    assert approved[0]["payload"]["reviewer"] == TEST_DISPLAY_NAME


def test_review_any_client_reviewer_forbidden_and_session_identity_stored(review_app_env) -> None:
    """任何客户端 reviewer（空白或带字）都是 forbidden extra；合法请求记会话身份。"""
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
    assert padded.status_code == 422

    honest = client.post(f"/api/tasks/{task_id}/review", json={"action": "approve"})
    assert honest.status_code == 200
    events = client.get(f"/api/tasks/{task_id}/events").json()
    approved = [e for e in events if e["event_type"] == "review_approved"]
    assert approved[0]["payload"]["reviewer"] == TEST_DISPLAY_NAME


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
        f"/api/tasks/{task_id}/review", json={"action": "approve"}
    )
    assert resp.status_code == 409
    assert "并发" in resp.json()["detail"]

    monkeypatch.undo()
    # 竞态被拒后任务未被本次请求触碰，仍可正常人工放行。
    ok = client.post(
        f"/api/tasks/{task_id}/review", json={"action": "approve"}
    )
    assert ok.status_code == 200


# ── me: 工程师私有贡献端点（批C 轨2，私有=安全线）──────────────────────────


@pytest.fixture()
def me_two_user_env(tmp_path: Path):
    """两个已登录身份的 client：alice/bob 各自真实登录（F6 纪律，走真实
    /api/auth/login 换 Set-Cookie），复用 test_m11_auth.py `_anon(app)` 同款
    手法——第二个 client 不再 `with TestClient(app)`，直接在已由第一个 client
    启动过 lifespan 的同一 app 上开新实例（独立 cookie jar，共享 app.state）。

    seed(username, display_name, *, created, completed, waiting, feedback)：
    绕过 API 逐条 POST，直接用 repos.create_task/set_task_status/create_feedback
    造数据（同 test_repos.py::test_list_tasks_filters_by_created_by_username
    的直插样板）。created 条任务里前 completed 条经合法状态机路径
    （queued→validating→running→waiting_review→completed）转终态，紧接
    waiting 条只转到 waiting_review 停住，其余留在 created 态；feedback 条
    反馈全部挂在 task_ids[0] 上（feedback 计数只按 created_by 近似，不依赖
    挂在哪个具体任务）。
    """
    from backend.app.storage import repos
    from backend.app.storage.db import get_conn

    db_path = tmp_path / "flai_os.db"
    app = create_app(
        agents_dir=REPO_ROOT / "agents",
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        db_path=db_path,
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app) as alice_client:
        seed_user(db_path, username="alice", display_name="Alice", password="alice-pass-123")
        seed_user(db_path, username="bob", display_name="Bob", password="bob-pass-123")
        login(alice_client, username="alice", password="alice-pass-123")

        bob_client = TestClient(app)  # 同 app 已启动 lifespan：独立 cookie jar，共享 state
        login(bob_client, username="bob", password="bob-pass-123")

        def seed(
            username: str,
            display_name: str,
            *,
            created: int,
            completed: int,
            waiting: int,
            feedback: int,
        ) -> list[str]:
            conn = get_conn(db_path)
            try:
                task_ids = []
                for i in range(created):
                    tid = f"{username}-task-{i}"
                    repos.create_task(
                        conn,
                        task_id=tid,
                        agent_id="hello_agent",
                        agent_version="0.1.0",
                        name=None,
                        created_by=display_name,
                        created_by_username=username,
                    )
                    task_ids.append(tid)
                idx = 0
                for _ in range(completed):
                    tid = task_ids[idx]
                    idx += 1
                    for st in ("queued", "validating", "running", "waiting_review", "completed"):
                        repos.set_task_status(conn, tid, st)
                for _ in range(waiting):
                    tid = task_ids[idx]
                    idx += 1
                    for st in ("queued", "validating", "running", "waiting_review"):
                        repos.set_task_status(conn, tid, st)
                for _ in range(feedback):
                    repos.create_feedback(
                        conn,
                        task_id=task_ids[0],
                        agent_id="hello_agent",
                        agent_version="0.1.0",
                        rating="good",
                        category="usability",
                        message=None,
                        created_by=display_name,
                    )
                conn.commit()
            finally:
                conn.close()
            return task_ids

        yield alice_client, bob_client, seed


def test_me_contributions_precise_private_and_feedback_approx(me_two_user_env) -> None:
    alice_client, bob_client, seed = me_two_user_env
    seed("alice", "Alice", created=3, completed=1, waiting=1, feedback=2)
    seed("bob", "Bob", created=5, completed=2, waiting=0, feedback=1)

    since = "2000-01-01T00:00:00Z"  # 远早 → since_* 窗口含全部
    a = alice_client.get(f"/api/me/contributions?since={since}").json()
    assert a["username"] == "alice"
    assert a["total_created"] == 3  # 只计 alice，绝不含 bob 的 5
    assert a["since_completed"] == 1
    assert a["waiting_review"] == 1
    assert a["feedback_count_approx"] == 2  # 按 display_name "Alice"

    # 私有实证：bob 登录只拿到 bob 的数，无 username 参数可越权查 alice
    b = bob_client.get(f"/api/me/contributions?since={since}").json()
    assert b["username"] == "bob"
    assert b["total_created"] == 5
    # 端点不接受 username query（多给了也被忽略，仍返回自己的）
    b2 = bob_client.get(f"/api/me/contributions?since={since}&username=alice").json()
    assert b2["total_created"] == 5 and b2["username"] == "bob"

    # since 必填 422
    assert alice_client.get("/api/me/contributions").status_code == 422


def test_me_tasks_private_and_sensitive_redacted(me_two_user_env) -> None:
    alice_client, bob_client, seed = me_two_user_env
    alice_ids = seed("alice", "Alice", created=2, completed=0, waiting=0, feedback=0)
    seed("bob", "Bob", created=1, completed=0, waiting=0, feedback=0)

    a = alice_client.get("/api/me/tasks?limit=50").json()
    assert all(t["created_by_username"] == "alice" for t in a)  # 只我的
    assert len(a) == 2
    b = bob_client.get("/api/me/tasks?limit=50").json()
    assert all(t["created_by_username"] == "bob" for t in b)
    assert len(b) == 1
    # limit 夹取：>100 被拒或夹取（ge/le），0 被拒
    assert alice_client.get("/api/me/tasks?limit=0").status_code == 422
    assert alice_client.get("/api/me/tasks?limit=101").status_code == 422

    # ADR-0025 遮蔽 chokepoint：alice 一条任务标 sensitive 后，/api/me/tasks
    # 必须经 cgate.redact_task_row_if_sensitive 同款遮蔽（content_withheld=True），
    # 不因为「是我自己发起的任务」就绕过遮蔽门。
    from backend.app.storage import repos
    from backend.app.storage.db import get_conn

    conn = get_conn(alice_client.app.state.db_path)
    try:
        repos.set_task_data_classification(conn, alice_ids[0], "sensitive")
        conn.commit()
    finally:
        conn.close()

    a2 = alice_client.get("/api/me/tasks?limit=50").json()
    sensitive_row = next(t for t in a2 if t["id"] == alice_ids[0])
    assert sensitive_row["content_withheld"] is True
    assert sensitive_row["error_message"] is None
    assert sensitive_row["created_by_username"] == "alice"  # 元数据保留，只遮内容


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
    assert download_resp.headers["content-length"] == str(len(content))
    assert download_resp.headers["accept-ranges"] == "bytes"
    assert "sample.txt" in download_resp.headers["content-disposition"]
    assert "last-modified" in download_resp.headers
    assert "etag" in download_resp.headers

    range_resp = client.get(
        f"/api/files/{record['id']}/download", headers={"Range": "bytes=6-12"}
    )
    assert range_resp.status_code == 206
    assert range_resp.content == content[6:13]
    assert range_resp.headers["content-range"] == f"bytes 6-12/{len(content)}"


def test_download_same_size_tamper_returns_409(client: TestClient) -> None:
    """CDX-4 tamper 自证：只改内容不改大小，下载也必须 fail-closed。"""
    original = b"signed-A"
    tampered = b"forged-B"
    assert len(original) == len(tampered), "本测试必须锁定同尺寸替换威胁"
    upload_resp = client.post(
        "/api/files/upload",
        files={"file": ("tamper.txt", original, "text/plain")},
    )
    assert upload_resp.status_code == 200
    record = upload_resp.json()
    Path(record["path"]).write_bytes(tampered)

    response = client.get(f"/api/files/{record['id']}/download")

    assert response.status_code == 409
    assert response.json()["detail"] == "文件完整性校验失败：磁盘内容与登记指纹不符"
    assert tampered not in response.content


def test_download_symlink_replacement_returns_409(client: TestClient, tmp_path: Path) -> None:
    content = b"signed-content"
    upload_resp = client.post(
        "/api/files/upload",
        files={"file": ("linked.txt", content, "text/plain")},
    )
    assert upload_resp.status_code == 200
    record = upload_resp.json()
    path = Path(record["path"])
    target = tmp_path / "same-content.txt"
    target.write_bytes(content)
    path.unlink()
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("当前平台/权限不支持创建符号链接")

    response = client.get(f"/api/files/{record['id']}/download")

    assert response.status_code == 409
    assert response.json()["detail"] == "文件完整性校验失败：磁盘内容与登记指纹不符"


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


# ── governance: 批C Task 3 curated_cases_count ─────────────────────────────


@pytest.fixture()
def governance_client_env(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    """tmp agents 目录：hello_agent + review_agent（同 review_app_env 套路），
    供 curated_cases_count 端点测试造固化 case 文件、验证按 agent 精确 scope。
    """
    import shutil

    # registry.py _REQUIRED_DIRS=("eval_cases",)：eval_cases/ 目录本身是包注册
    # 的硬性前提（缺目录=整包不注册→_agent_or_404 会 404），所以拷贝件不能
    # rmtree 整个目录，只能清空目录内的 *.json（真实 hello_agent 自带
    # golden-sample case 文件，会把断言撑大，须先清掉再由测试自己写入）。
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    shutil.copytree(REPO_ROOT / "agents" / "hello_agent", agents_dir / "hello_agent")
    for p in (agents_dir / "hello_agent" / "eval_cases").glob("*.json"):
        p.unlink()
    review_dir = agents_dir / "review_agent"
    shutil.copytree(REPO_ROOT / "agents" / "hello_agent", review_dir)
    for p in (review_dir / "eval_cases").glob("*.json"):
        p.unlink()
    yaml_path = review_dir / "agent.yaml"
    yaml_text = yaml_path.read_text(encoding="utf-8")
    yaml_text = yaml_text.replace("id: hello_agent", "id: review_agent")
    yaml_path.write_text(yaml_text, encoding="utf-8")

    db_path = tmp_path / "flai_os.db"
    app = create_app(
        agents_dir=agents_dir,
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        db_path=db_path,
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app) as c:
        seed_and_login(c, db_path)
        yield c, agents_dir


def test_curated_cases_count_scoped_and_missing(governance_client_env) -> None:
    client, agents_dir = governance_client_env
    # 造 hello_agent 两个固化 case + 另一 agent 一个，验证按 agent 精确 scope
    (agents_dir / "hello_agent" / "eval_cases").mkdir(parents=True, exist_ok=True)
    (agents_dir / "hello_agent" / "eval_cases" / "case_001.json").write_text("{}", encoding="utf-8")
    (agents_dir / "hello_agent" / "eval_cases" / "case_002.json").write_text("{}", encoding="utf-8")

    r = client.get("/api/agents/hello_agent/curated_cases_count")
    assert r.status_code == 200
    assert r.json() == {"agent_id": "hello_agent", "count": 2}

    # 无 eval_cases 目录的 agent = 0（不抛）。registry 已在 fixture 内 TestClient
    # 启动时扫描完毕（agent 注册状态常驻内存），此刻才把磁盘上的 eval_cases/
    # 目录整个删掉，真实触达端点里 `cases_dir.is_dir()` 为 False 的分支——
    # 而不只是「目录存在但空」的近似。
    import shutil as _shutil

    _shutil.rmtree(agents_dir / "review_agent" / "eval_cases")
    r2 = client.get("/api/agents/review_agent/curated_cases_count")
    assert r2.status_code == 200
    assert r2.json()["count"] == 0

    # 不存在的 agent → 404
    assert client.get("/api/agents/no_such_agent/curated_cases_count").status_code == 404
